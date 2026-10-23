"""
API em JSON usada pelas páginas para atualizar em tempo real (sem recarregar):
- /api/notificacoes          avisos novos (ex.: "Pagamento recebido") para o usuário logado
- /api/pedidos/<c>/rastreio  posições GPS do entregador (cliente, vendedor e entregador do pedido)
- /api/pedidos/<c>/posicao   o entregador envia a posição atual
- /api/vendedor/financeiro   novos pagamentos para o extrato do vendedor
- /api/webhook/pix           aviso do provedor de pagamento quando um PIX é pago
"""
import hmac

from flask import Blueprint, abort, current_app, g, jsonify, request

from .. import db, servicos
from ..utils import MODALIDADES, STATUS_PEDIDO, brl, data_br

bp = Blueprint("api", __name__, url_prefix="/api")


def _exigir_login():
    if not g.usuario:
        abort(401)


@bp.route("/notificacoes")
def notificacoes():
    _exigir_login()
    desde = request.args.get("desde", type=int)   # sem 'desde' = primeira consulta da página (só o marcador)
    novas = db.todos("SELECT id, tipo, titulo, mensagem, link, criado_em FROM notificacoes WHERE usuario_id = ? AND id > ? "
                     "ORDER BY id LIMIT 20", (g.usuario["id"], desde or 0)) if desde is not None else []
    ultimo = db.um("SELECT COALESCE(MAX(id),0) AS m FROM notificacoes WHERE usuario_id = ?", (g.usuario["id"],))["m"]
    return jsonify({"nao_lidas": servicos.nao_lidas(g.usuario["id"]), "ultimo": ultimo,
                    "novas": [dict(n) for n in novas]})


@bp.route("/notificacoes/lidas", methods=["POST"])
def notificacoes_lidas():
    _exigir_login()
    db.executar("UPDATE notificacoes SET lida = 1 WHERE usuario_id = ?", (g.usuario["id"],))
    return jsonify({"ok": True})


def _pedido_visivel(codigo):
    _exigir_login()
    ped = db.um("SELECT * FROM pedidos WHERE codigo = ?", (codigo,))
    if not ped or g.usuario["id"] not in (ped["cliente_id"], ped["vendedor_id"], ped["entregador_id"]):
        abort(404)
    return ped


@bp.route("/pedidos/<codigo>/rastreio")
def rastreio(codigo):
    ped = _pedido_visivel(codigo)
    desde = request.args.get("desde", 0, type=int)
    pontos = db.todos("SELECT id, lat, lng, precisao, velocidade, criado_em FROM rastreamento WHERE pedido_id = ? AND id > ? "
                      "ORDER BY id LIMIT 500", (ped["id"], desde))
    return jsonify({
        "status": ped["status"], "status_texto": STATUS_PEDIDO[ped["status"]],
        "origem": [ped["origem_lat"], ped["origem_lng"]], "destino": [ped["destino_lat"], ped["destino_lng"]],
        "pontos": [dict(p) for p in pontos],
    })


@bp.route("/pedidos/<codigo>/posicao", methods=["POST"])
def enviar_posicao(codigo):
    ped = _pedido_visivel(codigo)
    if g.usuario["id"] != ped["entregador_id"] or ped["status"] != "saiu_entrega":
        abort(403)
    d = request.get_json(silent=True) or {}
    try:
        lat, lng = float(d["lat"]), float(d["lng"])
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "erro": "Coordenadas inválidas"}), 400
    db.executar("INSERT INTO rastreamento (pedido_id, lat, lng, precisao, velocidade) VALUES (?,?,?,?,?)",
                (ped["id"], lat, lng, d.get("precisao"), d.get("velocidade")))
    return jsonify({"ok": True})


@bp.route("/vendedor/financeiro")
def financeiro():
    _exigir_login()
    if g.usuario["papel"] != "vendedor":
        abort(403)
    desde = request.args.get("desde", 0, type=int)
    rows = db.todos("SELECT pg.*, p.codigo, u.nome_completo AS cliente, "
                    "COALESCE(pg.estornado_em, pg.confirmado_em, pg.criado_em) AS momento "
                    "FROM pagamentos pg JOIN pedidos p ON p.id = pg.pedido_id JOIN usuarios u ON u.id = p.cliente_id "
                    "WHERE pg.vendedor_id = ? AND (pg.id > ? OR COALESCE(pg.estornado_em, pg.confirmado_em) >= "
                    "datetime('now','localtime','-15 seconds')) ORDER BY pg.id", (g.usuario["id"], desde))
    hoje = db.um("SELECT COALESCE(SUM(valor),0) AS v, COUNT(*) AS n FROM pagamentos WHERE vendedor_id = ? AND status = 'aprovado' "
                 "AND date(confirmado_em) = date('now','localtime')", (g.usuario["id"],))
    return jsonify({
        "hoje_valor": brl(hoje["v"]), "hoje_qtd": hoje["n"],
        "movimentos": [{"id": r["id"], "momento": data_br(r["momento"]), "codigo": r["codigo"], "cliente": r["cliente"],
                        "modalidade": MODALIDADES[r["modalidade"]], "bandeira": r["bandeira"], "final": r["cartao_final"], "parcelas": r["parcelas"],
                        "valor": brl(r["valor"]), "status": r["status"]} for r in rows],
    })


@bp.route("/webhook/pix", methods=["POST"])
def webhook_pix():
    """
    Ponto de integração com o provedor de PIX (PSP). O provedor envia:
        POST /api/webhook/pix   cabeçalho  X-Webhook-Token: <PIX_WEBHOOK_TOKEN>
        {"txid": "FC1A2B3C4D", "valor": 29.84}
    """
    token = request.headers.get("X-Webhook-Token", "")
    if not hmac.compare_digest(token, current_app.config["PIX_WEBHOOK_TOKEN"]):
        abort(401)
    d = request.get_json(silent=True) or {}
    pag = db.um("SELECT * FROM pagamentos WHERE pix_txid = ? AND modalidade = 'pix'", (str(d.get("txid", "")),))
    if not pag:
        return jsonify({"ok": False, "erro": "txid desconhecido"}), 404
    try:
        if abs(float(d.get("valor", 0)) - pag["valor"]) > 0.009:
            return jsonify({"ok": False, "erro": "valor divergente"}), 409
    except (TypeError, ValueError):
        return jsonify({"ok": False, "erro": "valor inválido"}), 400
    servicos.confirmar_pagamento(pag["id"], origem="webhook")
    return jsonify({"ok": True})

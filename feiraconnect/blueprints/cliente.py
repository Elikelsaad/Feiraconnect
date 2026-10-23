"""
Área do cliente (/cliente): compras, PIX, rastreio GPS, cancelamento em até 20 minutos,
cartões cadastrados (Visa, Mastercard, Elo · crédito ou débito), perfil e avisos.
O cliente só comenta e avalia produtos — não altera fotos nem dados dos produtos.
"""
from flask import (Blueprint, abort, current_app, flash, g, redirect,
                   render_template, request, url_for)

from .. import db, servicos
from ..imagens import ErroImagem, apagar_arquivo, salvar_foto_perfil
from ..pix import qrcode_base64
from ..validacao import (ErroValidacao, mascarar_documento, validar_celular,
                         validar_cep)
from .auth import gravar_cartao, papel_requerido, validar_cartao

bp = Blueprint("cliente", __name__, url_prefix="/cliente")


@bp.before_request
@papel_requerido("cliente")
def _so_cliente():
    pass


def _meu_pedido(codigo):
    return db.um("SELECT * FROM pedidos WHERE codigo = ? AND cliente_id = ?", (codigo, g.usuario["id"])) or abort(404)


@bp.route("/compra/<codigo>")
def compra(codigo):
    pedidos = db.todos("SELECT p.*, v.ponto_comercial AS banca FROM pedidos p JOIN vendedores v ON v.usuario_id = p.vendedor_id "
                       "WHERE p.compra_codigo = ? AND p.cliente_id = ? ORDER BY p.id", (codigo, g.usuario["id"]))
    if not pedidos:
        abort(404)
    blocos = []
    for ped in pedidos:
        pag = db.um("SELECT * FROM pagamentos WHERE pedido_id = ? ORDER BY id DESC LIMIT 1", (ped["id"],))
        itens = db.todos("SELECT * FROM itens_pedido WHERE pedido_id = ?", (ped["id"],))
        qr = qrcode_base64(pag["pix_payload"]) if pag and pag["pix_payload"] and pag["status"] == "pendente" else None
        blocos.append({"ped": ped, "pag": pag, "itens": itens, "qr": qr})
    total = sum(p["total"] for p in pedidos)
    return render_template("cliente/compra.html", codigo=codigo, blocos=blocos, total=total)


@bp.route("/pedidos")
def pedidos():
    lista = db.todos("SELECT p.*, v.ponto_comercial AS banca, "
                     "(SELECT GROUP_CONCAT(i.quantidade || '× ' || i.nome, ', ') FROM itens_pedido i WHERE i.pedido_id = p.id) AS resumo "
                     "FROM pedidos p JOIN vendedores v ON v.usuario_id = p.vendedor_id WHERE p.cliente_id = ? "
                     "ORDER BY p.id DESC", (g.usuario["id"],))
    return render_template("cliente/pedidos.html", pedidos=lista)


@bp.route("/pedidos/<codigo>", methods=["GET", "POST"])
def pedido(codigo):
    ped = _meu_pedido(codigo)
    cfg = db.get_config()
    if request.method == "POST":
        acao = request.form.get("acao")
        if acao == "cancelar":
            if servicos.pode_cancelar(ped, cfg):
                servicos.cancelar_pedido(ped, "cliente", (request.form.get("motivo") or "").strip())
                flash("Compra cancelada. Se já havia pago, o estorno foi solicitado.", "ok")
            else:
                flash(f"O prazo para cancelar ({cfg['cancelamento_minutos']} minutos após a confirmação) já passou.", "erro")
        elif acao == "simular_pix" and current_app.config["MODO_TESTE"]:
            pag = db.um("SELECT id FROM pagamentos WHERE pedido_id = ? AND status = 'pendente'", (ped["id"],))
            if pag:
                servicos.confirmar_pagamento(pag["id"], origem="teste")
                flash("Pagamento PIX simulado com sucesso (modo de teste).", "ok")
        return redirect(url_for("cliente.pedido", codigo=codigo))
    itens = db.todos("SELECT i.*, (SELECT miniatura FROM produto_imagens pi WHERE pi.produto_id = i.produto_id "
                     "ORDER BY ordem LIMIT 1) AS capa FROM itens_pedido i WHERE pedido_id = ?", (ped["id"],))
    pag = db.um("SELECT * FROM pagamentos WHERE pedido_id = ? ORDER BY id DESC LIMIT 1", (ped["id"],))
    qr = qrcode_base64(pag["pix_payload"]) if pag and pag["pix_payload"] and pag["status"] == "pendente" else None
    banca = db.um("SELECT v.ponto_comercial, v.feira, u.celular FROM vendedores v JOIN usuarios u ON u.id = v.usuario_id "
                  "WHERE v.usuario_id = ?", (ped["vendedor_id"],))
    entregador = db.um("SELECT u.nome_completo, u.foto, u.celular, en.veiculo, en.placa FROM usuarios u "
                       "JOIN entregadores en ON en.usuario_id = u.id WHERE u.id = ?",
                       (ped["entregador_id"],)) if ped["entregador_id"] else None
    limite = servicos.prazo_cancelamento(ped, cfg)
    return render_template("cliente/pedido.html", ped=ped, itens=itens, pag=pag, qr=qr, banca=banca,
                           entregador=entregador, pode_cancelar=servicos.pode_cancelar(ped, cfg),
                           limite_iso=limite.strftime("%Y-%m-%dT%H:%M:%S"), modo_teste=current_app.config["MODO_TESTE"])


@bp.route("/cartoes", methods=["GET", "POST"])
def cartoes():
    uid = g.usuario["id"]
    if request.method == "POST":
        if request.form.get("acao") == "remover":
            db.executar("DELETE FROM cartoes WHERE id = ? AND cliente_id = ?", (request.form.get("id", type=int), uid))
            flash("Cartão removido.", "ok")
        else:
            try:
                c = validar_cartao(request.form)
                con = db.get_db()
                gravar_cartao(con, uid, c)
                con.commit()
                flash(f"Cartão {c['bandeira']} final {c['final']} cadastrado.", "ok")
            except ErroValidacao as e:
                flash(str(e), "erro")
        return redirect(url_for("cliente.cartoes"))
    return render_template("cliente/cartoes.html", cartoes=db.todos("SELECT * FROM cartoes WHERE cliente_id = ? ORDER BY id DESC", (uid,)))


@bp.route("/perfil", methods=["GET", "POST"])
def perfil():
    uid = g.usuario["id"]
    end = db.um("SELECT * FROM enderecos WHERE usuario_id = ?", (uid,))
    if request.method == "POST":
        f = request.form
        try:
            celular = validar_celular(f.get("celular"))
            cep = validar_cep(f.get("cep"))
            for campo in ("logradouro", "numero", "bairro", "cidade", "referencia"):
                if not (f.get(campo) or "").strip():
                    raise ErroValidacao("Preencha o endereço completo e o ponto de referência.")
        except ErroValidacao as e:
            flash(str(e), "erro")
            return redirect(url_for("cliente.perfil"))
        con = db.get_db()
        if request.files.get("foto") and request.files["foto"].filename:
            try:
                nova = salvar_foto_perfil(request.files["foto"])
                apagar_arquivo(g.usuario["foto"])
                con.execute("UPDATE usuarios SET foto = ? WHERE id = ?", (nova, uid))
            except ErroImagem as e:
                flash(f"Foto: {e}", "erro")
        lat = f.get("lat", type=float)
        lng = f.get("lng", type=float)
        con.execute("UPDATE usuarios SET celular = ? WHERE id = ?", (celular, uid))
        con.execute("UPDATE enderecos SET cep=?, logradouro=?, numero=?, complemento=?, bairro=?, cidade=?, uf=?, referencia=?, "
                    "lat=COALESCE(?, lat), lng=COALESCE(?, lng) WHERE usuario_id = ?",
                    (cep, f["logradouro"].strip()[:120], f["numero"].strip()[:20], (f.get("complemento") or "").strip()[:80],
                     f["bairro"].strip()[:80], f["cidade"].strip()[:80], (f.get("uf") or "AM")[:2].upper(),
                     f["referencia"].strip()[:160], lat, lng, uid))
        con.commit()
        flash("Dados atualizados.", "ok")
        return redirect(url_for("cliente.perfil"))
    return render_template("cliente/perfil.html", end=end,
                           doc=mascarar_documento(g.usuario["documento_tipo"], g.usuario["documento"]))


@bp.route("/notificacoes")
def notificacoes():
    lista = db.todos("SELECT * FROM notificacoes WHERE usuario_id = ? ORDER BY id DESC LIMIT 200", (g.usuario["id"],))
    db.executar("UPDATE notificacoes SET lida = 1 WHERE usuario_id = ?", (g.usuario["id"],))
    return render_template("notificacoes.html", notificacoes=lista, base="base.html")

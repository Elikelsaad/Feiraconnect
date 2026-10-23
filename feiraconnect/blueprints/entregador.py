"""
Área do entregador (/entregador): pega uma entrega disponível, compartilha a posição GPS
durante o trajeto (cliente e vendedor acompanham no mapa) e confirma a entrega.
"""
from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, url_for)

from .. import db, servicos
from ..validacao import mascarar_documento
from .auth import papel_requerido

bp = Blueprint("entregador", __name__, url_prefix="/entregador")


@bp.before_request
@papel_requerido("entregador")
def _so_entregador():
    g.perfil = db.um("SELECT * FROM entregadores WHERE usuario_id = ?", (g.usuario["id"],))


PEDIDO_SQL = ("SELECT p.*, v.ponto_comercial AS banca, v.feira, uv.celular AS banca_celular, "
              "uc.nome_completo AS cliente, uc.celular AS cliente_celular, "
              "ev.logradouro || ', ' || ev.numero || ' - ' || ev.bairro AS banca_endereco, "
              "(SELECT SUM(quantidade) FROM itens_pedido i WHERE i.pedido_id = p.id) AS volumes "
              "FROM pedidos p JOIN vendedores v ON v.usuario_id = p.vendedor_id JOIN usuarios uv ON uv.id = p.vendedor_id "
              "JOIN usuarios uc ON uc.id = p.cliente_id LEFT JOIN enderecos ev ON ev.usuario_id = p.vendedor_id ")


@bp.route("/")
def painel():
    uid = g.usuario["id"]
    disponiveis = db.todos(PEDIDO_SQL + "WHERE p.status = 'aguardando_entregador' AND p.entregador_id IS NULL "
                           "AND p.entrega_modo = ? ORDER BY p.id", (g.perfil["veiculo"],))
    outros = db.todos(PEDIDO_SQL + "WHERE p.status = 'aguardando_entregador' AND p.entregador_id IS NULL "
                      "AND p.entrega_modo != ? AND p.entrega_modo != 'retirada' ORDER BY p.id", (g.perfil["veiculo"],))
    minhas = db.todos(PEDIDO_SQL + "WHERE p.entregador_id = ? AND p.status IN ('aguardando_entregador','saiu_entrega') "
                      "ORDER BY p.id", (uid,))
    feitas = db.todos(PEDIDO_SQL + "WHERE p.entregador_id = ? AND p.status IN ('entregue','cancelado') "
                      "ORDER BY p.id DESC LIMIT 30", (uid,))
    ganhos = db.um("SELECT COALESCE(SUM(entrega_valor),0) AS total, COUNT(*) AS n FROM pedidos WHERE entregador_id = ? "
                   "AND status = 'entregue' AND date(entregue_em) = date('now','localtime')", (uid,))
    return render_template("entregador/painel.html", disponiveis=disponiveis, outros=outros, minhas=minhas,
                           feitas=feitas, ganhos=ganhos, doc=mascarar_documento("CPF", g.usuario["documento"]))


@bp.route("/entregas/<codigo>", methods=["GET", "POST"])
def entrega(codigo):
    uid = g.usuario["id"]
    ped = db.um(PEDIDO_SQL + "WHERE p.codigo = ?", (codigo,)) or abort(404)
    if ped["entregador_id"] not in (None, uid):
        abort(403)
    if request.method == "POST":
        acao = request.form.get("acao")
        con = db.get_db()
        if acao == "aceitar" and ped["status"] == "aguardando_entregador" and ped["entregador_id"] is None:
            cur = con.execute("UPDATE pedidos SET entregador_id = ? WHERE id = ? AND entregador_id IS NULL", (uid, ped["id"]))
            if cur.rowcount:
                servicos.notificar(ped["vendedor_id"], "entrega", f"Entregador a caminho da banca · #{codigo}",
                                   f"{g.usuario['nome_completo']} vai retirar o pedido.", f"/vendedor/pedidos/{codigo}", commit=False)
                con.commit()
                flash("Entrega aceita. Retire os produtos na banca.", "ok")
            else:
                flash("Outro entregador pegou esta entrega primeiro.", "erro")
        elif acao == "iniciar" and ped["entregador_id"] == uid and ped["status"] == "aguardando_entregador":
            servicos.mudar_status(ped, "saiu_entrega", "saiu_em")
            flash("Entrega iniciada. Mantenha esta página aberta para enviar sua localização.", "ok")
        elif acao == "finalizar" and ped["entregador_id"] == uid and ped["status"] == "saiu_entrega":
            servicos.mudar_status(ped, "entregue", "entregue_em")
            flash("Entrega concluída. Obrigado!", "ok")
            return redirect(url_for("entregador.painel"))
        elif acao == "desistir" and ped["entregador_id"] == uid and ped["status"] == "aguardando_entregador":
            con.execute("UPDATE pedidos SET entregador_id = NULL WHERE id = ?", (ped["id"],))
            con.commit()
            flash("Você liberou a entrega para outro entregador.", "ok")
            return redirect(url_for("entregador.painel"))
        return redirect(url_for("entregador.entrega", codigo=codigo))
    itens = db.todos("SELECT * FROM itens_pedido WHERE pedido_id = ?", (ped["id"],))
    return render_template("entregador/entrega.html", ped=ped, itens=itens)


@bp.route("/disponibilidade", methods=["POST"])
def disponibilidade():
    db.executar("UPDATE entregadores SET disponivel = 1 - disponivel WHERE usuario_id = ?", (g.usuario["id"],))
    return redirect(url_for("entregador.painel"))


@bp.route("/notificacoes")
def notificacoes():
    lista = db.todos("SELECT * FROM notificacoes WHERE usuario_id = ? ORDER BY id DESC LIMIT 200", (g.usuario["id"],))
    db.executar("UPDATE notificacoes SET lida = 1 WHERE usuario_id = ?", (g.usuario["id"],))
    return render_template("notificacoes.html", notificacoes=lista, base="base.html")

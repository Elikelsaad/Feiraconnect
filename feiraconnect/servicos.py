"""
Regras de negócio compartilhadas pelos painéis:
notificações, confirmação de pagamento, cancelamento (prazo de 20 min) e etapas da entrega.
Manter essas regras aqui (e não espalhadas pelas rotas) facilita futuras atualizações.
"""
from datetime import datetime, timedelta

from . import db
from .utils import MODALIDADES, STATUS_PEDIDO, agora, brl


# ---------------------------------------------------------------- notificações
def notificar(usuario_id, tipo, titulo, mensagem="", link="", commit=True):
    con = db.get_db()
    con.execute("INSERT INTO notificacoes (usuario_id, tipo, titulo, mensagem, link) VALUES (?,?,?,?,?)",
                (usuario_id, tipo, titulo, mensagem, link))
    if commit:
        con.commit()


def nao_lidas(usuario_id):
    return db.um("SELECT COUNT(*) AS n FROM notificacoes WHERE usuario_id = ? AND lida = 0", (usuario_id,))["n"]


# ---------------------------------------------------------------- pagamentos
def confirmar_pagamento(pagamento_id, origem="sistema"):
    """Marca o pagamento como aprovado, atualiza o pedido e avisa vendedor e cliente."""
    con = db.get_db()
    pag = con.execute("SELECT * FROM pagamentos WHERE id = ?", (pagamento_id,)).fetchone()
    if not pag or pag["status"] != "pendente":
        return False
    momento = agora()
    con.execute("UPDATE pagamentos SET status = 'aprovado', confirmado_em = ? WHERE id = ?", (momento, pagamento_id))
    ped = con.execute("SELECT * FROM pedidos WHERE id = ?", (pag["pedido_id"],)).fetchone()
    if ped["status"] == "aguardando_pagamento":
        con.execute("UPDATE pedidos SET status = 'pago', pago_em = ? WHERE id = ?", (momento, ped["id"]))
    forma = MODALIDADES[pag["modalidade"]] + (f" {pag['bandeira']}" if pag["bandeira"] else "")
    if pag["parcelas"] > 1:
        forma += f" em {pag['parcelas']}x"
    notificar(ped["vendedor_id"], "pagamento", f"💰 Pagamento recebido: {brl(pag['valor'])}",
              f"Pedido #{ped['codigo']} pago via {forma}. Separe os produtos para entrega.",
              f"/vendedor/pedidos/{ped['codigo']}", commit=False)
    notificar(ped["cliente_id"], "pagamento", "Pagamento confirmado",
              f"Seu pedido #{ped['codigo']} foi pago e já está com o feirante.",
              f"/cliente/pedidos/{ped['codigo']}", commit=False)
    con.commit()
    return True


# ---------------------------------------------------------------- cancelamento
def prazo_cancelamento(ped, cfg):
    """Retorna o datetime limite para o cliente cancelar (confirmação + N minutos)."""
    base = ped["pago_em"] or ped["criado_em"]
    return datetime.strptime(base, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=int(cfg["cancelamento_minutos"]))


def pode_cancelar(ped, cfg):
    if ped["status"] in ("entregue", "cancelado"):
        return False
    return datetime.now() <= prazo_cancelamento(ped, cfg)


def cancelar_pedido(ped, por, motivo=""):
    """Cancela, devolve o estoque, estorna os pagamentos aprovados e avisa os envolvidos."""
    con = db.get_db()
    momento = agora()
    con.execute("UPDATE pedidos SET status = 'cancelado', cancelado_em = ?, cancelado_por = ?, "
                "motivo_cancelamento = ? WHERE id = ?", (momento, por, motivo[:300], ped["id"]))
    for item in con.execute("SELECT * FROM itens_pedido WHERE pedido_id = ?", (ped["id"],)).fetchall():
        con.execute("UPDATE produtos SET estoque = estoque + ?, vendidos = MAX(vendidos - ?, 0) WHERE id = ?",
                    (item["quantidade"], item["quantidade"], item["produto_id"]))
    estornados = con.execute("SELECT COUNT(*) FROM pagamentos WHERE pedido_id = ? AND status = 'aprovado'",
                             (ped["id"],)).fetchone()[0]
    con.execute("UPDATE pagamentos SET status = 'estornado', estornado_em = ? WHERE pedido_id = ? AND status = 'aprovado'",
                (momento, ped["id"]))
    con.execute("UPDATE pagamentos SET status = 'recusado' WHERE pedido_id = ? AND status = 'pendente'", (ped["id"],))
    quem = {"cliente": "pelo cliente", "vendedor": "pelo vendedor"}.get(por, "")
    notificar(ped["vendedor_id"], "cancelamento", f"Pedido #{ped['codigo']} cancelado {quem}",
              (f"Motivo: {motivo}. " if motivo else "") + ("O valor foi estornado ao cliente. " if estornados else "")
              + "Os produtos voltaram ao estoque.", f"/vendedor/pedidos/{ped['codigo']}", commit=False)
    notificar(ped["cliente_id"], "cancelamento", f"Pedido #{ped['codigo']} cancelado",
              "O estorno do valor pago foi solicitado." if estornados else "Nenhuma cobrança foi feita.",
              f"/cliente/pedidos/{ped['codigo']}", commit=False)
    if ped["entregador_id"]:
        notificar(ped["entregador_id"], "cancelamento", f"Entrega #{ped['codigo']} cancelada",
                  "Se já retirou os produtos, devolva-os na banca.", "/entregador/", commit=False)
    con.commit()


# ---------------------------------------------------------------- etapas da entrega
TRANSICOES_VENDEDOR = {
    "pago": ["em_preparo"],
    "em_preparo": ["aguardando_entregador", "entregue"],   # 'entregue' direto quando é retirada na banca
}


def mudar_status(ped, novo, campo_data=None):
    con = db.get_db()
    if campo_data:
        con.execute(f"UPDATE pedidos SET status = ?, {campo_data} = ? WHERE id = ?", (novo, agora(), ped["id"]))
    else:
        con.execute("UPDATE pedidos SET status = ? WHERE id = ?", (novo, ped["id"]))
    textos = {
        "em_preparo": "O feirante está separando seus produtos.",
        "aguardando_entregador": "Seu pedido está pronto e aguardando um entregador.",
        "saiu_entrega": "Seu pedido saiu para entrega. Acompanhe pelo mapa em tempo real.",
        "entregue": "Pedido entregue. Que tal avaliar os produtos?",
    }
    if novo in textos:
        notificar(ped["cliente_id"], "pedido", f"Pedido #{ped['codigo']}: {STATUS_PEDIDO[novo]}", textos[novo],
                  f"/cliente/pedidos/{ped['codigo']}", commit=False)
    if novo in ("saiu_entrega", "entregue") :
        notificar(ped["vendedor_id"], "pedido", f"Pedido #{ped['codigo']}: {STATUS_PEDIDO[novo]}", "",
                  f"/vendedor/pedidos/{ped['codigo']}", commit=False)
    con.commit()

"""
Painel do vendedor (/vendedor) — o vendedor é o administrador do próprio acesso:
dashboard de vendas, produtos com até 10 fotos HD/4K e legendas, conta bancária,
pedidos (com rastreio GPS), financeiro em tempo real, visualizações, comentários e notificações.
Toda consulta filtra pelo vendedor logado: um vendedor nunca vê dados de outro.
"""
import csv
import io
from datetime import date, timedelta

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect,
                   render_template, request, url_for)

from .. import db, relatorios, servicos
from ..imagens import (MAX_IMAGENS_PRODUTO, ErroImagem, apagar_arquivo,
                       rotulo_resolucao, salvar_foto_perfil,
                       salvar_foto_produto)
from ..utils import MODALIDADES, STATUS_PEDIDO, agora
from ..validacao import (ErroValidacao, cnpj_valido, cpf_valido,
                         mascarar_documento, so_digitos, validar_celular,
                         validar_cep)
from .auth import papel_requerido

bp = Blueprint("vendedor", __name__, url_prefix="/vendedor")

BANCOS = [("001", "Banco do Brasil"), ("104", "Caixa Econômica Federal"), ("237", "Bradesco"), ("341", "Itaú"),
          ("033", "Santander"), ("260", "Nubank"), ("077", "Banco Inter"), ("336", "C6 Bank"), ("756", "Sicoob"),
          ("748", "Sicredi"), ("037", "Banco da Amazônia (Basa)"), ("290", "PagBank"), ("323", "Mercado Pago"),
          ("380", "PicPay"), ("000", "Outro")]


@bp.before_request
@papel_requerido("vendedor")
def _so_vendedor():
    g.conta = db.um("SELECT * FROM contas_bancarias WHERE vendedor_id = ?", (g.usuario["id"],))
    g.loja = db.um("SELECT * FROM vendedores WHERE usuario_id = ?", (g.usuario["id"],))


def _meu_produto(produto_id):
    p = db.obter_produto(produto_id)
    if not p or p["vendedor_id"] != g.usuario["id"]:
        abort(404)
    return p


def _meu_pedido(codigo):
    ped = db.um("SELECT * FROM pedidos WHERE codigo = ? AND vendedor_id = ?", (codigo, g.usuario["id"]))
    return ped or abort(404)


def _num(valor, padrao=None, tipo=float):
    try:
        return tipo(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return padrao


# ---------------------------------------------------------------- dashboard
@bp.route("/")
def painel():
    periodo = request.args.get("periodo", "dia")
    ref = relatorios.ler_data(request.args.get("ref"))
    dados = relatorios.dashboard(g.usuario["id"], periodo, ref)
    uid = g.usuario["id"]
    pendentes = db.todos("SELECT * FROM pedidos WHERE vendedor_id = ? AND status IN ('pago','em_preparo') ORDER BY id", (uid,))
    estoque_baixo = db.listar_produtos("p.vendedor_id = ? AND p.ativo = 1 AND p.estoque <= ?",
                                       (uid, current_app.config["ESTOQUE_BAIXO"]), "p.estoque")
    return render_template("vendedor/painel.html", d=dados, pendentes=pendentes, estoque_baixo=estoque_baixo,
                           periodos=relatorios.PERIODOS)


# ---------------------------------------------------------------- produtos
@bp.route("/produtos")
def produtos():
    lista = db.listar_produtos("p.vendedor_id = ?", (g.usuario["id"],), "p.ativo DESC, p.nome")
    return render_template("vendedor/produtos.html", produtos=lista)


@bp.route("/produtos/novo", methods=["GET", "POST"])
@bp.route("/produtos/<int:produto_id>", methods=["GET", "POST"])
def produto_form(produto_id=None):
    p = _meu_produto(produto_id) if produto_id else None
    if request.method == "POST":
        f = request.form
        dados = {
            "nome": (f.get("nome") or "").strip()[:120],
            "descricao": (f.get("descricao") or "").strip()[:3000],
            "preco": _num(f.get("preco")),
            "preco_original": _num(f.get("preco_original")) or None,
            "unidade": (f.get("unidade") or "un").strip()[:20],
            "estoque": max(_num(f.get("estoque"), 0, int), 0),
            "origem": (f.get("origem") or "").strip()[:80],
            "categoria_id": _num(f.get("categoria_id"), None, int),
            "promocao_dia": 1 if f.get("promocao_dia") else 0,
            "fim_de_feira": 1 if f.get("fim_de_feira") else 0,
            "ativo": 1 if f.get("ativo") else 0,
        }
        if not dados["nome"] or dados["preco"] is None or dados["preco"] < 0:
            flash("Preencha o nome e um preço válido.", "erro")
            return render_template("vendedor/produto_form.html", p=dict(p or {}, **dados), imagens=[],
                                   categorias=db.listar_categorias(), max_img=MAX_IMAGENS_PRODUTO), 400
        if dados["preco_original"] and dados["preco_original"] <= dados["preco"]:
            dados["preco_original"] = None
        con = db.get_db()
        if p:
            sets = ", ".join(f"{k} = ?" for k in dados)
            con.execute(f"UPDATE produtos SET {sets}, atualizado_em = ? WHERE id = ?", (*dados.values(), agora(), p["id"]))
            pid = p["id"]
        else:
            dados["vendedor_id"] = g.usuario["id"]
            pid = con.execute(f"INSERT INTO produtos ({', '.join(dados)}) VALUES ({', '.join('?' * len(dados))})",
                              tuple(dados.values())).lastrowid
        con.commit()
        n = _receber_fotos(pid, request.files.getlist("fotos"), request.form.getlist("legendas_novas"))
        flash(("Produto salvo." if p else "Produto cadastrado.") + (f" {n} foto(s) adicionada(s)." if n else ""), "ok")
        return redirect(url_for("vendedor.produto_form", produto_id=pid))
    imagens = db.imagens_produto(produto_id) if p else []
    return render_template("vendedor/produto_form.html", p=p or {}, imagens=imagens, categorias=db.listar_categorias(),
                           max_img=MAX_IMAGENS_PRODUTO, rotulo_resolucao=rotulo_resolucao)


def _receber_fotos(produto_id, arquivos, legendas):
    arquivos = [a for a in arquivos if a and a.filename]
    if not arquivos:
        return 0
    con = db.get_db()
    existentes = con.execute("SELECT COUNT(*) FROM produto_imagens WHERE produto_id = ?", (produto_id,)).fetchone()[0]
    vagas = MAX_IMAGENS_PRODUTO - existentes
    if len(arquivos) > vagas:
        flash(f"Cada produto pode ter no máximo {MAX_IMAGENS_PRODUTO} fotos. "
              f"{'Só cabem mais ' + str(vagas) + '.' if vagas > 0 else 'Exclua alguma antes de enviar outra.'}", "erro")
        arquivos = arquivos[:max(vagas, 0)]
    ordem = con.execute("SELECT COALESCE(MAX(ordem), -1) FROM produto_imagens WHERE produto_id = ?", (produto_id,)).fetchone()[0]
    salvas = 0
    for i, arq in enumerate(arquivos):
        try:
            info = salvar_foto_produto(arq)
        except ErroImagem as e:
            flash(str(e), "erro")
            continue
        ordem += 1
        legenda = (legendas[i] if i < len(legendas) else "").strip()[:300]
        con.execute("INSERT INTO produto_imagens (produto_id, arquivo, miniatura, largura, altura, legenda, ordem) "
                    "VALUES (?,?,?,?,?,?,?)", (produto_id, info["arquivo"], info["miniatura"], info["largura"],
                                                info["altura"], legenda, ordem))
        salvas += 1
    con.execute("UPDATE produtos SET atualizado_em = ? WHERE id = ?", (agora(), produto_id))
    con.commit()
    return salvas


@bp.route("/produtos/<int:produto_id>/imagens", methods=["POST"])
def imagens(produto_id):
    """Atualiza legendas, ordem, capa, troca ou exclusão das fotos — quantas vezes quiser."""
    _meu_produto(produto_id)
    con = db.get_db()
    acao, _, alvo = request.form.get("acao", "salvar").partition(":")   # ex.: "excluir:12"
    img_id = _num(alvo, None, int)
    img = con.execute("SELECT * FROM produto_imagens WHERE id = ? AND produto_id = ?", (img_id, produto_id)).fetchone() if img_id else None
    if acao == "excluir" and img:
        con.execute("DELETE FROM produto_imagens WHERE id = ?", (img_id,))
        apagar_arquivo(img["arquivo"]); apagar_arquivo(img["miniatura"])
        flash("Foto excluída.", "ok")
    elif acao == "capa" and img:
        con.execute("UPDATE produto_imagens SET ordem = ordem + 1 WHERE produto_id = ?", (produto_id,))
        con.execute("UPDATE produto_imagens SET ordem = 0 WHERE id = ?", (img_id,))
        flash("Capa do produto alterada.", "ok")
    elif acao in ("subir", "descer") and img:
        lista = con.execute("SELECT id FROM produto_imagens WHERE produto_id = ? ORDER BY ordem, id", (produto_id,)).fetchall()
        ids = [r["id"] for r in lista]
        i = ids.index(img_id)
        j = i - 1 if acao == "subir" else i + 1
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
            for pos, x in enumerate(ids):
                con.execute("UPDATE produto_imagens SET ordem = ? WHERE id = ?", (pos, x))
    elif acao == "trocar" and img:
        try:
            info = salvar_foto_produto(request.files.get(f"nova_foto_{img_id}"))
            con.execute("UPDATE produto_imagens SET arquivo = ?, miniatura = ?, largura = ?, altura = ? WHERE id = ?",
                        (info["arquivo"], info["miniatura"], info["largura"], info["altura"], img_id))
            apagar_arquivo(img["arquivo"]); apagar_arquivo(img["miniatura"])
            flash("Foto substituída.", "ok")
        except ErroImagem as e:
            flash(str(e), "erro")
    if acao in ("salvar", "trocar", "capa", "subir", "descer"):  # sempre guarda as legendas digitadas
        for chave, valor in request.form.items():
            if chave.startswith("legenda_"):
                con.execute("UPDATE produto_imagens SET legenda = ? WHERE id = ? AND produto_id = ?",
                            (valor.strip()[:300], _num(chave[8:], 0, int), produto_id))
        if acao == "salvar":
            flash("Comentários das fotos salvos.", "ok")
    con.execute("UPDATE produtos SET atualizado_em = ? WHERE id = ?", (agora(), produto_id))
    con.commit()
    return redirect(url_for("vendedor.produto_form", produto_id=produto_id) + "#fotos")


@bp.route("/produtos/<int:produto_id>/excluir", methods=["POST"])
def produto_excluir(produto_id):
    _meu_produto(produto_id)
    con = db.get_db()
    if con.execute("SELECT 1 FROM itens_pedido WHERE produto_id = ? LIMIT 1", (produto_id,)).fetchone():
        con.execute("UPDATE produtos SET ativo = 0 WHERE id = ?", (produto_id,))
        flash("O produto tem vendas no histórico, então foi apenas desativado.", "ok")
    else:
        for img in con.execute("SELECT * FROM produto_imagens WHERE produto_id = ?", (produto_id,)).fetchall():
            apagar_arquivo(img["arquivo"]); apagar_arquivo(img["miniatura"])
        con.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
        flash("Produto excluído.", "ok")
    con.commit()
    return redirect(url_for("vendedor.produtos"))


@bp.route("/produtos/<int:produto_id>/estoque", methods=["POST"])
def produto_estoque(produto_id):
    _meu_produto(produto_id)
    db.executar("UPDATE produtos SET estoque = MAX(estoque + ?, 0) WHERE id = ?",
                (_num(request.form.get("ajuste"), 0, int), produto_id))
    return redirect(request.referrer or url_for("vendedor.produtos"))


# ---------------------------------------------------------------- conta bancária
@bp.route("/conta-bancaria", methods=["GET", "POST"])
def conta_bancaria():
    if request.method == "POST":
        f = request.form
        erros = []
        banco = f.get("banco_codigo", "")
        banco_nome = dict(BANCOS).get(banco) or ""
        if banco == "000":
            banco_nome = (f.get("banco_outro") or "").strip()[:60]
        if not banco_nome:
            erros.append("Escolha o banco.")
        agencia = so_digitos(f.get("agencia"))[:6]
        conta = so_digitos(f.get("conta"))[:14]
        if not agencia or not conta:
            erros.append("Informe agência e conta.")
        tipo = f.get("conta_tipo")
        if tipo not in ("corrente", "poupanca", "pagamento"):
            erros.append("Escolha o tipo de conta.")
        titular = (f.get("titular") or "").strip()[:80]
        doc = so_digitos(f.get("titular_documento"))
        if not titular:
            erros.append("Informe o nome do titular da conta.")
        if not (cpf_valido(doc) or cnpj_valido(doc)):
            erros.append("CPF/CNPJ do titular inválido.")
        aceita = {k: 1 if f.get(k) else 0 for k in ("aceita_credito", "aceita_debito", "aceita_pix",
                                                   "bandeira_visa", "bandeira_mastercard", "bandeira_elo")}
        if not (aceita["aceita_credito"] or aceita["aceita_debito"] or aceita["aceita_pix"]):
            erros.append("Escolha pelo menos uma forma de recebimento.")
        if (aceita["aceita_credito"] or aceita["aceita_debito"]) and not (
                aceita["bandeira_visa"] or aceita["bandeira_mastercard"] or aceita["bandeira_elo"]):
            erros.append("Escolha pelo menos uma bandeira de cartão (Visa, Mastercard ou Elo).")
        pix_tipo = f.get("pix_tipo", "")
        pix_chave = (f.get("pix_chave") or "").strip()[:77]
        if aceita["aceita_pix"]:
            try:
                pix_chave = _validar_chave_pix(pix_tipo, pix_chave)
            except ErroValidacao as e:
                erros.append(str(e))
        if erros:
            for e in erros:
                flash(e, "erro")
            return render_template("vendedor/conta.html", c=f, bancos=BANCOS), 400
        valores = (banco if banco != "000" else "000", banco_nome, agencia, conta, so_digitos(f.get("conta_digito"))[:2],
                   tipo, titular, doc, pix_tipo, pix_chave, *aceita.values(), agora())
        db.executar("""INSERT INTO contas_bancarias (banco_codigo, banco_nome, agencia, conta, conta_digito, conta_tipo, titular,
                       titular_documento, pix_tipo, pix_chave, aceita_credito, aceita_debito, aceita_pix, bandeira_visa,
                       bandeira_mastercard, bandeira_elo, atualizado_em, vendedor_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(vendedor_id) DO UPDATE SET banco_codigo=excluded.banco_codigo, banco_nome=excluded.banco_nome,
                       agencia=excluded.agencia, conta=excluded.conta, conta_digito=excluded.conta_digito,
                       conta_tipo=excluded.conta_tipo, titular=excluded.titular, titular_documento=excluded.titular_documento,
                       pix_tipo=excluded.pix_tipo, pix_chave=excluded.pix_chave, aceita_credito=excluded.aceita_credito,
                       aceita_debito=excluded.aceita_debito, aceita_pix=excluded.aceita_pix, bandeira_visa=excluded.bandeira_visa,
                       bandeira_mastercard=excluded.bandeira_mastercard, bandeira_elo=excluded.bandeira_elo,
                       atualizado_em=excluded.atualizado_em""", (*valores, g.usuario["id"]))
        flash("Conta bancária salva. Seus produtos já podem ser vendidos.", "ok")
        return redirect(url_for("vendedor.conta_bancaria"))
    c = dict(g.conta) if g.conta else {"titular": g.usuario["nome_completo"], "titular_documento": g.usuario["documento"],
                                        "aceita_credito": 1, "aceita_debito": 1, "aceita_pix": 1, "bandeira_visa": 1,
                                        "bandeira_mastercard": 1, "bandeira_elo": 1}
    return render_template("vendedor/conta.html", c=c, bancos=BANCOS)


def _validar_chave_pix(tipo, chave):
    import re
    if tipo == "cpf_cnpj":
        d = so_digitos(chave)
        if not (cpf_valido(d) or cnpj_valido(d)):
            raise ErroValidacao("Chave PIX: CPF/CNPJ inválido.")
        return d
    if tipo == "email":
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", chave):
            raise ErroValidacao("Chave PIX: e-mail inválido.")
        return chave.lower()
    if tipo == "celular":
        d = so_digitos(chave)
        d = d[2:] if d.startswith("55") and len(d) == 13 else d
        if len(d) != 11:
            raise ErroValidacao("Chave PIX: celular inválido (DDD + 9 dígitos).")
        return "+55" + d
    if tipo == "aleatoria":
        if not re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", chave):
            raise ErroValidacao("Chave PIX aleatória inválida.")
        return chave.lower()
    raise ErroValidacao("Escolha o tipo da chave PIX.")


# ---------------------------------------------------------------- pedidos
@bp.route("/pedidos")
def pedidos():
    status = request.args.get("status", "")
    sql = ("SELECT p.*, u.nome_completo AS cliente, pg.modalidade, pg.bandeira, pg.status AS pag_status "
           "FROM pedidos p JOIN usuarios u ON u.id = p.cliente_id LEFT JOIN pagamentos pg ON pg.pedido_id = p.id "
           "WHERE p.vendedor_id = ?")
    params = [g.usuario["id"]]
    if status in STATUS_PEDIDO:
        sql += " AND p.status = ?"
        params.append(status)
    return render_template("vendedor/pedidos.html", pedidos=db.todos(sql + " ORDER BY p.id DESC LIMIT 300", params),
                           status=status)


@bp.route("/pedidos/<codigo>", methods=["GET", "POST"])
def pedido(codigo):
    ped = _meu_pedido(codigo)
    if request.method == "POST":
        acao = request.form.get("acao")
        if acao == "confirmar_pix":
            pag = db.um("SELECT id FROM pagamentos WHERE pedido_id = ? AND status = 'pendente'", (ped["id"],))
            if pag and servicos.confirmar_pagamento(pag["id"], origem="vendedor"):
                flash("Pagamento PIX confirmado.", "ok")
        elif acao == "cancelar" and ped["status"] not in ("entregue", "cancelado", "saiu_entrega"):
            servicos.cancelar_pedido(ped, "vendedor", (request.form.get("motivo") or "").strip())
            flash("Pedido cancelado e estoque devolvido.", "ok")
        elif acao in servicos.TRANSICOES_VENDEDOR.get(ped["status"], []):
            if acao == "entregue" and ped["entrega_modo"] != "retirada":
                abort(400, "Use 'entregue' apenas para retirada na banca.")
            servicos.mudar_status(ped, acao, "entregue_em" if acao == "entregue" else None)
            flash(f"Pedido atualizado: {STATUS_PEDIDO[acao]}.", "ok")
        return redirect(url_for("vendedor.pedido", codigo=codigo))
    itens = db.todos("SELECT * FROM itens_pedido WHERE pedido_id = ?", (ped["id"],))
    pags = db.todos("SELECT * FROM pagamentos WHERE pedido_id = ? ORDER BY id", (ped["id"],))
    cliente = db.um("SELECT u.nome_completo, u.celular, u.foto, e.referencia FROM usuarios u "
                    "LEFT JOIN enderecos e ON e.usuario_id = u.id WHERE u.id = ?", (ped["cliente_id"],))
    entregador = db.um("SELECT u.nome_completo, u.celular, u.foto, en.veiculo, en.placa FROM usuarios u "
                       "JOIN entregadores en ON en.usuario_id = u.id WHERE u.id = ?", (ped["entregador_id"],)) if ped["entregador_id"] else None
    return render_template("vendedor/pedido.html", ped=ped, itens=itens, pags=pags, cliente=cliente, entregador=entregador)


# ---------------------------------------------------------------- financeiro
def _periodo_financeiro():
    ini = relatorios.ler_data(request.args.get("de")) if request.args.get("de") else date.today() - timedelta(days=30)
    fim = relatorios.ler_data(request.args.get("ate")) if request.args.get("ate") else date.today()
    return ini, fim + timedelta(days=1)


@bp.route("/financeiro")
def financeiro():
    ini, fim = _periodo_financeiro()
    movs = relatorios.movimentacao(g.usuario["id"], ini, fim)
    aprovado = sum(m["valor"] for m in movs if m["status"] == "aprovado")
    estornado = sum(m["valor"] for m in movs if m["status"] == "estornado")
    pendente = sum(m["valor"] for m in movs if m["status"] == "pendente")
    por_mod = {}
    for m in movs:
        if m["status"] == "aprovado":
            por_mod[m["modalidade"]] = por_mod.get(m["modalidade"], 0) + m["valor"]
    ultimo = max((m["id"] for m in movs), default=0)
    return render_template("vendedor/financeiro.html", movs=movs, aprovado=aprovado, estornado=estornado,
                           pendente=pendente, por_mod=por_mod, de=ini, ate=fim - timedelta(days=1), ultimo=ultimo)


@bp.route("/financeiro.csv")
def financeiro_csv():
    ini, fim = _periodo_financeiro()
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";")
    w.writerow(["Data e hora", "Pedido", "Cliente", "Forma de pagamento", "Bandeira", "Parcelas", "Valor (R$)", "Situação"])
    for m in relatorios.movimentacao(g.usuario["id"], ini, fim, limite=100000):
        w.writerow([m["momento"], m["codigo"], m["cliente"], MODALIDADES[m["modalidade"]], m["bandeira"], m["parcelas"],
                    f"{m['valor']:.2f}".replace(".", ","), m["status"]])
    return Response("﻿" + saida.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=financeiro_{ini}_{fim}.csv"})


# ---------------------------------------------------------------- avaliações e visualizações
@bp.route("/avaliacoes")
def avaliacoes():
    uid = g.usuario["id"]
    lista = db.todos("SELECT a.*, p.nome AS produto, p.id AS produto_id, u.nome_completo AS cliente, u.foto "
                     "FROM avaliacoes a JOIN produtos p ON p.id = a.produto_id JOIN usuarios u ON u.id = a.cliente_id "
                     "WHERE p.vendedor_id = ? ORDER BY COALESCE(a.atualizado_em, a.criado_em) DESC LIMIT 300", (uid,))
    produtos = db.todos("SELECT p.id, p.nome, p.visualizacoes, p.vendidos, "
                        "(SELECT COUNT(*) FROM visualizacoes v WHERE v.produto_id = p.id AND v.dia = date('now','localtime')) AS hoje, "
                        "(SELECT COUNT(*) FROM visualizacoes v WHERE v.produto_id = p.id AND v.dia >= date('now','localtime','-6 days')) AS semana, "
                        "(SELECT COUNT(*) FROM avaliacoes a WHERE a.produto_id = p.id) AS comentarios, "
                        "COALESCE((SELECT ROUND(AVG(a.nota),1) FROM avaliacoes a WHERE a.produto_id = p.id),0) AS nota "
                        "FROM produtos p WHERE p.vendedor_id = ? ORDER BY p.visualizacoes DESC", (uid,))
    return render_template("vendedor/avaliacoes.html", avaliacoes=lista, produtos=produtos)


# ---------------------------------------------------------------- notificações e perfil
@bp.route("/notificacoes")
def notificacoes():
    lista = db.todos("SELECT * FROM notificacoes WHERE usuario_id = ? ORDER BY id DESC LIMIT 200", (g.usuario["id"],))
    db.executar("UPDATE notificacoes SET lida = 1 WHERE usuario_id = ?", (g.usuario["id"],))
    return render_template("notificacoes.html", notificacoes=lista, base="vendedor/base.html")


@bp.route("/perfil", methods=["GET", "POST"])
def perfil():
    uid = g.usuario["id"]
    end = db.um("SELECT * FROM enderecos WHERE usuario_id = ?", (uid,))
    if request.method == "POST":
        f = request.form
        con = db.get_db()
        try:
            celular = validar_celular(f.get("celular"))
            cep = validar_cep(f.get("cep"))
        except ErroValidacao as e:
            flash(str(e), "erro")
            return redirect(url_for("vendedor.perfil"))
        if request.files.get("foto") and request.files["foto"].filename:
            try:
                nova = salvar_foto_perfil(request.files["foto"])
                apagar_arquivo(g.usuario["foto"])
                con.execute("UPDATE usuarios SET foto = ? WHERE id = ?", (nova, uid))
            except ErroImagem as e:
                flash(f"Foto: {e}", "erro")
        con.execute("UPDATE usuarios SET celular = ? WHERE id = ?", (celular, uid))
        con.execute("UPDATE vendedores SET ponto_comercial = ?, feira = ?, descricao = ?, banca_lat = ?, banca_lng = ? "
                    "WHERE usuario_id = ?", ((f.get("ponto_comercial") or g.loja["ponto_comercial"]).strip()[:80],
                                             (f.get("feira") or "").strip()[:80], (f.get("descricao") or "").strip()[:500],
                                             _num(f.get("lat")), _num(f.get("lng")), uid))
        con.execute("UPDATE enderecos SET cep = ?, logradouro = ?, numero = ?, bairro = ?, cidade = ?, uf = ? WHERE usuario_id = ?",
                    (cep, f.get("logradouro", "").strip()[:120], f.get("numero", "").strip()[:20],
                     f.get("bairro", "").strip()[:80], f.get("cidade", "").strip()[:80], (f.get("uf") or "AM")[:2].upper(), uid))
        con.commit()
        flash("Dados atualizados.", "ok")
        return redirect(url_for("vendedor.perfil"))
    return render_template("vendedor/perfil.html", end=end,
                           doc=mascarar_documento(g.usuario["documento_tipo"], g.usuario["documento"]))

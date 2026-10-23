"""
Loja (área pública e compra): vitrine, busca, produto, avaliações, carrinho e checkout.

Uma compra com produtos de vários feirantes vira um pedido por vendedor,
porque cada vendedor recebe na sua própria conta (PIX ou cartão).
"""
import hashlib
from datetime import date

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)

from .. import db, servicos
from ..pix import gerar_payload
from ..utils import (MODALIDADES, agora, calcular_fretes, distancia_rota_km,
                     gerar_codigo)
from ..validacao import ErroValidacao
from .auth import gravar_cartao, papel_requerido, validar_cartao

bp = Blueprint("loja", __name__)

# Produto só aparece na loja se o vendedor já cadastrou a conta bancária
VISIVEL = db.LOJA_VISIVEL + " AND EXISTS (SELECT 1 FROM contas_bancarias cb WHERE cb.vendedor_id = p.vendedor_id)"


# ---------------------------------------------------------------- auxiliares
def posicao_cliente():
    local = session.get("local") or {}
    if not local and g.usuario and g.usuario["papel"] == "cliente":
        end = db.um("SELECT lat, lng FROM enderecos WHERE usuario_id = ?", (g.usuario["id"],))
        if end and end["lat"]:
            return end["lat"], end["lng"]
    return (local.get("lat") or current_app.config["LAT_PADRAO"], local.get("lng") or current_app.config["LNG_PADRAO"])


def com_distancia(produtos):
    lat, lng = posicao_cliente()
    saida = []
    for p in produtos:
        item = dict(p)
        item["distancia"] = distancia_rota_km(lat, lng, p["vendedor_lat"], p["vendedor_lng"])
        saida.append(item)
    return saida


def registrar_visualizacao(produto_id):
    """Conta 1 visualização por visitante por dia (não conta o próprio vendedor)."""
    if g.usuario and g.usuario["papel"] == "vendedor":
        return
    if "visitante" not in session:
        session["visitante"] = hashlib.sha1(session["csrf"].encode()).hexdigest()[:16]
    con = db.get_db()
    cur = con.execute("INSERT OR IGNORE INTO visualizacoes (produto_id, visitante, dia) VALUES (?,?,?)",
                      (produto_id, session["visitante"], date.today().isoformat()))
    if cur.rowcount:
        con.execute("UPDATE produtos SET visualizacoes = visualizacoes + 1 WHERE id = ?", (produto_id,))
    con.commit()


# ---------------------------------------------------------------- vitrine
@bp.route("/")
def inicio():
    promocoes = com_distancia(db.listar_produtos(VISIVEL + " AND p.promocao_dia = 1", ordem="p.preco ASC"))
    promocoes.sort(key=lambda p: p["distancia"] or 999)
    sobras = com_distancia(db.listar_produtos(VISIVEL + " AND p.fim_de_feira = 1"))
    mais_vendidos = com_distancia(db.listar_produtos(VISIVEL, ordem="p.vendidos DESC", limite=10))
    melhores = com_distancia(db.listar_produtos(VISIVEL, ordem="nota_media DESC, total_avaliacoes DESC", limite=10))
    lat, lng = posicao_cliente()
    vendedores = sorted([dict(v, distancia=distancia_rota_km(lat, lng, v["lat"], v["lng"])) for v in db.listar_vendedores()],
                        key=lambda v: v["distancia"] or 999)
    return render_template("index.html", promocoes=promocoes, sobras=sobras, mais_vendidos=mais_vendidos,
                           melhor_avaliados=melhores, vendedores=vendedores)


@bp.route("/busca")
def busca():
    q = request.args.get("q", "").strip()
    cat = request.args.get("categoria", "")
    ordem = request.args.get("ordem", "relevancia")
    estrelas = request.args.get("estrelas", type=int)
    preco_max = request.args.get("preco_max", type=float)
    filtro = request.args.get("filtro", "")
    where, params = [VISIVEL], []
    if q:
        where.append("(p.nome LIKE ? OR p.descricao LIKE ? OR p.origem LIKE ? OR u.nome_completo LIKE ? OR v.ponto_comercial LIKE ?)")
        params += [f"%{q}%"] * 5
    if cat:
        where.append("c.slug = ?")
        params.append(cat)
    if preco_max:
        where.append("p.preco <= ?")
        params.append(preco_max)
    if filtro == "promocao":
        where.append("(p.promocao_dia = 1 OR p.preco_original IS NOT NULL)")
    if filtro == "sobras":
        where.append("p.fim_de_feira = 1")
    ordens = {"relevancia": "p.vendidos DESC", "menor_preco": "p.preco ASC", "maior_preco": "p.preco DESC",
              "avaliacao": "nota_media DESC", "visualizados": "p.visualizacoes DESC"}
    produtos = com_distancia(db.listar_produtos(" AND ".join(where), params, ordens.get(ordem, ordens["relevancia"])))
    if estrelas:
        produtos = [p for p in produtos if p["nota_media"] >= estrelas]
    if ordem == "distancia":
        produtos.sort(key=lambda p: p["distancia"] or 999)
    categoria = next((c for c in db.listar_categorias() if c["slug"] == cat), None)
    return render_template("busca.html", produtos=produtos, q=q, categoria=categoria, cat=cat, ordem=ordem,
                           estrelas=estrelas, preco_max=preco_max, filtro=filtro)


@bp.route("/produto/<int:produto_id>")
def produto(produto_id):
    p = db.obter_produto(produto_id)
    dono = g.usuario and g.usuario["id"] == (p["vendedor_id"] if p else None)
    if not p or (not p["ativo"] and not dono):
        abort(404)
    registrar_visualizacao(produto_id)
    p = com_distancia([p])[0]
    avaliacoes = db.todos("SELECT a.*, u.nome_completo AS nome, u.foto FROM avaliacoes a JOIN usuarios u ON u.id = a.cliente_id "
                          "WHERE a.produto_id = ? ORDER BY COALESCE(a.atualizado_em, a.criado_em) DESC", (produto_id,))
    dist = {n: 0 for n in range(5, 0, -1)}
    for a in avaliacoes:
        dist[a["nota"]] += 1
    minha = None
    if g.usuario and g.usuario["papel"] == "cliente":
        minha = next((a for a in avaliacoes if a["cliente_id"] == g.usuario["id"]), None)
    similares = com_distancia(
        list(db.listar_produtos(VISIVEL + " AND p.categoria_id = ? AND p.id != ?", (p["categoria_id"], p["id"]), "p.preco"))
        + list(db.listar_produtos(VISIVEL + " AND p.categoria_id != ? AND p.id != ?", (p["categoria_id"], p["id"]),
                                  "RANDOM()", limite=10)))[:10]
    conta = db.um("SELECT * FROM contas_bancarias WHERE vendedor_id = ?", (p["vendedor_id"],))
    return render_template("produto.html", p=p, imagens=db.imagens_produto(produto_id), avaliacoes=avaliacoes,
                           distribuicao=dist, minha=minha, similares=similares, conta=conta,
                           fretes=calcular_fretes(p["distancia"], db.get_config(), p["preco"]),
                           vendedor=db.obter_vendedor_publico(p["vendedor_id"]), dono=dono)


@bp.route("/produto/<int:produto_id>/avaliar", methods=["POST"])
@papel_requerido("cliente")
def avaliar(produto_id):
    """Cliente comenta e classifica com 1 a 5 estrelas (Péssimo → Excelente). Pode atualizar a própria avaliação."""
    p = db.obter_produto(produto_id) or abort(404)
    nota = request.form.get("nota", type=int)
    comentario = (request.form.get("comentario") or "").strip()[:800]
    if not nota or not 1 <= nota <= 5:
        flash("Escolha de 1 a 5 estrelas.", "erro")
        return redirect(url_for("loja.produto", produto_id=produto_id) + "#avaliacoes")
    con = db.get_db()
    existente = con.execute("SELECT id FROM avaliacoes WHERE produto_id = ? AND cliente_id = ?",
                            (produto_id, g.usuario["id"])).fetchone()
    if existente:
        con.execute("UPDATE avaliacoes SET nota = ?, comentario = ?, atualizado_em = ? WHERE id = ?",
                    (nota, comentario, agora(), existente["id"]))
    else:
        con.execute("INSERT INTO avaliacoes (produto_id, cliente_id, nota, comentario) VALUES (?,?,?,?)",
                    (produto_id, g.usuario["id"], nota, comentario))
    servicos.notificar(p["vendedor_id"], "avaliacao", f"Nova avaliação: {'★' * nota}{'☆' * (5 - nota)}",
                       f"{g.usuario['nome_completo'].split()[0]} avaliou {p['nome']}" + (f": “{comentario[:80]}”" if comentario else "."),
                       "/vendedor/avaliacoes", commit=False)
    con.commit()
    flash("Obrigado! Sua avaliação foi publicada.", "ok")
    return redirect(url_for("loja.produto", produto_id=produto_id) + "#avaliacoes")


@bp.route("/feirante/<int:vendedor_id>")
def vendedor(vendedor_id):
    v = db.obter_vendedor_publico(vendedor_id) or abort(404)
    produtos = com_distancia(db.listar_produtos(VISIVEL + " AND p.vendedor_id = ?", (vendedor_id,)))
    lat, lng = posicao_cliente()
    return render_template("vendedor.html", v=v, produtos=produtos, distancia=distancia_rota_km(lat, lng, v["lat"], v["lng"]))


@bp.route("/api/localizacao", methods=["POST"])
def salvar_localizacao():
    d = request.get_json(silent=True) or {}
    try:
        lat, lng = float(d["lat"]), float(d["lng"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "erro": "Coordenadas inválidas"}), 400
    session["local"] = {"lat": lat, "lng": lng, "endereco": (d.get("endereco") or "").strip()[:250] or f"{lat:.5f}, {lng:.5f}",
                        "curto": (d.get("curto") or "").strip()[:80]}
    return jsonify({"ok": True, "local": session["local"]})


# ---------------------------------------------------------------- carrinho
def itens_carrinho():
    itens, subtotal = [], 0.0
    for pid, qtd in session.get("carrinho", {}).items():
        p = db.obter_produto(int(pid))
        if not p or not p["ativo"]:
            continue
        qtd = min(qtd, max(p["estoque"], 0))
        if qtd <= 0:
            continue
        total = round(p["preco"] * qtd, 2)
        subtotal += total
        itens.append({"p": p, "qtd": qtd, "total": total})
    return itens, round(subtotal, 2)


def agrupar_por_vendedor(itens):
    grupos = {}
    for i in itens:
        grupos.setdefault(i["p"]["vendedor_id"], []).append(i)
    return grupos


@bp.route("/carrinho")
def carrinho():
    itens, subtotal = itens_carrinho()
    sugestoes = com_distancia(db.listar_produtos(VISIVEL + " AND p.promocao_dia = 1", ordem="RANDOM()", limite=8))
    return render_template("carrinho.html", itens=itens, subtotal=subtotal, sugestoes=sugestoes,
                           n_vendedores=len(agrupar_por_vendedor(itens)))


@bp.route("/carrinho/adicionar", methods=["POST"])
def carrinho_adicionar():
    pid = request.form.get("produto_id", type=int)
    qtd = max(request.form.get("quantidade", 1, type=int), 1)
    p = db.obter_produto(pid or 0)
    if not p or p["estoque"] <= 0 or not p["ativo"]:
        flash("Produto sem estoque no momento.", "erro")
        return redirect(request.referrer or url_for("loja.inicio"))
    if g.usuario and g.usuario["id"] == p["vendedor_id"]:
        flash("Você não pode comprar o seu próprio produto.", "erro")
        return redirect(url_for("loja.produto", produto_id=pid))
    car = session.get("carrinho", {})
    car[str(pid)] = min(car.get(str(pid), 0) + qtd, p["estoque"])
    session["carrinho"] = car
    if request.form.get("comprar_agora"):
        return redirect(url_for("loja.checkout"))
    flash(f"{p['nome']} foi adicionado ao carrinho.", "ok")
    return redirect(request.referrer or url_for("loja.carrinho"))


@bp.route("/carrinho/atualizar", methods=["POST"])
def carrinho_atualizar():
    car = session.get("carrinho", {})
    pid = request.form.get("produto_id", "")
    qtd = request.form.get("quantidade", 0, type=int)
    if qtd <= 0:
        car.pop(pid, None)
    elif pid in car:
        p = db.obter_produto(int(pid))
        car[pid] = min(qtd, p["estoque"]) if p else 0
    session["carrinho"] = car
    return redirect(url_for("loja.carrinho"))


# ---------------------------------------------------------------- checkout
def _montar_entregas(grupos, lat, lng, cfg):
    entregas = []
    for vid, itens in grupos.items():
        p0 = itens[0]["p"]
        dist = distancia_rota_km(lat, lng, p0["vendedor_lat"], p0["vendedor_lng"]) or 0
        sub = round(sum(i["total"] for i in itens), 2)
        conta = db.um("SELECT * FROM contas_bancarias WHERE vendedor_id = ?", (vid,))
        entregas.append({"vendedor_id": vid, "banca": p0["vendedor_banca"], "feira": p0["vendedor_feira"], "itens": itens,
                         "subtotal": sub, "distancia": dist, "fretes": calcular_fretes(dist, cfg, sub), "conta": conta,
                         "origem": (p0["vendedor_lat"], p0["vendedor_lng"])})
    return entregas


@bp.route("/checkout", methods=["GET", "POST"])
@papel_requerido("cliente")
def checkout():
    itens, subtotal = itens_carrinho()
    if not itens:
        flash("Seu carrinho está vazio.", "erro")
        return redirect(url_for("loja.inicio"))
    cfg = db.get_config()
    uid = g.usuario["id"]
    end = db.um("SELECT * FROM enderecos WHERE usuario_id = ?", (uid,))
    local = session.get("local") or {}
    lat = local.get("lat") or (end["lat"] if end else None) or current_app.config["LAT_PADRAO"]
    lng = local.get("lng") or (end["lng"] if end else None) or current_app.config["LNG_PADRAO"]
    entregas = _montar_entregas(agrupar_por_vendedor(itens), lat, lng, cfg)
    cartoes = db.todos("SELECT * FROM cartoes WHERE cliente_id = ? ORDER BY id DESC", (uid,))
    endereco_txt = (f"{end['logradouro']}, {end['numero']}{' - ' + end['complemento'] if end['complemento'] else ''} - "
                    f"{end['bairro']}, {end['cidade']} - {end['uf']}, CEP {end['cep']}") if end else ""
    ctx = dict(entregas=entregas, subtotal=subtotal, cartoes=cartoes, endereco_txt=endereco_txt,
               referencia=end["referencia"] if end else "", parcelas_max=int(cfg["parcelas_max"]),
               parcela_min=float(cfg["parcela_minima"]))
    if request.method == "GET":
        return render_template("checkout.html", **ctx, form={})

    f = request.form
    erros = []
    endereco = (f.get("endereco") or endereco_txt).strip()[:250]
    referencia = (f.get("referencia") or "").strip()[:160]
    pagamento = f.get("pagamento", "pix")
    if pagamento not in MODALIDADES:
        erros.append("Escolha a forma de pagamento.")

    # Cartão: salvo ou novo (o CVV só é conferido, nunca guardado)
    cartao = None
    if pagamento in ("credito", "debito"):
        escolha = f.get("cartao_id", "novo")
        if escolha != "novo":
            cartao = db.um("SELECT * FROM cartoes WHERE id = ? AND cliente_id = ?", (escolha, uid))
            if not cartao:
                erros.append("Cartão não encontrado.")
            elif cartao["tipo"] != pagamento:
                erros.append(f"O cartão final {cartao['final']} é de {MODALIDADES[cartao['tipo']].lower()}.")
        else:
            try:
                dados = f.to_dict()
                dados["cartao_tipo"] = pagamento
                cartao = validar_cartao(dados)
            except ErroValidacao as ex:
                erros.append(str(ex))
        cvv = f.get("cartao_cvv", "")
        if not (cvv.isdigit() and len(cvv) in (3, 4)):
            erros.append("CVV inválido.")
    parcelas = max(1, min(f.get("parcelas", 1, type=int), int(cfg["parcelas_max"]))) if pagamento == "credito" else 1

    escolhas = []
    for e in entregas:
        modo = f.get(f"entrega_{e['vendedor_id']}", "moto")
        frete = next((o for o in e["fretes"] if o["modo"] == modo and o["disponivel"]), None)
        if not frete:
            erros.append(f"Escolha uma entrega disponível para {e['banca']}.")
            continue
        if modo != "retirada" and not endereco:
            erros.append("Informe o endereço de entrega.")
        c = e["conta"]
        if not c:
            erros.append(f"{e['banca']} ainda não pode receber pagamentos.")
        elif not c[f"aceita_{pagamento}"]:
            erros.append(f"{e['banca']} não aceita {MODALIDADES.get(pagamento, '').lower()}.")
        elif pagamento == "pix" and not c["pix_chave"]:
            erros.append(f"{e['banca']} não cadastrou chave PIX.")
        elif cartao and not c[f"bandeira_{cartao['bandeira'].lower()}"]:
            erros.append(f"{e['banca']} não aceita a bandeira {cartao['bandeira']}.")
        escolhas.append((e, frete))

    if erros:
        for x in dict.fromkeys(erros):
            flash(x, "erro")
        return render_template("checkout.html", **ctx, form=f), 400

    con = db.get_db()
    if cartao and isinstance(cartao, dict) and f.get("salvar_cartao"):
        gravar_cartao(con, uid, cartao)
    compra = gerar_codigo("C")
    pagamentos_aprovar = []
    for e, frete in escolhas:
        # Confere o estoque de novo dentro da transação
        for i in e["itens"]:
            atual = con.execute("SELECT estoque FROM produtos WHERE id = ?", (i["p"]["id"],)).fetchone()["estoque"]
            if atual < i["qtd"]:
                con.rollback()
                flash(f"{i['p']['nome']}: só restam {atual} {i['p']['unidade']}.", "erro")
                return redirect(url_for("loja.carrinho"))
        total = round(e["subtotal"] + frete["valor"], 2)
        codigo = gerar_codigo("FC")
        pid = con.execute(
            "INSERT INTO pedidos (codigo, compra_codigo, cliente_id, vendedor_id, endereco, referencia, destino_lat, destino_lng, "
            "origem_lat, origem_lng, entrega_modo, entrega_valor, distancia_km, subtotal, total) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (codigo, compra, uid, e["vendedor_id"], endereco if frete["modo"] != "retirada" else "Retirada na banca",
             referencia, lat, lng, e["origem"][0], e["origem"][1], frete["modo"], frete["valor"], e["distancia"],
             e["subtotal"], total)).lastrowid
        for i in e["itens"]:
            con.execute("INSERT INTO itens_pedido (pedido_id, produto_id, nome, preco, quantidade) VALUES (?,?,?,?,?)",
                        (pid, i["p"]["id"], i["p"]["nome"], i["p"]["preco"], i["qtd"]))
            con.execute("UPDATE produtos SET estoque = estoque - ?, vendidos = vendidos + ? WHERE id = ?",
                        (i["qtd"], i["qtd"], i["p"]["id"]))
        payload, txid = "", ""
        if pagamento == "pix":
            txid = codigo
            payload = gerar_payload(e["conta"]["pix_chave"], total, e["conta"]["titular"], g_cidade(e), txid)
        pag_id = con.execute(
            "INSERT INTO pagamentos (pedido_id, vendedor_id, modalidade, bandeira, cartao_final, parcelas, valor, pix_txid, pix_payload) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (pid, e["vendedor_id"], pagamento, cartao["bandeira"] if cartao else "", cartao["final"] if cartao else "",
             parcelas, total, txid, payload)).lastrowid
        servicos.notificar(e["vendedor_id"], "pedido", f"🛒 Novo pedido #{codigo}",
                           f"{len(e['itens'])} produto(s) · {MODALIDADES[pagamento]}"
                           + (" — aguardando o PIX" if pagamento == "pix" else ""),
                           f"/vendedor/pedidos/{codigo}", commit=False)
        if pagamento != "pix":
            pagamentos_aprovar.append(pag_id)
    con.commit()
    # Cartão: aqui entraria a chamada ao gateway. Em MODO_TESTE a autorização é simulada e aprovada.
    for pag_id in pagamentos_aprovar:
        servicos.confirmar_pagamento(pag_id, origem="cartao")
    session["carrinho"] = {}
    return redirect(url_for("cliente.compra", codigo=compra))


def g_cidade(entrega):
    end = db.um("SELECT cidade FROM enderecos WHERE usuario_id = ?", (entrega["vendedor_id"],))
    return end["cidade"] if end else "BRASIL"

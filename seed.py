"""
Cria dados de EXEMPLO para testar o FeiraConnect: feirantes com conta bancária,
clientes, entregadores, produtos com fotos HD, avaliações e um histórico de vendas
de 14 meses (para o dashboard dia/mês/trimestre/ano ter o que mostrar).

    python seed.py            # só popula se o banco estiver vazio
    python seed.py --reset    # apaga o banco e as fotos enviadas e recria tudo

Todos os nomes, CPFs, telefones e coordenadas são fictícios. Senha de todas as contas: feira123
"""
import io
import os
import random
import shutil
import sys
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from config import Config

BASE = os.path.dirname(os.path.abspath(__file__))
FOTOS = os.path.join(BASE, "dados_exemplo", "fotos")
SENHA = "feira123"
rnd = random.Random(2026)


def gerar_cpf():
    n = [rnd.randint(0, 9) for _ in range(9)]
    for tam in (9, 10):
        s = sum(v * (tam + 1 - i) for i, v in enumerate(n[:tam]))
        n.append((s * 10 % 11) % 10)
    return "".join(map(str, n))


def foto_iniciais(nome, cor):
    """Foto de perfil de exemplo (círculo com iniciais)."""
    img = Image.new("RGB", (512, 512), cor)
    d = ImageDraw.Draw(img)
    ini = (nome.split()[0][0] + nome.split()[-1][0]).upper()
    try:
        fonte = ImageFont.truetype("DejaVuSans-Bold.ttf", 200)
    except OSError:
        fonte = ImageFont.load_default(size=200)
    d.text((256, 256), ini, fill="white", font=fonte, anchor="mm")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    buf.seek(0)
    return FileStorage(buf, filename="perfil.jpg")


CATEGORIAS = [("Frutas", "frutas", "img/cat/frutas.svg"), ("Verduras e Legumes", "verduras", "img/cat/verduras.svg"),
              ("Peixes", "peixes", "img/cat/peixes.svg"), ("Farinhas e Grãos", "farinhas", "img/cat/farinhas.svg"),
              ("Polpas e Bebidas", "polpas", "img/cat/polpas.svg"), ("Laticínios e Ovos", "laticinios", "img/cat/laticinios.svg"),
              ("Mel e Naturais", "naturais", "img/cat/naturais.svg"), ("Cestas e Sobras", "cestas", "img/cat/cestas.svg")]

# login, nome, banca, feira, rua, número, bairro, CEP, lat, lng, cor, chave PIX (tipo, valor)
VENDEDORES = [
    ("raimunda", "Raimunda Souza Lima", "Banca da Dona Raimunda", "Feira da Manaus Moderna", "Rua dos Barés", "42", "Centro",
     "69005-020", -3.1386, -60.0236, "#8D5B3A", ("email", "raimunda.banca@exemplo.com.br")),
    ("chico", "Francisco Lima Pereira", "Hortifrúti do Chico", "Feira do Produtor Rural", "Av. Cosme Ferreira", "18", "Coroado",
     "69082-230", -3.0858, -59.9812, "#2E7D32", ("celular", "+5592991000002")),
    ("joana", "Joana Batista Rocha", "Peixaria Rio Negro", "Feira da Panair", "Rua Belém", "7", "Educandos",
     "69070-150", -3.1408, -60.0078, "#1F5C8A", ("email", "peixaria.rionegro@exemplo.com.br")),
    ("antonio", "Antônio Pereira Gomes", "Sítio Boa Esperança", "Feira do Produtor Rural", "Av. Cosme Ferreira", "31", "Coroado",
     "69082-230", -3.0861, -59.9806, "#6C8E2F", ("email", "sitio.esperanca@exemplo.com.br")),
    ("graca", "Maria das Graças Nunes", "Cantinho Amazônico", "Feira da Banana", "Rua Barão de São Domingos", "15", "Centro",
     "69005-030", -3.1394, -60.0251, "#C2692B", ("email", "cantinho.amazonico@exemplo.com.br")),
    ("elias", "Elias Monteiro Costa", "Meliponário Sem Ferrão", "Feira do Parque 10", "Rua do Comércio", "4", "Parque 10 de Novembro",
     "69054-570", -3.0899, -60.0149, "#A07A12", ("email", "meliponario@exemplo.com.br")),
]

CLIENTES = [("elikel", "Elikel Lima de Assunção", "Av. Djalma Batista", "1661", "Chapada", "69050-010", "Próximo ao shopping", -3.0997, -60.0262),
            ("ana", "Ana Paula Ferreira", "Rua Ramos Ferreira", "820", "Centro", "69010-120", "Prédio azul, portaria 24h", -3.1268, -60.0215),
            ("denilson", "Denilson Tavares Duarte", "Rua Pará", "305", "Vieiralves", "69053-575", "Ao lado da farmácia", -3.1022, -60.0168),
            ("thiago", "Thiago Augusto Pereira", "Av. André Araújo", "97", "Aleixo", "69060-000", "Em frente ao INPA", -3.0960, -59.9870),
            ("luana", "Luana Magalhães Leal", "Rua 10 de Julho", "540", "Centro", "69010-060", "Perto do Teatro Amazonas", -3.1301, -60.0230)]

ENTREGADORES = [("carlos", "Carlos Eduardo Silva", "moto", "QZA1B23"), ("bruno", "Bruno Alves Matos", "bicicleta", ""),
                ("sandra", "Sandra Oliveira Reis", "carro", "PHX4C56")]

# nome, descrição, preço, preço "de", unidade, estoque, origem, foto, categoria, vendedor, promo, sobra, (legenda1, legenda2)
PRODUTOS = [
    ("Açaí batido grosso - 1 litro", "Açaí tipo grosso, batido na hora e congelado. Sem açúcar e sem conservantes.", 18.00, 24.00, "litro", 40, "Codajás - AM", "acai", "polpas", 4, 1, 0, ("Batido hoje às 5h da manhã", "Grosso e sem açúcar")),
    ("Cupuaçu inteiro (fruto)", "Fruto maduro, ótimo para sucos, cremes e doces. Peso médio de 1,2 kg.", 9.00, None, "un", 25, "Presidente Figueiredo - AM", "cupuacu", "frutas", 0, 0, 0, ("Fruto inteiro, maduro", "Polpa cheirosa")),
    ("Tucumã (polpa fatiada) - 500 g", "Polpa fresquinha, pronta para o X-Caboquinho e tapioca.", 14.00, 18.00, "pacote", 18, "Autazes - AM", "tucuma", "frutas", 0, 1, 0, ("Fatiado na hora", "")),
    ("Banana prata - dúzia", "Banana prata madura no ponto, colhida no interior.", 6.50, None, "dúzia", 60, "Manacapuru - AM", "banana", "frutas", 0, 0, 0, ("Chegou de barco hoje", "")),
    ("Abacaxi de Novo Remanso", "O famoso abacaxi doce de Novo Remanso, tamanho grande.", 7.00, 10.00, "un", 35, "Itacoatiara (Novo Remanso) - AM", "abacaxi", "frutas", 0, 1, 0, ("Tamanho grande, bem doce", "Coroa verdinha")),
    ("Farinha d'água de Uarini - 1 kg", "Farinha ovinha de Uarini, crocante e amarelinha.", 14.00, None, "kg", 50, "Uarini - AM", "farinha", "farinhas", 3, 0, 0, ("Farinha ovinha legítima", "")),
    ("Castanha-do-pará - 500 g", "Castanha selecionada, sem casca, embalada a vácuo.", 29.90, 36.00, "pacote", 22, "Beruri - AM", "castanha", "naturais", 4, 1, 0, ("Selecionada a dedo", "")),
    ("Tambaqui fresco (inteiro) - kg", "Tambaqui de piscicultura, limpo e com escamas retiradas na hora.", 24.90, None, "kg", 30, "Rio Preto da Eva - AM", "tambaqui", "peixes", 2, 0, 0, ("Pescado nesta madrugada", "Limpamos na hora")),
    ("Jambu - maço", "Jambu fresquinho para tacacá e pato no tucupi.", 4.00, None, "maço", 45, "Iranduba - AM", "jambu", "verduras", 1, 0, 0, ("Maço generoso", "")),
    ("Pimenta-de-cheiro - 250 g", "Pimenta-de-cheiro amarela e vermelha, perfumada e pouco ardida.", 5.00, None, "pacote", 4, "Careiro da Várzea - AM", "pimenta", "verduras", 1, 0, 0, ("", "")),
    ("Macaxeira descascada - kg", "Macaxeira mansa, descascada e lavada, pronta para cozinhar.", 5.50, 7.00, "kg", 38, "Manacapuru - AM", "macaxeira", "verduras", 3, 1, 0, ("Descascada e lavada", "")),
    ("Tomate regional - kg", "Tomate firme e saboroso, ideal para saladas e molhos.", 8.90, None, "kg", 3, "Iranduba - AM", "tomate", "verduras", 1, 0, 0, ("", "")),
    ("Alface crespa hidropônica", "Pé grande de alface crespa, cultivo hidropônico.", 3.50, None, "pé", 28, "Manaus - AM", "alface", "verduras", 1, 0, 0, ("", "")),
    ("Cheiro-verde - maço", "Cebolinha e coentro fresquinhos, maço generoso.", 2.50, 3.50, "maço", 50, "Iranduba - AM", "cheiro-verde", "verduras", 1, 1, 0, ("", "")),
    ("Mel de abelha sem ferrão - 300 ml", "Mel de jandaíra/uruçu, leve e ácido. Produção artesanal.", 45.00, None, "frasco", 12, "Boa Vista do Ramos - AM", "mel", "naturais", 5, 0, 0, ("Colheita de outubro", "Frasco de vidro de 300 ml")),
    ("Ovos caipira - dúzia", "Ovos de galinhas criadas soltas, gema bem amarela.", 16.00, None, "dúzia", 26, "Rio Preto da Eva - AM", "ovos", "laticinios", 3, 0, 0, ("Galinhas criadas soltas", "")),
    ("Guaraná em pó de Maués - 100 g", "Guaraná ralado em bastão e moído, 100% puro.", 15.00, 19.00, "pacote", 20, "Maués - AM", "guarana", "naturais", 5, 1, 0, ("100% puro", "")),
    ("Queijo coalho artesanal - kg", "Queijo coalho de leite cru, firme, ótimo para assar.", 42.00, None, "kg", 9, "Autazes - AM", "queijo", "laticinios", 3, 0, 0, ("", "")),
    ("Melancia inteira", "Melancia doce e vermelhinha, média de 8 kg.", 15.00, None, "un", 14, "Careiro - AM", "melancia", "frutas", 0, 0, 0, ("", "")),
    ("Cesta 'Sobras do Dia' - fim de feira", "Mix surpresa de frutas e verduras em ótimo estado que sobraram da feira.", 19.90, 45.00, "cesta", 8, "Feiras de Manaus - AM", "cesta", "cestas", 1, 1, 1, ("Cada cesta é uma surpresa", "")),
    ("Limão regional - kg", "Limão galego suculento, ideal para sucos e temperos.", 4.80, 8.00, "kg", 15, "Iranduba - AM", "limao", "frutas", 0, 0, 1, ("", "")),
    ("Abacate manteiga - kg", "Abacate cremoso, no ponto de consumo amanhã.", 6.90, 11.50, "kg", 11, "Presidente Figueiredo - AM", "abacate", "frutas", 0, 0, 1, ("", "")),
]

COMENTARIOS = {5: ["Produto fresquinho, chegou rapidinho de moto!", "Melhor que no supermercado. Recomendo!", "Feirante muito atenciosa, embalagem caprichada."],
               4: ["Muito bom, só demorou um pouco a entrega.", "Gostei bastante, preço justo."],
               3: ["Ok, mas esperava um pouco maior."], 2: ["Veio um pouco passado do ponto."], 1: ["Chegou amassado."]}


def criar(reset=False):
    if reset:
        if os.path.exists(Config.DATABASE):
            os.remove(Config.DATABASE)
        for sub in ("produtos", "perfis"):
            shutil.rmtree(os.path.join(Config.UPLOAD_FOLDER, sub), ignore_errors=True)
    from feiraconnect import create_app, db
    from feiraconnect.imagens import salvar_foto_perfil, salvar_foto_produto
    from feiraconnect.pix import gerar_payload

    app = create_app()
    with app.app_context():
        con = db.get_db()
        if con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]:
            print("O banco já tem dados. Use `python seed.py --reset` para recriar do zero.")
            return
        senha = generate_password_hash(SENHA)
        cat = {}
        for nome, slug, icone in CATEGORIAS:
            cat[slug] = con.execute("INSERT INTO categorias (nome, slug, icone) VALUES (?,?,?)", (nome, slug, icone)).lastrowid

        def usuario(papel, login, nome, cor, nasc):
            return con.execute("INSERT INTO usuarios (papel, login, senha_hash, nome_completo, documento_tipo, documento, nascimento, celular, foto) "
                               "VALUES (?,?,?,?,?,?,?,?,?)",
                               (papel, login, senha, nome, "CPF", gerar_cpf(), nasc,
                                f"(92) 9{rnd.randint(8100, 9999)}-{rnd.randint(1000, 9999)}",
                                salvar_foto_perfil(foto_iniciais(nome, cor)))).lastrowid

        vend = []
        for (login, nome, banca, feira, rua, num, bairro, cep, lat, lng, cor, pix) in VENDEDORES:
            uid = usuario("vendedor", login, nome, cor, f"19{rnd.randint(60, 90)}-0{rnd.randint(1, 9)}-1{rnd.randint(0, 9)}")
            con.execute("INSERT INTO enderecos (usuario_id, cep, logradouro, numero, bairro, cidade, uf, lat, lng) VALUES (?,?,?,?,?,?,?,?,?)",
                        (uid, cep, rua, num, bairro, "Manaus", "AM", lat, lng))
            con.execute("INSERT INTO vendedores (usuario_id, ponto_comercial, feira, descricao, banca_lat, banca_lng) VALUES (?,?,?,?,?,?)",
                        (uid, banca, feira, "Produtos frescos da região, direto do produtor.", lat, lng))
            doc = con.execute("SELECT documento FROM usuarios WHERE id = ?", (uid,)).fetchone()[0]
            con.execute("INSERT INTO contas_bancarias (vendedor_id, banco_codigo, banco_nome, agencia, conta, conta_digito, conta_tipo, "
                        "titular, titular_documento, pix_tipo, pix_chave) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (uid, "037", "Banco da Amazônia (Basa)", str(rnd.randint(1000, 9999)), str(rnd.randint(100000, 999999)),
                         str(rnd.randint(0, 9)), "corrente", nome, doc, pix[0], pix[1]))
            vend.append(uid)

        clientes = []
        for (login, nome, rua, num, bairro, cep, ref, lat, lng) in CLIENTES:
            uid = usuario("cliente", login, nome, rnd.choice(["#5B7F3A", "#8D5B3A", "#1F5C8A", "#7A4E9E"]), f"19{rnd.randint(85, 99)}-0{rnd.randint(1, 9)}-2{rnd.randint(0, 8)}")
            con.execute("INSERT INTO enderecos (usuario_id, cep, logradouro, numero, bairro, cidade, uf, referencia, lat, lng) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)", (uid, cep, rua, num, bairro, "Manaus", "AM", ref, lat, lng))
            for tipo, band, final in (("credito", rnd.choice(["Visa", "Mastercard", "Elo"]), f"{rnd.randint(1000, 9999)}"),
                                      ("debito", rnd.choice(["Visa", "Elo"]), f"{rnd.randint(1000, 9999)}")):
                con.execute("INSERT INTO cartoes (cliente_id, tipo, bandeira, final, titular, validade, token) VALUES (?,?,?,?,?,?,?)",
                            (uid, tipo, band, final, nome.upper()[:26], "08/30", f"tok_exemplo_{uid}_{tipo}"))
            clientes.append((uid, lat, lng, f"{rua}, {num} - {bairro}, Manaus - AM, CEP {cep}", ref))

        entregadores = []
        for login, nome, veiculo, placa in ENTREGADORES:
            uid = usuario("entregador", login, nome, "#3E5C2A", f"199{rnd.randint(0, 9)}-1{rnd.randint(0, 2)}-1{rnd.randint(0, 9)}")
            con.execute("INSERT INTO entregadores (usuario_id, veiculo, placa) VALUES (?,?,?)", (uid, veiculo, placa))
            entregadores.append((uid, veiculo))

        prods = []
        for (nome, desc, preco, orig, un, est, origem, foto, c, vi, promo, sobra, legendas) in PRODUTOS:
            pid = con.execute("INSERT INTO produtos (vendedor_id, categoria_id, nome, descricao, preco, preco_original, unidade, estoque, "
                              "origem, promocao_dia, fim_de_feira) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                              (vend[vi], cat[c], nome, desc, preco, orig, un, est, origem, promo, sobra)).lastrowid
            for k in (1, 2):
                caminho = os.path.join(FOTOS, f"{foto}_{k}.jpg")
                if not os.path.exists(caminho):
                    continue
                with open(caminho, "rb") as fh:
                    info = salvar_foto_produto(FileStorage(io.BytesIO(fh.read()), filename=f"{foto}.jpg"))
                con.execute("INSERT INTO produto_imagens (produto_id, arquivo, miniatura, largura, altura, legenda, ordem) VALUES (?,?,?,?,?,?,?)",
                            (pid, info["arquivo"], info["miniatura"], info["largura"], info["altura"], legendas[k - 1], k - 1))
            prods.append((pid, nome, preco, vend[vi]))

        # Avaliações (uma por cliente por produto)
        for pid, *_ in prods:
            for (cid, *_r) in rnd.sample(clientes, rnd.randint(2, 5)):
                nota = rnd.choices([5, 4, 3, 2, 1], weights=[55, 28, 10, 4, 3])[0]
                dia = datetime.now() - timedelta(days=rnd.randint(1, 120))
                con.execute("INSERT INTO avaliacoes (produto_id, cliente_id, nota, comentario, criado_em) VALUES (?,?,?,?,?)",
                            (pid, cid, nota, rnd.choice(COMENTARIOS[nota]), dia.strftime("%Y-%m-%d %H:%M:%S")))

        # Histórico de vendas: ~14 meses, mais movimento nos fins de semana e de manhã
        agora = datetime.now()
        por_vendedor = {}
        for p in prods:
            por_vendedor.setdefault(p[3], []).append(p)
        n = 0
        for dias_atras in range(420, -1, -1):
            dia = agora - timedelta(days=dias_atras)
            qtd = rnd.randint(1, 4) + (3 if dia.weekday() >= 5 else 0) + (2 if dias_atras < 60 else 0)
            for _ in range(qtd):
                hora = rnd.choices(range(6, 22), weights=[6, 9, 10, 9, 7, 6, 5, 4, 4, 5, 6, 6, 5, 4, 3, 2])[0]
                momento = dia.replace(hour=hora, minute=rnd.randint(0, 59), second=rnd.randint(0, 59))
                if momento > agora - timedelta(minutes=40):
                    continue
                vid = rnd.choice(vend)
                itens = rnd.sample(por_vendedor[vid], min(len(por_vendedor[vid]), rnd.randint(1, 3)))
                cid, clat, clng, cend, cref = rnd.choice(clientes)
                modo = rnd.choice(["moto", "moto", "carro", "bicicleta", "retirada"])
                frete = {"moto": 7.9, "carro": 12.6, "bicicleta": 4.6, "retirada": 0}[modo]
                qtds = [rnd.randint(1, 3) for _ in itens]
                sub = round(sum(i[2] * q for i, q in zip(itens, qtds)), 2)
                total = round(sub + frete, 2)
                modal = rnd.choices(["pix", "credito", "debito"], weights=[55, 30, 15])[0]
                cancelado = rnd.random() < 0.05
                status = "cancelado" if cancelado else "entregue"
                n += 1
                codigo = f"FCX{n:05d}"
                ts = momento.strftime("%Y-%m-%d %H:%M:%S")
                pago = (momento + timedelta(minutes=rnd.randint(0, 4))).strftime("%Y-%m-%d %H:%M:%S")
                ent = rnd.choice(entregadores)[0] if modo != "retirada" and not cancelado else None
                vlat, vlng = next((v[8], v[9]) for v in VENDEDORES if v[0] == con.execute("SELECT login FROM usuarios WHERE id=?", (vid,)).fetchone()[0])
                ped = con.execute(
                    "INSERT INTO pedidos (codigo, compra_codigo, cliente_id, vendedor_id, entregador_id, endereco, referencia, destino_lat, "
                    "destino_lng, origem_lat, origem_lng, entrega_modo, entrega_valor, distancia_km, subtotal, total, status, criado_em, "
                    "pago_em, saiu_em, entregue_em, cancelado_em, cancelado_por) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (codigo, "C" + codigo, cid, vid, ent, cend if modo != "retirada" else "Retirada na banca", cref, clat, clng, vlat, vlng,
                     modo, frete, round(rnd.uniform(1.5, 9), 1), sub, total, status, ts, pago,
                     None if cancelado else pago, None if cancelado else (momento + timedelta(minutes=35)).strftime("%Y-%m-%d %H:%M:%S"),
                     (momento + timedelta(minutes=8)).strftime("%Y-%m-%d %H:%M:%S") if cancelado else None,
                     "cliente" if cancelado else None)).lastrowid
                for (pid, nome, preco, _v), q in zip(itens, qtds):
                    con.execute("INSERT INTO itens_pedido (pedido_id, produto_id, nome, preco, quantidade) VALUES (?,?,?,?,?)", (ped, pid, nome, preco, q))
                    if not cancelado:
                        con.execute("UPDATE produtos SET vendidos = vendidos + ? WHERE id = ?", (q, pid))
                band = "" if modal == "pix" else rnd.choice(["Visa", "Mastercard", "Elo"])
                con.execute("INSERT INTO pagamentos (pedido_id, vendedor_id, modalidade, bandeira, cartao_final, parcelas, valor, status, "
                            "pix_txid, criado_em, confirmado_em, estornado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            (ped, vid, modal, band, "" if modal == "pix" else str(rnd.randint(1000, 9999)),
                             rnd.choice([1, 1, 2, 3]) if modal == "credito" else 1, total, "estornado" if cancelado else "aprovado",
                             codigo if modal == "pix" else "", ts, pago,
                             (momento + timedelta(minutes=8)).strftime("%Y-%m-%d %H:%M:%S") if cancelado else None))
                # visualizações daquele dia
                for (pid, *_x) in itens:
                    for v in range(rnd.randint(2, 6)):
                        con.execute("INSERT OR IGNORE INTO visualizacoes (produto_id, visitante, dia, criado_em) VALUES (?,?,?,?)",
                                    (pid, f"v{n}_{v}", momento.date().isoformat(), ts))
        con.execute("UPDATE produtos SET visualizacoes = (SELECT COUNT(*) FROM visualizacoes v WHERE v.produto_id = produtos.id)")

        # Um pedido em andamento, a caminho, com trajeto GPS (para ver o rastreio funcionando)
        cid, clat, clng, cend, cref = clientes[0]
        vid = vend[0]
        momento = agora - timedelta(minutes=12)
        ts = momento.strftime("%Y-%m-%d %H:%M:%S")
        abacaxi = next(p for p in prods if p[1].startswith("Abacaxi"))
        ped = con.execute("INSERT INTO pedidos (codigo, compra_codigo, cliente_id, vendedor_id, entregador_id, endereco, referencia, destino_lat, "
                          "destino_lng, origem_lat, origem_lng, entrega_modo, entrega_valor, distancia_km, subtotal, total, status, criado_em, "
                          "pago_em, saiu_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          ("FCDEMOGPS", "CFCDEMOGPS", cid, vid, entregadores[0][0], cend, cref, clat, clng, -3.1386, -60.0236, "moto", 9.40,
                           6.0, 21.0, 30.40, "saiu_entrega", ts, ts, (momento + timedelta(minutes=6)).strftime("%Y-%m-%d %H:%M:%S"))).lastrowid
        con.execute("INSERT INTO itens_pedido (pedido_id, produto_id, nome, preco, quantidade) VALUES (?,?,?,?,?)", (ped, abacaxi[0], abacaxi[1], 7.0, 3))
        con.execute("INSERT INTO pagamentos (pedido_id, vendedor_id, modalidade, bandeira, cartao_final, valor, status, criado_em, confirmado_em) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", (ped, vid, "credito", "Visa", "4242", 30.40, "aprovado", ts, ts))
        for i in range(12):
            t = i / 11
            lat = -3.1386 + (clat + 3.1386) * t + rnd.uniform(-0.0007, 0.0007)
            lng = -60.0236 + (clng + 60.0236) * t * 0.85 + rnd.uniform(-0.0007, 0.0007)
            con.execute("INSERT INTO rastreamento (pedido_id, lat, lng, precisao, criado_em) VALUES (?,?,?,?,?)",
                        (ped, lat, lng, 8, (momento + timedelta(minutes=6, seconds=i * 25)).strftime("%Y-%m-%d %H:%M:%S")))

        # Um pedido pago aguardando preparo (aparece em "Precisa da sua atenção")
        ped2 = con.execute("INSERT INTO pedidos (codigo, compra_codigo, cliente_id, vendedor_id, endereco, referencia, destino_lat, destino_lng, "
                           "origem_lat, origem_lng, entrega_modo, entrega_valor, distancia_km, subtotal, total, status, criado_em, pago_em) "
                           "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           ("FCDEMOPAGO", "CFCDEMOPAGO", clientes[1][0], vid, clientes[1][3], clientes[1][4], clientes[1][1], clientes[1][2],
                            -3.1386, -60.0236, "bicicleta", 4.10, 1.4, 36.0, 40.10, "pago",
                            (agora - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"), (agora - timedelta(minutes=4)).strftime("%Y-%m-%d %H:%M:%S"))).lastrowid
        cupu = next(p for p in prods if p[1].startswith("Cupuaçu"))
        con.execute("INSERT INTO itens_pedido (pedido_id, produto_id, nome, preco, quantidade) VALUES (?,?,?,?,?)", (ped2, cupu[0], cupu[1], 9.0, 4))
        conta = con.execute("SELECT * FROM contas_bancarias WHERE vendedor_id = ?", (vid,)).fetchone()
        con.execute("INSERT INTO pagamentos (pedido_id, vendedor_id, modalidade, valor, status, pix_txid, pix_payload, criado_em, confirmado_em) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", (ped2, vid, "pix", 40.10, "aprovado", "FCDEMOPAGO",
                                                   gerar_payload(conta["pix_chave"], 40.10, conta["titular"], "MANAUS", "FCDEMOPAGO"),
                                                   (agora - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
                                                   (agora - timedelta(minutes=4)).strftime("%Y-%m-%d %H:%M:%S")))
        con.execute("INSERT INTO notificacoes (usuario_id, tipo, titulo, mensagem, link) VALUES (?,?,?,?,?)",
                    (vid, "pagamento", "💰 Pagamento recebido: R$ 40,10", "Pedido #FCDEMOPAGO pago via PIX. Separe os produtos para entrega.",
                     "/vendedor/pedidos/FCDEMOPAGO"))
        con.commit()
        print(f"Banco criado em {Config.DATABASE} com {n + 2} pedidos de exemplo.")
        print("Contas de teste (senha de todas: feira123):")
        print("  Vendedores:   " + ", ".join(v[0] for v in VENDEDORES))
        print("  Clientes:     " + ", ".join(c[0] for c in CLIENTES))
        print("  Entregadores: " + ", ".join(e[0] for e in ENTREGADORES))


if __name__ == "__main__":
    criar(reset="--reset" in sys.argv)

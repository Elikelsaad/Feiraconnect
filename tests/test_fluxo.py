"""
Testes automáticos do fluxo completo. Rode com:   python -m pytest -q
Cada teste usa um banco novo e temporário (os seus dados não são tocados).
"""
import io
import re

import pytest
from PIL import Image

from feiraconnect import create_app, db
from feiraconnect.validacao import cnpj_valido, cpf_valido
from feiraconnect.utils import bandeira_cartao

CPFS = ["52998224725", "11144477735", "39053344705", "15350946056", "71428793860"]


def jpg(larg=1920, alt=1080, cor=(120, 160, 60)):
    buf = io.BytesIO()
    Image.new("RGB", (larg, alt), cor).save(buf, "JPEG")
    buf.seek(0)
    return buf


@pytest.fixture()
def app(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "teste.db"), "UPLOAD_FOLDER": str(tmp_path / "up")})
    with app.app_context():
        con = db.get_db()
        con.execute("INSERT INTO categorias (nome, slug) VALUES ('Frutas', 'frutas')")
        con.commit()
    return app


def csrf(c):
    c.get("/")
    with c.session_transaction() as s:
        return s["csrf"]


def token_atual(c):
    """O token muda ao entrar na conta (proteção contra fixação de sessão)."""
    with c.session_transaction() as s:
        return s["csrf"]


def pessoais(login, cpf, **extra):
    d = {"nome_completo": "Fulano de Tal", "documento": cpf, "nascimento": "1990-05-10", "celular": "(92) 99123-4567",
         "login": login, "senha": "feira123", "senha2": "feira123", "foto": (jpg(600, 600), "eu.jpg")}
    d.update(extra)
    return d


ENDERECO = {"cep": "69005-020", "logradouro": "Rua dos Barés", "numero": "42", "bairro": "Centro", "cidade": "Manaus", "uf": "AM",
            "lat": "-3.1386", "lng": "-60.0236"}


def cadastrar_vendedor(c, login="vend1", cpf=CPFS[0]):
    t = csrf(c)
    r = c.post("/cadastro/vendedor", data={**pessoais(login, cpf), **ENDERECO, "ponto_comercial": "Banca Teste",
                                           "feira": "Feira da Panair", "csrf_token": t}, content_type="multipart/form-data")
    assert r.status_code == 302, r.data[:2000]
    t = token_atual(c)
    r = c.post("/vendedor/conta-bancaria", data={"csrf_token": t, "banco_codigo": "037", "agencia": "1234", "conta": "56789",
                                                  "conta_digito": "0", "conta_tipo": "corrente", "titular": "Fulano de Tal",
                                                  "titular_documento": cpf, "aceita_pix": "on", "aceita_credito": "on",
                                                  "aceita_debito": "on", "bandeira_visa": "on", "bandeira_mastercard": "on",
                                                  "bandeira_elo": "on", "pix_tipo": "email", "pix_chave": "banca@teste.com"})
    assert r.status_code == 302
    return t


def criar_produto(c, t, fotos=1):
    r = c.post("/vendedor/produtos/novo", data={"csrf_token": t, "nome": "Abacaxi", "preco": "7,50", "estoque": "10",
                                                 "unidade": "un", "origem": "Itacoatiara - AM", "categoria_id": "1", "ativo": "on",
                                                 "fotos": [(jpg(), f"f{i}.jpg") for i in range(fotos)],
                                                 "legendas_novas": [f"legenda {i}" for i in range(fotos)]},
               content_type="multipart/form-data")
    assert r.status_code == 302
    return int(re.search(r"/produtos/(\d+)", r.headers["Location"]).group(1))


def cadastrar_cliente(c, login="cli1", cpf=CPFS[1], cartao=True):
    t = csrf(c)
    extra = {"cartao_tipo": "credito", "cartao_numero": "4111 1111 1111 1111", "cartao_titular": "FULANO", "cartao_validade": "12/30"} if cartao else {}
    r = c.post("/cadastro/cliente", data={**pessoais(login, cpf), **ENDERECO, "referencia": "Portão verde", "csrf_token": t, **extra},
               content_type="multipart/form-data")
    assert r.status_code == 302, r.data[:2000]
    return token_atual(c)


# ---------------------------------------------------------------- validações
def test_validadores():
    assert cpf_valido("529.982.247-25") and not cpf_valido("529.982.247-24") and not cpf_valido("11111111111")
    assert cnpj_valido("11.222.333/0001-81") and not cnpj_valido("11.222.333/0001-80")
    assert bandeira_cartao("4111111111111111") == "Visa"
    assert bandeira_cartao("5555555555554444") == "Mastercard"
    assert bandeira_cartao("6362970000457013") == "Elo"
    assert bandeira_cartao("378282246310005") == ""   # Amex não é aceito


def test_cadastro_recusa_dados_invalidos(app):
    c = app.test_client()
    t = csrf(c)
    r = c.post("/cadastro/cliente", data={**pessoais("login_grande_demais", "12345678900"), **ENDERECO, "csrf_token": t},
               content_type="multipart/form-data")
    html = r.data.decode()
    assert r.status_code == 400
    assert "CPF inválido" in html and "no máximo" not in html or "10 caracteres" in html
    r = c.post("/cadastro/entregador", data={**pessoais("ok123", CPFS[2], nascimento="2015-01-01"), "csrf_token": t},
               content_type="multipart/form-data")
    assert "18 anos" in r.data.decode()


# ---------------------------------------------------------------- vendedor
def test_vendedor_fotos_limite_e_resolucao(app):
    c = app.test_client()
    t = cadastrar_vendedor(c)
    pid = criar_produto(c, t, fotos=3)
    with app.app_context():
        imgs = db.imagens_produto(pid)
        assert len(imgs) == 3 and imgs[0]["legenda"] == "legenda 0" and imgs[0]["largura"] == 1920
    # foto pequena demais é recusada
    r = c.post(f"/vendedor/produtos/{pid}", data={"csrf_token": t, "nome": "Abacaxi", "preco": "7.5", "ativo": "on",
                                                   "fotos": [(jpg(640, 480), "pequena.jpg")]}, content_type="multipart/form-data",
               follow_redirects=True)
    assert "HD" in r.data.decode()
    # tenta passar de 10
    c.post(f"/vendedor/produtos/{pid}", data={"csrf_token": t, "nome": "Abacaxi", "preco": "7.5", "ativo": "on",
                                               "fotos": [(jpg(), f"x{i}.jpg") for i in range(9)]}, content_type="multipart/form-data")
    with app.app_context():
        assert len(db.imagens_produto(pid)) == 10
        primeira = db.imagens_produto(pid)[0]["id"]
    # editar legenda e excluir foto
    c.post(f"/vendedor/produtos/{pid}/imagens", data={"csrf_token": t, "acao": "salvar", f"legenda_{primeira}": "Nova legenda"})
    c.post(f"/vendedor/produtos/{pid}/imagens", data={"csrf_token": t, "acao": f"excluir:{primeira}"})
    with app.app_context():
        imgs = db.imagens_produto(pid)
        assert len(imgs) == 9 and all(i["id"] != primeira for i in imgs)


def test_cliente_nao_acessa_painel_do_vendedor(app):
    c = app.test_client()
    cadastrar_cliente(c)
    assert c.get("/vendedor/").status_code == 403
    assert c.get("/vendedor/produtos/novo").status_code == 403


# ---------------------------------------------------------------- compra completa
def test_compra_pix_notifica_vendedor_e_entrega_com_gps(app):
    cv, cc, ce = app.test_client(), app.test_client(), app.test_client()
    tv = cadastrar_vendedor(cv)
    pid = criar_produto(cv, tv)
    # visualização conta
    tc = cadastrar_cliente(cc)
    cc.get(f"/produto/{pid}")
    cc.get(f"/produto/{pid}")
    with app.app_context():
        assert db.obter_produto(pid)["visualizacoes"] == 1
    # cliente avalia
    cc.post(f"/produto/{pid}/avaliar", data={"csrf_token": tc, "nota": "5", "comentario": "Excelente!"})
    # compra com PIX
    cc.post("/carrinho/adicionar", data={"csrf_token": tc, "produto_id": pid, "quantidade": 2})
    vid = None
    with app.app_context():
        vid = db.obter_produto(pid)["vendedor_id"]
    r = cc.post("/checkout", data={"csrf_token": tc, f"entrega_{vid}": "moto", "pagamento": "pix", "endereco": "Rua X, 1", "referencia": "ref"})
    assert r.status_code == 302, r.data[:3000]
    pagina = cc.get(r.headers["Location"]).data.decode()
    assert "000201" in pagina and "br.gov.bcb.pix" in pagina   # PIX copia e cola com o valor
    with app.app_context():
        ped = db.um("SELECT * FROM pedidos")
        assert ped["status"] == "aguardando_pagamento"
        assert db.obter_produto(pid)["estoque"] == 8
    codigo = ped["codigo"]
    # webhook do banco confirma o PIX
    with app.app_context():
        pag = db.um("SELECT * FROM pagamentos")
    r = cc.post("/api/webhook/pix", json={"txid": pag["pix_txid"], "valor": pag["valor"]}, headers={"X-Webhook-Token": "errado"})
    assert r.status_code == 401
    r = cc.post("/api/webhook/pix", json={"txid": pag["pix_txid"], "valor": pag["valor"]},
                headers={"X-Webhook-Token": app.config["PIX_WEBHOOK_TOKEN"]})
    assert r.json["ok"]
    # vendedor recebe o aviso em tempo real
    j = cv.get("/api/notificacoes?desde=0").json
    assert any("Pagamento recebido" in n["titulo"] for n in j["novas"])
    fin = cv.get("/api/vendedor/financeiro?desde=0").json
    assert fin["movimentos"][0]["modalidade"] == "PIX" and fin["movimentos"][0]["status"] == "aprovado"
    # vendedor prepara e chama entregador
    cv.post(f"/vendedor/pedidos/{codigo}", data={"csrf_token": tv, "acao": "em_preparo"})
    cv.post(f"/vendedor/pedidos/{codigo}", data={"csrf_token": tv, "acao": "aguardando_entregador"})
    # entregador aceita, sai e manda GPS
    te = csrf(ce)
    r = ce.post("/cadastro/entregador", data={**pessoais("moto1", CPFS[2]), "veiculo": "moto", "csrf_token": te},
                content_type="multipart/form-data")
    assert r.status_code == 302
    te = token_atual(ce)
    ce.post(f"/entregador/entregas/{codigo}", data={"csrf_token": te, "acao": "aceitar"})
    ce.post(f"/entregador/entregas/{codigo}", data={"csrf_token": te, "acao": "iniciar"})
    r = ce.post(f"/api/pedidos/{codigo}/posicao", json={"lat": -3.12, "lng": -60.02}, headers={"X-CSRF-Token": te})
    assert r.json["ok"]
    # cliente e vendedor veem o trajeto
    assert cc.get(f"/api/pedidos/{codigo}/rastreio").json["pontos"][0]["lat"] == -3.12
    assert cv.get(f"/api/pedidos/{codigo}/rastreio").json["status"] == "saiu_entrega"
    # outro cliente não vê
    outro = app.test_client()
    cadastrar_cliente(outro, "cli2", CPFS[3], cartao=False)
    assert outro.get(f"/api/pedidos/{codigo}/rastreio").status_code == 404
    ce.post(f"/entregador/entregas/{codigo}", data={"csrf_token": te, "acao": "finalizar"})
    with app.app_context():
        assert db.um("SELECT status FROM pedidos")["status"] == "entregue"
    # dashboard em todos os períodos
    for per in ("dia", "mes", "trimestre", "ano"):
        r = cv.get(f"/vendedor/?periodo={per}")
        assert r.status_code == 200 and "Faturamento" in r.data.decode()
    assert "Pedido" in cv.get("/vendedor/financeiro.csv").data.decode("utf-8-sig")


def test_compra_cartao_e_cancelamento_no_prazo(app):
    cv, cc = app.test_client(), app.test_client()
    tv = cadastrar_vendedor(cv)
    pid = criar_produto(cv, tv)
    tc = cadastrar_cliente(cc)
    with app.app_context():
        vid = db.obter_produto(pid)["vendedor_id"]
        cartao = db.um("SELECT id FROM cartoes")["id"]
    cc.post("/carrinho/adicionar", data={"csrf_token": tc, "produto_id": pid, "quantidade": 3})
    r = cc.post("/checkout", data={"csrf_token": tc, f"entrega_{vid}": "retirada", "pagamento": "credito", "cartao_id": cartao,
                                   "cartao_cvv": "123", "parcelas": "2"})
    assert r.status_code == 302
    with app.app_context():
        ped = db.um("SELECT * FROM pedidos")
        assert ped["status"] == "pago"
        assert db.um("SELECT parcelas, bandeira FROM pagamentos")["bandeira"] == "Visa"
    assert any("Pagamento recebido" in n["titulo"] for n in cv.get("/api/notificacoes?desde=0").json["novas"])
    # cancela dentro de 20 min
    cc.post(f"/cliente/pedidos/{ped['codigo']}", data={"csrf_token": tc, "acao": "cancelar", "motivo": "Desisti"})
    with app.app_context():
        assert db.um("SELECT status FROM pedidos")["status"] == "cancelado"
        assert db.um("SELECT status FROM pagamentos")["status"] == "estornado"
        assert db.obter_produto(pid)["estoque"] == 10


def test_cancelamento_fora_do_prazo_e_recusado(app):
    cv, cc = app.test_client(), app.test_client()
    tv = cadastrar_vendedor(cv)
    pid = criar_produto(cv, tv)
    tc = cadastrar_cliente(cc)
    with app.app_context():
        vid = db.obter_produto(pid)["vendedor_id"]
    cc.post("/carrinho/adicionar", data={"csrf_token": tc, "produto_id": pid})
    cc.post("/checkout", data={"csrf_token": tc, f"entrega_{vid}": "moto", "pagamento": "pix", "endereco": "Rua X"})
    with app.app_context():
        con = db.get_db()
        con.execute("UPDATE pedidos SET criado_em = datetime('now','localtime','-25 minutes')")
        con.commit()
        codigo = db.um("SELECT codigo FROM pedidos")["codigo"]
    r = cc.post(f"/cliente/pedidos/{codigo}", data={"csrf_token": tc, "acao": "cancelar"}, follow_redirects=True)
    assert "já passou" in r.data.decode()
    with app.app_context():
        assert db.um("SELECT status FROM pedidos")["status"] == "aguardando_pagamento"


def test_login_bloqueia_apos_5_erros(app):
    c = app.test_client()
    cadastrar_cliente(c)
    c.get("/sair")
    t = csrf(c)
    for _ in range(5):
        c.post("/entrar", data={"csrf_token": t, "login": "cli1", "senha": "errada1"})
    r = c.post("/entrar", data={"csrf_token": t, "login": "cli1", "senha": "feira123"})
    assert r.status_code == 429

"""
Contas: entrar, sair e os três cadastros (vendedor, cliente, entregador).

Regras:
- login de 3 a 10 caracteres e senha de 6 a 10 caracteres (letras e números);
- CPF (cliente e entregador) ou CPF/CNPJ (vendedor) validados pelos dígitos verificadores;
- maiores de 18 anos;
- foto obrigatória;
- 5 tentativas de senha erradas bloqueiam o login por 15 minutos.
"""
import secrets
from functools import wraps

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .. import db
from ..imagens import ErroImagem, salvar_foto_perfil
from ..utils import BANDEIRAS_ACEITAS, bandeira_cartao, luhn_valido
from ..validacao import (ErroValidacao, LOGIN_MAX, SENHA_MAX, obrigatorio,
                         validar_celular, validar_cep, validar_documento,
                         validar_login, validar_nascimento, validar_nome,
                         validar_senha)

bp = Blueprint("auth", __name__)

PAINEL = {"vendedor": "vendedor.painel", "cliente": "cliente.pedidos", "entregador": "entregador.painel"}


# ---------------------------------------------------------------- proteção das rotas
def papel_requerido(*papeis):
    """Só deixa entrar quem está logado com um dos papéis informados."""
    def deco(view):
        @wraps(view)
        def wrapper(*a, **kw):
            if not g.usuario:
                flash("Entre na sua conta para continuar.", "erro")
                return redirect(url_for("auth.entrar", proximo=request.full_path))
            if g.usuario["papel"] not in papeis:
                abort(403)
            return view(*a, **kw)
        return wrapper
    return deco


# ---------------------------------------------------------------- entrar / sair
def _bloqueado(login, ip):
    r = db.um("SELECT COUNT(*) AS n FROM tentativas_login WHERE (login = ? OR ip = ?) AND sucesso = 0 "
              "AND criado_em >= datetime('now','localtime','-15 minutes')", (login, ip))
    return r["n"] >= 5


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    if request.method == "POST":
        login = (request.form.get("login") or "").strip().lower()[:LOGIN_MAX]
        senha = (request.form.get("senha") or "")[:SENHA_MAX]
        ip = request.remote_addr or ""
        if _bloqueado(login, ip):
            flash("Muitas tentativas erradas. Aguarde 15 minutos e tente de novo.", "erro")
            return render_template("auth/entrar.html", login=login), 429
        u = db.um("SELECT * FROM usuarios WHERE login = ?", (login,))
        ok = bool(u and u["ativo"] and check_password_hash(u["senha_hash"], senha))
        db.executar("INSERT INTO tentativas_login (login, ip, sucesso) VALUES (?,?,?)", (login, ip, int(ok)))
        if ok:
            carrinho = session.get("carrinho", {})
            local = session.get("local")
            session.clear()                       # evita fixação de sessão
            session.permanent = True
            session.update(uid=u["id"], csrf=secrets.token_hex(16), carrinho=carrinho)
            if local:
                session["local"] = local
            db.executar("UPDATE usuarios SET ultimo_acesso = datetime('now','localtime') WHERE id = ?", (u["id"],))
            proximo = request.args.get("proximo", "")
            if proximo.startswith("/") and not proximo.startswith("//"):
                return redirect(proximo)
            return redirect(url_for(PAINEL[u["papel"]]))
        flash("Login ou senha incorretos.", "erro")
        return render_template("auth/entrar.html", login=login), 401
    return render_template("auth/entrar.html")


@bp.route("/sair")
def sair():
    carrinho = session.get("carrinho", {})
    session.clear()
    session["carrinho"] = carrinho
    flash("Você saiu da sua conta.", "ok")
    return redirect(url_for("loja.inicio"))


@bp.route("/cadastro")
def escolher_cadastro():
    return render_template("auth/escolher_cadastro.html")


# ---------------------------------------------------------------- cadastro: partes comuns
def _dados_pessoais(f, aceita_cnpj=False):
    erros, d = [], {}
    for campo, func in (
        ("nome_completo", lambda: validar_nome(f.get("nome_completo"))),
        ("documento", lambda: validar_documento(f.get("documento"), aceita_cnpj)),
        ("nascimento", lambda: validar_nascimento(f.get("nascimento", ""))),
        ("celular", lambda: validar_celular(f.get("celular"))),
        ("login", lambda: validar_login(f.get("login"))),
        ("senha", lambda: validar_senha(f.get("senha"), f.get("senha2"))),
    ):
        try:
            d[campo] = func()
        except ErroValidacao as e:
            erros.append(str(e))
    if "login" in d and db.um("SELECT 1 FROM usuarios WHERE login = ?", (d["login"],)):
        erros.append("Este login já está em uso. Escolha outro.")
    return d, erros


def _endereco(f, referencia_obrigatoria=False):
    erros, e = [], {}
    try:
        e["cep"] = validar_cep(f.get("cep"))
    except ErroValidacao as ex:
        erros.append(str(ex))
    for campo, rotulo in (("logradouro", "rua"), ("numero", "número"), ("bairro", "bairro"), ("cidade", "cidade")):
        try:
            e[campo] = obrigatorio(f.get(campo), rotulo, 120)
        except ErroValidacao as ex:
            erros.append(str(ex))
    e["uf"] = (f.get("uf") or "AM").strip().upper()[:2]
    e["complemento"] = (f.get("complemento") or "").strip()[:80]
    e["referencia"] = (f.get("referencia") or "").strip()[:160]
    if referencia_obrigatoria and not e["referencia"]:
        erros.append("Informe um ponto de referência para facilitar a entrega.")
    for k in ("lat", "lng"):
        try:
            e[k] = float(f.get(k)) if f.get(k) else None
        except ValueError:
            e[k] = None
    return e, erros


def _foto(erros):
    try:
        return salvar_foto_perfil(request.files.get("foto"))
    except ErroImagem as ex:
        erros.append(f"Foto: {ex}")
        return ""


def _criar_usuario(papel, d, foto):
    tipo, doc = d["documento"]
    if db.um("SELECT 1 FROM usuarios WHERE papel = ? AND documento = ?", (papel, doc)):
        raise ErroValidacao(f"Já existe uma conta de {papel} com este {tipo}.")
    return db.get_db().execute(
        "INSERT INTO usuarios (papel, login, senha_hash, nome_completo, documento_tipo, documento, nascimento, celular, foto) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (papel, d["login"], generate_password_hash(d["senha"]), d["nome_completo"], tipo, doc, d["nascimento"],
         d["celular"], foto)).lastrowid


def _salvar_endereco(con, uid, e):
    con.execute("INSERT INTO enderecos (usuario_id, cep, logradouro, numero, complemento, bairro, cidade, uf, referencia, lat, lng) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (uid, e["cep"], e["logradouro"], e["numero"], e["complemento"], e["bairro"], e["cidade"], e["uf"],
                 e["referencia"], e["lat"], e["lng"]))


def validar_cartao(f, prefixo=""):
    """Valida um cartão digitado. Retorna dict pronto para gravar (sem número completo nem CVV)."""
    numero = f.get(prefixo + "cartao_numero", "")
    digitos = "".join(c for c in numero if c.isdigit())
    tipo = f.get(prefixo + "cartao_tipo", "credito")
    titular = (f.get(prefixo + "cartao_titular") or "").strip().upper()[:60]
    validade = (f.get(prefixo + "cartao_validade") or "").strip()
    erros = []
    bandeira = bandeira_cartao(digitos)
    if not luhn_valido(digitos):
        erros.append("Número do cartão inválido.")
    elif bandeira not in BANDEIRAS_ACEITAS:
        erros.append("Aceitamos apenas cartões Visa, Mastercard e Elo.")
    if tipo not in ("credito", "debito"):
        erros.append("Escolha crédito ou débito.")
    if not titular:
        erros.append("Informe o nome impresso no cartão.")
    try:
        from datetime import date
        mes, ano = validade.split("/")
        mes, ano = int(mes), 2000 + int(ano[-2:])
        if not 1 <= mes <= 12 or (ano, mes) < (date.today().year, date.today().month):
            raise ValueError
    except ValueError:
        erros.append("Validade do cartão inválida ou vencida (use MM/AA).")
    if erros:
        raise ErroValidacao(" ".join(erros))
    return {"tipo": tipo, "bandeira": bandeira, "final": digitos[-4:], "titular": titular,
            "validade": f"{mes:02d}/{str(ano)[-2:]}", "token": "tok_" + secrets.token_hex(12)}


def gravar_cartao(con, cliente_id, c):
    return con.execute("INSERT INTO cartoes (cliente_id, tipo, bandeira, final, titular, validade, token) "
                       "VALUES (?,?,?,?,?,?,?)",
                       (cliente_id, c["tipo"], c["bandeira"], c["final"], c["titular"], c["validade"], c["token"])).lastrowid


def _entrar_apos_cadastro(uid, papel, nome):
    carrinho = session.get("carrinho", {})
    local = session.get("local")
    session.clear()
    session.permanent = True
    session.update(uid=uid, csrf=secrets.token_hex(16), carrinho=carrinho)
    if local:
        session["local"] = local
    flash(f"Bem-vindo(a), {nome.split()[0]}! Sua conta de {papel} foi criada.", "ok")


# ---------------------------------------------------------------- cadastro: vendedor
@bp.route("/cadastro/vendedor", methods=["GET", "POST"])
def cadastro_vendedor():
    if request.method == "POST":
        f = request.form
        d, erros = _dados_pessoais(f, aceita_cnpj=True)
        e, erros_end = _endereco(f)
        erros += erros_end
        ponto = (f.get("ponto_comercial") or "").strip()[:80]
        if not ponto:
            erros.append("Informe o nome do ponto comercial ou da banca.")
        feira = (f.get("feira") or "").strip()[:80]
        foto = "" if erros else _foto(erros)
        if not erros:
            try:
                con = db.get_db()
                uid = _criar_usuario("vendedor", d, foto)
                _salvar_endereco(con, uid, e)
                con.execute("INSERT INTO vendedores (usuario_id, ponto_comercial, feira, descricao, banca_lat, banca_lng) "
                            "VALUES (?,?,?,?,?,?)", (uid, ponto, feira, (f.get("descricao") or "")[:500], e["lat"], e["lng"]))
                con.commit()
                _entrar_apos_cadastro(uid, "vendedor", d["nome_completo"])
                flash("Agora cadastre a conta bancária para receber os pagamentos.", "ok")
                return redirect(url_for("vendedor.conta_bancaria"))
            except ErroValidacao as ex:
                db.get_db().rollback()
                erros.append(str(ex))
        for x in erros:
            flash(x, "erro")
        return render_template("auth/cadastro_vendedor.html", f=f), 400
    return render_template("auth/cadastro_vendedor.html", f={})


# ---------------------------------------------------------------- cadastro: cliente
@bp.route("/cadastro/cliente", methods=["GET", "POST"])
def cadastro_cliente():
    if request.method == "POST":
        f = request.form
        d, erros = _dados_pessoais(f, aceita_cnpj=False)
        e, erros_end = _endereco(f, referencia_obrigatoria=True)
        erros += erros_end
        cartao = None
        if f.get("cartao_numero"):
            try:
                cartao = validar_cartao(f)
            except ErroValidacao as ex:
                erros.append(f"Cartão: {ex}")
        foto = "" if erros else _foto(erros)
        if not erros:
            try:
                con = db.get_db()
                uid = _criar_usuario("cliente", d, foto)
                _salvar_endereco(con, uid, e)
                if cartao:
                    gravar_cartao(con, uid, cartao)
                con.commit()
                _entrar_apos_cadastro(uid, "cliente", d["nome_completo"])
                proximo = request.args.get("proximo", "")
                return redirect(proximo if proximo.startswith("/") and not proximo.startswith("//")
                                else url_for("loja.inicio"))
            except ErroValidacao as ex:
                db.get_db().rollback()
                erros.append(str(ex))
        for x in erros:
            flash(x, "erro")
        return render_template("auth/cadastro_cliente.html", f=f), 400
    return render_template("auth/cadastro_cliente.html", f={})


# ---------------------------------------------------------------- cadastro: entregador
@bp.route("/cadastro/entregador", methods=["GET", "POST"])
def cadastro_entregador():
    if request.method == "POST":
        f = request.form
        d, erros = _dados_pessoais(f, aceita_cnpj=False)
        veiculo = f.get("veiculo", "moto")
        if veiculo not in ("moto", "carro", "bicicleta"):
            erros.append("Escolha o veículo de entrega.")
        foto = "" if erros else _foto(erros)
        if not erros:
            try:
                con = db.get_db()
                uid = _criar_usuario("entregador", d, foto)
                con.execute("INSERT INTO entregadores (usuario_id, veiculo, placa) VALUES (?,?,?)",
                            (uid, veiculo, (f.get("placa") or "").strip().upper()[:8]))
                con.commit()
                _entrar_apos_cadastro(uid, "entregador", d["nome_completo"])
                return redirect(url_for("entregador.painel"))
            except ErroValidacao as ex:
                db.get_db().rollback()
                erros.append(str(ex))
        for x in erros:
            flash(x, "erro")
        return render_template("auth/cadastro_entregador.html", f=f), 400
    return render_template("auth/cadastro_entregador.html", f={})

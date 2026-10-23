"""
FeiraConnect — plataforma de feiras livres (Python + Flask + SQL)

Organização (cada parte pode ser atualizada sem mexer nas outras):
    blueprints/loja.py        vitrine, produto, carrinho, checkout
    blueprints/auth.py        entrar, sair e cadastro de vendedor, cliente e entregador
    blueprints/vendedor.py    painel do vendedor (produtos, fotos, conta bancária, pedidos, financeiro, dashboard)
    blueprints/cliente.py     área do cliente (perfil, cartões, pedidos, cancelamento, avaliações)
    blueprints/entregador.py  área do entregador (entregas e GPS)
    blueprints/api.py         dados em tempo real (notificações, rastreio, financeiro, webhook PIX)
    sql/migrations            estrutura do banco, versionada
    sql/dashboard             consultas SQL do dashboard de vendas
"""
import os
import secrets
from datetime import datetime

from flask import Flask, abort, g, render_template, request, session

from . import db
from .utils import (MODALIDADES, MODOS_ENTREGA, NOTAS, STATUS_PEDIDO, brl,
                    data_br, desconto_pct, partes_preco)

__version__ = "2.0.0"


def create_app(config_extra=None):
    app = Flask(__name__)
    app.config.from_object("config.Config")
    if config_extra:
        app.config.update(config_extra)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.aplicar_migracoes(app.config["DATABASE"])
    app.teardown_appcontext(db.fechar_db)

    app.jinja_env.filters.update(brl=brl, data_br=data_br)
    app.jinja_env.globals.update(partes_preco=partes_preco, desconto_pct=desconto_pct, STATUS_PEDIDO=STATUS_PEDIDO,
                                 MODOS_ENTREGA=MODOS_ENTREGA, MODALIDADES=MODALIDADES, NOTAS=NOTAS,
                                 VERSAO=__version__)

    from .blueprints import api, auth, cliente, entregador, loja, vendedor
    for bp in (loja.bp, auth.bp, vendedor.bp, cliente.bp, entregador.bp, api.bp):
        app.register_blueprint(bp)

    @app.before_request
    def antes():
        # Proteção CSRF em todos os formulários e chamadas que alteram dados
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        if request.method == "POST" and not request.path.startswith("/api/webhook/"):
            token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if token != session["csrf"]:
                abort(400, "Formulário expirado. Recarregue a página e tente novamente.")
        # Usuário logado
        g.usuario = None
        if session.get("uid"):
            g.usuario = db.um("SELECT * FROM usuarios WHERE id = ? AND ativo = 1", (session["uid"],))
            if not g.usuario:
                session.pop("uid", None)

    @app.context_processor
    def contexto():
        from .servicos import nao_lidas
        carrinho = session.get("carrinho", {})
        u = g.get("usuario")
        return {
            "cfg": db.get_config(),
            "categorias_menu": db.listar_categorias(),
            "qtd_carrinho": sum(carrinho.values()),
            "local": session.get("local"),
            "csrf_token": session.get("csrf", ""),
            "usuario": u,
            "notif_nao_lidas": nao_lidas(u["id"]) if u else 0,
            "ano": datetime.now().year,
        }

    @app.after_request
    def cabecalhos(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp

    @app.errorhandler(403)
    def proibido(e):
        return render_template("erro.html", titulo="Acesso não permitido",
                               mensagem="Esta área é de outro tipo de conta."), 403

    @app.errorhandler(404)
    def nao_encontrado(_e):
        return render_template("erro.html", titulo="Página não encontrada",
                               mensagem="O produto ou a página que você procura não existe mais."), 404

    @app.errorhandler(400)
    def invalido(e):
        return render_template("erro.html", titulo="Algo deu errado", mensagem=e.description), 400

    @app.errorhandler(413)
    def grande_demais(_e):
        return render_template("erro.html", titulo="Arquivo grande demais",
                               mensagem="Cada envio pode ter até 120 MB no total. Envie menos fotos por vez."), 413

    return app

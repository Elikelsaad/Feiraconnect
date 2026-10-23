"""
Banco de dados (SQLite) — conexão, migrações versionadas e consultas SQL em arquivo.

- Migrações: cada arquivo em sql/migrations/NNN_nome.sql roda uma única vez,
  em ordem, e fica registrado na tabela schema_migrations. Para atualizar o
  banco no futuro (novo campo, nova tabela) basta criar o próximo arquivo.
- Consultas do dashboard ficam em sql/dashboard/*.sql e são carregadas por nome
  com `consulta_sql("kpis")`, para que possam ser lidas e ajustadas por quem
  conhece SQL sem mexer no Python.
"""
import os
import sqlite3
from functools import lru_cache

from flask import current_app, g

PASTA_SQL = os.path.join(os.path.dirname(__file__), "sql")

CONFIG_PADRAO = {
    "loja_nome": "FeiraConnect",
    "loja_slogan": "Da feira livre para a sua casa",
    "parcelas_max": "6",
    "parcela_minima": "10",
    "frete_moto_base": "5.00", "frete_moto_km": "1.20", "frete_moto_vel": "30",
    "frete_carro_base": "8.00", "frete_carro_km": "1.80", "frete_carro_vel": "22",
    "frete_bicicleta_base": "3.00", "frete_bicicleta_km": "0.90", "frete_bicicleta_vel": "12",
    "frete_bicicleta_raio": "6",
    "frete_gratis_acima": "150.00",
    "cancelamento_minutos": "20",
    "aviso_promocao": "Promoções do dia: até 40% OFF em frutas regionais. Sobras de fim de feira a partir das 15h!",
}


def conectar(caminho):
    con = sqlite3.connect(caminho, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")   # leituras e escritas simultâneas (tempo real)
    return con


def get_db():
    if "db" not in g:
        g.db = conectar(current_app.config["DATABASE"])
    return g.db


def fechar_db(_erro=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def aplicar_migracoes(caminho):
    """Aplica as migrações pendentes. Retorna a lista das que foram aplicadas agora."""
    con = conectar(caminho)
    con.execute("CREATE TABLE IF NOT EXISTS schema_migrations (versao TEXT PRIMARY KEY, aplicada_em TEXT "
                "NOT NULL DEFAULT (datetime('now','localtime')))")
    feitas = {r[0] for r in con.execute("SELECT versao FROM schema_migrations")}
    pasta = os.path.join(PASTA_SQL, "migrations")
    novas = []
    for nome in sorted(os.listdir(pasta)):
        if not nome.endswith(".sql") or nome in feitas:
            continue
        with open(os.path.join(pasta, nome), encoding="utf-8") as f:
            script = f.read()
        try:
            con.executescript("BEGIN;\n" + script + "\nCOMMIT;")
        except sqlite3.Error:
            con.rollback()
            con.close()
            raise
        con.execute("INSERT INTO schema_migrations (versao) VALUES (?)", (nome,))
        con.commit()
        novas.append(nome)
    for chave, valor in CONFIG_PADRAO.items():
        con.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)", (chave, valor))
    con.commit()
    con.close()
    return novas


@lru_cache(maxsize=None)
def consulta_sql(nome):
    """Lê sql/dashboard/<nome>.sql (com cache)."""
    with open(os.path.join(PASTA_SQL, "dashboard", f"{nome}.sql"), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- atalhos
def um(sql, params=()):
    return get_db().execute(sql, params).fetchone()


def todos(sql, params=()):
    return get_db().execute(sql, params).fetchall()


def executar(sql, params=()):
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur.lastrowid


def get_config():
    cfg = dict(CONFIG_PADRAO)
    cfg.update({r["chave"]: r["valor"] for r in todos("SELECT chave, valor FROM configuracoes")})
    return cfg


# ---------------------------------------------------------------- catálogo (consultas da loja)
PRODUTO_SELECT = """
SELECT p.*,
       c.nome AS categoria_nome, c.slug AS categoria_slug,
       u.nome_completo AS vendedor_nome, u.foto AS vendedor_foto,
       v.ponto_comercial AS vendedor_banca, v.feira AS vendedor_feira,
       e.logradouro || ', ' || e.numero || ' - ' || e.bairro AS vendedor_endereco,
       e.cidade || ' - ' || e.uf AS vendedor_cidade,
       COALESCE(v.banca_lat, e.lat) AS vendedor_lat, COALESCE(v.banca_lng, e.lng) AS vendedor_lng,
       (SELECT i.miniatura FROM produto_imagens i WHERE i.produto_id = p.id ORDER BY i.ordem, i.id LIMIT 1) AS capa,
       (SELECT COUNT(*) FROM produto_imagens i WHERE i.produto_id = p.id) AS total_imagens,
       COALESCE((SELECT ROUND(AVG(a.nota), 1) FROM avaliacoes a WHERE a.produto_id = p.id), 0) AS nota_media,
       (SELECT COUNT(*) FROM avaliacoes a WHERE a.produto_id = p.id) AS total_avaliacoes
FROM produtos p
JOIN usuarios u   ON u.id = p.vendedor_id
JOIN vendedores v ON v.usuario_id = p.vendedor_id
LEFT JOIN enderecos e  ON e.usuario_id = p.vendedor_id
LEFT JOIN categorias c ON c.id = p.categoria_id
"""

LOJA_VISIVEL = "p.ativo = 1 AND u.ativo = 1"


def listar_produtos(where=LOJA_VISIVEL, params=(), ordem="p.id DESC", limite=None):
    sql = f"{PRODUTO_SELECT} WHERE {where} ORDER BY {ordem}"
    if limite:
        sql += f" LIMIT {int(limite)}"
    return todos(sql, params)


def obter_produto(produto_id):
    return um(f"{PRODUTO_SELECT} WHERE p.id = ?", (produto_id,))


def imagens_produto(produto_id):
    return todos("SELECT * FROM produto_imagens WHERE produto_id = ? ORDER BY ordem, id", (produto_id,))


def listar_categorias():
    return todos("SELECT c.*, (SELECT COUNT(*) FROM produtos p WHERE p.categoria_id = c.id AND p.ativo = 1) AS total "
                 "FROM categorias c ORDER BY c.nome")


VENDEDOR_SELECT = """
SELECT u.id, u.nome_completo AS nome, u.foto, u.celular, u.criado_em, v.ponto_comercial AS banca, v.feira, v.descricao,
       e.logradouro || ', ' || e.numero || ' - ' || e.bairro AS endereco, e.cidade || ' - ' || e.uf AS cidade,
       COALESCE(v.banca_lat, e.lat) AS lat, COALESCE(v.banca_lng, e.lng) AS lng,
       COALESCE((SELECT ROUND(AVG(a.nota),1) FROM avaliacoes a JOIN produtos p ON p.id = a.produto_id
                 WHERE p.vendedor_id = u.id), 0) AS nota_media,
       (SELECT COALESCE(SUM(p.vendidos),0) FROM produtos p WHERE p.vendedor_id = u.id) AS total_vendidos
FROM usuarios u JOIN vendedores v ON v.usuario_id = u.id LEFT JOIN enderecos e ON e.usuario_id = u.id
WHERE u.ativo = 1
"""


def listar_vendedores():
    return todos(VENDEDOR_SELECT + " ORDER BY v.ponto_comercial")


def obter_vendedor_publico(vendedor_id):
    return um(VENDEDOR_SELECT + " AND u.id = ?", (vendedor_id,))

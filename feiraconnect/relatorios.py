"""
Dashboard de vendas do vendedor: monta os períodos (dia, mês, trimestre, ano)
e executa as consultas SQL de sql/dashboard/.
"""
from datetime import date, datetime, timedelta

from . import db

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
                "outubro", "novembro", "dezembro"]
PERIODOS = {"dia": "Dia", "mes": "Mês", "trimestre": "Trimestre", "ano": "Ano"}


def _somar_meses(d, n):
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def intervalo(periodo, ref):
    """Retorna (inicio, fim, rotulo, formato_sql, grupos[(chave, rótulo)])."""
    if periodo == "dia":
        ini = ref
        fim = ref + timedelta(days=1)
        rot = ref.strftime("%d/%m/%Y")
        grupos = [(f"{h:02d}", f"{h}h") for h in range(5, 23)]
        fmt = "%H"
    elif periodo == "mes":
        ini = ref.replace(day=1)
        fim = _somar_meses(ini, 1)
        rot = f"{MESES_LONGOS[ini.month - 1].capitalize()} de {ini.year}"
        grupos = [((ini + timedelta(days=i)).isoformat(), str(i + 1)) for i in range((fim - ini).days)]
        fmt = "%Y-%m-%d"
    elif periodo == "trimestre":
        tri = (ref.month - 1) // 3
        ini = date(ref.year, tri * 3 + 1, 1)
        fim = _somar_meses(ini, 3)
        rot = f"{tri + 1}º trimestre de {ini.year}"
        grupos, d = [], ini
        while d < fim:
            chave = d.strftime("%Y-%W")
            if not grupos or grupos[-1][0] != chave:
                grupos.append((chave, f"{d.day:02d}/{MESES[d.month - 1]}"))
            d += timedelta(days=1)
        fmt = "%Y-%W"
    else:  # ano
        ini = date(ref.year, 1, 1)
        fim = date(ref.year + 1, 1, 1)
        rot = str(ref.year)
        grupos = [(f"{ref.year}-{m:02d}", MESES[m - 1]) for m in range(1, 13)]
        fmt = "%Y-%m"
    return ini, fim, rot, fmt, grupos


def anterior(periodo, ref):
    if periodo == "dia":
        return ref - timedelta(days=1)
    if periodo == "mes":
        return _somar_meses(ref.replace(day=1), -1)
    if periodo == "trimestre":
        return _somar_meses(ref.replace(day=1), -3)
    return date(ref.year - 1, 1, 1)


def proximo(periodo, ref):
    if periodo == "dia":
        return ref + timedelta(days=1)
    if periodo == "mes":
        return _somar_meses(ref.replace(day=1), 1)
    if periodo == "trimestre":
        return _somar_meses(ref.replace(day=1), 3)
    return date(ref.year + 1, 1, 1)


def _params(vendedor_id, ini, fim, **extra):
    return {"vendedor": vendedor_id, "inicio": f"{ini.isoformat()} 00:00:00", "fim": f"{fim.isoformat()} 00:00:00", **extra}


def variacao(atual, antes):
    if not antes:
        return None if not atual else 100.0
    return round((atual - antes) / antes * 100, 1)


def dashboard(vendedor_id, periodo="mes", ref=None):
    periodo = periodo if periodo in PERIODOS else "mes"
    ref = ref or date.today()
    ini, fim, rotulo, fmt, grupos = intervalo(periodo, ref)
    p = _params(vendedor_id, ini, fim)

    kpis = dict(db.um(db.consulta_sql("kpis"), p))
    kpis.update(dict(db.um(db.consulta_sql("itens_vendidos"), p)))
    kpis.update(dict(db.um(db.consulta_sql("visualizacoes"), p)))
    kpis["conversao"] = round(kpis["pedidos_pagos"] / kpis["visitantes"] * 100, 1) if kpis["visitantes"] else 0

    ref_ant = anterior(periodo, ref)
    ini_a, fim_a, rot_a, _, _ = intervalo(periodo, ref_ant)
    kpis_ant = dict(db.um(db.consulta_sql("kpis"), _params(vendedor_id, ini_a, fim_a)))

    serie_db = {r["grupo"]: r for r in db.todos(db.consulta_sql("serie_vendas"), dict(p, formato=fmt))}
    serie = [{"rotulo": rot, "valor": serie_db[ch]["valor"] if ch in serie_db else 0,
              "pedidos": serie_db[ch]["pedidos"] if ch in serie_db else 0} for ch, rot in grupos]
    if periodo == "dia":   # inclui horas fora do intervalo padrão, se houver vendas
        extras = [k for k in serie_db if k not in dict(grupos)]
        for k in sorted(extras):
            serie.append({"rotulo": f"{int(k)}h", "valor": serie_db[k]["valor"], "pedidos": serie_db[k]["pedidos"]})

    return {
        "periodo": periodo, "rotulo": rotulo, "ref": ref, "rotulo_anterior": rot_a,
        "ref_anterior": ref_ant, "ref_proximo": proximo(periodo, ref), "pode_avancar": proximo(periodo, ref) <= date.today(),
        "kpis": kpis, "kpis_anterior": kpis_ant,
        "var_faturamento": variacao(kpis["faturamento"], kpis_ant["faturamento"]),
        "var_pedidos": variacao(kpis["pedidos_pagos"], kpis_ant["pedidos_pagos"]),
        "serie": serie,
        "modalidades": [dict(r) for r in db.todos(db.consulta_sql("por_modalidade"), p)],
        "top": [dict(r) for r in db.todos(db.consulta_sql("top_produtos"), p)],
        "inicio": ini, "fim": fim,
    }


def movimentacao(vendedor_id, ini, fim, limite=500):
    return db.todos(db.consulta_sql("movimentacao"), _params(vendedor_id, ini, fim, limite=limite))


def ler_data(texto):
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return date.today()

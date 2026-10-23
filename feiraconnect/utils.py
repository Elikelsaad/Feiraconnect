"""
Funções auxiliares: dinheiro, distância GPS, cálculo de frete e validação de cartão.
"""
import math
import re
import secrets


# ---------------------------------------------------------------- dinheiro
def brl(valor):
    """1234.5 -> 'R$ 1.234,50'"""
    valor = float(valor or 0)
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def partes_preco(valor):
    """Separa reais e centavos para exibir no estilo marketplace: R$ 18⁰⁰"""
    valor = float(valor or 0)
    reais = int(valor)
    centavos = int(round((valor - reais) * 100))
    if centavos == 100:
        reais, centavos = reais + 1, 0
    return f"{reais:,}".replace(",", "."), f"{centavos:02d}"


def desconto_pct(produto):
    if produto["preco_original"] and produto["preco_original"] > produto["preco"]:
        return int(round((1 - produto["preco"] / produto["preco_original"]) * 100))
    return 0


# ---------------------------------------------------------------- GPS / distância
def haversine_km(lat1, lng1, lat2, lng2):
    """Distância em linha reta entre duas coordenadas (km)."""
    if None in (lat1, lng1, lat2, lng2):
        return None
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def distancia_rota_km(lat1, lng1, lat2, lng2):
    """Estimativa da distância pelas ruas (linha reta × 1,3)."""
    d = haversine_km(lat1, lng1, lat2, lng2)
    return None if d is None else round(max(d * 1.3, 0.5), 1)


# ---------------------------------------------------------------- frete
MODOS_ENTREGA = {
    "moto": {"nome": "Moto", "icone": "moto", "descricao": "Rápida, ideal para pedidos pequenos e médios"},
    "carro": {"nome": "Carro", "icone": "carro", "descricao": "Para compras grandes, caixas e peixes"},
    "bicicleta": {"nome": "Bicicleta", "icone": "bike", "descricao": "Entrega sustentável para quem está perto"},
    "retirada": {"nome": "Retirar na banca", "icone": "banca", "descricao": "Busque na feira, sem custo"},
}


def calcular_fretes(distancia_km, cfg, subtotal=0):
    """Retorna uma lista com preço e prazo de cada modalidade de entrega."""
    d = distancia_km or 0
    opcoes = []
    for modo in ("moto", "carro", "bicicleta"):
        base = float(cfg[f"frete_{modo}_base"])
        por_km = float(cfg[f"frete_{modo}_km"])
        vel = float(cfg[f"frete_{modo}_vel"])
        valor = round(base + por_km * d, 2)
        minutos = int(15 + (d / vel) * 60)  # 15 min de separação na banca
        disponivel = True
        aviso = ""
        if modo == "bicicleta" and d > float(cfg["frete_bicicleta_raio"]):
            disponivel = False
            aviso = f"Disponível até {cfg['frete_bicicleta_raio']} km"
        if modo == "moto" and subtotal >= float(cfg["frete_gratis_acima"]):
            valor = 0.0
        opcoes.append({
            "modo": modo, **MODOS_ENTREGA[modo], "valor": valor,
            "minutos": minutos, "prazo": _prazo(minutos), "disponivel": disponivel, "aviso": aviso,
        })
    opcoes.append({"modo": "retirada", **MODOS_ENTREGA["retirada"], "valor": 0.0, "minutos": 20,
                   "prazo": "Pronto em ~20 min", "disponivel": True, "aviso": ""})
    return opcoes


def _prazo(minutos):
    if minutos < 60:
        return f"Chega em ~{minutos} min"
    h, m = divmod(minutos, 60)
    return f"Chega em ~{h}h{m:02d}"


# ---------------------------------------------------------------- cartão (simulação)
def luhn_valido(numero):
    digitos = [int(c) for c in re.sub(r"\D", "", numero)]
    if len(digitos) < 13 or len(digitos) > 19:
        return False
    soma = 0
    for i, d in enumerate(reversed(digitos)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        soma += d
    return soma % 10 == 0


BANDEIRAS_ACEITAS = ("Visa", "Mastercard", "Elo")


def bandeira_cartao(numero):
    """Identifica a bandeira. A plataforma aceita apenas Visa, Mastercard e Elo."""
    n = re.sub(r"\D", "", numero)
    if re.match(r"^(401178|401179|431274|438935|451416|457393|457631|457632|504175|506699|5067[0-7]\d|"
                r"509\d{3}|627780|636297|636368|650[0-9]{3}|6516[5-7]\d|6550[0-5]\d)", n):
        return "Elo"
    if n.startswith("4"):
        return "Visa"
    if re.match(r"^(5[1-5]|2(2[2-9]|[3-6]\d|7[01]|720))", n):
        return "Mastercard"
    return ""


def gerar_codigo(prefixo="FC"):
    return prefixo + secrets.token_hex(4).upper()


STATUS_PEDIDO = {
    "aguardando_pagamento": "Aguardando pagamento",
    "pago": "Pagamento aprovado",
    "em_preparo": "Separando na banca",
    "aguardando_entregador": "Aguardando entregador",
    "saiu_entrega": "A caminho",
    "entregue": "Entregue",
    "cancelado": "Cancelado",
}

MODALIDADES = {"credito": "Cartão de crédito", "debito": "Cartão de débito", "pix": "PIX"}

NOTAS = {1: "Péssimo", 2: "Ruim", 3: "Regular", 4: "Bom", 5: "Excelente"}


def agora():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def data_br(texto, com_hora=True):
    """'2026-10-20 18:40:12' -> '20/10/2026 18:40'"""
    if not texto:
        return ""
    d, _, h = str(texto).partition(" ")
    partes = d.split("-")
    if len(partes) != 3:
        return texto
    saida = f"{partes[2]}/{partes[1]}/{partes[0]}"
    return f"{saida} {h[:5]}" if com_hora and h else saida

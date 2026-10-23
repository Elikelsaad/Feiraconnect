"""
Geração do PIX "Copia e Cola" (BR Code / padrão EMV do Banco Central) e do QR Code.

O QR gerado aqui é um PIX ESTÁTICO com o valor do pedido já preenchido.
Basta cadastrar uma chave PIX real em Admin > Configurações para que o
cliente consiga pagar pelo app do banco. A confirmação do pagamento é feita
pelo administrador (Admin > Pedidos > "Confirmar pagamento").

Para confirmação automática, integre um PSP (Mercado Pago, PagSeguro,
Gerencianet/Efí, banco próprio) e troque `gerar_payload` pela cobrança dinâmica
do provedor (campo 26 com URL "pix.bcb.gov.br/...").
"""
import base64
import io
import re
import unicodedata

import qrcode


def _campo(id_, valor):
    return f"{id_}{len(valor):02d}{valor}"


def _limpar(texto, limite):
    """Remove acentos e caracteres não permitidos; corta no tamanho máximo do campo."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^A-Za-z0-9 .@\-_]", "", texto).strip().upper()
    return texto[:limite] or "NA"


def _crc16(payload):
    """CRC16-CCITT (polinômio 0x1021, valor inicial 0xFFFF), exigido no campo 63."""
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def gerar_payload(chave, valor, recebedor, cidade, txid="***"):
    """Monta o texto do PIX Copia e Cola com o valor informado."""
    txid = re.sub(r"[^A-Za-z0-9]", "", txid)[:25] or "***"
    conta = _campo("00", "br.gov.bcb.pix") + _campo("01", chave.strip())
    payload = (
        _campo("00", "01")
        + _campo("26", conta)
        + _campo("52", "0000")
        + _campo("53", "986")                 # 986 = Real brasileiro
        + _campo("54", f"{valor:.2f}")
        + _campo("58", "BR")
        + _campo("59", _limpar(recebedor, 25))
        + _campo("60", _limpar(cidade, 15))
        + _campo("62", _campo("05", txid))
        + "6304"
    )
    return payload + _crc16(payload)


def qrcode_base64(payload):
    """Retorna o QR Code em PNG codificado em base64 (pronto para <img src="data:...">)."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1F3A1F", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()

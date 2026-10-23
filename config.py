"""
Configurações do FeiraConnect. Tudo pode ser trocado por variáveis de ambiente no servidor.
"""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # EM PRODUÇÃO defina SECRET_KEY com um valor longo e aleatório
    SECRET_KEY = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao")
    DATABASE = os.environ.get("DATABASE", os.path.join(BASE_DIR, "feiraconnect.db"))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "feiraconnect", "static", "uploads")

    # 10 fotos 4K por envio cabem com folga
    MAX_CONTENT_LENGTH = 120 * 1024 * 1024

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("HTTPS", "0") == "1"   # ative quando o site estiver em HTTPS
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12                      # 12 horas logado

    # Ponto padrão do mapa quando o cliente não liberou o GPS (Centro de Manaus)
    LAT_PADRAO = -3.1316
    LNG_PADRAO = -60.0233
    ESTOQUE_BAIXO = 5

    # MODO_TESTE mostra o botão "Simular pagamento PIX" e aprova cartões sem gateway.
    # Desligue (MODO_TESTE=0) ao integrar um gateway de pagamento real.
    MODO_TESTE = os.environ.get("MODO_TESTE", "1") == "1"

    # Token que o provedor de pagamento (PSP) usa para avisar que um PIX foi pago
    PIX_WEBHOOK_TOKEN = os.environ.get("PIX_WEBHOOK_TOKEN", "troque-este-token")

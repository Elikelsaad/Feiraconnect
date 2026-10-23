"""
Tratamento das fotos enviadas (produtos e perfis).

Fotos de produto:
  - até 10 por produto;
  - resolução mínima HD (1280 × 720) e preservação de até 4K (3840 px no maior lado);
  - gera uma miniatura leve (800 px) para as listas, deixando o site rápido;
  - corrige a rotação de fotos de celular (EXIF) e remove metadados como a localização GPS.
Fotos de perfil: recorte quadrado de 512 px.
"""
import os
import uuid

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

try:  # fotos HEIC do iPhone (opcional: pip install pillow-heif)
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

Image.MAX_IMAGE_PIXELS = 60_000_000   # protege contra imagens gigantes maliciosas

MAX_IMAGENS_PRODUTO = 10
HD_MIN = (1280, 720)
LADO_MAX_4K = 3840
LADO_MINIATURA = 800
LADO_PERFIL = 512
EXTENSOES = {"jpg", "jpeg", "png", "webp", "heic", "heif"}


class ErroImagem(ValueError):
    pass


def _abrir(arquivo):
    if not arquivo or not arquivo.filename:
        raise ErroImagem("Nenhuma imagem enviada.")
    ext = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
    if ext not in EXTENSOES:
        raise ErroImagem(f"“{arquivo.filename}”: formato não aceito. Use JPG, PNG ou WEBP.")
    try:
        img = Image.open(arquivo.stream)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ErroImagem(f"“{arquivo.filename}” não é uma imagem válida.")
    img = ImageOps.exif_transpose(img)          # gira conforme o celular
    if img.mode not in ("RGB", "L"):
        fundo = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            fundo.paste(img, mask=img.split()[-1])
            img = fundo
        else:
            img = img.convert("RGB")
    return img


def _pasta(sub):
    pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], sub)
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _salvar(img, sub, sufixo, qualidade):
    nome = f"{uuid.uuid4().hex}{sufixo}.jpg"
    img.save(os.path.join(_pasta(sub), nome), "JPEG", quality=qualidade, optimize=True, progressive=True)
    return f"uploads/{sub}/{nome}"   # caminho relativo a /static


def salvar_foto_produto(arquivo):
    """Retorna dict com arquivo, miniatura, largura, altura."""
    img = _abrir(arquivo)
    larg, alt = img.size
    maior, menor = max(larg, alt), min(larg, alt)
    if maior < HD_MIN[0] or menor < HD_MIN[1]:
        raise ErroImagem(f"“{arquivo.filename}” tem {larg}×{alt} px. A foto precisa ter resolução HD "
                         f"(pelo menos 1280×720) ou 4K.")
    if maior > LADO_MAX_4K:
        img.thumbnail((LADO_MAX_4K, LADO_MAX_4K), Image.LANCZOS)
    completa = _salvar(img, "produtos", "", 90)
    mini = img.copy()
    mini.thumbnail((LADO_MINIATURA, LADO_MINIATURA), Image.LANCZOS)
    miniatura = _salvar(mini, "produtos", "_mini", 82)
    return {"arquivo": completa, "miniatura": miniatura, "largura": img.size[0], "altura": img.size[1]}


def salvar_foto_perfil(arquivo):
    img = _abrir(arquivo)
    img = ImageOps.fit(img, (LADO_PERFIL, LADO_PERFIL), Image.LANCZOS)
    return _salvar(img, "perfis", "", 88)


def apagar_arquivo(caminho_relativo):
    """Remove um arquivo enviado (ignora imagens de exemplo fora de uploads/)."""
    if not caminho_relativo or not caminho_relativo.startswith("uploads/"):
        return
    caminho = os.path.join(current_app.static_folder, caminho_relativo)
    try:
        os.remove(caminho)
    except OSError:
        pass


def rotulo_resolucao(larg, alt):
    maior = max(larg or 0, alt or 0)
    if maior >= 3840:
        return "4K"
    if maior >= 2560:
        return "2K"
    if maior >= 1920:
        return "Full HD"
    if maior >= 1280:
        return "HD"
    return "Ilustração"

import io
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime
from .palette import CORES_LOTERIAS, LOGOS_LOTERIAS, norm_key

def gerar_imagem_loteria(loteria, concurso, data, numeros, url_resultado, largura=1080, altura=1080):
    """Gera imagem 3D com logo, números e link da publicação"""

    loteria_norm = norm_key(loteria)
    cor_fundo = CORES_LOTERIAS.get(loteria_norm, "#333333")
    logo_url = LOGOS_LOTERIAS.get(loteria_norm)

    img = Image.new("RGB", (largura, altura), color=cor_fundo)
    draw = ImageDraw.Draw(img)

    sombra = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sombra_draw = ImageDraw.Draw(sombra)
    sombra_draw.rectangle([50, 50, largura-50, altura-50], fill=(0, 0, 0, 150))
    img = Image.alpha_composite(img.convert("RGBA"), sombra).convert("RGB")

    logo = None
    if logo_url:
        try:
            resp = requests.get(logo_url, timeout=10)
            logo = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            logo.thumbnail((400, 400))
            img.paste(logo, (int((largura-logo.width)/2), 50), logo)
        except Exception:
            pass

    fonte_titulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 70)
    fonte_dados = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
    fonte_numeros = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 65)

    y_atual = 480
    draw.text((largura/2, y_atual), f"{loteria.upper()} – CONC. {concurso}", anchor="mm", fill="white", font=fonte_titulo)
    y_atual += 90
    draw.text((largura/2, y_atual), f"{data}", anchor="mm", fill="white", font=fonte_dados)
    y_atual += 120

    numeros_lista = [n.strip() for n in str(numeros).replace(",", " ").split()]
    espacamento = 120
    total_largura = len(numeros_lista) * espacamento
    x_inicial = (largura - total_largura) / 2 + espacamento / 2

    for i, num in enumerate(numeros_lista):
        x = x_inicial + i * espacamento
        y = y_atual
        draw.ellipse((x-55, y-55, x+55, y+55), fill="white", outline="#ccc", width=4)
        draw.text((x, y), num, anchor="mm", fill=cor_fundo, font=fonte_numeros)

    y_atual += 200
    draw.text((largura/2, y_atual), "Portal SimonSports", anchor="mm", fill="white", font=fonte_dados)
    y_atual += 60
    draw.text((largura/2, y_atual), url_resultado, anchor="mm", fill="white", font=fonte_numeros)

    img = img.filter(ImageFilter.GaussianBlur(0.3))

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", quality=95)
    buffer.seek(0)
    return buffer
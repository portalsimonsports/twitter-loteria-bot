import os
import re
from datetime import datetime

from moviepy.editor import (
    TextClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip
)

def gerar_video_loteria(dados):
    """
    Gera um vídeo MP4 a partir do dicionário de dados.
    Suporta usar imagem pronta como fundo (recomendado).
    
    Espera (mínimo):
      dados['loteria'], dados['concurso'], dados['numeros']
    Opcionais:
      dados['premio']
      dados['imagem_path']  -> caminho local do PNG/JPG (arte final)
      dados['cor_fundo_rgb'] -> tuple (R,G,B)
      dados['duracao'] -> int/float (segundos)
    """
    loteria = str(dados.get("loteria", "")).strip() or "LOTERIA"
    concurso = str(dados.get("concurso", "")).strip() or "-"
    numeros = str(dados.get("numeros", "")).strip() or "-"
    premio = str(dados.get("premio", "")).strip() or ""
    imagem_path = str(dados.get("imagem_path", "")).strip()
    cor_fundo = dados.get("cor_fundo_rgb", (0, 114, 54))  # fallback
    duracao = float(dados.get("duracao", 8))

    _log_video(f"Gerando vídeo para {loteria} concurso {concurso}...")

    # Vertical (Reels/Shorts)
    LARGURA, ALTURA = 1080, 1920

    # 1) Fundo: preferencialmente a IMAGEM FINAL já gerada
    clips = []
    if imagem_path and os.path.exists(imagem_path):
        fundo_img = (
            ImageClip(imagem_path)
            .resize(height=ALTURA)  # encaixa altura
        )
        # Se sobrar largura, corta ao centro para 1080
        if fundo_img.w > LARGURA:
            x1 = (fundo_img.w - LARGURA) / 2
            fundo_img = fundo_img.crop(x1=x1, y1=0, x2=x1 + LARGURA, y2=ALTURA)
        else:
            # Se faltar, redimensiona por largura
            fundo_img = fundo_img.resize(width=LARGURA)
            if fundo_img.h > ALTURA:
                y1 = (fundo_img.h - ALTURA) / 2
                fundo_img = fundo_img.crop(x1=0, y1=y1, x2=LARGURA, y2=y1 + ALTURA)

        clips.append(fundo_img.set_duration(duracao))
    else:
        # fallback: cor sólida
        clips.append(ColorClip(size=(LARGURA, ALTURA), color=cor_fundo, duration=duracao))

    # 2) Textos (mantenha simples para evitar problemas de fonte)
    # Use fonte que existe no Ubuntu: DejaVu-Sans-Bold (mais confiável)
    fonte = "DejaVu-Sans-Bold"

    txt_topo = TextClip(
        f"{loteria.upper()}  |  CONCURSO {concurso}",
        fontsize=68,
        color="white",
        font=fonte,
        method="caption",
        size=(int(LARGURA * 0.92), None)
    ).set_position(("center", 120)).set_duration(duracao)

    txt_nums = TextClip(
        numeros,
        fontsize=110,
        color="yellow",
        font=fonte,
        method="caption",
        size=(int(LARGURA * 0.92), None)
    ).set_position(("center", "center")).set_duration(duracao)

    clips.append(txt_topo)
    clips.append(txt_nums)

    if premio:
        txt_premio = TextClip(
            f"PRÊMIO ESTIMADO:\n{premio}",
            fontsize=58,
            color="white",
            font=fonte,
            method="caption",
            size=(int(LARGURA * 0.92), None)
        ).set_position(("center", 1480)).set_duration(duracao)
        clips.append(txt_premio)

    # 3) Nome de saída único por loteria+concurso
    safe_loteria = re.sub(r"[^a-zA-Z0-9_-]+", "-", loteria.lower()).strip("-")
    safe_concurso = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(concurso)).strip("-")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs("output", exist_ok=True)
    output_path = os.path.join("output", f"video_{safe_loteria}_{safe_concurso}_{ts}.mp4")

    video = CompositeVideoClip(clips, size=(LARGURA, ALTURA))

    # Render sem áudio (rápido)
    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio=False,
        threads=2,
        logger=None
    )

    _log_video(f"OK: {output_path}")
    return output_path


def _log_video(*a):
    print("[VÍDEO]", *a, flush=True)

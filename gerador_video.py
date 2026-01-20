import os
from moviepy.editor import TextClip, ColorClip, CompositeVideoClip

def gerar_video_loteria(dados):
    """
    Recebe um dicionário com os dados da loteria e gera um MP4.
    """
    _log_video(f"Gerando vídeo para {dados['loteria']}...")

    # Configurações de layout (Vertical para Redes Sociais)
    LARGURA, ALTURA = 1080, 1920
    DURACAO = 8
    COR_FUNDO = (0, 114, 54) # Verde oficial

    # 1. Fundo
    fundo = ColorClip(size=(LARGURA, ALTURA), color=COR_FUNDO, duration=DURACAO)

    # 2. Textos
    txt_concurso = TextClip(
        f"{dados['loteria'].upper()}\nCONCURSO {dados['concurso']}",
        fontsize=80, color='white', font='Arial-Bold', method='caption', size=(LARGURA*0.8, None)
    ).set_position(('center', 300)).set_duration(DURACAO)

    txt_numeros = TextClip(
        dados['numeros'],
        fontsize=120, color='yellow', font='Arial-Bold', method='caption', size=(LARGURA*0.9, None)
    ).set_position('center').set_duration(DURACAO).crossfadein(1)

    txt_premio = TextClip(
        f"PRÊMIO ESTIMADO:\n{dados['premio']}",
        fontsize=65, color='white', font='Arial-Bold', method='caption', size=(LARGURA*0.8, None)
    ).set_position(('center', 1450)).set_duration(DURACAO)

    # 3. Composição e Exportação
    video = CompositeVideoClip([fundo, txt_concurso, txt_numeros, txt_premio])
    output_path = "video_resultado.mp4"
    
    # Renderização sem áudio para ser rápido no GitHub Actions
    video.write_videofile(output_path, fps=24, codec="libx264", audio=False, logger=None)
    
    return output_path

def _log_video(*a):
    print(f"[VÍDEO] ", *a, flush=True)

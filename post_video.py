import os
from moviepy.editor import TextClip, ColorClip, CompositeVideoClip

def executar(dados):
    """
    dados: dicionário vindo do seu leitor de planilha 
    ex: {'concurso': '2850', 'numeros': '01 02 03 04 05 06', 'premio': 'R$ 2.000.000,00'}
    """
    
    print("Iniciando geração do vídeo...")
    
    # Configurações de estilo
    LARGURA, ALTURA = 1080, 1920  # Formato Reels/TikTok
    DURACAO = 8  # Segundos
    COR_FUNDO = (0, 114, 54) # Verde loteria (RGB)

    # 1. Criar o fundo
    fundo = ColorClip(size=(LARGURA, ALTURA), color=COR_FUNDO, duration=DURACAO)

    # 2. Texto do Concurso (Topo)
    txt_concurso = TextClip(
        f"CONCURSO {dados['concurso']}",
        fontsize=70, color='white', font='Arial-Bold', method='caption', size=(LARGURA*0.8, None)
    ).set_position(('center', 300)).set_duration(DURACAO)

    # 3. Texto dos Números (Centro) - Com efeito de entrada
    # Vamos separar os números para facilitar a leitura se houver muitos
    numeros_formatados = dados['numeros'].replace(" ", "  ") 
    txt_numeros = TextClip(
        numeros_formatados,
        fontsize=110, color='yellow', font='Arial-Bold', method='caption', size=(LARGURA*0.9, None)
    ).set_position('center').set_duration(DURACAO).crossfadein(1.5)

    # 4. Texto do Prêmio (Base)
    txt_premio = TextClip(
        f"PRÊMIO ESTIMADO:\n{dados['premio']}",
        fontsize=60, color='white', font='Arial-Bold', method='caption', size=(LARGURA*0.8, None)
    ).set_position(('center', 1400)).set_duration(DURACAO)

    # 5. Montagem Final
    video = CompositeVideoClip([fundo, txt_concurso, txt_numeros, txt_premio])
    
    # Exportação (Otimizada para Redes Sociais)
    nome_arquivo = "resultado_loteria.mp4"
    video.write_videofile(nome_arquivo, fps=24, codec="libx264", audio=False)
    
    print(f"Vídeo salvo como {nome_arquivo}")
    return nome_arquivo

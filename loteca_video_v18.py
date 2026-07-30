from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from audio_identity_v9 import write_soundtrack
from lottery_result_v18 import LotecaGame, loteca_game_for_speech, parse_lottery_result, team_name_without_code
from voice_narration_v18 import (
    SpeechSegment,
    pair_label,
    select_presenter_pair,
    select_single_voice,
    synthesize_custom_segments,
    voice_label,
)

FULL_DURATION = 270.0
SHORT_DURATION = 90.0
FULL_GAME_START = 30.0
FULL_GAME_SLOT = 13.0
SHORT_GAME_START = 8.0
SHORT_GAME_SLOT = 4.80


def _run(command: Sequence[str]) -> None:
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"Falha no vídeo especial da Loteca V18: {process.stderr[-7000:]}")


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start: int, minimum: int = 18) -> ImageFont.FreeTypeFont:
    for size in range(start, minimum - 1, -2):
        font = _font(size, True)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    return _font(minimum, True)


def _gradient(size: Tuple[int, int], top=(0, 119, 193), bottom=(0, 24, 56)) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        ratio = ratio * ratio * (3 - 2 * ratio)
        color = tuple(round(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3))
        draw.line((0, y, width, y), fill=color)
    return image


def _scale(size: Tuple[int, int]) -> float:
    return size[0] / (1920.0 if size[0] >= size[1] else 1080.0)


def _brand(draw: ImageDraw.ImageDraw, size: Tuple[int, int], preview: bool) -> None:
    width, _height = size
    scale = _scale(size)
    draw.rounded_rectangle(
        (40 * scale, 32 * scale, width - 40 * scale, 145 * scale),
        radius=30 * scale,
        fill=(0, 18, 42, 225),
        outline=(130, 217, 255, 160),
        width=max(2, round(3 * scale)),
    )
    draw.ellipse(
        (70 * scale, 55 * scale, 140 * scale, 125 * scale),
        fill=(0, 119, 193), outline=(160, 230, 255), width=max(2, round(3 * scale)),
    )
    draw.text((105 * scale, 90 * scale), "S", font=_font(round(35 * scale), True), fill="white", anchor="mm")
    draw.text((170 * scale, 64 * scale), "PORTAL", font=_font(round(24 * scale), True), fill=(160, 230, 255))
    draw.text((170 * scale, 92 * scale), "SIMONSPORTS", font=_font(round(40 * scale), True), fill="white")
    draw.text((width - 75 * scale, 91 * scale), "RESULTADOS", font=_font(round(22 * scale), True), fill=(160, 230, 255), anchor="rm")
    if preview:
        draw.rounded_rectangle(
            (width - 350 * scale, 165 * scale, width - 45 * scale, 225 * scale),
            radius=18 * scale, fill=(244, 188, 35),
        )
        draw.text((width - 198 * scale, 195 * scale), "PRÉVIA LOTECA", font=_font(round(18 * scale), True), fill=(25, 22, 10), anchor="mm")


def _footer(draw: ImageDraw.ImageDraw, size: Tuple[int, int]) -> None:
    width, height = size
    scale = _scale(size)
    draw.text(
        (width / 2, height - 52 * scale),
        "FONTE: CAIXA LOTERIAS • CONTEÚDO INFORMATIVO",
        font=_font(round(18 * scale), True), fill=(190, 236, 255), anchor="mm",
    )


def _team(value: str) -> str:
    return team_name_without_code(value).upper()


def _intro_scene(data: Dict[str, Any], size: Tuple[int, int]) -> Image.Image:
    image = _gradient(size)
    draw = ImageDraw.Draw(image, "RGBA")
    _brand(draw, size, bool(data.get("previa", False)))
    width, height = size
    horizontal = width > height
    center = width // 2
    y = 330 if horizontal else 470
    draw.text((center, y), "LOTECA", font=_font(120 if horizontal else 108, True), fill="white", anchor="mm", stroke_width=3, stroke_fill=(0, 20, 50))
    contest = str(data.get("concurso") or "").strip()
    draw.rounded_rectangle((center - 360, y + 105, center + 360, y + 205), radius=36, fill=(0, 119, 193), outline=(160, 230, 255), width=3)
    draw.text((center, y + 155), f"CONCURSO {contest}" if contest else "RESULTADO OFICIAL", font=_font(42 if horizontal else 38, True), fill="white", anchor="mm")
    draw.text((center, y + 310), "OS 14 JOGOS, PLACAR POR PLACAR", font=_font(48 if horizontal else 42, True), fill=(160, 230, 255), anchor="mm")
    date = str(data.get("data") or "").strip()
    if date:
        draw.text((center, y + 390), f"RESULTADOS DE {date}", font=_font(30 if horizontal else 28, True), fill="white", anchor="mm")
    _footer(draw, size)
    return image


def _game_scene(data: Dict[str, Any], game: LotecaGame, size: Tuple[int, int]) -> Image.Image:
    image = _gradient(size, top=(0, 105, 180), bottom=(0, 20, 48))
    draw = ImageDraw.Draw(image, "RGBA")
    _brand(draw, size, bool(data.get("previa", False)))
    width, height = size
    horizontal = width > height
    center = width // 2
    y0 = 265 if horizontal else 360
    draw.rounded_rectangle((center - 230, y0, center + 230, y0 + 78), radius=28, fill=(0, 119, 193), outline=(160, 230, 255), width=3)
    draw.text((center, y0 + 39), f"JOGO {game.index:02d} DE 14", font=_font(34, True), fill="white", anchor="mm")

    home, away = _team(game.home), _team(game.away)
    team_width = 690 if horizontal else 880
    home_font = _fit_font(draw, home, team_width, 62 if horizontal else 54, 28)
    away_font = _fit_font(draw, away, team_width, 62 if horizontal else 54, 28)
    if horizontal:
        draw.rounded_rectangle((110, y0 + 145, 760, y0 + 520), radius=45, fill=(2, 28, 62, 225), outline=(130, 217, 255, 140), width=3)
        draw.rounded_rectangle((1160, y0 + 145, 1810, y0 + 520), radius=45, fill=(2, 28, 62, 225), outline=(130, 217, 255, 140), width=3)
        draw.text((435, y0 + 285), home, font=home_font, fill="white", anchor="mm", align="center")
        draw.text((1485, y0 + 285), away, font=away_font, fill="white", anchor="mm", align="center")
        draw.text((center, y0 + 310), f"{game.home_score}  x  {game.away_score}", font=_font(118, True), fill=(255, 224, 105), anchor="mm", stroke_width=3, stroke_fill=(0, 20, 48))
        result_y = y0 + 610
    else:
        draw.rounded_rectangle((80, y0 + 130, width - 80, y0 + 440), radius=42, fill=(2, 28, 62, 225), outline=(130, 217, 255, 140), width=3)
        draw.text((center, y0 + 220), home, font=home_font, fill="white", anchor="mm", align="center")
        draw.text((center, y0 + 350), f"{game.home_score}  x  {game.away_score}", font=_font(112, True), fill=(255, 224, 105), anchor="mm", stroke_width=3, stroke_fill=(0, 20, 48))
        draw.rounded_rectangle((80, y0 + 490, width - 80, y0 + 800), radius=42, fill=(2, 28, 62, 225), outline=(130, 217, 255, 140), width=3)
        draw.text((center, y0 + 650), away, font=away_font, fill="white", anchor="mm", align="center")
        result_y = y0 + 930

    result = "EMPATE" if game.home_score == game.away_score else f"VITÓRIA DO {_team(game.home if game.home_score > game.away_score else game.away)}"
    result_font = _fit_font(draw, result, width - 180, 44 if horizontal else 39, 24)
    draw.rounded_rectangle((90, result_y - 58, width - 90, result_y + 58), radius=34, fill=(0, 119, 193, 235), outline=(160, 230, 255), width=3)
    draw.text((center, result_y), result, font=result_font, fill="white", anchor="mm")
    if game.margin >= 3:
        draw.text((center, result_y + 92), "PLACAR ELÁSTICO", font=_font(27, True), fill=(255, 224, 105), anchor="mm")
    if game.day:
        draw.text((center, result_y + 135), f"PARTIDA: {game.day.upper()}", font=_font(23, True), fill=(190, 236, 255), anchor="mm")
    _footer(draw, size)
    return image


def _summary_scene(data: Dict[str, Any], games: Sequence[LotecaGame], start: int, end: int) -> Image.Image:
    size = (1920, 1080)
    image = _gradient(size, top=(0, 97, 169), bottom=(0, 18, 44))
    draw = ImageDraw.Draw(image, "RGBA")
    _brand(draw, size, bool(data.get("previa", False)))
    draw.text((960, 255), f"RESUMO DOS JOGOS {start + 1} A {end}", font=_font(46, True), fill="white", anchor="mm")
    y = 350
    for game in games[start:end]:
        line = f"{game.index:02d}. {_team(game.home)}  {game.home_score} x {game.away_score}  {_team(game.away)}"
        font = _fit_font(draw, line, 1760, 30, 18)
        draw.rounded_rectangle((70, y - 30, 1850, y + 38), radius=20, fill=(2, 30, 65, 210), outline=(130, 217, 255, 100), width=2)
        draw.text((960, y + 3), line, font=font, fill="white", anchor="mm")
        y += 82
    _footer(draw, size)
    return image


def _poster_scene(data: Dict[str, Any], games: Sequence[LotecaGame]) -> Image.Image:
    size = (1920, 1080)
    image = _gradient(size, top=(0, 97, 169), bottom=(0, 18, 44))
    draw = ImageDraw.Draw(image, "RGBA")
    _brand(draw, size, bool(data.get("previa", False)))
    contest = str(data.get("concurso") or "").strip()
    draw.text((960, 220), f"LOTECA {contest} • 14 RESULTADOS", font=_font(48, True), fill="white", anchor="mm")
    for index, game in enumerate(games[:14]):
        column = 0 if index < 7 else 1
        row = index if index < 7 else index - 7
        left = 65 + column * 930
        right = left + 860
        y = 305 + row * 92
        line = f"{game.index:02d}. {_team(game.home)}  {game.home_score} x {game.away_score}  {_team(game.away)}"
        font = _fit_font(draw, line, right - left - 40, 25, 16)
        draw.rounded_rectangle((left, y - 31, right, y + 38), radius=18, fill=(2, 30, 65, 215), outline=(130, 217, 255, 100), width=2)
        draw.text(((left + right) / 2, y + 3), line, font=font, fill="white", anchor="mm")
    _footer(draw, size)
    return image


def _closing_scene(data: Dict[str, Any], size: Tuple[int, int]) -> Image.Image:
    image = _gradient(size, top=(0, 90, 160), bottom=(0, 16, 38))
    draw = ImageDraw.Draw(image, "RGBA")
    _brand(draw, size, bool(data.get("previa", False)))
    width, height = size
    center = width // 2
    y = 330 if width > height else 480
    draw.text((center, y), "RESULTADO COMPLETO DA LOTECA", font=_font(57 if width > height else 47, True), fill="white", anchor="mm")
    draw.text((center, y + 110), "VOCÊ CONSIDERA QUE DEU ZEBRA EM ALGUM JOGO?", font=_font(36 if width > height else 30, True), fill=(255, 224, 105), anchor="mm")
    draw.text((center, y + 220), "CONTE NOS COMENTÁRIOS", font=_font(41 if width > height else 35, True), fill=(160, 230, 255), anchor="mm")
    draw.rounded_rectangle((center - 520, y + 310, center + 520, y + 430), radius=38, fill=(0, 119, 193), outline=(160, 230, 255), width=3)
    draw.text((center, y + 370), "portalsimonsports.com • Loterias Caixa", font=_font(34 if width > height else 29, True), fill="white", anchor="mm")
    draw.text((center, y + 530), "INSCREVA-SE • CURTA • COMPARTILHE", font=_font(36 if width > height else 30, True), fill="white", anchor="mm")
    _footer(draw, size)
    return image


def _write_concat_video(images: Sequence[Tuple[Image.Image, float]], audio: Path, output: Path, duration: float, temp: Path) -> None:
    list_path = temp / "timeline.txt"
    lines: List[str] = []
    for index, (image, scene_duration) in enumerate(images):
        path = temp / f"scene_{index:02d}.png"
        image.save(path, quality=95)
        escaped = str(path).replace("'", "'\\''")
        lines.extend((f"file '{escaped}'", f"duration {scene_duration:.3f}"))
    last_path = temp / f"scene_{len(images) - 1:02d}.png"
    escaped_last = str(last_path).replace("'", "'\\''")
    lines.append(f"file '{escaped_last}'")
    list_path.write_text("\n".join(lines), encoding="utf-8")
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-i", str(audio), "-vf", "fps=30,format=yuv420p", "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
        "-t", f"{duration:.3f}", "-movflags", "+faststart", str(output),
    ])


def _full_segments(data: Dict[str, Any], games: Sequence[LotecaGame], pair: Tuple[str, str]) -> List[SpeechSegment]:
    primary, secondary = pair
    contest = str(data.get("concurso") or "").strip()
    date = str(data.get("data") or "").strip()
    segments: List[SpeechSegment] = [
        SpeechSegment(0.35, primary, "Olá! Seja muito bem-vindo ao Portal SimonSports. Hoje a nossa conferência é especial: vamos acompanhar, jogo a jogo, o resultado completo da Loteca.", 1.0, None, "opening"),
        SpeechSegment(9.20, secondary, f"Este é o concurso {contest}" + (f", com resultados divulgados em {date}." if date else ".") + " São quatorze partidas, com os placares apresentados de forma organizada para facilitar a sua conferência.", 1.0, None, "opening"),
        SpeechSegment(20.20, primary, "Separe o seu comprovante e acompanhe com a gente. Durante a apresentação, conte nos comentários como está o seu desempenho.", 1.0, None, "opening"),
    ]
    interactions = {
        4: "Quatro jogos conferidos. Até aqui, algum placar surpreendeu você? Como está o seu desempenho?",
        8: "Chegamos à metade do concurso. Já apareceu algum resultado que você não esperava?",
        12: "Entramos na reta final. Você considera que deu zebra em algum desses jogos? Conte para a gente.",
    }
    for index, game in enumerate(games):
        start = FULL_GAME_START + index * FULL_GAME_SLOT
        voice = primary if index % 2 == 0 else secondary
        segments.append(SpeechSegment(start + 0.65, voice, loteca_game_for_speech(game), 1.02, "+3%", "loteca_game"))
        game_number = index + 1
        if game_number in interactions:
            other = secondary if voice == primary else primary
            segments.append(SpeechSegment(start + 8.65, other, interactions[game_number], 1.0, "+7%", "engagement"))
    segments.extend([
        SpeechSegment(213.50, primary, "Os quatorze resultados já foram apresentados. Na tela, você confere agora o resumo completo do concurso.", 1.0, None, "summary"),
        SpeechSegment(228.00, secondary, "Revise com calma os seus palpites. Teve algum resultado inesperado ou alguma partida que, na sua opinião, foi uma verdadeira zebra?", 1.0, None, "closing"),
        SpeechSegment(241.50, primary, "Para consultar este e outros resultados da Loteca, acesse portalsimonsports.com e abra a seção Loterias Caixa.", 1.0, "+2%", "closing"),
        SpeechSegment(254.00, secondary, "Deixe o seu like, compartilhe este vídeo e inscreva-se no canal para acompanhar os próximos concursos.", 1.0, None, "closing"),
        SpeechSegment(264.00, primary, "SimonSports, simplesmente o melhor. Até o próximo resultado!", 1.0, "+4%", "closing"),
    ])
    return sorted(segments, key=lambda item: item.start)


def _short_segments(data: Dict[str, Any], games: Sequence[LotecaGame], voice: str) -> List[SpeechSegment]:
    contest = str(data.get("concurso") or "").strip()
    segments = [SpeechSegment(0.20, voice, f"Portal SimonSports. Resultado da Loteca, concurso {contest}. Confira os quatorze placares.", 1.03, "+10%", "opening")]
    for index, game in enumerate(games):
        start = SHORT_GAME_START + index * SHORT_GAME_SLOT
        home = team_name_without_code(game.home).title()
        away = team_name_without_code(game.away).title()
        segments.append(SpeechSegment(start, voice, f"Jogo {game.index}. {home}, {game.home_score}. {away}, {game.away_score}.", 1.04, "+18%", "loteca_game"))
    segments.extend([
        SpeechSegment(76.00, voice, "Confira o resultado completo no canal e diga nos comentários se algum placar foi uma zebra para você.", 1.02, "+12%", "closing"),
        SpeechSegment(85.00, voice, "Portal SimonSports. Inscreva-se e acompanhe os próximos resultados.", 1.02, "+12%", "closing"),
    ])
    return sorted(segments, key=lambda item: item.start)


def gerar_pacote_loteca(data: Dict[str, Any]) -> Dict[str, str]:
    raw = data.get("numeros") or data.get("descricao") or data.get("Descrição") or ""
    games = list(parse_lottery_result("Loteca", raw).loteca_games)
    if len(games) != 14:
        raise RuntimeError(f"A prévia da Loteca exige 14 jogos válidos; foram identificados {len(games)}.")
    output_dir = Path(str(data.get("output_dir") or "output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    contest = re.sub(r"\D+", "", str(data.get("concurso") or "resultado")) or "resultado"
    full_output = output_dir / f"video_completo_loteca_{contest}_{round(FULL_DURATION)}s_dialogo_v18.mp4"
    short_output = output_dir / f"short_loteca_{contest}_{round(SHORT_DURATION)}s_voz_v18.mp4"
    poster_output = output_dir / f"poster_loteca_{contest}_v18.png"
    pair = select_presenter_pair(data)
    short_voice = select_single_voice(data)

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-loteca-v18-") as temp_dir:
        temp = Path(temp_dir)
        full_music, full_audio = temp / "full_music.wav", temp / "full_audio.wav"
        write_soundtrack(full_music, FULL_DURATION, "Loteca", contest, 213.0, 236.0)
        synthesize_custom_segments(data, FULL_DURATION, _full_segments(data, games, pair), full_music, full_audio, primary_voice=pair[0])
        full_images: List[Tuple[Image.Image, float]] = [(_intro_scene(data, (1920, 1080)), FULL_GAME_START)]
        full_images.extend((_game_scene(data, game, (1920, 1080)), FULL_GAME_SLOT) for game in games)
        full_images.extend([
            (_summary_scene(data, games, 0, 7), 12.0),
            (_summary_scene(data, games, 7, 14), 12.0),
            (_closing_scene(data, (1920, 1080)), 34.0),
        ])
        full_temp = temp / "full"
        full_temp.mkdir()
        _write_concat_video(full_images, full_audio, full_output, FULL_DURATION, full_temp)

        short_music, short_audio = temp / "short_music.wav", temp / "short_audio.wav"
        write_soundtrack(short_music, SHORT_DURATION, "Loteca", contest, 76.0, 82.0)
        synthesize_custom_segments(data, SHORT_DURATION, _short_segments(data, games, short_voice), short_music, short_audio, primary_voice=short_voice)
        short_images: List[Tuple[Image.Image, float]] = [(_intro_scene(data, (1080, 1920)), SHORT_GAME_START)]
        short_images.extend((_game_scene(data, game, (1080, 1920)), SHORT_GAME_SLOT) for game in games)
        short_images.append((_closing_scene(data, (1080, 1920)), 14.8))
        short_temp = temp / "short"
        short_temp.mkdir()
        _write_concat_video(short_images, short_audio, short_output, SHORT_DURATION, short_temp)
        _poster_scene(data, games).save(poster_output, quality=95)

    presenter = pair_label(pair)
    print(f"[LOTECA V18] completo={full_output.name} ({presenter}) | Short={short_output.name} ({voice_label(short_voice)}) | jogos=14", flush=True)
    return {
        "short": str(short_output), "completo": str(full_output), "base": "",
        "poster": str(poster_output), "voz": presenter,
        "modo_apresentacao": "Loteca especial com dois apresentadores",
    }


__all__ = ["FULL_DURATION", "SHORT_DURATION", "gerar_pacote_loteca"]

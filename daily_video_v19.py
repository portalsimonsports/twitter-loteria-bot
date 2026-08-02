from __future__ import annotations

import math
import os
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from audio_identity_v9 import write_soundtrack
from lottery_result_v18 import parse_lottery_result, team_name_without_code
from voice_narration_v18 import (
    SpeechSegment,
    pair_label,
    select_presenter_pair,
    select_single_voice,
    synthesize_custom_segments,
    voice_label,
)

VERSION = "V19"
FULL_RATE = "-5%"
SHORT_RATE = "-3%"
FULL_INTRO_DURATION = 7.0
FULL_ENGAGEMENT_DURATION = 9.0
FULL_CLOSING_DURATION = 17.0
SHORT_CLOSING_DURATION = 6.0

Scene = Tuple[Image.Image, float]


def _run(command: Sequence[str]) -> None:
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"Falha no vídeo diário V19: {process.stderr[-8000:]}")


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_font(draw: ImageDraw.ImageDraw, text: str, width: int, start: int, minimum: int = 18) -> ImageFont.FreeTypeFont:
    for size in range(start, minimum - 1, -2):
        font = _font(size, True)
        if draw.textbbox((0, 0), text, font=font)[2] <= width:
            return font
    return _font(minimum, True)


def _gradient(size: Tuple[int, int], top=(6, 105, 173), bottom=(0, 18, 44)) -> Image.Image:
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


def _brand(draw: ImageDraw.ImageDraw, size: Tuple[int, int]) -> None:
    width, _height = size
    scale = _scale(size)
    draw.rounded_rectangle(
        (40 * scale, 30 * scale, width - 40 * scale, 142 * scale),
        radius=30 * scale,
        fill=(0, 18, 42, 235),
        outline=(130, 217, 255, 170),
        width=max(2, round(3 * scale)),
    )
    draw.ellipse(
        (70 * scale, 53 * scale, 140 * scale, 123 * scale),
        fill=(0, 119, 193),
        outline=(160, 230, 255),
        width=max(2, round(3 * scale)),
    )
    draw.text((105 * scale, 88 * scale), "S", font=_font(round(35 * scale), True), fill="white", anchor="mm")
    draw.text((170 * scale, 61 * scale), "PORTAL", font=_font(round(23 * scale), True), fill=(160, 230, 255))
    draw.text((170 * scale, 89 * scale), "SIMONSPORTS", font=_font(round(39 * scale), True), fill="white")
    draw.text((width - 75 * scale, 88 * scale), "RESULTADOS DO DIA", font=_font(round(21 * scale), True), fill=(160, 230, 255), anchor="rm")


def _footer(draw: ImageDraw.ImageDraw, size: Tuple[int, int]) -> None:
    width, height = size
    scale = _scale(size)
    draw.text(
        (width / 2, height - 42 * scale),
        "FONTE: CAIXA LOTERIAS • CONTEÚDO INFORMATIVO",
        font=_font(round(17 * scale), True),
        fill=(190, 236, 255),
        anchor="mm",
    )


def _normalize_name(value: Any) -> str:
    text = " ".join(str(value or "").strip().split())
    replacements = {
        "Mega Sena": "Mega-Sena",
        "Lotofacil": "Lotofácil",
        "Mais Milionaria": "+Milionária",
        "Maís Milionaria": "+Milionária",
        "Loteria Federal": "Loteria Federal",
    }
    return replacements.get(text, text or "Loteria")


def _speech_normalize(text: str) -> str:
    value = str(text or "")
    value = value.replace("SimonSports", "Simon Sports")
    value = re.sub(r"\bFranca\b", "França", value)
    value = re.sub(r"\bJogo\b", "Jôgo", value)
    value = re.sub(r"\bjogo\b", "jôgo", value)
    return value


def _date_key(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or "")) or "sem_data"


def _raw_result(data: Dict[str, Any]) -> str:
    return str(data.get("numeros") or data.get("descricao") or data.get("Descrição") or "").strip()


def _optional_line(data: Dict[str, Any]) -> str:
    prize = str(data.get("premiacao") or data.get("premio") or data.get("prêmio") or "").strip()
    winners = str(data.get("ganhadores") or data.get("qtd_ganhadores") or data.get("quantidade_ganhadores") or "").strip()
    parts: List[str] = []
    if prize:
        parts.append(f"Premiação: {prize}")
    if winners:
        parts.append(f"Ganhadores: {winners}")
    return " • ".join(parts)


def _special_display(parts) -> str:
    if parts.trevos:
        return "TREVOS DA SORTE: " + " E ".join(parts.trevos)
    if parts.team:
        return "TIME DO CORAÇÃO: " + team_name_without_code(parts.team).upper()
    if parts.lucky_month:
        return "MÊS DA SORTE: " + str(parts.lucky_month).upper()
    return ""


def _special_speech(parts) -> str:
    if parts.trevos:
        return " Trevos da Sorte: " + " e ".join(str(int(value)) for value in parts.trevos) + "."
    if parts.team:
        return " Time do Coração: " + team_name_without_code(parts.team).title() + "."
    if parts.lucky_month:
        return " Mês da Sorte: " + str(parts.lucky_month).title() + "."
    return ""


def _federal_prizes(raw: str) -> List[str]:
    return [item.strip() for item in raw.split("|") if item.strip()][:5]


def _number_grid(
    draw: ImageDraw.ImageDraw,
    numbers: Sequence[str],
    size: Tuple[int, int],
    *,
    top_y: int,
    bottom_y: int,
) -> None:
    width, _height = size
    count = max(1, len(numbers))
    horizontal = width > size[1]
    if horizontal:
        columns = 10 if count > 15 else 8 if count > 8 else count
    else:
        columns = 5 if count > 10 else 4 if count > 6 else min(count, 3)
    rows = math.ceil(count / max(1, columns))
    usable_width = width - (180 if horizontal else 120)
    cell_width = usable_width / max(1, columns)
    cell_height = max(88, (bottom_y - top_y) / max(1, rows))
    radius = min(54 if horizontal else 66, int(cell_width * 0.34), int(cell_height * 0.36))
    number_font = _font(max(24, int(radius * 0.78)), True)

    for index, number in enumerate(numbers):
        row = index // columns
        column = index % columns
        current_row_count = min(columns, count - row * columns)
        row_width = current_row_count * cell_width
        start_x = (width - row_width) / 2
        cx = start_x + (column + 0.5) * cell_width
        cy = top_y + (row + 0.5) * cell_height
        draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            fill=(0, 119, 193, 245),
            outline=(180, 238, 255),
            width=3,
        )
        clean = str(number).strip()
        draw.text((cx, cy), clean.zfill(2) if clean.isdigit() and len(clean) < 2 else clean, font=number_font, fill="white", anchor="mm")


def _base_result_image(data: Dict[str, Any], size: Tuple[int, int], *, section: str = "") -> Tuple[Image.Image, ImageDraw.ImageDraw, int]:
    image = _gradient(size)
    draw = ImageDraw.Draw(image, "RGBA")
    _brand(draw, size)
    width, height = size
    horizontal = width > height
    lottery = _normalize_name(data.get("loteria"))
    contest = str(data.get("concurso") or "").strip()
    date = str(data.get("data") or "").strip()
    title_y = 215 if horizontal else 235
    title_font = _fit_font(draw, lottery.upper(), width - 150, 66 if horizontal else 58, 30)
    draw.text((width / 2, title_y), lottery.upper(), font=title_font, fill="white", anchor="mm")
    subtitle = f"CONCURSO {contest}" if contest else "RESULTADO OFICIAL"
    if date:
        subtitle += f"  •  {date}"
    if section:
        subtitle += f"  •  {section}"
    draw.text((width / 2, title_y + 72), subtitle, font=_font(29 if horizontal else 27, True), fill=(180, 238, 255), anchor="mm")
    _footer(draw, size)
    return image, draw, title_y + 125


def _standard_result_image(data: Dict[str, Any], size: Tuple[int, int]) -> Image.Image:
    image, draw, content_top = _base_result_image(data, size)
    width, height = size
    parts = parse_lottery_result(_normalize_name(data.get("loteria")), _raw_result(data))
    bottom = height - (170 if width > height else 270)
    _number_grid(draw, parts.display_numbers, size, top_y=content_top, bottom_y=bottom)
    special = _special_display(parts)
    optional = _optional_line(data)
    y = height - (125 if width > height else 205)
    if special:
        draw.rounded_rectangle((90, y - 45, width - 90, y + 45), radius=28, fill=(244, 188, 35, 245))
        draw.text((width / 2, y), special, font=_fit_font(draw, special, width - 220, 34, 20), fill=(20, 24, 32), anchor="mm")
        y += 73
    if optional:
        draw.text((width / 2, min(height - 78, y)), optional, font=_fit_font(draw, optional, width - 180, 25, 17), fill=(220, 245, 255), anchor="mm")
    return image


def _federal_result_image(data: Dict[str, Any], size: Tuple[int, int]) -> Image.Image:
    image, draw, content_top = _base_result_image(data, size)
    width, height = size
    prizes = _federal_prizes(_raw_result(data))
    y = content_top + 20
    row_height = 115 if width > height else 190
    for index, prize in enumerate(prizes, start=1):
        draw.rounded_rectangle((100, y, width - 100, y + row_height - 22), radius=30, fill=(2, 30, 65, 225), outline=(130, 217, 255), width=3)
        draw.text((155, y + (row_height - 22) / 2), f"{index}º PRÊMIO", font=_font(30 if width > height else 28, True), fill=(180, 238, 255), anchor="lm")
        draw.text((width - 155, y + (row_height - 22) / 2), prize, font=_font(55 if width > height else 52, True), fill="white", anchor="rm")
        y += row_height
    optional = _optional_line(data)
    if optional:
        draw.text((width / 2, height - 90), optional, font=_fit_font(draw, optional, width - 180, 25, 17), fill=(220, 245, 255), anchor="mm")
    return image


def _loteca_result_image(data: Dict[str, Any], games: Sequence[Any], size: Tuple[int, int], start: int, end: int) -> Image.Image:
    section = f"JOGOS {start + 1} A {end}"
    image, draw, content_top = _base_result_image(data, size, section=section)
    width, _height = size
    y = content_top + 8
    rows = games[start:end]
    row_height = 92 if width > size[1] else 178
    for game in rows:
        home = team_name_without_code(game.home).upper()
        away = team_name_without_code(game.away).upper()
        if game.home_score > game.away_score:
            label = "COLUNA 1"
        elif game.home_score == game.away_score:
            label = "EMPATE"
        else:
            label = "COLUNA 2"
        line = f"{game.index:02d}. {home}  {game.home_score} x {game.away_score}  {away}  —  {label}"
        draw.rounded_rectangle((70, y, width - 70, y + row_height - 16), radius=20, fill=(2, 30, 65, 225), outline=(130, 217, 255, 120), width=2)
        draw.text((width / 2, y + (row_height - 16) / 2), line, font=_fit_font(draw, line, width - 180, 29 if width > size[1] else 27, 16), fill="white", anchor="mm")
        y += row_height
    return image


def _intro_image(results: Sequence[Dict[str, Any]], size: Tuple[int, int]) -> Image.Image:
    image = _gradient(size, top=(8, 119, 190), bottom=(0, 18, 44))
    draw = ImageDraw.Draw(image, "RGBA")
    _brand(draw, size)
    width, height = size
    date = str(results[0].get("data") or "").strip() if results else ""
    y = 300 if width > height else 470
    draw.text((width / 2, y), "RESULTADOS DAS LOTERIAS DE HOJE", font=_fit_font(draw, "RESULTADOS DAS LOTERIAS DE HOJE", width - 150, 62 if width > height else 53, 28), fill="white", anchor="mm")
    if date:
        draw.text((width / 2, y + 100), date, font=_font(38 if width > height else 35, True), fill=(255, 224, 105), anchor="mm")
    names = " • ".join(_normalize_name(item.get("loteria")) for item in results)
    draw.rounded_rectangle((100, y + 175, width - 100, y + 320), radius=38, fill=(0, 18, 42, 225), outline=(130, 217, 255), width=3)
    draw.text((width / 2, y + 247), names, font=_fit_font(draw, names, width - 260, 35 if width > height else 30, 18), fill=(180, 238, 255), anchor="mm")
    _footer(draw, size)
    return image


def _engagement_image(size: Tuple[int, int]) -> Image.Image:
    image = _gradient(size, top=(13, 89, 155), bottom=(0, 18, 44))
    draw = ImageDraw.Draw(image, "RGBA")
    _brand(draw, size)
    width, height = size
    y = height / 2 - 70
    draw.text((width / 2, y), "JÁ CONFERIU OS SEUS JOGOS?", font=_fit_font(draw, "JÁ CONFERIU OS SEUS JOGOS?", width - 150, 62 if width > height else 51, 28), fill="white", anchor="mm")
    draw.text((width / 2, y + 115), "CURTA • COMENTE • COMPARTILHE", font=_fit_font(draw, "CURTA • COMENTE • COMPARTILHE", width - 180, 42 if width > height else 36, 22), fill=(255, 224, 105), anchor="mm")
    _footer(draw, size)
    return image


def _closing_image(results: Sequence[Dict[str, Any]], size: Tuple[int, int]) -> Image.Image:
    image = _gradient(size, top=(8, 95, 165), bottom=(0, 16, 38))
    draw = ImageDraw.Draw(image, "RGBA")
    _brand(draw, size)
    width, height = size
    y = height / 2 - 140
    draw.text((width / 2, y), "RESULTADOS COMPLETOS NO CANAL", font=_fit_font(draw, "RESULTADOS COMPLETOS NO CANAL", width - 150, 60 if width > height else 49, 26), fill="white", anchor="mm")
    draw.text((width / 2, y + 110), "PORTAL SIMONSPORTS", font=_font(50 if width > height else 43, True), fill=(180, 238, 255), anchor="mm")
    draw.rounded_rectangle((130, y + 195, width - 130, y + 315), radius=36, fill=(0, 119, 193), outline=(180, 238, 255), width=3)
    draw.text((width / 2, y + 255), "INSCREVA-SE • CURTA • COMENTE • COMPARTILHE", font=_fit_font(draw, "INSCREVA-SE • CURTA • COMENTE • COMPARTILHE", width - 320, 35 if width > height else 29, 18), fill="white", anchor="mm")
    draw.text((width / 2, y + 405), "portalsimonsports.com", font=_font(30 if width > height else 27, True), fill=(255, 224, 105), anchor="mm")
    _footer(draw, size)
    return image


def _full_speech(data: Dict[str, Any], *, loteca_games: Sequence[Any] | None = None) -> str:
    lottery = _normalize_name(data.get("loteria"))
    contest = str(data.get("concurso") or "").strip()
    raw = _raw_result(data)
    if loteca_games is not None:
        phrases: List[str] = [f"{lottery}, concurso {contest}."]
        for game in loteca_games:
            home = team_name_without_code(game.home).title()
            away = team_name_without_code(game.away).title()
            if game.home_score > game.away_score:
                label = "Coluna 1"
            elif game.home_score == game.away_score:
                label = "Empate"
            else:
                label = "Coluna 2"
            phrases.append(f"Jogo {game.index}. {home}, {game.home_score}. {away}, {game.away_score}. {label}.")
        return _speech_normalize(" ".join(phrases))
    if lottery == "Loteria Federal":
        prizes = _federal_prizes(raw)
        ordinals = ("Primeiro", "Segundo", "Terceiro", "Quarto", "Quinto")
        phrases = [f"Loteria Federal, concurso {contest}."]
        phrases.extend(f"{ordinals[index]} prêmio: {value}." for index, value in enumerate(prizes))
        return " ".join(phrases)
    parts = parse_lottery_result(lottery, raw)
    numbers = ", ".join(str(int(value)) if str(value).isdigit() else str(value) for value in parts.display_numbers)
    text = f"{lottery}, concurso {contest}. Dezenas sorteadas: {numbers}." + _special_speech(parts)
    optional = _optional_line(data)
    if optional:
        text += " " + optional.replace(" • ", ". ") + "."
    return _speech_normalize(text)


def _short_speech(data: Dict[str, Any]) -> str:
    lottery = _normalize_name(data.get("loteria"))
    contest = str(data.get("concurso") or "").strip()
    raw = _raw_result(data)
    parts = parse_lottery_result(lottery, raw)
    if parts.loteca_games:
        return _speech_normalize(f"Loteca, concurso {contest}. Os quatorze placares estão na tela e no vídeo completo.")
    if lottery == "Loteria Federal":
        prizes = _federal_prizes(raw)
        first = prizes[0] if prizes else "resultado na tela"
        return f"Loteria Federal, concurso {contest}. Primeiro prêmio: {first}."
    if len(parts.display_numbers) <= 7:
        numbers = ", ".join(str(int(value)) if str(value).isdigit() else str(value) for value in parts.display_numbers)
        return _speech_normalize(f"{lottery}, concurso {contest}: {numbers}." + _special_speech(parts))
    return _speech_normalize(f"{lottery}, concurso {contest}. Confira todas as dezenas na tela.")


def _estimated_scene_duration(text: str, minimum: float = 12.0, maximum: float = 36.0) -> float:
    words = len(str(text or "").split())
    return max(minimum, min(maximum, words * 0.48 + 4.0))


def _result_full_scenes(data: Dict[str, Any]) -> List[Tuple[Image.Image, float, str]]:
    size = (1920, 1080)
    lottery = _normalize_name(data.get("loteria"))
    parts = parse_lottery_result(lottery, _raw_result(data))
    if parts.loteca_games:
        output: List[Tuple[Image.Image, float, str]] = []
        games = list(parts.loteca_games)
        for start, end in ((0, 7), (7, 14)):
            speech = _full_speech(data, loteca_games=games[start:end])
            output.append((_loteca_result_image(data, games, size, start, end), _estimated_scene_duration(speech, 26.0, 34.0), speech))
        return output
    if lottery == "Loteria Federal":
        speech = _full_speech(data)
        return [(_federal_result_image(data, size), _estimated_scene_duration(speech, 22.0, 32.0), speech)]
    speech = _full_speech(data)
    minimum = 17.0 if len(parts.display_numbers) > 10 else 13.0
    return [(_standard_result_image(data, size), _estimated_scene_duration(speech, minimum, 28.0), speech)]


def _result_short_image(data: Dict[str, Any]) -> Image.Image:
    size = (1080, 1920)
    lottery = _normalize_name(data.get("loteria"))
    parts = parse_lottery_result(lottery, _raw_result(data))
    if parts.loteca_games:
        return _loteca_result_image(data, list(parts.loteca_games), size, 0, min(7, len(parts.loteca_games)))
    if lottery == "Loteria Federal":
        return _federal_result_image(data, size)
    return _standard_result_image(data, size)


def _write_concat_video(scenes: Sequence[Scene], audio: Path, output: Path, duration: float, temp: Path) -> None:
    list_path = temp / "timeline.txt"
    lines: List[str] = []
    for index, (image, scene_duration) in enumerate(scenes):
        image_path = temp / f"scene_{index:03d}.png"
        image.save(image_path, quality=95)
        escaped = str(image_path).replace("'", "'\\''")
        lines.extend((f"file '{escaped}'", f"duration {scene_duration:.3f}"))
    last_path = temp / f"scene_{len(scenes) - 1:03d}.png"
    escaped_last = str(last_path).replace("'", "'\\''")
    lines.append(f"file '{escaped_last}'")
    list_path.write_text("\n".join(lines), encoding="utf-8")
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-i", str(audio), "-vf", "fps=30,format=yuv420p", "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
        "-t", f"{duration:.3f}", "-movflags", "+faststart", str(output),
    ])


def _build_full(results: Sequence[Dict[str, Any]], output: Path, temp: Path, pair: Tuple[str, str]) -> float:
    primary, secondary = pair
    scenes: List[Scene] = [(_intro_image(results, (1920, 1080)), FULL_INTRO_DURATION)]
    segments: List[SpeechSegment] = [
        SpeechSegment(
            0.25,
            primary,
            "Portal Simon Sports, simplesmente o melhor. Confira os resultados das loterias de hoje.",
            1.0,
            FULL_RATE,
            "opening",
        )
    ]
    current = FULL_INTRO_DURATION
    total_result_scenes = sum(len(_result_full_scenes(item)) for item in results)
    engagement_after = max(1, total_result_scenes // 2)
    scene_counter = 0

    for result_index, data in enumerate(results):
        voice = primary if result_index % 2 == 0 else secondary
        for image, scene_duration, speech in _result_full_scenes(data):
            scenes.append((image, scene_duration))
            segments.append(SpeechSegment(current + 0.35, voice, speech, 1.0, FULL_RATE, "daily_result"))
            current += scene_duration
            scene_counter += 1
            if total_result_scenes >= 4 and scene_counter == engagement_after:
                scenes.append((_engagement_image((1920, 1080)), FULL_ENGAGEMENT_DURATION))
                other = secondary if voice == primary else primary
                segments.append(
                    SpeechSegment(
                        current + 0.35,
                        other,
                        "Já conferiu os seus jogos? Deixe o seu like, conte nos comentários e compartilhe este boletim.",
                        1.0,
                        FULL_RATE,
                        "engagement",
                    )
                )
                current += FULL_ENGAGEMENT_DURATION

    scenes.append((_closing_image(results, (1920, 1080)), FULL_CLOSING_DURATION))
    segments.extend([
        SpeechSegment(
            current + 0.35,
            secondary,
            "Os resultados completos e os links de cada concurso estão na descrição e no Portal Simon Sports.",
            1.0,
            FULL_RATE,
            "closing",
        ),
        SpeechSegment(
            current + 8.5,
            primary,
            "Curta, comente, compartilhe e inscreva-se no canal. Portal Simon Sports, simplesmente o melhor.",
            1.0,
            FULL_RATE,
            "closing",
        ),
    ])
    duration = current + FULL_CLOSING_DURATION
    music = temp / "daily_full_music.wav"
    audio = temp / "daily_full_audio.wav"
    contest_seed = _date_key(results[0].get("data") if results else "")
    write_soundtrack(music, duration, "Resultados Diários", contest_seed, FULL_INTRO_DURATION, current)
    synthesize_custom_segments(results[0] if results else {}, duration, segments, music, audio, primary_voice=primary)
    render_dir = temp / "daily_full_render"
    render_dir.mkdir()
    _write_concat_video(scenes, audio, output, duration, render_dir)
    return duration


def _build_short(results: Sequence[Dict[str, Any]], output: Path, temp: Path, voice: str) -> float:
    if not results:
        raise RuntimeError("Nenhum resultado informado para o Short diário.")
    available = 53.0
    per_result = max(5.5, min(10.0, available / len(results)))
    scenes: List[Scene] = []
    segments: List[SpeechSegment] = []
    current = 0.0
    for data in results:
        scenes.append((_result_short_image(data), per_result))
        segments.append(SpeechSegment(current + 0.20, voice, _short_speech(data), 1.0, SHORT_RATE, "daily_short_result"))
        current += per_result
    scenes.append((_closing_image(results, (1080, 1920)), SHORT_CLOSING_DURATION))
    segments.append(
        SpeechSegment(
            current + 0.20,
            voice,
            "Resultados completos no canal Simon Sports. Inscreva-se e acompanhe os próximos sorteios.",
            1.0,
            SHORT_RATE,
            "closing",
        )
    )
    duration = current + SHORT_CLOSING_DURATION
    if duration > 60.0:
        raise RuntimeError(f"Short diário excedeu 60 segundos: {duration:.1f}s")
    music = temp / "daily_short_music.wav"
    audio = temp / "daily_short_audio.wav"
    contest_seed = _date_key(results[0].get("data"))
    write_soundtrack(music, duration, "Resultados Diários", contest_seed, 0.0, current)
    synthesize_custom_segments(results[0], duration, segments, music, audio, primary_voice=voice)
    render_dir = temp / "daily_short_render"
    render_dir.mkdir()
    _write_concat_video(scenes, audio, output, duration, render_dir)
    return duration


def gerar_pacote_diario(
    resultados: Sequence[Dict[str, Any]],
    *,
    output_dir: str | Path = "output",
    gerar_short: bool = True,
) -> Dict[str, str]:
    results = [dict(item) for item in resultados if item]
    if not results:
        raise RuntimeError("Nenhum resultado disponível para o vídeo diário.")
    dates = {str(item.get("data") or "").strip() for item in results}
    if len(dates) != 1:
        raise RuntimeError(f"O pacote diário exige uma única data; recebidas: {sorted(dates)}")

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    key = _date_key(results[0].get("data"))
    full_output = directory / f"resultados_loterias_{key}_completo_v19.mp4"
    short_output = directory / f"resultados_loterias_{key}_short_v19.mp4"
    poster_output = directory / f"resultados_loterias_{key}_capa_v19.png"
    pair = select_presenter_pair({"concurso": key, "loteria": "Resultados Diários"})
    short_voice = select_single_voice({"concurso": key, "loteria": "Resultados Diários"})

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-diario-v19-") as temp_dir:
        temp = Path(temp_dir)
        full_duration = _build_full(results, full_output, temp, pair)
        short_duration = 0.0
        if gerar_short:
            short_duration = _build_short(results, short_output, temp, short_voice)
        _intro_image(results, (1920, 1080)).save(poster_output, quality=95)

    package = {
        "completo": str(full_output),
        "short": str(short_output) if gerar_short else "",
        "poster": str(poster_output),
        "data": str(results[0].get("data") or ""),
        "voz": pair_label(pair),
        "voz_short": voice_label(short_voice),
        "duracao_completo": f"{full_duration:.1f}",
        "duracao_short": f"{short_duration:.1f}" if gerar_short else "0",
        "versao": VERSION,
    }
    print(
        f"[DIÁRIO {VERSION}] data={package['data']} | loterias={len(results)} | "
        f"completo={full_output.name} ({full_duration:.1f}s) | "
        f"short={(short_output.name if gerar_short else 'não gerado')} ({short_duration:.1f}s)",
        flush=True,
    )
    return package


__all__ = [
    "FULL_RATE",
    "SHORT_RATE",
    "VERSION",
    "gerar_pacote_diario",
]

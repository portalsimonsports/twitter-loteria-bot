from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, List, Tuple


STATE_NAMES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
    "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco",
    "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}


@dataclass(frozen=True)
class LotecaGame:
    index: int
    home: str
    away: str
    home_score: int
    away_score: int
    day: str = ""

    @property
    def result_label(self) -> str:
        if self.home_score == self.away_score:
            return "EMPATE"
        return f"VITÓRIA DO {self.home if self.home_score > self.away_score else self.away}"

    @property
    def margin(self) -> int:
        return abs(self.home_score - self.away_score)


@dataclass(frozen=True)
class ParsedLotteryResult:
    lottery: str
    key: str
    main_numbers: Tuple[str, ...] = ()
    second_draw_numbers: Tuple[str, ...] = ()
    trevos: Tuple[str, ...] = ()
    team: str = ""
    lucky_month: str = ""
    loteca_games: Tuple[LotecaGame, ...] = ()
    generic_extra: str = ""

    @property
    def display_numbers(self) -> List[str]:
        return list(self.main_numbers + self.second_draw_numbers)

    @property
    def extra_display(self) -> str:
        if self.trevos:
            return "TREVOS DA SORTE: " + " E ".join(self.trevos)
        if self.team:
            return f"TIME DO CORAÇÃO: {self.team}"
        if self.lucky_month:
            return f"MÊS DA SORTE: {self.lucky_month}"
        if self.loteca_games:
            return f"{len(self.loteca_games)} JOGOS COM PLACARES"
        return self.generic_extra

    @property
    def has_special(self) -> bool:
        return bool(self.trevos or self.team or self.lucky_month)


def slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = ascii_text.replace("+", "mais ")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")


def _string_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _clean_source(value: Any) -> str:
    return re.sub(r"^n[uú]meros?\s*:\s*", "", _string_value(value), flags=re.I).strip()


def _number_tokens(value: str, *, max_count: int | None = None) -> Tuple[str, ...]:
    found = re.findall(r"(?<!\d)\d{1,6}(?!\d)", str(value or ""))
    output = tuple(token.zfill(2) if len(token) <= 2 else token for token in found)
    return output[:max_count] if max_count is not None else output


def _split_extra(text: str) -> Tuple[str, str]:
    parts = re.split(r"\s+-\s+", text, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return text.strip(), ""


def _parse_loteca_game(index: int, raw: str) -> LotecaGame | None:
    text = re.sub(r"\s+", " ", str(raw or "").strip())
    match = re.match(
        r"^(\d+)\s+(.+?)\s+[xX]\s+(.+?)\s+(\d+)\s*(?:\(([^)]+)\))?$",
        text,
    )
    if not match:
        return None
    home_score, home, away, away_score, day = match.groups()
    return LotecaGame(
        index=index,
        home=home.strip(),
        away=away.strip(),
        home_score=int(home_score),
        away_score=int(away_score),
        day=(day or "").strip(),
    )


def parse_lottery_result(lottery: str, value: Any) -> ParsedLotteryResult:
    text = _clean_source(value)
    key = slug(lottery)

    if "loteca" in key:
        games = []
        for index, item in enumerate(re.split(r"\s*\|\s*", text), start=1):
            game = _parse_loteca_game(index, item)
            if game:
                games.append(game)
        return ParsedLotteryResult(lottery, key, loteca_games=tuple(games))

    if "dupla-sena" in key:
        parts = re.split(r"\s*\|\s*", text, maxsplit=1)
        first = _number_tokens(parts[0], max_count=6)
        second = _number_tokens(parts[1], max_count=6) if len(parts) > 1 else ()
        if not second:
            all_numbers = _number_tokens(text, max_count=12)
            first, second = all_numbers[:6], all_numbers[6:12]
        return ParsedLotteryResult(lottery, key, first, second)

    if "mais-milionaria" in key or "milionaria" in key:
        parts = re.split(r"\s*\+\s*", text, maxsplit=1)
        main = _number_tokens(parts[0], max_count=6)
        trevos = _number_tokens(parts[1], max_count=2) if len(parts) > 1 else ()
        if not trevos:
            all_numbers = _number_tokens(text, max_count=8)
            main, trevos = all_numbers[:6], all_numbers[6:8]
        return ParsedLotteryResult(lottery, key, main_numbers=main, trevos=trevos)

    if "timemania" in key:
        numbers_part, team = _split_extra(text)
        return ParsedLotteryResult(
            lottery, key, main_numbers=_number_tokens(numbers_part, max_count=7), team=team
        )

    if "dia-de-sorte" in key:
        numbers_part, month = _split_extra(text)
        return ParsedLotteryResult(
            lottery, key, main_numbers=_number_tokens(numbers_part, max_count=7), lucky_month=month
        )

    limits = {
        "super-sete": 7, "lotomania": 20, "federal": 5,
        "lotofacil": 15, "mega-sena": 6, "quina": 5,
    }
    limit = next((amount for name, amount in limits.items() if name in key), 20)
    numbers = _number_tokens(text, max_count=limit)

    extras = []
    for token in re.split(r"[,;|\n]+", text):
        clean = token.strip()
        if clean and not re.fullmatch(r"\d{1,6}", clean) and clean not in {"-", "+", "x", "X"}:
            extras.append(clean)
    return ParsedLotteryResult(
        lottery, key, main_numbers=numbers, generic_extra=" • ".join(extras[:2])
    )


def team_for_speech(team: str) -> str:
    text = re.sub(r"\s+", " ", str(team or "").strip())
    match = re.match(r"^(.*?)\s*/\s*([A-Za-z]{2})$", text)
    if not match:
        return text.title()
    name, state = match.groups()
    state_name = STATE_NAMES.get(state.upper(), state.upper())
    return f"{name.strip().title()}, {state_name}"


def team_name_without_code(team: str) -> str:
    text = re.sub(r"\s+", " ", str(team or "").strip())
    return re.sub(r"\s*/\s*[A-Za-z]{2,3}$", "", text).strip()


def loteca_game_for_speech(game: LotecaGame) -> str:
    home = team_name_without_code(game.home).title()
    away = team_name_without_code(game.away).title()
    if game.home_score == game.away_score:
        result = "Empate."
    elif game.home_score > game.away_score:
        result = f"Vitória do {home}."
    else:
        result = f"Vitória do {away}."
    emphasis = " Placar elástico." if game.margin >= 3 else ""
    return (
        f"Jogo {game.index}. {home}, {game.home_score}. "
        f"{away}, {game.away_score}. {result}{emphasis}"
    )


def special_speech(parts: ParsedLotteryResult) -> str:
    if parts.trevos:
        values = " e ".join(str(int(value)) for value in parts.trevos)
        return f"E os Trevos da Sorte foram {values}."
    if parts.team:
        return f"O Time do Coração sorteado foi {team_for_speech(parts.team)}."
    if parts.lucky_month:
        return f"E o Mês da Sorte foi {parts.lucky_month.title()}."
    return ""


__all__ = [
    "LotecaGame", "ParsedLotteryResult", "loteca_game_for_speech",
    "parse_lottery_result", "slug", "special_speech",
    "team_for_speech", "team_name_without_code",
]

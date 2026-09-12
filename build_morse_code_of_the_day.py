from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import re
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

APOCALYPSE_YEAR_OFFSET = 196

MORSE_ALPHABET: dict[str, str] = {
    "A": ".-",
    "B": "-...",
    "C": "-.-.",
    "D": "-..",
    "E": ".",
    "F": "..-.",
    "G": "--.",
    "H": "....",
    "I": "..",
    "J": ".---",
    "K": "-.-",
    "L": ".-..",
    "M": "--",
    "N": "-.",
    "O": "---",
    "P": ".--.",
    "Q": "--.-",
    "R": ".-.",
    "S": "...",
    "T": "-",
    "U": "..-",
    "V": "...-",
    "W": ".--",
    "X": "-..-",
    "Y": "-.--",
    "Z": "--..",
    "0": "-----",
    "1": ".----",
    "2": "..---",
    "3": "...--",
    "4": "....-",
    "5": ".....",
    "6": "-....",
    "7": "--...",
    "8": "---..",
    "9": "----.",
}

CHALLENGES: list[dict[str, str]] = [
    {
        "challenge_title": "Schichtwechsel",
        "plain_text": "SCHICHTWECHSEL 1930",
        "difficulty": "leicht",
        "hint": "Uhrzeit eines festen Abendslots.",
    },
    {
        "challenge_title": "Funkdisziplin",
        "plain_text": "RUHE IM AETHER",
        "difficulty": "mittel",
        "hint": "Leise hoeren, dann handeln.",
    },
    {
        "challenge_title": "Nachtfenster",
        "plain_text": "NUR KURZE RUNS",
        "difficulty": "leicht",
        "hint": "Es geht um Bewegung draussen.",
    },
    {
        "challenge_title": "Signalprobe",
        "plain_text": "CODE BLEIBT KLAR",
        "difficulty": "mittel",
        "hint": "Das Signal selbst ist die Aussage.",
    },
    {
        "challenge_title": "Knotenpunkt",
        "plain_text": "TREFFPUNKT NULLPUNKT",
        "difficulty": "hart",
        "hint": "Ein Handelsposten taucht direkt im Klartext auf.",
    },
    {
        "challenge_title": "Staubroute",
        "plain_text": "WECHSEL ZU SUEDROUTE",
        "difficulty": "mittel",
        "hint": "Eine Richtungsangabe steckt drin.",
    },
    {
        "challenge_title": "Lagebild",
        "plain_text": "STACKCAST STUMM",
        "difficulty": "leicht",
        "hint": "Wenn etwas ausbleibt, ist es selbst ein Ereignis.",
    },
    {
        "challenge_title": "Notiz aus dem Rauschen",
        "plain_text": "GEOCACHER IM OSTEN",
        "difficulty": "mittel",
        "hint": "Eine Fraktion plus Himmelsrichtung.",
    },
    {
        "challenge_title": "Bergungsfenster",
        "plain_text": "ZEHN MINUTEN LUFT",
        "difficulty": "leicht",
        "hint": "Knappes Zeitfenster.",
    },
    {
        "challenge_title": "Matzes Marker",
        "plain_text": "HOERER BLEIBEN WACH",
        "difficulty": "mittel",
        "hint": "Direkte Ansage an das Publikum.",
    },
    {
        "challenge_title": "Linienbruch",
        "plain_text": "NOCH KEIN ENTWARNUNG",
        "difficulty": "hart",
        "hint": "Ein fehlendes S irritiert viele beim ersten Lesen.",
    },
    {
        "challenge_title": "Konvoi",
        "plain_text": "NUR IM VERBUND",
        "difficulty": "leicht",
        "hint": "Allein ist heute keine Option.",
    },
]

INTRO_LINES: list[str] = [
    "Piep Matze hier. Puls pruefen. Muster halten.",
    "Abendcheck. Ein Code. Ein Versuch. Dann Ruhe.",
    "Signal steht. Wer hoert, kann lesen.",
    "Morsecode des Tages. Kein Drama, nur Takt.",
]


def _prepare_text(raw_text: str) -> str:
    cleaned = raw_text.upper().strip()
    cleaned = (
        cleaned.replace("Ä", "AE")
        .replace("Ö", "OE")
        .replace("Ü", "UE")
        .replace("ẞ", "SS")
        .replace("ß", "SS")
    )
    return " ".join(cleaned.split())


def normalize_text(raw_text: str) -> str:
    cleaned = _prepare_text(raw_text)
    return "".join(ch for ch in cleaned if ch in MORSE_ALPHABET or ch == " ")


def find_invalid_chars(raw_text: str) -> list[str]:
    prepared = _prepare_text(raw_text)
    invalid = sorted({ch for ch in prepared if ch != " " and ch not in MORSE_ALPHABET})
    return invalid


def validate_challenge_catalog() -> None:
    for challenge in CHALLENGES:
        title = challenge.get("challenge_title", "<unbenannt>")
        raw_plain_text = challenge.get("plain_text", "")
        invalid_chars = find_invalid_chars(raw_plain_text)
        if invalid_chars:
            joined = ", ".join(invalid_chars)
            raise ValueError(f"Challenge '{title}' enthält ungültige Zeichen: {joined}")

        normalized_plain_text = normalize_text(raw_plain_text)
        if not normalized_plain_text:
            raise ValueError(f"Challenge '{title}' enthält nach Normalisierung keinen verwendbaren Text.")


def text_to_morse(plain_text: str) -> str:
    normalized = normalize_text(plain_text)
    words: list[str] = []
    for word in normalized.split(" "):
        letter_codes = [MORSE_ALPHABET[ch] for ch in word if ch in MORSE_ALPHABET]
        if letter_codes:
            words.append(" ".join(letter_codes))
    return " / ".join(words)


def _apocalypse_year_for_real_year(real_year: int) -> int:
    return real_year + APOCALYPSE_YEAR_OFFSET


def to_2222_date(real_day: date) -> str:
    target_year = _apocalypse_year_for_real_year(real_day.year)
    days_in_target_month = calendar.monthrange(target_year, real_day.month)[1]
    safe_day = min(real_day.day, days_in_target_month)
    return date(target_year, real_day.month, safe_day).isoformat()


def challenge_code_hex_for_day_key(day_key: str) -> str:
    # FNV-1a hash, trimmed to 24 bits => stable 6-digit hexadecimal code.
    value = 0x811C9DC5
    source = f"piep-matze-hex:{day_key}"
    for byte in source.encode("utf-8"):
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    return f"{value & 0xFFFFFF:06X}"


def pick_daily_payload(day: date) -> dict[str, str]:
    day_key = day.isoformat()
    digest = hashlib.sha256(f"piep-matze:{day_key}".encode("utf-8")).hexdigest()
    challenge_index = int(digest[:8], 16) % len(CHALLENGES)
    intro_index = int(digest[8:16], 16) % len(INTRO_LINES)
    challenge = CHALLENGES[challenge_index]

    plain_text = normalize_text(challenge["plain_text"])
    display_date = to_2222_date(day)
    display_year = display_date[:4]
    return {
        "date": day_key,
        "date_2222": display_date,
        "challenge_title": challenge["challenge_title"],
        "plain_text": plain_text,
        "morse_text": text_to_morse(plain_text),
        "intro_line": INTRO_LINES[intro_index],
        "difficulty": challenge["difficulty"],
        "hint": challenge["hint"],
        "source_bot": "Piep Matze",
        "challenge_code_hex": challenge_code_hex_for_day_key(day_key),
        "calendar_year": display_year,
        "generator_version": "1.2",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the Morse code of the day for the static game."
    )
    parser.add_argument(
        "--date",
        dest="override_date",
        help="Optional date override in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        default="docs/games/morse/api/morse-code-of-the-day.json",
        help="Target JSON file path.",
    )
    parser.add_argument(
        "--history-output",
        dest="history_output_path",
        default="docs/games/morse/api/morse-code-history.json",
        help="Target JSON path for challenge history.",
    )
    parser.add_argument(
        "--history-lookback-days",
        dest="history_lookback_days",
        type=int,
        default=60,
        help="Seed missing history entries from the previous N days (including today).",
    )
    return parser.parse_args()


def _resolve_day(override: str | None) -> date:
    if override:
        return date.fromisoformat(override)
    berlin_now = datetime.now(ZoneInfo("Europe/Berlin"))
    return berlin_now.date()


def _default_history_document() -> dict:
    berlin_today = datetime.now(ZoneInfo("Europe/Berlin")).date()
    display_year = _apocalypse_year_for_real_year(berlin_today.year)
    return {
        "service": {"name": "Piep Matze Morsecode Dienst", "version": "1"},
        "calendar_year": display_year,
        "updated_at": "",
        "entries": [],
    }


def _load_history_document(history_path: Path) -> dict:
    document = _default_history_document()
    if not history_path.exists():
        return document

    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return document

    if not isinstance(payload, dict):
        return document

    if isinstance(payload.get("service"), dict):
        document["service"] = payload["service"]
    raw_calendar_year = payload.get("calendar_year")
    if isinstance(raw_calendar_year, int):
        document["calendar_year"] = raw_calendar_year
    elif isinstance(raw_calendar_year, str) and raw_calendar_year.isdigit():
        document["calendar_year"] = int(raw_calendar_year)
    if isinstance(payload.get("updated_at"), str):
        document["updated_at"] = payload["updated_at"]
    if isinstance(payload.get("entries"), list):
        normalized_entries: list[dict] = []
        for entry in payload["entries"]:
            if not isinstance(entry, dict):
                continue
            normalized = deepcopy(entry)
            entry_date = normalized.get("date")
            raw_code = normalized.get("challenge_code_hex")
            is_valid_code = isinstance(raw_code, str) and bool(re.fullmatch(r"[0-9A-F]{6}", raw_code.strip()))
            if isinstance(entry_date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry_date):
                if not is_valid_code:
                    normalized["challenge_code_hex"] = challenge_code_hex_for_day_key(entry_date)
                else:
                    normalized["challenge_code_hex"] = raw_code.strip().upper()
            normalized_entries.append(normalized)
        document["entries"] = normalized_entries
    return document


def _append_history_entry(history_path: Path, payload: dict, *, replace_existing: bool = True) -> None:
    document = _load_history_document(history_path)
    entries = document.get("entries")
    if not isinstance(entries, list):
        entries = []

    new_entry = deepcopy(payload)

    replaced = False
    for index, existing in enumerate(entries):
        if isinstance(existing, dict) and existing.get("date") == new_entry.get("date"):
            if replace_existing:
                entries[index] = new_entry
                replaced = True
            else:
                replaced = True
            break

    if not replaced:
        entries.append(new_entry)

    entries.sort(key=lambda entry: str(entry.get("date", "")))
    document["entries"] = entries
    document["updated_at"] = str(payload.get("generated_at", ""))
    raw_calendar_year = payload.get("calendar_year")
    if isinstance(raw_calendar_year, int):
        document["calendar_year"] = raw_calendar_year
    elif isinstance(raw_calendar_year, str) and raw_calendar_year.isdigit():
        document["calendar_year"] = int(raw_calendar_year)
    elif isinstance(payload.get("date"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", payload["date"]):
        payload_date = date.fromisoformat(payload["date"])
        document["calendar_year"] = _apocalypse_year_for_real_year(payload_date.year)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _seed_history_window(history_path: Path, anchor_day: date, lookback_days: int) -> None:
    if lookback_days <= 0:
        return
    for delta in range(lookback_days, 0, -1):
        previous_day = anchor_day - timedelta(days=delta)
        payload = pick_daily_payload(previous_day)
        payload["generated_at"] = datetime.now(ZoneInfo("Europe/Berlin")).isoformat(timespec="seconds")
        _append_history_entry(history_path, payload, replace_existing=False)


def main() -> None:
    args = parse_args()
    validate_challenge_catalog()
    day = _resolve_day(args.override_date)
    payload = pick_daily_payload(day)
    payload["generated_at"] = datetime.now(ZoneInfo("Europe/Berlin")).isoformat(timespec="seconds")

    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    history_path = Path(args.history_output_path)
    _seed_history_window(history_path, day, args.history_lookback_days)
    _append_history_entry(history_path, payload)


if __name__ == "__main__":
    main()

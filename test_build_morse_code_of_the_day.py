from __future__ import annotations

import json
import shutil
import unittest
from datetime import date
from pathlib import Path

from tools.morse_service.build_morse_code_of_the_day import (
    CHALLENGES,
    MORSE_ALPHABET,
    _append_history_entry,
    _load_history_document,
    challenge_code_hex_for_day_key,
    find_invalid_chars,
    normalize_text,
    pick_daily_payload,
    text_to_morse,
    to_2222_date,
    validate_challenge_catalog,
)


class MorseCodeOfTheDayTests(unittest.TestCase):
    def test_normalize_text_transliterates_umlauts_and_filters_symbols(self) -> None:
        normalized = normalize_text("Fünf Grüße, Äther! #42")
        self.assertEqual(normalized, "FUENF GRUESSE AETHER 42")

    def test_text_to_morse_encodes_words_with_slash_separator(self) -> None:
        morse = text_to_morse("SOS 42")
        self.assertEqual(morse, "... --- ... / ....- ..---")

    def test_pick_daily_payload_is_deterministic_per_day(self) -> None:
        day = date(2026, 4, 21)
        first = pick_daily_payload(day)
        second = pick_daily_payload(day)
        self.assertEqual(first, second)

    def test_pick_daily_payload_contains_required_fields(self) -> None:
        payload = pick_daily_payload(date(2026, 4, 21))
        required_keys = {
            "date",
            "date_2222",
            "challenge_title",
            "plain_text",
            "morse_text",
            "intro_line",
            "difficulty",
            "hint",
            "source_bot",
            "challenge_code_hex",
            "calendar_year",
            "generator_version",
        }
        self.assertTrue(required_keys.issubset(set(payload.keys())))
        self.assertIn(payload["difficulty"], {"leicht", "mittel", "hart"})
        self.assertNotEqual(payload["morse_text"], "")
        self.assertRegex(payload["challenge_code_hex"], r"^[0-9A-F]{6}$")
        self.assertEqual(payload["calendar_year"], "2222")

    def test_challenge_code_hex_is_deterministic_and_six_digit(self) -> None:
        first = challenge_code_hex_for_day_key("2026-04-21")
        second = challenge_code_hex_for_day_key("2026-04-21")
        other = challenge_code_hex_for_day_key("2026-04-22")
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[0-9A-F]{6}$")
        self.assertNotEqual(first, other)

    def test_challenge_catalog_uses_only_keyboard_supported_chars(self) -> None:
        validate_challenge_catalog()
        for challenge in CHALLENGES:
            invalid = find_invalid_chars(challenge["plain_text"])
            self.assertEqual(
                invalid,
                [],
                msg=f"Challenge '{challenge['challenge_title']}' hat ungültige Zeichen: {invalid}",
            )

    def test_pick_daily_payload_plain_text_can_be_typed_with_keyboard(self) -> None:
        payload = pick_daily_payload(date(2026, 4, 21))
        for char in payload["plain_text"]:
            self.assertTrue(char == " " or char in MORSE_ALPHABET)

    def test_to_2222_date_maps_month_and_day_to_calendar_year(self) -> None:
        mapped = to_2222_date(date(2026, 4, 21))
        self.assertEqual(mapped, "2222-04-21")
        mapped_next_year = to_2222_date(date(2027, 4, 21))
        self.assertEqual(mapped_next_year, "2223-04-21")

    def test_history_append_replaces_same_date_and_keeps_sort_order(self) -> None:
        tmp_dir = Path.cwd() / ".tmp" / "morse_service_history"
        shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        history_path = tmp_dir / "morse-code-history.json"
        try:
            old_payload = pick_daily_payload(date(2026, 4, 20))
            old_payload["generated_at"] = "2026-04-20T10:00:00+02:00"
            _append_history_entry(history_path, old_payload)

            day_payload = pick_daily_payload(date(2026, 4, 21))
            day_payload["generated_at"] = "2026-04-21T10:00:00+02:00"
            _append_history_entry(history_path, day_payload)

            day_payload_update = dict(day_payload)
            day_payload_update["hint"] = "Aktualisierter Hinweis"
            day_payload_update["generated_at"] = "2026-04-21T11:00:00+02:00"
            _append_history_entry(history_path, day_payload_update)

            document = _load_history_document(history_path)
            entries = document["entries"]
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["date"], "2026-04-20")
            self.assertEqual(entries[1]["date"], "2026-04-21")
            self.assertEqual(entries[1]["hint"], "Aktualisierter Hinweis")
            self.assertRegex(entries[1]["challenge_code_hex"], r"^[0-9A-F]{6}$")
            self.assertEqual(document["updated_at"], "2026-04-21T11:00:00+02:00")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_history_load_backfills_missing_challenge_code_hex(self) -> None:
        tmp_dir = Path.cwd() / ".tmp" / "morse_service_history_backfill"
        shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        history_path = tmp_dir / "morse-code-history.json"
        try:
            raw_history = {
                "service": {"name": "Piep Matze Morsecode Dienst", "version": "1"},
                "calendar_year": 2222,
                "updated_at": "2026-04-21T10:00:00+02:00",
                "entries": [
                    {
                        "date": "2026-04-20",
                        "date_2222": "2222-04-20",
                        "challenge_title": "Alt",
                        "plain_text": "NUR IM VERBUND",
                        "morse_text": "-. ..- .-. / .. -- / ...- . .-. -... ..- -. -..",
                    }
                ],
            }
            history_path.write_text(json.dumps(raw_history, ensure_ascii=False, indent=2), encoding="utf-8")
            loaded = _load_history_document(history_path)
            entries = loaded["entries"]
            self.assertEqual(len(entries), 1)
            self.assertRegex(entries[0]["challenge_code_hex"], r"^[0-9A-F]{6}$")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_json_roundtrip_for_daily_payload(self) -> None:
        payload = pick_daily_payload(date(2026, 4, 21))
        tmp_dir = Path.cwd() / ".tmp" / "morse_service_test"
        shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            out = tmp_dir / "morse-code-of-the-day.json"
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            loaded = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(loaded["plain_text"], payload["plain_text"])
            self.assertEqual(loaded["morse_text"], payload["morse_text"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

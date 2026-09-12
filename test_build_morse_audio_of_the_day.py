from __future__ import annotations

import shutil
import unittest
import wave
from pathlib import Path

from tools.morse_service.build_morse_audio_of_the_day import (
    _audio_date_key_from_payload,
    _build_enriched_payload,
    _build_mix_command,
    _build_segments,
    _parse_morse_words,
    _render_morse_wav,
    _resolve_output_path,
    _to_site_relative_path,
)


class MorseAudioOfTheDayTests(unittest.TestCase):
    def test_parse_morse_words_accepts_words_and_letters(self) -> None:
        words = _parse_morse_words("... --- ... / ....- ..---")
        self.assertEqual(words, [["...", "---", "..."], ["....-", "..---"]])

    def test_parse_morse_words_rejects_invalid_tokens(self) -> None:
        with self.assertRaises(ValueError):
            _parse_morse_words("... X ...")

    def test_build_segments_creates_tone_and_silence_entries(self) -> None:
        segments = _build_segments("... --- ...", dot_ms=72)
        self.assertGreater(len(segments), 0)
        self.assertTrue(any(is_tone for is_tone, _ in segments))
        self.assertTrue(any((not is_tone) for is_tone, _ in segments))

    def test_build_segments_repeats_message_with_pause(self) -> None:
        single = _build_segments("... --- ...", dot_ms=72, repeat_count=1, repeat_pause_seconds=5.0)
        triple = _build_segments("... --- ...", dot_ms=72, repeat_count=3, repeat_pause_seconds=5.0)
        single_tone_duration = sum(duration for is_tone, duration in single if is_tone)
        triple_tone_duration = sum(duration for is_tone, duration in triple if is_tone)
        self.assertAlmostEqual(triple_tone_duration, single_tone_duration * 3, places=4)
        self.assertGreaterEqual(sum(1 for is_tone, duration in triple if (not is_tone and duration >= 5.0)), 2)

    def test_build_segments_uses_explicit_pre_and_post_roll_silence(self) -> None:
        segments = _build_segments(
            "... --- ...",
            dot_ms=72,
            repeat_count=1,
            repeat_pause_seconds=0.0,
            pre_roll_seconds=1.25,
            post_roll_seconds=0.75,
        )
        self.assertGreater(len(segments), 2)
        self.assertEqual(segments[0], (False, 1.25))
        self.assertEqual(segments[-1], (False, 0.75))

    def test_render_morse_wav_creates_pcm_wave_file(self) -> None:
        tmp_dir = Path.cwd() / ".tmp" / "morse_audio_test"
        shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        wav_path = tmp_dir / "morse.wav"
        try:
            _render_morse_wav(
                "... --- ...",
                wav_path,
                sample_rate=44_100,
                frequency_hz=620.0,
                amplitude=0.5,
                dot_ms=72,
            )
            self.assertTrue(wav_path.exists())
            self.assertGreater(wav_path.stat().st_size, 1024)
            with wave.open(str(wav_path), "rb") as handle:
                self.assertEqual(handle.getnchannels(), 1)
                self.assertEqual(handle.getframerate(), 44_100)
                self.assertEqual(handle.getsampwidth(), 2)
                self.assertGreater(handle.getnframes(), 1000)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_build_mix_command_uses_intro_morse_and_outro(self) -> None:
        command = _build_mix_command(
            intro_path=Path("intro.mp3"),
            morse_wav_path=Path("morse.wav"),
            output_mp3_path=Path("out.mp3"),
            bed_path=Path("bg.mp3"),
            outro_path=Path("outro.mp3"),
            bg_volume=0.2,
            xfade_seconds=0.85,
        )
        command_text = " ".join(command)
        self.assertIn("intro.mp3", command_text)
        self.assertIn("morse.wav", command_text)
        self.assertIn("bg.mp3", command_text)
        self.assertIn("outro.mp3", command_text)
        self.assertIn("acrossfade", command_text)

    def test_to_site_relative_path_supports_docs_and_gh_pages_roots(self) -> None:
        self.assertEqual(
            _to_site_relative_path(Path("gh-pages/games/morse/audio/2222-04-21_MCDT.mp3")),
            "/games/morse/audio/2222-04-21_MCDT.mp3",
        )
        self.assertEqual(
            _to_site_relative_path(Path("docs/games/morse/audio/history/2222-04-21_MCDT.mp3")),
            "/games/morse/audio/history/2222-04-21_MCDT.mp3",
        )

    def test_build_enriched_payload_contains_direct_audio_links(self) -> None:
        tmp_dir = Path.cwd() / ".tmp" / "morse_audio_details_test"
        shutil.rmtree(tmp_dir, ignore_errors=True)
        (tmp_dir / "gh-pages" / "games" / "morse" / "audio" / "history").mkdir(parents=True, exist_ok=True)
        output_mp3 = tmp_dir / "gh-pages" / "games" / "morse" / "audio" / "2222-04-21_MCDT.mp3"
        archive_mp3 = tmp_dir / "gh-pages" / "games" / "morse" / "audio" / "history" / "2222-04-21_MCDT.mp3"
        payload = {
            "date": "2026-04-21",
            "challenge_title": "Nachtfenster",
            "plain_text": "NUR KURZE RUNS",
        }

        try:
            output_mp3.write_bytes(b"ID3demo")
            archive_mp3.write_bytes(b"ID3demo")
            details = _build_enriched_payload(
                payload=payload,
                output_mp3_path=output_mp3,
                archive_mp3_path=archive_mp3,
                site_base_url="https://doomsday.radio",
            )
            self.assertEqual(details["challenge_title"], "Nachtfenster")
            self.assertEqual(details["audio_file_path"], "/games/morse/audio/2222-04-21_MCDT.mp3")
            self.assertEqual(
                details["audio_file_url"],
                "https://doomsday.radio/games/morse/audio/2222-04-21_MCDT.mp3",
            )
            self.assertEqual(details["audio_history_file_path"], "/games/morse/audio/history/2222-04-21_MCDT.mp3")
            self.assertEqual(
                details["audio_history_file_url"],
                "https://doomsday.radio/games/morse/audio/history/2222-04-21_MCDT.mp3",
            )
            self.assertEqual(details["audio_file_size_bytes"], 7)
            self.assertEqual(details["audio_history_file_size_bytes"], 7)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_resolve_output_path_maps_template_and_legacy_name(self) -> None:
        self.assertEqual(
            _resolve_output_path("docs/games/morse/audio/{date}_MCDT.mp3", "2222-04-21"),
            Path("docs/games/morse/audio/2222-04-21_MCDT.mp3"),
        )
        self.assertEqual(
            _resolve_output_path("docs/games/morse/audio/morse-code-of-the-day.mp3", "2222-04-21"),
            Path("docs/games/morse/audio/2222-04-21_MCDT.mp3"),
        )

    def test_audio_date_key_prefers_2222_date_and_maps_real_date(self) -> None:
        self.assertEqual(
            _audio_date_key_from_payload({"date_2222": "2222-04-21", "date": "2026-04-21"}),
            "2222-04-21",
        )
        self.assertEqual(
            _audio_date_key_from_payload({"date": "2026-04-21"}),
            "2222-04-21",
        )
        self.assertEqual(
            _audio_date_key_from_payload({"date": "2027-04-21"}),
            "2223-04-21",
        )


if __name__ == "__main__":
    unittest.main()

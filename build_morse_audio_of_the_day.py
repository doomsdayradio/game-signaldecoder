from __future__ import annotations

import argparse
import calendar
import json
import math
import re
import shutil
import subprocess
import wave
from array import array
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

APOCALYPSE_YEAR_OFFSET = 196


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and mix a daily Morse audio file (intro + morse + optional outro)."
    )
    parser.add_argument(
        "--payload",
        default="docs/games/morse/api/morse-code-of-the-day.json",
        help="Path to morse-code-of-the-day JSON payload.",
    )
    parser.add_argument(
        "--output",
        default="docs/games/morse/audio/{date}_MCDT.mp3",
        help="Target MP3 file path. Supports '{date}' placeholder (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--history-dir",
        default="docs/games/morse/audio/history",
        help="Optional directory for date-stamped archive copies.",
    )
    parser.add_argument(
        "--site-base-url",
        default="https://doomsday.radio",
        help="Public site base URL used to build absolute MP3 links.",
    )
    parser.add_argument(
        "--intro",
        default="docs/games/morse/assets/intro.mp3",
        help="Intro audio path.",
    )
    parser.add_argument(
        "--outro",
        default="docs/games/morse/assets/outro.mp3",
        help="Outro audio path.",
    )
    parser.add_argument(
        "--bed",
        default="docs/games/morse/assets/morse-bed.mp3",
        help="Background bed audio path for the morse segment (optional).",
    )
    parser.add_argument(
        "--allow-missing-outro",
        action="store_true",
        help="If set, missing outro files are ignored.",
    )
    parser.add_argument(
        "--allow-missing-bed",
        action="store_true",
        help="If set, missing background bed files are ignored.",
    )
    parser.add_argument(
        "--tone-frequency",
        type=float,
        default=620.0,
        help="Tone frequency in Hz.",
    )
    parser.add_argument(
        "--dot-ms",
        type=int,
        default=72,
        help="Morse dot duration in milliseconds.",
    )
    parser.add_argument(
        "--amplitude",
        type=float,
        default=0.6,
        help="Tone amplitude in range 0..1.",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=44_100,
        help="Generated WAV sample rate.",
    )
    parser.add_argument(
        "--bg-volume",
        type=float,
        default=0.2,
        help="Background bed volume factor.",
    )
    parser.add_argument(
        "--xfade-seconds",
        type=float,
        default=0.85,
        help="Crossfade length in seconds between intro/morse and morse/outro.",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="How many times the Morse code message is repeated.",
    )
    parser.add_argument(
        "--repeat-pause-seconds",
        type=float,
        default=5.0,
        help="Silence in seconds between repeated Morse message passes.",
    )
    parser.add_argument(
        "--pre-roll-seconds",
        type=float,
        default=1.0,
        help="Silence in seconds before the first Morse symbol.",
    )
    parser.add_argument(
        "--post-roll-seconds",
        type=float,
        default=1.0,
        help="Silence in seconds after the last Morse symbol.",
    )
    return parser.parse_args()


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found in PATH. Please install ffmpeg.")


def _load_payload(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object.")
    if not isinstance(payload.get("morse_text"), str) or not payload["morse_text"].strip():
        raise ValueError("Payload has no valid morse_text value.")
    return payload


def _parse_morse_words(morse_text: str) -> list[list[str]]:
    words: list[list[str]] = []
    for raw_word in morse_text.split("/"):
        letters = [token.strip() for token in raw_word.strip().split(" ") if token.strip()]
        if letters:
            words.append(letters)

    if not words:
        raise ValueError("morse_text did not contain any usable morse symbols.")

    for word in words:
        for letter in word:
            if any(ch not in ".-" for ch in letter):
                raise ValueError(f"Invalid morse token '{letter}' in payload.")
    return words


def _build_single_pass_segments(morse_text: str, dot_s: float) -> list[tuple[bool, float]]:
    dash_s = dot_s * 3
    intra_symbol_gap = dot_s
    letter_gap = dot_s * 3
    word_gap = dot_s * 7
    segments: list[tuple[bool, float]] = []
    words = _parse_morse_words(morse_text)

    for word_index, letters in enumerate(words):
        for letter_index, letter in enumerate(letters):
            for symbol_index, symbol in enumerate(letter):
                tone_duration = dot_s if symbol == "." else dash_s
                segments.append((True, tone_duration))
                if symbol_index < len(letter) - 1:
                    segments.append((False, intra_symbol_gap))
            if letter_index < len(letters) - 1:
                segments.append((False, letter_gap))
        if word_index < len(words) - 1:
            segments.append((False, word_gap))
    return segments


def _build_segments(
    morse_text: str,
    dot_ms: int,
    *,
    repeat_count: int = 3,
    repeat_pause_seconds: float = 5.0,
    pre_roll_seconds: float = 1.0,
    post_roll_seconds: float = 1.0,
) -> list[tuple[bool, float]]:
    dot_s = max(0.005, dot_ms / 1000.0)
    repeat_count = max(1, repeat_count)
    repeat_pause_seconds = max(0.0, repeat_pause_seconds)
    pre_roll_seconds = max(0.0, pre_roll_seconds)
    post_roll_seconds = max(0.0, post_roll_seconds)
    segments: list[tuple[bool, float]] = [(False, pre_roll_seconds)]
    single_pass = _build_single_pass_segments(morse_text, dot_s)
    for pass_index in range(repeat_count):
        segments.extend(single_pass)
        if pass_index < repeat_count - 1 and repeat_pause_seconds > 0:
            segments.append((False, repeat_pause_seconds))

    segments.append((False, post_roll_seconds))
    return segments


def _sine_sample(phase: float) -> float:
    return math.sin(phase)


def _render_morse_wav(
    morse_text: str,
    output_wav_path: Path,
    *,
    sample_rate: int,
    frequency_hz: float,
    amplitude: float,
    dot_ms: int,
    repeat_count: int = 3,
    repeat_pause_seconds: float = 5.0,
    pre_roll_seconds: float = 1.0,
    post_roll_seconds: float = 1.0,
) -> None:
    amplitude = max(0.0, min(1.0, amplitude))
    sample_rate = max(8_000, sample_rate)
    frequency_hz = max(20.0, frequency_hz)

    segments = _build_segments(
        morse_text,
        dot_ms,
        repeat_count=repeat_count,
        repeat_pause_seconds=repeat_pause_seconds,
        pre_roll_seconds=pre_roll_seconds,
        post_roll_seconds=post_roll_seconds,
    )
    pcm = array("h")
    attack_samples = int(sample_rate * 0.003)
    release_samples = int(sample_rate * 0.004)
    max_i16 = 32_767
    phase_step = 2.0 * math.pi * (frequency_hz / sample_rate)
    phase = 0.0

    for is_tone, duration in segments:
        sample_count = max(1, int(round(duration * sample_rate)))
        if not is_tone:
            pcm.extend([0] * sample_count)
            continue

        for index in range(sample_count):
            env = 1.0
            if attack_samples > 0 and index < attack_samples:
                env = min(env, index / attack_samples)
            if release_samples > 0 and index >= sample_count - release_samples:
                env = min(env, (sample_count - index) / max(1, release_samples))
            sample = _sine_sample(phase) * amplitude * env
            pcm.append(int(sample * max_i16))
            phase += phase_step

    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())


def _run_ffmpeg(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _build_mix_command(
    *,
    intro_path: Path,
    morse_wav_path: Path,
    output_mp3_path: Path,
    bed_path: Path | None,
    outro_path: Path | None,
    bg_volume: float,
    xfade_seconds: float,
) -> list[str]:
    cmd: list[str] = ["ffmpeg", "-hide_banner", "-y", "-i", str(intro_path), "-i", str(morse_wav_path)]
    has_bed = bed_path is not None
    has_outro = outro_path is not None

    if has_bed:
        cmd.extend(["-stream_loop", "-1", "-i", str(bed_path)])
    if has_outro:
        cmd.extend(["-i", str(outro_path)])

    bg_volume = max(0.0, bg_volume)
    xfade_seconds = max(0.0, xfade_seconds)

    next_input_index = 2
    bed_index = None
    if has_bed:
        bed_index = next_input_index
        next_input_index += 1
    outro_index = next_input_index if has_outro else None

    filters: list[str] = [
        "[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[intro]",
        "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[morse]",
    ]
    if bed_index is not None:
        filters.append(
            f"[{bed_index}:a]volume={bg_volume},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[bg]"
        )
        filters.append("[morse][bg]amix=inputs=2:duration=first:dropout_transition=0[morsemix]")
    else:
        filters.append("[morse]anull[morsemix]")

    if outro_index is not None:
        filters.append(
            f"[{outro_index}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[outro]"
        )
        filters.append(
            f"[intro][morsemix]acrossfade=d={xfade_seconds}:c1=tri:c2=tri[mid]"
        )
        filters.append(
            f"[mid][outro]acrossfade=d={xfade_seconds}:c1=tri:c2=tri[final]"
        )
    else:
        filters.append(
            f"[intro][morsemix]acrossfade=d={xfade_seconds}:c1=tri:c2=tri[final]"
        )

    cmd.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[final]",
            "-ar",
            "44100",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(output_mp3_path),
        ]
    )
    return cmd


def _archive_copy(output_mp3_path: Path, history_dir: Path, payload_date: str) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    archive_path = history_dir / f"{payload_date}_MCDT.mp3"
    shutil.copy2(output_mp3_path, archive_path)
    return archive_path


def _resolve_output_path(output_template: str, payload_date: str) -> Path:
    if "{date}" in output_template:
        return Path(output_template.replace("{date}", payload_date))
    fallback_name = "morse-code-of-the-day.mp3"
    candidate = Path(output_template)
    if candidate.name == fallback_name:
        return candidate.with_name(f"{payload_date}_MCDT.mp3")
    return candidate


def _is_iso_date(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def _to_2222_date_from_iso(real_iso: str) -> str:
    real_day = date.fromisoformat(real_iso)
    target_year = real_day.year + APOCALYPSE_YEAR_OFFSET
    max_day = calendar.monthrange(target_year, real_day.month)[1]
    safe_day = min(real_day.day, max_day)
    return date(target_year, real_day.month, safe_day).isoformat()


def _audio_date_key_from_payload(payload: dict) -> str:
    raw_2222 = str(payload.get("date_2222", "")).strip()
    if raw_2222 and _is_iso_date(raw_2222):
        return raw_2222

    raw_date = str(payload.get("date", "")).strip()
    if raw_date and _is_iso_date(raw_date):
        return _to_2222_date_from_iso(raw_date)

    berlin_today = datetime.now(ZoneInfo("Europe/Berlin")).date()
    return _to_2222_date_from_iso(berlin_today.isoformat())


def _to_site_relative_path(path: Path) -> str:
    normalized = path.as_posix().replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    for anchor in ("gh-pages", "docs"):
        if anchor in parts:
            anchor_index = parts.index(anchor)
            rel_parts = parts[anchor_index + 1 :]
            if rel_parts:
                return "/" + "/".join(rel_parts)
    if "games" in parts:
        games_index = parts.index("games")
        return "/" + "/".join(parts[games_index:])
    return "/" + "/".join(parts)


def _to_absolute_site_url(site_base_url: str, site_relative_path: str) -> str:
    return f"{site_base_url.rstrip('/')}/{site_relative_path.lstrip('/')}"


def _build_enriched_payload(
    *,
    payload: dict,
    output_mp3_path: Path,
    archive_mp3_path: Path,
    site_base_url: str,
) -> dict:
    output_relative_path = _to_site_relative_path(output_mp3_path)
    archive_relative_path = _to_site_relative_path(archive_mp3_path)
    output_size = output_mp3_path.stat().st_size if output_mp3_path.exists() else 0
    archive_size = archive_mp3_path.stat().st_size if archive_mp3_path.exists() else 0
    enriched = dict(payload)
    enriched.update(
        {
            "audio_file_path": output_relative_path,
            "audio_file_url": _to_absolute_site_url(site_base_url, output_relative_path),
            "audio_file_size_bytes": output_size,
            "audio_history_file_path": archive_relative_path,
            "audio_history_file_url": _to_absolute_site_url(site_base_url, archive_relative_path),
            "audio_history_file_size_bytes": archive_size,
            "audio_generated_at": datetime.now(ZoneInfo("Europe/Berlin")).replace(microsecond=0).isoformat(),
            "audio_generator_version": "1.0",
        }
    )
    return enriched


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    _require_ffmpeg()

    payload_path = Path(args.payload)
    intro_path = Path(args.intro)
    outro_path = Path(args.outro)
    bed_path = Path(args.bed)

    payload = _load_payload(payload_path)
    morse_text = str(payload["morse_text"])
    audio_date_key = _audio_date_key_from_payload(payload)
    output_path = _resolve_output_path(args.output, audio_date_key)

    if not intro_path.exists():
        raise FileNotFoundError(f"Intro file not found: {intro_path}")

    if outro_path.exists():
        use_outro: Path | None = outro_path
    elif args.allow_missing_outro:
        use_outro = None
    else:
        raise FileNotFoundError(f"Outro file not found: {outro_path}")

    use_bed: Path | None = bed_path if bed_path.exists() else None
    if use_bed is None and not args.allow_missing_bed:
        raise FileNotFoundError(f"Bed file not found: {bed_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    morse_wav_path = output_path.parent / "morse-code-of-the-day.generated.wav"
    try:
        _render_morse_wav(
            morse_text,
            morse_wav_path,
            sample_rate=args.sample_rate,
            frequency_hz=args.tone_frequency,
            amplitude=args.amplitude,
            dot_ms=args.dot_ms,
            repeat_count=args.repeat_count,
            repeat_pause_seconds=args.repeat_pause_seconds,
            pre_roll_seconds=args.pre_roll_seconds,
            post_roll_seconds=args.post_roll_seconds,
        )

        mix_cmd = _build_mix_command(
            intro_path=intro_path,
            morse_wav_path=morse_wav_path,
            output_mp3_path=output_path,
            bed_path=use_bed,
            outro_path=use_outro,
            bg_volume=args.bg_volume,
            xfade_seconds=args.xfade_seconds,
        )
        _run_ffmpeg(mix_cmd)
    finally:
        try:
            morse_wav_path.unlink(missing_ok=True)
        except OSError:
            pass

    archive_path = _archive_copy(output_path, Path(args.history_dir), audio_date_key)
    payload_output_path = payload_path
    enriched_payload = _build_enriched_payload(
        payload=payload,
        output_mp3_path=output_path,
        archive_mp3_path=archive_path,
        site_base_url=args.site_base_url,
    )
    _write_json(payload_output_path, enriched_payload)
    print(f"Created morse audio: {output_path}")
    print(f"Archived morse audio: {archive_path}")
    print(f"Wrote enriched morse payload JSON: {payload_output_path}")


if __name__ == "__main__":
    main()

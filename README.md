# Signal Decoder

Generator für das tägliche Morse-Rätsel von Doomsday Radio. Ein Skript erzeugt
die JSON-Nutzlast mit Aufgabe und Historie, ein zweites rendert daraus eine
sendefähige Audiodatei.

## Voraussetzungen

- Python 3.9 oder neuer
- `ffmpeg` im `PATH` für die Audioerzeugung

Die JSON-Erzeugung verwendet ausschließlich die Python-Standardbibliothek.

## Tagesrätsel erzeugen

```bash
python build_morse_code_of_the_day.py \
	--output build/morse-code-of-the-day.json \
	--history-output build/morse-code-history.json
```

Mit `--date YYYY-MM-DD` lässt sich ein bestimmter Tag reproduzieren. Ohne
Datumsangabe gilt der aktuelle Tag in der Zeitzone `Europe/Berlin`.

## Audio erzeugen

```bash
python build_morse_audio_of_the_day.py \
	--payload build/morse-code-of-the-day.json \
	--intro path/to/intro.mp3 \
	--outro path/to/outro.mp3 \
	--bed path/to/morse-bed.mp3 \
	--output "build/{date}_MCDT.mp3"
```

Intro, Outro und Hintergrundbett werden nicht in diesem Repository mitgeführt.
Mit `--allow-missing-outro` und `--allow-missing-bed` können die beiden
optionalen Spuren ausgelassen werden. Alle Parameter zeigt `python
build_morse_audio_of_the_day.py --help`.

## Teststatus

```bash
python -m unittest -v
```

Die vorhandenen Tests decken die deterministische Tagesauswahl,
Morse-Codierung und Audioerzeugung ab. Nach der Repository-Aufteilung sind ihre
Imports allerdings noch nicht migriert: Sie erwarten weiterhin das nicht
enthaltene Paket `tools.morse_service`. Der obige Aufruf schlägt deshalb derzeit
bereits bei der Test-Erkennung mit `ModuleNotFoundError` fehl.

## Herkunft

Das Repository wurde aus `docs/games/morse` und `tools/morse_service` des
früheren Monorepos herausgelöst.

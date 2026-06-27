#!/usr/bin/env python3
"""Télécharge fra.traineddata (Tesseract 3.x) et copie eng si absent."""

from __future__ import annotations

import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESSDATA = ROOT / "tessdata"
FRA_URL = "https://github.com/tesseract-ocr/tessdata/raw/3.04.00/fra.traineddata"
ENG_SOURCE = Path(r"C:\Program Files (x86)\Tesseract-OCR\tessdata\eng.traineddata")
ENG_ALT = Path(r"C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata")


def download(url: str, dest: Path) -> None:
    print(f"Telechargement {url} -> {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)
    print(f"  OK ({dest.stat().st_size} octets)")


def main() -> int:
    TESSDATA.mkdir(parents=True, exist_ok=True)

    fra = TESSDATA / "fra.traineddata"
    if not fra.is_file():
        try:
            download(FRA_URL, fra)
        except Exception as exc:
            print(f"Échec téléchargement fra: {exc}", file=sys.stderr)
            return 1
    else:
        print(f"Deja present: {fra}")

    eng = TESSDATA / "eng.traineddata"
    if not eng.is_file():
        for src in (ENG_SOURCE, ENG_ALT):
            if src.is_file():
                shutil.copy2(src, eng)
                print(f"Copie {src} -> {eng}")
                break
        else:
            print("eng.traineddata introuvable — copiez-le manuellement dans tessdata/")
            return 1
    else:
        print(f"Deja present: {eng}")

    print(f"\nTessdata pret: {TESSDATA}")
    print("Ajoutez dans .env :")
    print(f"  TESSDATA_PREFIX={TESSDATA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

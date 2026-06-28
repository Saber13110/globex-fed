"""Tests module file_ingestion — compatible llama3.2:3b text-only."""

from __future__ import annotations

import io

import pytest

from jarvis.providers.documents.context_builder import (
    build_context_from_file,
    select_context_for_question,
)
from jarvis.providers.documents.excel_reader import read_csv, read_excel
from jarvis.providers.documents.file_ingestion import UnsupportedFileTypeError, ingest_file
from jarvis.providers.documents.image_ocr_reader import is_visual_analysis_request, vision_model_unavailable_message
from jarvis.providers.documents.types import FileContext


def test_read_plain_txt():
    data = b"Bonjour\nLigne deux\nTroisieme ligne"
    ctx = ingest_file(data, filename="notes.txt")
    assert ctx.file_type == ".txt"
    assert "Bonjour" in ctx.extracted_text
    assert ctx.metadata["size_bytes"] == len(data)


def test_read_csv():
    data = b"nom,age\nAlice,30\nBob,25\n"
    text, meta, warnings = read_csv(data, file_name="users.csv")
    assert "Alice" in text
    assert meta["columns"] == ["nom", "age"]
    assert meta["rows"] == 2
    assert not warnings


def test_read_excel():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Ventes"
    ws.append(["Produit", "Qte"])
    ws.append(["Widget", 10])
    ws.append(["Gadget", 5])
    buf = io.BytesIO()
    wb.save(buf)

    text, meta, _ = read_excel(buf.getvalue(), file_name="ventes.xlsx")
    assert "Ventes" in text
    assert "Produit" in text
    assert "Widget" in text
    assert meta["sheets"] == ["Ventes"]


def test_pdf_text_extraction():
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Page test PDF Globex")
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()

    ctx = build_context_from_file(buf.getvalue(), filename="test.pdf")
    assert "Page 1:" in ctx.extracted_text
    assert "Globex" in ctx.extracted_text
    assert any("PDF" in w for w in ctx.warnings)


def test_unsupported_type():
    with pytest.raises(UnsupportedFileTypeError):
        ingest_file(b"binary", filename="file.bin")


def test_visual_analysis_detection():
    assert is_visual_analysis_request("Décris cette image en détail")
    assert is_visual_analysis_request("Qu'est-ce que tu vois sur la photo?")
    assert not is_visual_analysis_request("Quel est le total dans le tableau?")


def test_vision_message_contains_model_hint():
    msg = vision_model_unavailable_message()
    assert "llama3.2:3b" in msg
    assert "OCR" in msg


def test_select_context_keywords():
    long_text = "Introduction générale.\n\n" + ("Données facturation client XYZ.\n" * 50)
    ctx = FileContext(
        file_name="doc.txt",
        file_type=".txt",
        extracted_text=long_text,
    )
    selected = select_context_for_question("facturation client XYZ", ctx, max_chars=500)
    assert "facturation" in selected.lower()
    assert len(selected) <= 500


def test_ocr_image_smoke():
    """OCR réel si Tesseract + tessdata projet sont configurés."""
    from jarvis.providers.documents.image_ocr_reader import ocr_image_bytes
    from jarvis.providers.documents.tesseract_config import configure_pytesseract
    from jarvis.kernel.settings import settings

    if not configure_pytesseract(
        tesseract_cmd=settings.tesseract_cmd,
        tessdata_prefix=settings.tessdata_prefix,
    ):
        pytest.skip("Tesseract non installé")

    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (800, 200), color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    draw.text((30, 70), "Bonjour OCR Globex", fill="black", font=font)
    buf = BytesIO()
    img.save(buf, format="PNG")

    text = ocr_image_bytes(buf.getvalue())
    assert "Bonjour" in text or "Globex" in text


@pytest.mark.asyncio
async def test_ask_llama_empty_context():
    from jarvis.providers.documents.ollama_service import ask_llama

    reply = await ask_llama("Question?", {"extracted_text": ""})
    assert "ne trouve pas" in reply.lower() or "pas" in reply.lower()

"""Извлечение текста из загруженных файлов: .txt, .pdf, .docx."""
from __future__ import annotations

import io
from pathlib import PurePath


class UnsupportedFileError(Exception):
    """Файл такого типа бот не поддерживает."""


def extract_text(filename: str, data: bytes) -> str:
    suffix = PurePath(filename).suffix.lower()

    if suffix in {".txt", ".md", ".csv", ".log"}:
        return data.decode("utf-8", errors="replace")

    if suffix == ".pdf":
        return _extract_pdf(data)

    if suffix == ".docx":
        return _extract_docx(data)

    raise UnsupportedFileError(
        f"Формат '{suffix or 'без расширения'}' не поддерживается. "
        "Поддерживаются: .txt, .md, .csv, .pdf, .docx."
    )


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader  # локальный импорт, чтобы не тянуть зря

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _extract_docx(data: bytes) -> str:
    from docx import Document  # python-docx

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)

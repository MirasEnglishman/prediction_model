"""Telegram-бот «Анонимайзер данных».

Точка входа. Запуск:
    python -m src.bot
"""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime
from pathlib import Path
from pathlib import PurePath

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .anonymizer import Anonymizer
from .config import load_settings
from .extractors import UnsupportedFileError, extract_text

logger = logging.getLogger("anonymizer-bot")

LOG_DIR = Path("logs")
PROMPT_LOG_FILE = LOG_DIR / "prompts.jsonl"

WELCOME = (
    "Привет! Я — анонимайзер документов.\n\n"
    "Пришли мне текст или файл (.txt, .pdf, .docx) — "
    "я найду в нём персональные данные (ФИО, юрлица, телефоны, email, ИИН/БИН, БИК, "
    "адреса, даты рождения, номера карт) и заменю их на безопасные плейсхолдеры.\n\n"
    "Команды:\n"
    "/start — это сообщение\n"
    "/help — что я умею"
)

HELP = (
    "Что я умею:\n"
    "• Принять текстовое сообщение и вернуть его обезличенную версию.\n"
    "• Принять документ (.txt, .pdf, .docx) до заданного лимита размера.\n\n"
    "Как это работает:\n"
    "1) Regex-предфильтр маскирует структурные данные (телефон, email, ИИН, БИК, карты).\n"
    "2) LLM (OpenAI) дочищает контекстные сущности — ФИО, адреса, юрлица, даты рождения.\n"
    "3) Все промпты и ответы пишутся в logs/prompts.jsonl для отчётности.\n\n"
    "Примечание: бот работает с текстом до ~10 000 символов за один запрос. "
    "Большие файлы лучше резать на части."
)

MAX_INPUT_CHARS = 10_000


# --- Handlers -----------------------------------------------------------------


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME)


async def cmd_help(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    await _process_and_reply(
        update,
        context,
        text,
        source="text",
        reply_as_docx=False,
        reply_as_pdf=False,
        original_filename=None,
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    document = update.message.document

    if document.file_size and document.file_size > settings.max_file_size_bytes:
        mb = settings.max_file_size_bytes / 1024 / 1024
        await update.message.reply_text(
            f"Файл слишком большой. Лимит: {mb:.1f} МБ."
        )
        return

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    tg_file = await document.get_file()
    raw = await tg_file.download_as_bytearray()

    try:
        text = extract_text(document.file_name or "file", bytes(raw))
    except UnsupportedFileError as exc:
        await update.message.reply_text(str(exc))
        return
    except Exception:
        logger.exception("Ошибка извлечения текста из файла")
        await update.message.reply_text(
            "Не получилось прочитать файл. Попробуй .txt или другой документ."
        )
        return

    if not text.strip():
        await update.message.reply_text("Файл пустой или из него не удалось извлечь текст.")
        return

    suffix = PurePath(document.file_name or "").suffix.lower()
    await _process_and_reply(
        update,
        context,
        text,
        source=f"document:{document.file_name}",
        reply_as_docx=(suffix == ".docx"),
        reply_as_pdf=(suffix == ".pdf"),
        original_filename=document.file_name,
    )


async def _process_and_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    source: str,
    reply_as_docx: bool,
    reply_as_pdf: bool,
    original_filename: str | None,
) -> None:
    if len(text) > MAX_INPUT_CHARS:
        await update.message.reply_text(
            f"Текст слишком длинный ({len(text)} символов). "
            f"Максимум за один запрос — {MAX_INPUT_CHARS}. Разбей на части."
        )
        return

    anonymizer: Anonymizer = context.application.bot_data["anonymizer"]

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    try:
        result = await anonymizer.anonymize(text)
    except Exception:
        logger.exception("LLM call failed")
        await update.message.reply_text(
            "Не удалось обработать запрос. Попробуй ещё раз через минуту."
        )
        return

    _append_prompt_log(update, source=source, prompt_log=result.prompt_log)

    cleaned = result.text or "(пусто)"

    if reply_as_docx:
        await _send_as_docx(update, context, cleaned, original_filename=original_filename)
        return

    if reply_as_pdf:
        await _send_as_pdf(update, context, cleaned, original_filename=original_filename)
        return

    # Telegram режет сообщения > 4096 символов — отправим кусками.
    for chunk in _chunks(cleaned, 3500):
        await update.message.reply_text(chunk)


# --- Helpers ------------------------------------------------------------------


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]


def _append_prompt_log(update: Update, *, source: str, prompt_log: dict) -> None:
    """Пишем JSONL-лог промптов — пригодится для сдачи задания."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "user_id": update.effective_user.id if update.effective_user else None,
        "chat_id": update.effective_chat.id if update.effective_chat else None,
        "source": source,
        **prompt_log,
    }
    with PROMPT_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


async def _send_as_docx(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    original_filename: str | None,
) -> None:
    """Возвращает анонимизированный текст в формате .docx."""
    from docx import Document

    doc = Document()
    for line in text.splitlines() or [""]:
        doc.add_paragraph(line)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    base = PurePath(original_filename or "document.docx").stem
    safe_base = (base or "document").replace(" ", "_")
    out_name = f"{safe_base}_anonymized.docx"
    buffer.name = out_name

    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=buffer,
        filename=out_name,
        caption="Готово: анонимизированный документ.",
    )


async def _send_as_pdf(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    original_filename: str | None,
) -> None:
    """Возвращает анонимизированный текст в формате .pdf."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font_name = _register_pdf_font()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left_margin = 40
    right_margin = width - 40
    y = height - 40
    line_height = 14

    for paragraph in text.splitlines() or [""]:
        words = paragraph.split(" ")
        current = ""
        if not words:
            words = [""]

        for word in words:
            candidate = (current + " " + word).strip()
            if candidate and c.stringWidth(candidate, font_name, 11) <= (right_margin - left_margin):
                current = candidate
                continue

            if current:
                c.setFont(font_name, 11)
                c.drawString(left_margin, y, current)
                y -= line_height
                if y < 40:
                    c.showPage()
                    c.setFont(font_name, 11)
                    y = height - 40
            current = word

        if current:
            c.setFont(font_name, 11)
            c.drawString(left_margin, y, current)
            y -= line_height
        else:
            y -= line_height

        if y < 40:
            c.showPage()
            c.setFont(font_name, 11)
            y = height - 40

    c.save()
    buffer.seek(0)

    base = PurePath(original_filename or "document.pdf").stem
    safe_base = (base or "document").replace(" ", "_")
    out_name = f"{safe_base}_anonymized.pdf"
    buffer.name = out_name

    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=buffer,
        filename=out_name,
        caption="Готово: анонимизированный PDF.",
    )


def _register_pdf_font() -> str:
    """Регистрирует Unicode-шрифт для корректного вывода кириллицы в PDF."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    for path in candidates:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont("UnicodeFallback", path))
                return "UnicodeFallback"
            except Exception:
                continue

    # Если Unicode-шрифт не найден, останется базовый Helvetica.
    # На некоторых системах кириллица в этом случае может отображаться некорректно.
    return "Helvetica"


# --- Bootstrap ----------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = load_settings()
    anonymizer = Anonymizer(api_key=settings.openai_api_key, model=settings.openai_model)

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data["settings"] = settings
    app.bot_data["anonymizer"] = anonymizer

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot is starting (model=%s)…", settings.openai_model)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

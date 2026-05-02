# Анонимайзер данных — Telegram-бот

MVP экзаменационного проекта: Telegram-бот, который принимает текст или
документ (`.txt`, `.pdf`, `.docx`), находит в нём персональные данные
(ФИО, телефоны, email, ИИН/БИН, адреса, даты рождения, номера карт) и
заменяет их на безопасные плейсхолдеры (`[ИМЯ]`, `[ТЕЛЕФОН]`, …).

Если входной файл — `.docx` или `.pdf`, бот отправляет результат в том же формате
(`*_anonymized.docx` / `*_anonymized.pdf`).

> ⚠️ Если вы случайно поделились боевыми API-ключами в чате/коммите —
> отзовите их в [@BotFather](https://t.me/BotFather) и
> <https://platform.openai.com/api-keys>, выпустите новые и положите в `.env`.

## Структура

```
prediction_model/
├── src/
│   ├── bot.py           # точка входа — Telegram I/O
│   ├── anonymizer.py    # regex-предфильтр + вызов OpenAI
│   ├── extractors.py    # txt / pdf / docx → текст
│   ├── prompts.py       # system + user промпты
│   └── config.py        # загрузка .env
├── docs/
│   ├── architecture.md  # схема архитектуры (mermaid)
│   └── report_template.md
├── requirements.txt
├── .env.example
└── README.md
```

## Архитектура (кратко)

```
Telegram → Bot → Extractor (.pdf/.docx → текст) → Regex-предфильтр
        → OpenAI (gpt-4o-mini) → Анонимный текст → Telegram
                              ↘ logs/prompts.jsonl
```

Подробная схема — в [`docs/architecture.md`](docs/architecture.md).

## Запуск

```bash
# 1. создать виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate

# 2. установить зависимости
pip install -r requirements.txt

# 3. настроить ключи
cp .env.example .env
# отредактируй .env — впиши TELEGRAM_BOT_TOKEN и OPENAI_API_KEY

# 4. запустить бота
python -m src.bot
```

Если увидишь ошибку `TypeError: __init__() got an unexpected keyword argument 'proxies'`,
обнови зависимости с фиксацией `httpx`:

```bash
pip install --upgrade --force-reinstall -r requirements.txt
```

После запуска открой бота в Telegram (по нику, который ты задал в @BotFather),
напиши `/start` и пришли любой текст с персональными данными.

## Логи промптов

Все промпты и ответы LLM пишутся в `logs/prompts.jsonl`
(по одному JSON-объекту на строку). Этот файл нужен для сдачи задания
(«схема архитектуры + логи промптов»). В `.gitignore` он добавлен —
не коммить его, там может быть приватный текст.

Пример записи:

```json
{
  "ts": "2026-04-29T20:11:03Z",
  "user_id": 123456789,
  "source": "text",
  "model": "gpt-4o-mini",
  "system_prompt": "...",
  "user_prompt": "...",
  "response": "...",
  "usage": {"prompt_tokens": 412, "completion_tokens": 380, "total_tokens": 792}
}
```

## Что дальше

- [ ] Прогнать оценочный датасет и заполнить таблицу метрик в
      [`docs/report_template.md`](docs/report_template.md).
- [ ] Записать видео-демо: интервью, опрос, бот в работе.
- [ ] (Опционально) переключить LLM на локальную модель (Ollama + Llama 3 / Qwen)
      — снимет вопрос «данные уходят за границу».

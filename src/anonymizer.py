"""Ядро анонимизации.

Двухслойный подход:
1) Regex-предфильтр — гарантированно ловит структурные данные (телефон, email,
   ИИН/БИН, банковские карты, IBAN). Это быстро, дёшево и не зависит от LLM.
2) LLM-проход — ловит контекстные сущности, которые регуляркой не возьмёшь:
   ФИО, адреса, даты рождения, упоминания типа «мой паспорт ...».

Такой гибрид устойчивее, чем чистый LLM, и точнее, чем чистая regex-замена.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from .prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


# --- Regex-слой ---------------------------------------------------------------

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

# IBAN (упрощённо: 2 буквы + 2 цифры + 11–30 алфанум).
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")

# Банковские карты — 13–19 цифр, могут идти 4 группами по 4 (с пробелами/дефисами)
# или подряд. Порядок важен: карта матчится ДО ИИН и телефона.
_CARD_RE = re.compile(r"(?<!\d)(?:\d{4}[ \-]?){3}\d{1,7}(?!\d)")

# ИИН/БИН — ровно 12 цифр подряд, без разделителей.
_IIN_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")

# Телефон: + или цифра в начале + 10–15 цифр всего, разделители — пробел/дефис/скобки.
# Финальную фильтрацию делает callback (см. _phone_replace).
_PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d \-().]{8,20}\d(?!\w)")

# БИК/SWIFT банка: часто в формах как "БИК банка HSBKKZKX".
_BIC_RE = re.compile(r"(?i)\b(БИК(?:\s+банка)?\s*[:\-]?\s*)([A-Z0-9]{8,11})\b")

# Компании/юрлица: "ООО \"...\"", "ТОО \"...\"", "ИП Иванов И.И.".
_ORG_RE = re.compile(
    r"\b(?:ООО|ТОО|АО|ИП|LLP|JSC)\s+(?:\"[^\"]+\"|«[^»]+»|[A-Za-zА-Яа-я0-9 .-]{2,})"
)

# Адресные конструкции (практический паттерн для RU/KZ): "г. Алматы, ул. Абая 142, кв. 37".
_ADDRESS_RE = re.compile(
    r"(?i)\b(?:г\.\s*[А-Яа-яA-Za-z\-]+,\s*)?(?:ул\.|улица|проспект|пр-т|мкр\.?)\s*"
    r"[А-Яа-яA-Za-z0-9 .\-]+(?:,\s*(?:д\.?|дом)\s*\d+[А-Яа-яA-Za-z0-9/-]*)?"
    r"(?:,\s*(?:кв\.?|квартира)\s*\d+)?"
)


def _phone_replace(match: "re.Match[str]") -> str:
    s = match.group(0)
    digits = re.sub(r"\D", "", s)
    has_separator = any(c in " -().+" for c in s)
    if 10 <= len(digits) <= 15 and has_separator:
        return "[ТЕЛЕФОН]"
    return s


def regex_prefilter(text: str) -> str:
    """Заменяет структурные ПД на плейсхолдеры до отправки в LLM.

    Порядок применения важен: сначала самые «жёсткие» паттерны (email, IBAN,
    карта, ИИН), потом более «свободный» — телефон. Так мы не съедаем 12-значный
    ИИН телефонной регуляркой и наоборот.
    """
    out = text
    out = _EMAIL_RE.sub("[EMAIL]", out)
    out = _IBAN_RE.sub("[СЧЁТ]", out)
    out = _CARD_RE.sub("[СЧЁТ]", out)
    out = _IIN_RE.sub("[ИИН]", out)
    out = _PHONE_RE.sub(_phone_replace, out)
    out = _BIC_RE.sub(r"\1[БИК]", out)
    out = _ORG_RE.sub("[ОРГАНИЗАЦИЯ]", out)
    out = _ADDRESS_RE.sub("[АДРЕС]", out)
    return out


# --- LLM-слой -----------------------------------------------------------------


@dataclass
class AnonymizeResult:
    text: str
    model: str
    prompt_log: dict = field(default_factory=dict)


class Anonymizer:
    """Тонкая обёртка над OpenAI Chat Completions с логированием промптов.

    Логи промптов нужны по требованию задания («схема архитектуры + логи промптов»).
    """

    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def anonymize(self, text: str) -> AnonymizeResult:
        pre = regex_prefilter(text)
        user_prompt = build_user_prompt(pre)

        logger.info("LLM call: model=%s, input_chars=%d", self._model, len(pre))

        response = await self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        cleaned = (response.choices[0].message.content or "").strip()

        prompt_log = {
            "model": self._model,
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "response": cleaned,
            "usage": getattr(response, "usage", None) and {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        }

        return AnonymizeResult(text=cleaned, model=self._model, prompt_log=prompt_log)

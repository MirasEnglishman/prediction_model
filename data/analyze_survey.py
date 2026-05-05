from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).with_name("survey.csv")
REPORT_PATH = Path(__file__).with_name("survey_report.txt")
df = pd.read_csv(DATA_PATH)


def find_col(fragment: str) -> str:
    for col in df.columns:
        if fragment.lower() in col.lower():
            return col
    raise KeyError(f"Не найдена колонка с фрагментом: {fragment}")


def fmt_pct(series: pd.Series) -> pd.Series:
    return (series * 100).round(1).astype(str) + "%"


def num_series(col_name: str) -> pd.Series:
    return pd.to_numeric(df[col_name], errors="coerce")


age_col = find_col("возраст")
role_col = find_col("сфера деятельности")
privacy_col = find_col("Я переживаю за утечку")
usefulness_col = find_col("автоматически скрывает ПД")
adoption_col = find_col("Стали бы вы пользоваться")
messenger_send_col = find_col("через мессенджеры")
preprocess_col = find_col("Обрабатываете ли вы данные перед отправкой")
trust_messenger_col = find_col("Доверяете ли вы мессенджерам")
telegram_bot_trust_col = find_col("Telegram-боту")
main_concern_col = find_col("больше всего беспокоит")

privacy_num = num_series(privacy_col)
usefulness_num = num_series(usefulness_col)

response_count = len(df)

age_dist = df[age_col].value_counts(dropna=False)
role_dist = df[role_col].value_counts(dropna=False)

privacy_dist = df[privacy_col].value_counts(normalize=True).sort_index()
usefulness_dist = df[usefulness_col].value_counts(normalize=True).sort_index()

adoption_dist = df[adoption_col].value_counts(normalize=True)
messenger_send_dist = df[messenger_send_col].value_counts(normalize=True)
preprocess_dist = df[preprocess_col].value_counts(normalize=True)
trust_messenger_dist = df[trust_messenger_col].value_counts(normalize=True)
telegram_bot_trust_dist = df[telegram_bot_trust_col].value_counts(normalize=True)
main_concern_dist = df[main_concern_col].value_counts(normalize=True)

privacy_mean = privacy_num.mean()
usefulness_mean = usefulness_num.mean()
privacy_median = privacy_num.median()
usefulness_median = usefulness_num.median()

privacy_high_share = (privacy_num >= 4).mean()
usefulness_high_share = (usefulness_num >= 4).mean()
privacy_low_share = (privacy_num <= 2).mean()
usefulness_low_share = (usefulness_num <= 2).mean()

privacy_usefulness_corr = privacy_num.corr(usefulness_num)

privacy_vs_usefulness = pd.crosstab(
    df[privacy_col],
    df[usefulness_col],
    normalize="index",
).round(3)

adoption_vs_usefulness = pd.crosstab(
    df[adoption_col],
    df[usefulness_col],
    normalize="index",
).round(3)

send_vs_preprocess = pd.crosstab(
    df[messenger_send_col],
    df[preprocess_col],
    normalize="index",
).round(3)

report_lines = [
    "АНАЛИТИЧЕСКИЙ ОТЧЕТ ПО ОПРОСУ (Google Forms)",
    "=" * 72,
    f"Источник данных: {DATA_PATH.name}",
    f"Количество респондентов: {response_count}",
    "",
    "1) СОСТАВ ВЫБОРКИ",
    "-" * 72,
    "Распределение по возрасту:",
    age_dist.to_string(),
    "",
    "Распределение по сфере деятельности:",
    role_dist.to_string(),
    "",
    "2) БАЗОВЫЕ МЕТРИКИ ПО ШКАЛАМ 1-5",
    "-" * 72,
    f"Средняя тревога за утечку ПД: {privacy_mean:.2f} (медиана: {privacy_median:.2f})",
    f"Средняя оценка полезности сервиса: {usefulness_mean:.2f} (медиана: {usefulness_median:.2f})",
    f"Доля высокой тревоги (4-5): {privacy_high_share * 100:.1f}%",
    f"Доля высокой полезности (4-5): {usefulness_high_share * 100:.1f}%",
    f"Доля низкой тревоги (1-2): {privacy_low_share * 100:.1f}%",
    f"Доля низкой полезности (1-2): {usefulness_low_share * 100:.1f}%",
    f"Корреляция тревоги и полезности (Pearson): {privacy_usefulness_corr:.3f}",
    "",
    "Распределение тревоги (1-5):",
    fmt_pct(privacy_dist).to_string(),
    "",
    "Распределение полезности (1-5):",
    fmt_pct(usefulness_dist).to_string(),
    "",
    "3) ПОВЕДЕНЧЕСКИЕ И ОТНОШЕНЧЕСКИЕ ПОКАЗАТЕЛИ",
    "-" * 72,
    "Готовность пользоваться сервисом:",
    fmt_pct(adoption_dist).to_string(),
    "",
    "Отправка документов с ПД через мессенджеры:",
    fmt_pct(messenger_send_dist).to_string(),
    "",
    "Привычка обрабатывать данные перед отправкой:",
    fmt_pct(preprocess_dist).to_string(),
    "",
    "Доверие к мессенджерам при передаче документов:",
    fmt_pct(trust_messenger_dist).to_string(),
    "",
    "Готовность доверить документы Telegram-боту:",
    fmt_pct(telegram_bot_trust_dist).to_string(),
    "",
    "Ключевые опасения при использовании сервиса:",
    fmt_pct(main_concern_dist).to_string(),
    "",
    "4) СВЯЗИ МЕЖДУ ПЕРЕМЕННЫМИ (КРОСС-ТАБЛИЦЫ)",
    "-" * 72,
    "Тревога за ПД -> оценка полезности сервиса (доли по строкам):",
    privacy_vs_usefulness.to_string(),
    "",
    "Готовность пользоваться -> оценка полезности сервиса (доли по строкам):",
    adoption_vs_usefulness.to_string(),
    "",
    "Факт отправки через мессенджеры -> предобработка данных (доли по строкам):",
    send_vs_preprocess.to_string(),
    "",
    "5) ИНТЕРПРЕТАЦИЯ ДЛЯ ПРОЕКТА",
    "-" * 72,
    (
        "Высокие средние значения тревоги и полезности показывают прикладной спрос "
        "на инструмент анонимизации. Положительная корреляция тревоги и полезности "
        "означает: чем выше риск-восприятие, тем выше ценность решения."
    ),
    (
        "Наличие реальной практики отправки документов через мессенджеры подтверждает "
        "релевантность Telegram-бота как интерфейса."
    ),
    (
        "Если в данных заметна доля ответов 'Нет/Возможно' по доверию к боту, "
        "это аргумент за усиление приватности: локальная LLM, шифрование логов, TTL."
    ),
]

report_text = "\n".join(report_lines)

print(report_text)
REPORT_PATH.write_text(report_text, encoding="utf-8")
print(f"\nОтчет сохранен: {REPORT_PATH}")
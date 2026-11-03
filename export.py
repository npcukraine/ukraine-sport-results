import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

EVENT_NAMES = {
    "чс": "Чемпіонат світу", "мт": "Міжнародний турнір",
    "кє": "Кубок Європи", "кс": "Кубок світу",
    "пі": "Паралімпійські ігри", "чє": "Чемпіонат Європи",
    "ємі": "Європейські молодіжні ігри", "мз": "Міжнародні змагання",
}
EVENT_NAMES.update({name.casefold(): name for name in EVENT_NAMES.values()})
COUNTRY_NAMES = {
    "узбекістан": "Узбекистан", "узбекистан": "Узбекистан",
    "тайланд": "Таїланд", "таїланд": "Таїланд",
    "великобританія": "Велика Британія", "велика британія": "Велика Британія",
}


def normalize_dates(value):
    if not value:
        return "", "", ""
    cleaned = re.sub(r"\s+", "", value)
    cleaned = re.sub(r"[.,/]*[-–—]+", "-", cleaned)
    parts = re.split("-", re.sub(r"[,/]", ".", cleaned))
    try:
        if len(parts) not in (1, 2):
            raise ValueError
        day, month, year = parts[-1].split(".")
        year = "20" + year if len(year) == 2 else year
        if len(year) != 4:
            raise ValueError
        end = date(int(year), int(month), int(day))
        if len(parts) == 1:
            return end.strftime("%d.%m.%Y"), end.isoformat(), end.isoformat()
        first = parts[0].split(".")
        if len(first) > 3:
            raise ValueError
        start_year = int(first[2]) if len(first) == 3 else end.year
        if len(first) == 3 and len(first[2]) == 2:
            start_year += 2000
        start = date(start_year, int(first[1]) if len(first) > 1 else end.month, int(first[0]))
        if start > end:
            raise ValueError
        prefix = "%d.%m.%Y" if start.year != end.year else "%d.%m" if start.month != end.month else "%d"
        label = f"{start.strftime(prefix)}–{end.strftime('%d.%m.%Y')}"
        return label, start.isoformat(), end.isoformat()
    except ValueError:
        return "Дата потребує уточнення", "", ""


credentials = Credentials.from_service_account_info(
    json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"]),
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
)
sheet_id = quote(os.environ["GOOGLE_SHEET_ID"], safe="")
range_name = quote("'Результати'!A1:N", safe="")
response = AuthorizedSession(credentials).get(
    f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{range_name}",
    timeout=30,
)
response.raise_for_status()
header, *rows = response.json()["values"]
expected = ["Назва заходу", "Вид спорту", "Нозологія / нозології",
            "Дати за джерелом", "Країна", "Місто"]
alternate = expected[:3] + ["Дати заходу"] + expected[4:]
if header[:6] not in (expected, alternate) or header[9:12] != ["Золото", "Срібло", "Бронза"]:
    raise ValueError("Перевірте назви й порядок колонок.")
event_id_column = header.index("ID події") if "ID події" in header else None
results = []
for index, row in enumerate(rows, 2):
    row = [" ".join(value.split()) for value in (row + [""] * 14)[:14]]
    if not row[0].strip() or not any(row[9:12]):
        continue
    record = dict(zip(("event", "sport", "group", "dates", "country", "city"), row[:6]))
    record["eventSource"] = record["event"]
    event = record["event"]
    prefix = re.match(r"^\w+(?=$|[\s.:,–—-])", event)
    record["event"] = EVENT_NAMES.get(event.casefold(), event)
    if prefix and prefix.group().casefold() in EVENT_NAMES:
        record["event"] = EVENT_NAMES[prefix.group().casefold()] + event[prefix.end():]
    country = record["country"]
    record["country"] = COUNTRY_NAMES.get(country.casefold(), country)
    record["dates"], record["startDate"], record["endDate"] = normalize_dates(record["dates"])
    if record["dates"] == "Дата потребує уточнення":
        print(f"Рядок {index}: дата потребує уточнення")
    if record["country"] in {"Корея", "Боснія"}:
        print(f"Рядок {index}: країна потребує уточнення")
    record["eventId"] = row[event_id_column] if event_id_column is not None else ""
    for key, value in zip(("gold", "silver", "bronze"), row[9:12]):
        if value and not value.isdecimal():
            raise ValueError(f"Рядок {index}: медалі мають бути цілим невід'ємним числом.")
        record[key] = int(value) if value else None
    results.append(record)
Path("site/results.json").write_text(
    json.dumps({"updatedAt": datetime.now(timezone.utc).isoformat(), "results": results},
               ensure_ascii=False),
    encoding="utf-8",
)


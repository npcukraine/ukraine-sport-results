import json
import os
from pathlib import Path
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

credentials = Credentials.from_service_account_info(
    json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"]),
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
)
sheet_id = quote(os.environ["GOOGLE_SHEET_ID"], safe="")
range_name = quote("'Результати'!A1:M", safe="")
response = AuthorizedSession(credentials).get(
    f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{range_name}",
    timeout=30,
)
response.raise_for_status()
header, *rows = response.json()["values"]
expected = ["Назва заходу", "Вид спорту", "Нозологія / нозології",
            "Дати за джерелом", "Країна", "Місто"]
if header[:6] != expected or header[9:12] != ["Золото", "Срібло", "Бронза"]:
    raise ValueError("Перевірте назви й порядок колонок.")
results = []
for index, row in enumerate(rows, 2):
    row = (row + [""] * 13)[:13]
    if not row[0].strip() or not any(row[9:12]):
        continue
    record = dict(zip(("event", "sport", "group", "dates", "country", "city"), row[:6]))
    for key, value in zip(("gold", "silver", "bronze"), row[9:12]):
        if value and not value.isdecimal():
            raise ValueError(f"Рядок {index}: медалі мають бути цілим невід'ємним числом.")
        record[key] = int(value) if value else None
    results.append(record)
from datetime import datetime, timezone

Path("site/results.json").write_text(
    json.dumps({"updatedAt": datetime.now(timezone.utc).isoformat(), "results": results},
               ensure_ascii=False),
    encoding="utf-8",
)


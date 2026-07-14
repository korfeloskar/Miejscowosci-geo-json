"""Audyt pól GeoJSON w tabeli Obsługiwane."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from collections import Counter

from airtable_config import (
    BASE_ID,
    GEOJSON_ATTACHMENT_FIELD,
    GEOJSON_FIELD,
    GEOJSON_STATUS_FIELD,
    MAPA_ZBIORCZA_NAZWA,
    OBSLOGIWANE_TABLE,
)

PAT = os.environ["AIRTABLE_PAT"]
H = {"Authorization": f"Bearer {PAT}"}
URL = f"https://api.airtable.com/v0/{BASE_ID}/{urllib.parse.quote(OBSLOGIWANE_TABLE)}"


def main() -> None:
    status = Counter()
    geo_lens: list[int] = []
    attachments = 0
    offset = None
    total = 0
    sample_ok: dict | None = None

    while True:
        params = [
            "pageSize=100",
            "fields%5B%5D=nazwa",
            f"fields%5B%5D={urllib.parse.quote(GEOJSON_FIELD)}",
            f"fields%5B%5D={urllib.parse.quote(GEOJSON_STATUS_FIELD)}",
            f"fields%5B%5D={urllib.parse.quote(GEOJSON_ATTACHMENT_FIELD)}",
        ]
        if offset:
            params.append(f"offset={offset}")
        data = json.loads(
            urllib.request.urlopen(urllib.request.Request(f"{URL}?{'&'.join(params)}", headers=H)).read()
        )
        for rec in data["records"]:
            total += 1
            fields = rec["fields"]
            s = fields.get(GEOJSON_STATUS_FIELD) or "(brak statusu)"
            status[s] += 1
            geo = fields.get(GEOJSON_FIELD) or ""
            if geo:
                geo_lens.append(len(geo))
                if sample_ok is None and s == "ok":
                    sample_ok = {"nazwa": fields.get("nazwa"), "len": len(geo), "head": geo[:150]}
            att = fields.get(GEOJSON_ATTACHMENT_FIELD) or []
            if att:
                attachments += 1
                if fields.get("nazwa") in (MAPA_ZBIORCZA_NAZWA, "41-300"):
                    print(
                        "Załącznik:",
                        fields.get("nazwa"),
                        s,
                        [a.get("filename") for a in att],
                    )
        offset = data.get("offset")
        if not offset:
            break

    print(f"Rekordów: {total}")
    print("GeoJSON status:")
    for k, v in sorted(status.items(), key=lambda x: -x[1]):
        print(f"  {v:4d}  {k}")
    print(f"Pole GeoJSON wypełnione: {len(geo_lens)}")
    print(f"Rekordów z załącznikiem GeoJSON plik: {attachments}")
    if geo_lens:
        print(f"Długość JSON: min={min(geo_lens)} max={max(geo_lens)} avg={sum(geo_lens)//len(geo_lens)}")
    if sample_ok:
        print("Przykład OK:", sample_ok)


if __name__ == "__main__":
    main()

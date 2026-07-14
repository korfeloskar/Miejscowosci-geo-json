"""Mapa miejscowości (scalone poligony) → GeoJSON pod Framer.

Grupuje kody pocztowe po nazwie miasta z pola `miasto mapa`.
Przy wielu strefach w jednej miejscowości wygrywa niższa strefa (STREFA 0 < 1 < …).

  python build_miejscowosci_map.py
  python build_miejscowosci_map.py --upload
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

from airtable_config import (
    BASE_ID,
    GEOJSON_ATTACHMENT_FIELD,
    GEOJSON_STATUS_FIELD,
    MAPA_ZBIORCZA_NAZWA,
    OBSLOGIWANE_TABLE,
    OBSLOGIWANE_TABLE_ID,
)
from geojson_utils import (
    color_for_rank,
    first_lookup,
    format_price,
    index_geojson_by_code,
    merge_geometries,
    normalize_code,
    parse_city_name,
    strefa_label,
    strefa_rank,
)
from sync_postcodes_geojson import SLASKIE_GEOJSON, download_slaskie_geojson

PAT = os.environ.get("AIRTABLE_PAT", "")
API = f"https://api.airtable.com/v0/{BASE_ID}"
META = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}"
DATA_DIR = Path(__file__).resolve().parent / "data" / "postcodes"
FRAMER_DIR = Path(__file__).resolve().parent / "framer"
PUBLIC_DIR = Path(__file__).resolve().parent / "public"
MIASTA_OUT = DATA_DIR / "miejscowosci-polska.geojson"
PUBLIC_OUT = PUBLIC_DIR / "miejscowosci-polska.geojson"
POLSKA_OUT = FRAMER_DIR / "polska-wojewodztwa.geojson"
MAPA_MIEJSCOWOSCI_NAZWA = "=== MAPA MIEJSCOWOSCI ==="
POLSKA_WOJ_URL = (
    "https://raw.githubusercontent.com/andilabs/polska-wojewodztwa-geojson/master/"
    "polska-wojewodztwa.geojson"
)


def request(method: str, url: str, body: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(exc.read().decode()) from exc


def list_all_records(fields: list[str]) -> list[dict]:
    url = f"{API}/{urllib.parse.quote(OBSLOGIWANE_TABLE)}"
    records: list[dict] = []
    offset = None
    while True:
        params = ["pageSize=100"]
        if offset:
            params.append(f"offset={offset}")
        for field in fields:
            params.append(f"fields%5B%5D={urllib.parse.quote(field)}")
        data = request("GET", f"{url}?{'&'.join(params)}")
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


def ensure_polska_outline() -> None:
    FRAMER_DIR.mkdir(parents=True, exist_ok=True)
    if POLSKA_OUT.exists() and POLSKA_OUT.stat().st_size > 10_000:
        return
    print(f"Pobieram kontur Polski: {POLSKA_WOJ_URL}")
    req = urllib.request.Request(POLSKA_WOJ_URL, headers={"User-Agent": "PBS-MiejscowosciMap/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        POLSKA_OUT.write_bytes(resp.read())
    print(f"Zapisano {POLSKA_OUT} ({POLSKA_OUT.stat().st_size // 1024} KB)")


def build_city_features(rows: list[dict], by_code: dict[str, list[dict]]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        fields = row["fields"]
        code = normalize_code(fields.get("nazwa", ""))
        city_label = first_lookup(fields.get("miasto mapa"))
        if not code or not city_label:
            continue
        city = parse_city_name(city_label)
        kolor = first_lookup(fields.get("Kolor"))
        strefa = first_lookup(fields.get("Notes (from Table 8)"))
        koszt = first_lookup(fields.get("Koszt"))
        brutto = fields.get("Brutto")
        rank = strefa_rank(strefa, kolor)
        source = by_code.get(code)
        if not source:
            continue
        geometry = merge_geometries([f["geometry"] for f in source])
        if not geometry:
            continue
        grouped[city].append(
            {
                "code": code,
                "rank": rank,
                "kolor": kolor,
                "strefa": strefa or strefa_label(rank),
                "koszt_netto": koszt,
                "brutto": brutto,
                "geometry": geometry,
            }
        )

    features: list[dict] = []
    for city, items in sorted(grouped.items()):
        best_rank = min(item["rank"] for item in items)
        winning = next(item for item in items if item["rank"] == best_rank)
        winning_color = color_for_rank(best_rank, fallback=winning["kolor"])
        winning_strefa = strefa_label(best_rank)
        geometry = merge_geometries([item["geometry"] for item in items])
        if not geometry:
            continue
        codes = sorted({item["code"] for item in items})
        by_code_price: dict[str, dict] = {}
        for item in sorted(items, key=lambda x: x["code"]):
            if item["code"] not in by_code_price:
                by_code_price[item["code"]] = {
                    "kod": item["code"],
                    "dojazd_netto": format_price(item.get("koszt_netto")),
                    "dojazd_brutto": format_price(item.get("brutto")),
                }
        kody_dojazd = list(by_code_price.values())
        dojazd_netto = format_price(winning.get("koszt_netto"))
        dojazd_brutto = format_price(winning.get("brutto"))
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "miasto": city,
                    "kolor": winning_color,
                    "strefa": winning_strefa,
                    "strefa_rank": best_rank,
                    "dojazd_netto": dojazd_netto,
                    "dojazd_brutto": dojazd_brutto,
                    "kody_count": len(codes),
                    "kody": ",".join(codes[:12]) + ("…" if len(codes) > 12 else ""),
                    "kody_dojazd": json.dumps(kody_dojazd, ensure_ascii=False, separators=(",", ":")),
                },
            }
        )
    return features


def ensure_map_record(name: str) -> str:
    rows = list_all_records(["nazwa"])
    for row in rows:
        if row["fields"].get("nazwa") == name:
            return row["id"]
    created = request(
        "POST",
        f"{API}/{urllib.parse.quote(OBSLOGIWANE_TABLE)}",
        {"records": [{"fields": {"nazwa": name}}], "typecast": True},
    )
    return created["records"][0]["id"]


def ensure_attachment_field() -> None:
    schema = request("GET", f"{META}/tables")
    table = next(t for t in schema["tables"] if t["id"] == OBSLOGIWANE_TABLE_ID)
    if any(f["name"] == GEOJSON_ATTACHMENT_FIELD for f in table["fields"]):
        return
    request(
        "POST",
        f"{META}/tables/{OBSLOGIWANE_TABLE_ID}/fields",
        {"name": GEOJSON_ATTACHMENT_FIELD, "type": "multipleAttachments"},
    )
    time.sleep(0.3)


def upload_attachment(record_id: str, path: Path) -> None:
    payload = {
        "contentType": "application/geo+json",
        "filename": path.name,
        "file": base64.b64encode(path.read_bytes()).decode("ascii"),
    }
    url = (
        f"https://content.airtable.com/v0/{BASE_ID}/{record_id}/"
        f"{urllib.parse.quote(GEOJSON_ATTACHMENT_FIELD)}/uploadAttachment"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        resp.read()


def upload_to_airtable(path: Path) -> None:
    if not PAT:
        sys.exit("AIRTABLE_PAT is not set.")
    ensure_attachment_field()
    rec_id = ensure_map_record(MAPA_MIEJSCOWOSCI_NAZWA)
    upload_attachment(rec_id, path)
    request(
        "PATCH",
        f"{API}/{urllib.parse.quote(OBSLOGIWANE_TABLE)}",
        {
            "records": [
                {
                    "id": rec_id,
                    "fields": {
                        GEOJSON_STATUS_FIELD: f"mapa miejscowości ({path.stat().st_size // 1024} KB)",
                    },
                }
            ],
            "typecast": True,
        },
    )
    print(f"Załączono {path.name} -> rekord «{MAPA_MIEJSCOWOSCI_NAZWA}»")


def main() -> None:
    parser = argparse.ArgumentParser(description="Buduje mapę miejscowości (GeoJSON) pod Framer")
    parser.add_argument("--upload", action="store_true", help="Wgraj GeoJSON do Airtable jako załącznik")
    args = parser.parse_args()

    if args.upload and not PAT:
        sys.exit("AIRTABLE_PAT is not set.")

    ensure_polska_outline()
    download_slaskie_geojson()
    if not SLASKIE_GEOJSON.exists():
        sys.exit(f"Brak pliku: {SLASKIE_GEOJSON}")

    if not PAT:
        sys.exit("AIRTABLE_PAT is not set.")

    by_code = index_geojson_by_code(SLASKIE_GEOJSON)
    rows = list_all_records(
        ["nazwa", "miasto mapa", "Kolor", "Notes (from Table 8)", "Koszt", "Brutto", "GeoJSON status"]
    )
    features = build_city_features(rows, by_code)

    MIASTA_OUT.parent.mkdir(parents=True, exist_ok=True)
    collection = {"type": "FeatureCollection", "features": features}
    blob = json.dumps(collection, ensure_ascii=False)
    MIASTA_OUT.write_text(blob, encoding="utf-8")
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_OUT.write_text(blob, encoding="utf-8")

    size_kb = MIASTA_OUT.stat().st_size // 1024
    print(f"Miejscowości z poligonem: {len(features)}")
    print(f"Zapisano: {MIASTA_OUT} ({size_kb} KB)")
    print(f"Public (GitHub): {PUBLIC_OUT}")
    print()
    print("URL do Framera (GitHub raw, branch master):")
    print("  https://raw.githubusercontent.com/korfeloskar/Miejscowosci-geo-json/master/public/miejscowosci-polska.geojson")
    print("Przyklady:")
    for feat in features[:8]:
        props = feat["properties"]
        print(f"  {props['miasto']} — {props['strefa']}, dojazd {props.get('dojazd_netto')} / {props.get('dojazd_brutto')}")

    katowice = next((f for f in features if f["properties"]["miasto"] == "Katowice"), None)
    if katowice:
        p = katowice["properties"]
        print(f"Katowice: {p['strefa']} / dojazd {p['dojazd_netto']} / {p['dojazd_brutto']}")

    if args.upload:
        upload_to_airtable(MIASTA_OUT)


if __name__ == "__main__":
    main()

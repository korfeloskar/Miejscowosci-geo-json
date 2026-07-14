"""GeoJSON kodów pocztowych (PostCodesMaps) → Airtable Obsługiwane.

Źródło poligonów: https://github.com/GML22/PostCodesMaps (PRG, woj. śląskie).
Kody: tabela 🚗 Obsługiwane (pole nazwa, format XX-XXX).

  python sync_postcodes_geojson.py
  python sync_postcodes_geojson.py --dry-run
  python sync_postcodes_geojson.py --download-only
  python sync_postcodes_geojson.py --upload-map-only
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
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
    GEOJSON_FIELD,
    GEOJSON_STATUS_FIELD,
    MAPA_ZBIORCZA_NAZWA,
    OBSLOGIWANE_TABLE,
    OBSLOGIWANE_TABLE_ID,
    POSTCODES_MAPS_SLASKIE_URL,
)

PAT = os.environ.get("AIRTABLE_PAT", "")
API = f"https://api.airtable.com/v0/{BASE_ID}"
META = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}"
DATA_DIR = Path(__file__).resolve().parent / "data" / "postcodes"
SLASKIE_GEOJSON = DATA_DIR / "24_SLASKIE_ALL_PC_4326.geojson"
COMBINED_OUT = DATA_DIR / "obslugiwane-choropleth.geojson"
CODE_RE = re.compile(r"^(\d{2}-\d{3})$")


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


def list_all_records(table: str, fields: list[str] | None = None) -> list[dict]:
    url = f"{API}/{urllib.parse.quote(table)}"
    records: list[dict] = []
    offset = None
    while True:
        params = ["pageSize=100"]
        if offset:
            params.append(f"offset={offset}")
        if fields:
            for field in fields:
                params.append(f"fields%5B%5D={urllib.parse.quote(field)}")
        data = request("GET", f"{url}?{'&'.join(params)}")
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


def patch_batch(updates: list[tuple[str, dict]], *, dry_run: bool) -> int:
    if not updates:
        return 0
    if dry_run:
        return len(updates)
    url = f"{API}/{urllib.parse.quote(OBSLOGIWANE_TABLE)}"
    count = 0
    for i in range(0, len(updates), 10):
        batch = updates[i : i + 10]
        request(
            "PATCH",
            url,
            {
                "records": [{"id": rid, "fields": fields} for rid, fields in batch],
                "typecast": True,
            },
        )
        count += len(batch)
        time.sleep(0.22)
    return count


def ensure_text_field(table_id: str, name: str) -> None:
    schema = request("GET", f"{META}/tables")
    table = next(t for t in schema["tables"] if t["id"] == table_id)
    if any(f["name"] == name for f in table["fields"]):
        return
    request(
        "POST",
        f"{META}/tables/{table_id}/fields",
        {"name": name, "type": "singleLineText" if name == GEOJSON_STATUS_FIELD else "multilineText"},
    )
    time.sleep(0.3)
    print(f"Utworzono pole: {name}")


def ensure_attachment_field(table_id: str, name: str) -> None:
    schema = request("GET", f"{META}/tables")
    table = next(t for t in schema["tables"] if t["id"] == table_id)
    if any(f["name"] == name for f in table["fields"]):
        return
    request(
        "POST",
        f"{META}/tables/{table_id}/fields",
        {"name": name, "type": "multipleAttachments"},
    )
    time.sleep(0.3)
    print(f"Utworzono pole: {name}")


def upload_attachment(record_id: str, field_name: str, path: Path, *, content_type: str) -> None:
    payload = {
        "contentType": content_type,
        "filename": path.name,
        "file": base64.b64encode(path.read_bytes()).decode("ascii"),
    }
    url = (
        f"https://content.airtable.com/v0/{BASE_ID}/{record_id}/"
        f"{urllib.parse.quote(field_name)}/uploadAttachment"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(exc.read().decode()) from exc


def ensure_map_record() -> str:
    rows = list_all_records(OBSLOGIWANE_TABLE, fields=["nazwa"])
    for row in rows:
        if row["fields"].get("nazwa") == MAPA_ZBIORCZA_NAZWA:
            return row["id"]
    created = request(
        "POST",
        f"{API}/{urllib.parse.quote(OBSLOGIWANE_TABLE)}",
        {"records": [{"fields": {"nazwa": MAPA_ZBIORCZA_NAZWA}}], "typecast": True},
    )
    return created["records"][0]["id"]


def upload_combined_map_attachment() -> None:
    if not COMBINED_OUT.exists():
        raise RuntimeError(f"Brak pliku: {COMBINED_OUT}")
    size_mb = COMBINED_OUT.stat().st_size / 1024 / 1024
    if size_mb > 5:
        raise RuntimeError(f"Plik {COMBINED_OUT.name} ma {size_mb:.1f} MB — limit uploadAttachment to 5 MB")
    ensure_attachment_field(OBSLOGIWANE_TABLE_ID, GEOJSON_ATTACHMENT_FIELD)
    rec_id = ensure_map_record()
    upload_attachment(rec_id, GEOJSON_ATTACHMENT_FIELD, COMBINED_OUT, content_type="application/geo+json")
    request(
        "PATCH",
        f"{API}/{urllib.parse.quote(OBSLOGIWANE_TABLE)}",
        {
            "records": [
                {
                    "id": rec_id,
                    "fields": {
                        GEOJSON_STATUS_FIELD: f"mapa zbiorcza ({COMBINED_OUT.stat().st_size // 1024} KB)",
                    },
                }
            ],
            "typecast": True,
        },
    )
    print(f"Załączono mapę zbiorczą → rekord «{MAPA_ZBIORCZA_NAZWA}» ({size_mb:.2f} MB)")


def download_slaskie_geojson() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SLASKIE_GEOJSON.exists() and SLASKIE_GEOJSON.stat().st_size > 1_000_000:
        print(f"GeoJSON już jest: {SLASKIE_GEOJSON}")
        return
    print(f"Pobieram {POSTCODES_MAPS_SLASKIE_URL} …")
    req = urllib.request.Request(POSTCODES_MAPS_SLASKIE_URL, headers={"User-Agent": "PBS-PostCodesSync/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        SLASKIE_GEOJSON.write_bytes(resp.read())
    print(f"Zapisano {SLASKIE_GEOJSON} ({SLASKIE_GEOJSON.stat().st_size // 1024 // 1024} MB)")


def normalize_code(value: str) -> str | None:
    value = (value or "").strip()
    m = CODE_RE.match(value)
    if m:
        return m.group(1)
    m = re.match(r"^(\d{2}-\d{3})", value)
    return m.group(1) if m else None


def polygon_coords(geometry: dict) -> list:
    gtype = geometry.get("type")
    if gtype == "Polygon":
        return [geometry["coordinates"]]
    if gtype == "MultiPolygon":
        return geometry["coordinates"]
    return []


def merge_features(features: list[dict]) -> dict:
    if len(features) == 1:
        return features[0]
    polys: list = []
    for feat in features:
        polys.extend(polygon_coords(feat["geometry"]))
    base = dict(features[0])
    if len(polys) == 1:
        base["geometry"] = {"type": "Polygon", "coordinates": polys[0]}
    else:
        base["geometry"] = {"type": "MultiPolygon", "coordinates": polys}
    return base


def index_geojson_by_code(path: Path) -> dict[str, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    by_code: dict[str, list[dict]] = defaultdict(list)
    for feat in data.get("features") or []:
        code = normalize_code(str(feat.get("properties", {}).get("Name", "")))
        if code:
            by_code[code].append(feat)
    return by_code


def first_lookup(values: list | None) -> str:
    if not values:
        return ""
    return str(values[0]).strip()


def build_feature(code: str, source_feats: list[dict], row: dict) -> dict:
    merged = merge_features(source_feats)
    props = dict(merged.get("properties") or {})
    fields = row["fields"]
    props.update(
        {
            "kod": code,
            "kolor": first_lookup(fields.get("Kolor")),
            "strefa": first_lookup(fields.get("Notes (from Table 8)")),
            "koszt_netto": first_lookup(fields.get("Koszt")),
            "brutto": fields.get("Brutto"),
            "miasto": first_lookup(fields.get("miasto mapa")),
        }
    )
    return {"type": "Feature", "geometry": merged["geometry"], "properties": props}


def load_obslugiwane_rows() -> list[dict]:
    return list_all_records(
        OBSLOGIWANE_TABLE,
        fields=["nazwa", "Kolor", "Notes (from Table 8)", "Koszt", "Brutto", "miasto mapa"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync PostCodesMaps GeoJSON → Airtable")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--upload-map-only", action="store_true", help="Tylko załącznik mapy zbiorczej")
    args = parser.parse_args()

    if not PAT and not args.dry_run:
        sys.exit("AIRTABLE_PAT is not set.")

    download_slaskie_geojson()
    if args.download_only:
        return

    if args.upload_map_only:
        ensure_attachment_field(OBSLOGIWANE_TABLE_ID, GEOJSON_ATTACHMENT_FIELD)
        if not COMBINED_OUT.exists():
            sys.exit(f"Brak {COMBINED_OUT} — uruchom pełny sync najpierw.")
        upload_combined_map_attachment()
        return

    if not args.dry_run:
        ensure_text_field(OBSLOGIWANE_TABLE_ID, GEOJSON_FIELD)
        ensure_text_field(OBSLOGIWANE_TABLE_ID, GEOJSON_STATUS_FIELD)
        ensure_attachment_field(OBSLOGIWANE_TABLE_ID, GEOJSON_ATTACHMENT_FIELD)

    by_code = index_geojson_by_code(SLASKIE_GEOJSON)
    rows = load_obslugiwane_rows()
    updates: list[tuple[str, dict]] = []
    combined_features: list[dict] = []
    too_large_rows: list[tuple[str, Path, str]] = []
    ok = missing = too_large = 0

    for row in rows:
        code = normalize_code(row["fields"].get("nazwa", ""))
        if not code:
            continue
        source = by_code.get(code)
        if not source:
            missing += 1
            updates.append((row["id"], {GEOJSON_STATUS_FIELD: "brak w PostCodesMaps (śląskie)"}))
            continue
        feature = build_feature(code, source, row)
        blob = json.dumps(feature, ensure_ascii=False, separators=(",", ":"))
        if len(blob) > 95_000:
            too_large += 1
            tmp = DATA_DIR / f"{code.replace('-', '_')}.geojson"
            tmp.write_text(blob, encoding="utf-8")
            too_large_rows.append((row["id"], tmp, code))
            updates.append((row["id"], {GEOJSON_STATUS_FIELD: f"ok (plik, {len(blob)} znaków)"}))
            continue
        ok += 1
        combined_features.append(feature)
        updates.append(
            (
                row["id"],
                {
                    GEOJSON_FIELD: blob,
                    GEOJSON_STATUS_FIELD: "ok",
                },
            )
        )

    COMBINED_OUT.parent.mkdir(parents=True, exist_ok=True)
    combined = {"type": "FeatureCollection", "features": combined_features}
    COMBINED_OUT.write_text(json.dumps(combined, ensure_ascii=False), encoding="utf-8")

    if args.dry_run:
        print(f"[dry-run] ok={ok} missing={missing} too_large={too_large}")
        print(f"[dry-run] combined → {COMBINED_OUT} ({COMBINED_OUT.stat().st_size // 1024} KB)")
        return

    n = patch_batch(updates, dry_run=False)
    for rec_id, path, code in too_large_rows:
        upload_attachment(rec_id, GEOJSON_ATTACHMENT_FIELD, path, content_type="application/geo+json")
        print(f"  załącznik per kod: {code} ({path.stat().st_size // 1024} KB)")
        path.unlink(missing_ok=True)
    upload_combined_map_attachment()
    print(f"Zaktualizowano {n} rekordów w {OBSLOGIWANE_TABLE}")
    print(f"GeoJSON ok={ok}, brak poligonu={missing}, za duże={too_large}")
    print(f"Plik mapy (Framer): {COMBINED_OUT} ({COMBINED_OUT.stat().st_size // 1024 // 1024} MB)")
    print(f"https://airtable.com/{BASE_ID}/{OBSLOGIWANE_TABLE_ID}")


if __name__ == "__main__":
    main()

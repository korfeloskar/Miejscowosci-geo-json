"""Agregacja kodów pocztowych (MIEJSCOWOŚCI) → wszystkie 16 województw.

W bazie Airtable (appILpWFNjZbljnQz):
  MIEJSCOWOŚCI = pojedyncze „posty” / kody pocztowe (~23k)
  Województwa  = kontenery (ma być pełne 16)

Skrypt:
  1. Gwarantuje rekord dla każdego z 16 województw
  2. Tworzy pole linków «Kody» na Województwa → MIEJSCOWOŚCI
  3. Wpisuje do każdego województwa wszystkie należące kody
     (na podstawie istniejącego lookup Województwo na MIEJSCOWOŚCI)

  python sync_wojewodztwa_kody.py --dry-run
  python sync_wojewodztwa_kody.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

from airtable_config import BASE_ID, KOD_TABLE, KOD_TABLE_ID, WOJ_TABLE, WOJ_TABLE_ID

PAT = os.environ.get("AIRTABLE_PAT", "")
API = f"https://api.airtable.com/v0/{BASE_ID}"
META = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}"

WOJ_NAME_FIELD = "Województwo"
KODY_FIELD = "Kody"
COUNT_FIELD = "Liczba kodów"

# Pełna lista 16 województw (kanoniczne nazwy jak w Airtable).
WOJEWODZTWA_16 = [
    "DOLNOŚLĄSKIE",
    "KUJAWSKO-POMORSKIE",
    "LUBELSKIE",
    "LUBUSKIE",
    "ŁÓDZKIE",
    "MAŁOPOLSKIE",
    "MAZOWIECKIE",
    "OPOLSKIE",
    "PODKARPACKIE",
    "PODLASKIE",
    "POMORSKIE",
    "ŚLĄSKIE",
    "ŚWIĘTOKRZYSKIE",
    "WARMIŃSKO-MAZURSKIE",
    "WIELKOPOLSKIE",
    "ZACHODNIOPOMORSKIE",
]


def request(method: str, url: str, body: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(exc.read().decode()) from exc


def list_all(table: str, fields: list[str] | None = None) -> list[dict]:
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


def normalize_name(value: str) -> str:
    return " ".join(str(value).strip().upper().replace("–", "-").split())


def get_table_schema(table_id: str) -> dict:
    schema = request("GET", f"{META}/tables")
    return next(t for t in schema["tables"] if t["id"] == table_id)


def ensure_kody_link_field() -> str:
    """Zwraca field id pola Kody (multipleRecordLinks → MIEJSCOWOŚCI)."""
    table = get_table_schema(WOJ_TABLE_ID)
    for field in table["fields"]:
        if field["name"] == KODY_FIELD:
            return field["id"]
    created = request(
        "POST",
        f"{META}/tables/{WOJ_TABLE_ID}/fields",
        {
            "name": KODY_FIELD,
            "type": "multipleRecordLinks",
            "options": {
                "linkedTableId": KOD_TABLE_ID,
            },
        },
    )
    time.sleep(0.4)
    print(f"Utworzono pole «{KODY_FIELD}» na {WOJ_TABLE}")
    return created["id"]


def ensure_count_field(kody_field_id: str) -> None:
    table = get_table_schema(WOJ_TABLE_ID)
    if any(f["name"] == COUNT_FIELD for f in table["fields"]):
        return
    request(
        "POST",
        f"{META}/tables/{WOJ_TABLE_ID}/fields",
        {
            "name": COUNT_FIELD,
            "type": "count",
            "options": {"recordLinkFieldId": kody_field_id},
        },
    )
    time.sleep(0.3)
    print(f"Utworzono pole «{COUNT_FIELD}»")


def ensure_all_16(woj_rows: list[dict], *, dry_run: bool) -> dict[str, str]:
    """name -> preferred record id (rekord z powiatami > pusty duplikat)."""
    by_name: dict[str, list[dict]] = defaultdict(list)
    for row in woj_rows:
        name = normalize_name((row.get("fields") or {}).get(WOJ_NAME_FIELD) or "")
        if name:
            by_name[name].append(row)

    chosen: dict[str, str] = {}
    for name in WOJEWODZTWA_16:
        candidates = by_name.get(name, [])
        if not candidates:
            if dry_run:
                print(f"[dry-run] utworzylbym województwo: {name}")
                chosen[name] = f"NEW:{name}"
                continue
            created = request(
                "POST",
                f"{API}/{urllib.parse.quote(WOJ_TABLE)}",
                {
                    "records": [
                        {
                            "fields": {
                                WOJ_NAME_FIELD: name,
                                "KRAJ": "POLSKA",
                            }
                        }
                    ],
                    "typecast": True,
                },
            )
            rid = created["records"][0]["id"]
            chosen[name] = rid
            print(f"Utworzono województwo: {name} ({rid})")
            time.sleep(0.22)
            continue

        # Preferuj rekord z największą liczbą powiatów.
        def score(row: dict) -> int:
            return len((row.get("fields") or {}).get("Powiat") or [])

        best = max(candidates, key=score)
        chosen[name] = best["id"]
        extras = [c for c in candidates if c["id"] != best["id"]]
        for extra in extras:
            print(
                f"UWAGA: duplikat {name}: {extra['id']} "
                f"(powiatow={score(extra)}) — pomijam, uzywam {best['id']}"
            )
    return chosen


def group_posts_by_woj(miej_rows: list[dict]) -> tuple[dict[str, list[str]], int]:
    """woj_record_id -> [miejscowosc record ids]; returns also missing count."""
    grouped: dict[str, list[str]] = defaultdict(list)
    missing = 0
    for row in miej_rows:
        fields = row.get("fields") or {}
        woj = fields.get("Województwo")
        if not woj:
            missing += 1
            continue
        ids = woj if isinstance(woj, list) else [woj]
        # Lookup zwykle zwraca id rekordu województwa.
        for wid in ids:
            wid_s = str(wid).strip()
            if wid_s.startswith("rec"):
                grouped[wid_s].append(row["id"])
    return grouped, missing


def patch_kody(record_id: str, kody_ids: list[str], *, dry_run: bool) -> None:
    if dry_run:
        return
    # Airtable przyjmuje duże tablice linków; jeden rekord na request.
    request(
        "PATCH",
        f"{API}/{urllib.parse.quote(WOJ_TABLE)}",
        {
            "records": [{"id": record_id, "fields": {KODY_FIELD: kody_ids}}],
            "typecast": True,
        },
    )
    time.sleep(0.25)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agreguje kody MIEJSCOWOŚCI do wszystkich 16 województw"
    )
    parser.add_argument("--dry-run", action="store_true", help="Bez zapisu do Airtable")
    args = parser.parse_args()

    if not PAT:
        sys.exit("AIRTABLE_PAT is not set.")

    assert len(WOJEWODZTWA_16) == 16, "Lista musi miec dokladnie 16 wojewodztw"

    print(f"Cel: wszystkie {len(WOJEWODZTWA_16)} wojewodztw")
    if not args.dry_run:
        kody_field_id = ensure_kody_link_field()
        ensure_count_field(kody_field_id)
    else:
        print("[dry-run] pomijam tworzenie pol")

    print("Pobieram Województwa…")
    woj_rows = list_all(WOJ_TABLE, [WOJ_NAME_FIELD, "Powiat", "KRAJ"])
    chosen = ensure_all_16(woj_rows, dry_run=args.dry_run)
    if len(chosen) != 16:
        sys.exit(f"Oczekiwano 16 województw, mam {len(chosen)}")

    print(f"Pobieram {KOD_TABLE} (to moze potrwac)…")
    miej_rows = list_all(KOD_TABLE, ["Kod", "Województwo"])
    grouped, missing = group_posts_by_woj(miej_rows)

    # Zmapuj name → id wybranego rekordu; zbierz kody per name
    # Lookup na MIEJSCOWOŚCI wskazuje id województwa — używamy chosen ids.
    report = []
    total_assigned = 0
    for name in WOJEWODZTWA_16:
        rid = chosen[name]
        kody = grouped.get(rid, [])
        # Gdy dry-run i NEW: — brak id
        if rid.startswith("NEW:"):
            kody = []
        report.append((name, rid, len(kody)))
        total_assigned += len(kody)
        print(f"  {name}: {len(kody)} kodow -> {rid}")
        if not args.dry_run and not rid.startswith("NEW:"):
            patch_kody(rid, kody, dry_run=False)

    print()
    print(f"Wojewodztw: {len(WOJEWODZTWA_16)} / 16")
    print(f"MIEJSCOWOŚCI lacznie: {len(miej_rows)}")
    print(f"Przypisane do 16 woj.: {total_assigned}")
    print(f"Bez lookup Województwo: {missing}")
    if args.dry_run:
        print("Dry-run — nic nie zapisano.")
    else:
        print(f"Zapisano linki «{KODY_FIELD}» na tabeli {WOJ_TABLE}.")

    out = {
        "wojewodztwa": [
            {"nazwa": n, "record_id": rid, "kody_count": c} for n, rid, c in report
        ],
        "miejscowosci_total": len(miej_rows),
        "assigned": total_assigned,
        "missing_wojewodztwo": missing,
    }
    Path("data").mkdir(exist_ok=True)
    Path("data/wojewodztwa_kody_report.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Raport: data/wojewodztwa_kody_report.json")


if __name__ == "__main__":
    main()

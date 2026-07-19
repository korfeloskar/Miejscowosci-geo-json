"""Buduje JSON danych województw pod interaktywną mapę Framer.

Źródła Airtable:
  - Województwa — 16 kontenerów (nazwa, ID serwisant, Kody)
  - 🚗 Obsługiwane — faktycznie obsługiwane kody / miejscowości
  - Miasto — nazwy miejscowości (link z Obsługiwane)

Wyjście:
  public/wojewodztwa-map-data.json

  python build_wojewodztwa_map_data.py
  python build_wojewodztwa_map_data.py --out data/wojewodztwa-map-data.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from airtable_config import (
    BASE_ID,
    KOD_TABLE,
    OBSLOGIWANE_TABLE,
    WOJ_TABLE,
)
from geojson_utils import first_lookup, parse_city_name

PAT = os.environ.get("AIRTABLE_PAT", "")
API = f"https://api.airtable.com/v0/{BASE_ID}"
MIASTO_TABLE = "Miasto"
MAPA_PREFIX = "==="

ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "public" / "wojewodztwa-map-data.json"

# Kanoniczna lista 16 województw (jak w Airtable / sync_wojewodztwa_kody).
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

# id ascii → regionGroup
REGION_GROUP: dict[str, str] = {
    "pomorskie": "północ",
    "zachodniopomorskie": "północ",
    "warminsko-mazurskie": "północ",
    "kujawsko-pomorskie": "północ",
    "slaskie": "południe",
    "malopolskie": "południe",
    "podkarpackie": "południe",
    "opolskie": "południe",
    "lubelskie": "wschód",
    "podlaskie": "wschód",
    "swietokrzyskie": "wschód",
    "dolnoslaskie": "zachód",
    "lubuskie": "zachód",
    "wielkopolskie": "zachód",
    "mazowieckie": "centrum",
    "lodzkie": "centrum",
}

# Priorytet mainCities (gdy brak populacji w Airtable) — ranking ważności.
MAIN_CITY_PRIORITY: dict[str, list[str]] = {
    "slaskie": [
        "Katowice",
        "Gliwice",
        "Zabrze",
        "Sosnowiec",
        "Bytom",
        "Tychy",
        "Ruda Śląska",
        "Chorzów",
        "Dąbrowa Górnicza",
        "Rybnik",
        "Jaworzno",
        "Mysłowice",
        "Siemianowice Śląskie",
        "Piekary Śląskie",
        "Świętochłowice",
        "Tarnowskie Góry",
        "Mikołów",
        "Żory",
        "Będzin",
        "Knurów",
    ],
    "malopolskie": ["Kraków", "Tarnów", "Nowy Sącz", "Oświęcim", "Chrzanów"],
    "mazowieckie": ["Warszawa", "Radom", "Płock", "Siedlce", "Pruszków"],
    "dolnoslaskie": ["Wrocław", "Wałbrzych", "Legnica", "Jelenia Góra", "Lubin"],
    "wielkopolskie": ["Poznań", "Kalisz", "Konin", "Piła", "Ostrów Wielkopolski"],
    "pomorskie": ["Gdańsk", "Gdynia", "Sopot", "Słupsk", "Tczew"],
    "lodzkie": ["Łódź", "Piotrków Trybunalski", "Pabianice", "Tomaszów Mazowiecki"],
    "lubelskie": ["Lublin", "Chełm", "Zamość", "Biała Podlaska", "Puławy"],
    "podkarpackie": ["Rzeszów", "Przemyśl", "Stalowa Wola", "Mielec", "Krosno"],
    "zachodniopomorskie": ["Szczecin", "Koszalin", "Stargard", "Kołobrzeg", "Świnoujście"],
    "kujawsko-pomorskie": ["Bydgoszcz", "Toruń", "Włocławek", "Grudziądz", "Inowrocław"],
    "warminsko-mazurskie": ["Olsztyn", "Elbląg", "Ełk", "Ostróda", "Iława"],
    "podlaskie": ["Białystok", "Suwałki", "Łomża", "Augustów", "Bielsk Podlaski"],
    "swietokrzyskie": ["Kielce", "Ostrowiec Świętokrzyski", "Starachowice", "Skarżysko-Kamienna"],
    "lubuskie": ["Zielona Góra", "Gorzów Wielkopolski", "Nowa Sól", "Żary", "Żagań"],
    "opolskie": ["Opole", "Kędzierzyn-Koźle", "Nysa", "Brzeg", "Kluczbork"],
}

# Znane duże miasta (boost przy sortowaniu mainCities, gdy są w Airtable).
CITY_IMPORTANCE: dict[str, int] = {
    name.lower(): 1000 - i
    for names in MAIN_CITY_PRIORITY.values()
    for i, name in enumerate(names)
}


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


def strip_accents(value: str) -> str:
    # Zachowaj polskie znaki specjalne jako ascii-fold do id/slug.
    repl = {
        "ą": "a",
        "ć": "c",
        "ę": "e",
        "ł": "l",
        "ń": "n",
        "ó": "o",
        "ś": "s",
        "ź": "z",
        "ż": "z",
        "Ą": "A",
        "Ć": "C",
        "Ę": "E",
        "Ł": "L",
        "Ń": "N",
        "Ó": "O",
        "Ś": "S",
        "Ź": "Z",
        "Ż": "Z",
    }
    out = "".join(repl.get(ch, ch) for ch in value)
    out = unicodedata.normalize("NFKD", out)
    out = "".join(ch for ch in out if not unicodedata.combining(ch))
    return out


def woj_id(canonical: str) -> str:
    return strip_accents(canonical.lower().replace(" ", "-"))


def woj_display_name(canonical: str) -> str:
    """DOLNOŚLĄSKIE → Dolnośląskie."""
    return polish_title(canonical)


def polish_title(value: str) -> str:
    """Title-case z respektowaniem polskich znaków i łączników."""
    value = (value or "").strip()
    if not value:
        return value
    # Usuń śmieci typu „KATOWICE 002”
    value = re.sub(r"\s+\d{2,}$", "", value).strip()
    parts: list[str] = []
    for token in re.split(r"([\s\-]+)", value):
        if not token or re.fullmatch(r"[\s\-]+", token):
            parts.append(token)
            continue
        lower = token.lower()
        # „k.” przy „K. Będzina”
        if lower in {"k.", "k"}:
            parts.append(lower)
            continue
        parts.append(lower[:1].upper() + lower[1:])
    return "".join(parts)


def locative_adj(display: str) -> str:
    return {
        "Dolnośląskie": "dolnośląskim",
        "Kujawsko-Pomorskie": "kujawsko-pomorskim",
        "Lubelskie": "lubelskim",
        "Lubuskie": "lubuskim",
        "Łódzkie": "łódzkim",
        "Małopolskie": "małopolskim",
        "Mazowieckie": "mazowieckim",
        "Opolskie": "opolskim",
        "Podkarpackie": "podkarpackim",
        "Podlaskie": "podlaskim",
        "Pomorskie": "pomorskim",
        "Śląskie": "śląskim",
        "Świętokrzyskie": "świętokrzyskim",
        "Warmińsko-Mazurskie": "warmińsko-mazurskim",
        "Wielkopolskie": "wielkopolskim",
        "Zachodniopomorskie": "zachodniopomorskim",
    }.get(display, display.lower())


def contact_label(display: str) -> str:
    return f"Zapytaj o obsługę w woj. {locative_adj(display)}"


def description_for(display: str, is_active: bool, city_count: int, main: list[str]) -> str:
    loc = locative_adj(display)
    if is_active and city_count:
        mains = ", ".join(main[:3]) if main else display
        return (
            f"Obsługujemy województwo {display.lower()} — sprzedaż i serwis kas fiskalnych "
            f"oraz terminali płatniczych m.in. w: {mains}. "
            f"Aktualnie w zasięgu {city_count} miejscowości."
        )
    return (
        f"Planujemy rozwój obsługi kas fiskalnych, terminali i serwisu w województwie "
        f"{loc}. Zostaw kontakt — sprawdzimy dostępność dojazdu."
    )


def choose_woj_records(woj_rows: list[dict]) -> dict[str, dict]:
    """canonical name → preferred Airtable row (z powiatami > pusty duplikat)."""
    by_name: dict[str, list[dict]] = defaultdict(list)
    for row in woj_rows:
        name = normalize_name((row.get("fields") or {}).get("Województwo") or "")
        if name:
            by_name[name].append(row)

    chosen: dict[str, dict] = {}
    for name in WOJEWODZTWA_16:
        candidates = by_name.get(name, [])
        if not candidates:
            continue

        def score(row: dict) -> int:
            f = row.get("fields") or {}
            return len(f.get("Powiat") or []) + len(f.get("Kody") or [])

        chosen[name] = max(candidates, key=score)
    return chosen


def resolve_city_name(fields: dict, id_to_name: dict[str, str]) -> str | None:
    links = fields.get("Miasto") or []
    if isinstance(links, list):
        for lid in links:
            raw = id_to_name.get(str(lid), "")
            if raw:
                return polish_title(raw)
    mm = first_lookup(fields.get("miasto mapa"))
    if mm:
        return polish_title(parse_city_name(mm))
    return None


def pick_main_cities(cities: list[str], counts: Counter[str], woj_id_key: str, limit: int = 6) -> list[str]:
    if not cities:
        return []
    city_set = {c.lower(): c for c in cities}
    ranked: list[tuple[int, str]] = []
    for city in cities:
        key = city.lower()
        importance = CITY_IMPORTANCE.get(key, 0)
        # Priorytetowa lista województwa
        preferred = MAIN_CITY_PRIORITY.get(woj_id_key, [])
        pref_boost = 0
        for i, p in enumerate(preferred):
            if p.lower() == key:
                pref_boost = 500 - i
                break
        ranked.append((importance + pref_boost + counts.get(city, 0), city))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    out: list[str] = []
    seen: set[str] = set()
    for _, city in ranked:
        low = city.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(city_set[low])
        if len(out) >= limit:
            break
    return out


def build_payload(
    chosen: dict[str, dict],
    by_woj_cities: dict[str, Counter[str]],
    uncertain: list[dict],
) -> dict:
    regions: list[dict] = []
    for canonical in WOJEWODZTWA_16:
        rid_key = woj_id(canonical)
        display = woj_display_name(canonical)
        row = chosen.get(canonical)
        record_id = row["id"] if row else None
        counts = by_woj_cities.get(record_id or "", Counter())
        # Sort cities: by frequency desc, then alpha
        cities_sorted = [c for c, _ in counts.most_common()]
        if not cities_sorted:
            cities_sorted = sorted(counts.keys())
        # Deduplicate case-insensitively while keeping first (most frequent)
        dedup: list[str] = []
        seen: set[str] = set()
        for c in cities_sorted:
            low = c.lower()
            if low in seen:
                continue
            seen.add(low)
            dedup.append(c)

        is_active = len(dedup) > 0
        main = pick_main_cities(dedup, counts, rid_key)
        regions.append(
            {
                "id": rid_key,
                "name": display,
                "slug": f"wojewodztwo-{rid_key}",
                "isActive": is_active,
                "cities": dedup,
                "cityCount": len(dedup),
                "mainCities": main,
                "description": description_for(display, is_active, len(dedup), main),
                "contactLabel": contact_label(display),
                "regionGroup": REGION_GROUP.get(rid_key, "centrum"),
                "airtableRecordId": record_id,
            }
        )

    active = sum(1 for r in regions if r["isActive"])
    total_cities = sum(r["cityCount"] for r in regions)
    return {
        "regions": regions,
        "uncertainCities": uncertain,
        "summary": {
            "totalRegions": len(regions),
            "activeRegions": active,
            "totalCities": total_cities,
            "uncertainCities": len(uncertain),
        },
        "meta": {
            "source": {
                "baseId": BASE_ID,
                "wojewodztwaTable": WOJ_TABLE,
                "obslugiwaneTable": OBSLOGIWANE_TABLE,
                "miastoTable": MIASTO_TABLE,
                    "fields": [
                        "Województwa.Województwo",
                        "Województwa.Powiat",
                        "Województwa.Kody",
                        "Województwa.ID serwisant",
                        "Obsługiwane.nazwa",
                        "Obsługiwane.miasto mapa",
                        "Obsługiwane.Miasto",
                        "Obsługiwane.Województwo",
                        "Miasto.Name",
                        "MIEJSCOWOŚCI.Kod/Miasto/Województwo/Adres (tylko uncertain)",
                    ],
            },
            "notes": [
                "cities = unikalne miejscowości z tabeli 🚗 Obsługiwane (faktyczny zasięg serwisu).",
                "isActive = true gdy w województwie jest ≥1 obsłużona miejscowość.",
                "Nie inventujemy miast spoza Airtable; nieaktywne województwa mają cities=[].",
            ],
        },
    }


def build_from_airtable() -> dict:
    print("Pobieram Województwa…")
    woj_rows = list_all(WOJ_TABLE, ["Województwo", "Powiat", "Kody", "ID serwisant", "KRAJ"])
    chosen = choose_woj_records(woj_rows)
    if len(chosen) != 16:
        missing = [n for n in WOJEWODZTWA_16 if n not in chosen]
        raise RuntimeError(f"Brak {len(missing)} województw w Airtable: {missing}")

    print("Pobieram Miasto…")
    miasta = list_all(MIASTO_TABLE, ["Name"])
    id_to_name = {
        r["id"]: str((r.get("fields") or {}).get("Name") or "").strip() for r in miasta
    }

    print("Pobieram Obsługiwane…")
    rows = list_all(
        OBSLOGIWANE_TABLE,
        ["nazwa", "miasto mapa", "Miasto", "Województwo", "Gmina", "Powiat"],
    )

    id_to_woj_name = {row["id"]: canonical for canonical, row in chosen.items()}
    by_woj: dict[str, Counter[str]] = defaultdict(Counter)
    uncertain_raw: list[dict] = []
    chosen_ids = {r["id"] for r in chosen.values()}

    for row in rows:
        fields = row.get("fields") or {}
        code = str(fields.get("nazwa") or "").strip()
        if not code or code.startswith(MAPA_PREFIX):
            continue
        city = resolve_city_name(fields, id_to_name)
        woj = fields.get("Województwo")
        if not woj:
            uncertain_raw.append(
                {
                    "code": code,
                    "city": city,
                    "recordId": row["id"],
                }
            )
            continue
        wid = str(woj[0] if isinstance(woj, list) else woj)
        if wid not in chosen_ids:
            uncertain_raw.append(
                {
                    "code": code,
                    "city": city,
                    "recordId": row["id"],
                    "reason": f"Województwo {wid} nie jest wśród kanonicznych 16",
                    "wojewodztwoRecordId": wid,
                }
            )
            continue
        if not city:
            uncertain_raw.append(
                {
                    "code": code,
                    "city": None,
                    "recordId": row["id"],
                    "reason": "brak nazwy miasta (Miasto / miasto mapa)",
                    "wojewodztwoRecordId": wid,
                }
            )
            continue
        by_woj[wid][city] += 1

    # Wzbogać uncertain o podpowiedzi z MIEJSCOWOŚCI (tylko brakujące kody — bez pełnego dumpa).
    uncertain: list[dict] = []
    for item in uncertain_raw:
        if item.get("reason"):
            uncertain.append(item)
            continue
        code = item["code"]
        hint_city = item.get("city")
        hint_woj = None
        hint_adres = None
        formula = urllib.parse.quote(f"{{Kod}}='{code}'")
        url = (
            f"{API}/{urllib.parse.quote(KOD_TABLE)}"
            f"?filterByFormula={formula}&maxRecords=1"
            f"&fields%5B%5D={urllib.parse.quote('Kod')}"
            f"&fields%5B%5D={urllib.parse.quote('Miasto')}"
            f"&fields%5B%5D={urllib.parse.quote('Województwo')}"
            f"&fields%5B%5D={urllib.parse.quote('Adres')}"
        )
        try:
            data = request("GET", url)
            recs = data.get("records") or []
            if recs:
                hf = recs[0].get("fields") or {}
                hint_adres = hf.get("Adres")
                if not hint_city:
                    links = hf.get("Miasto") or []
                    if isinstance(links, list):
                        for lid in links:
                            raw = id_to_name.get(str(lid), "")
                            if raw:
                                hint_city = polish_title(raw)
                                break
                wids = hf.get("Województwo") or []
                if isinstance(wids, list) and wids:
                    hint_woj = id_to_woj_name.get(str(wids[0]))
        except Exception as exc:  # noqa: BLE001
            hint_adres = f"(lookup MIEJSCOWOŚCI failed: {exc})"

        uncertain.append(
            {
                "code": code,
                "city": hint_city,
                "reason": (
                    "brak lookup Województwo na rekordzie Obsługiwane; "
                    "nie przypisano automatycznie — wymaga ręcznej weryfikacji"
                    + (f" (MIEJSCOWOŚCI wskazuje: {hint_woj})" if hint_woj else "")
                    + (f"; adres: {hint_adres}" if hint_adres else "")
                ),
                "recordId": item["recordId"],
                "suggestedWojewodztwo": hint_woj,
            }
        )

    return build_payload(chosen, by_woj, uncertain)


def build_fallback_from_local() -> dict:
    """Gdy Airtable niedostępne — szkielet 16 woj. + miasta z lokalnego GeoJSON (śląskie)."""
    print("UWAGA: fallback z lokalnych plików (bez Airtable)")
    geo_path = ROOT / "public" / "miejscowosci-polska.geojson"
    cities: list[str] = []
    if geo_path.exists():
        data = json.loads(geo_path.read_text(encoding="utf-8"))
        for feat in data.get("features") or []:
            name = (feat.get("properties") or {}).get("miasto")
            if name:
                cities.append(polish_title(str(name)))
    cities = sorted(set(cities), key=lambda x: x.lower())
    counts = Counter({c: 1 for c in cities})
    # Przypisz do śląskiego (mapa lokalna to zasięg śląski)
    fake_chosen = {
        n: {"id": f"local:{woj_id(n)}"} for n in WOJEWODZTWA_16
    }
    by_woj: dict[str, Counter[str]] = defaultdict(Counter)
    if cities:
        by_woj["local:slaskie"] = counts
    uncertain = [
        {
            "code": None,
            "city": None,
            "reason": "Airtable niedostępne — dane częściowe z public/miejscowosci-polska.geojson",
        }
    ]
    payload = build_payload(fake_chosen, by_woj, uncertain)
    payload["meta"]["fallback"] = True
    return payload


def _safe_print(msg: str) -> None:
    """Windows consoles often use cp1250/cp1252 — avoid crashing on PL/emoji."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Buduje JSON województw pod Framer")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Ścieżka wyjściowa (domyślnie {DEFAULT_OUT})",
    )
    args = parser.parse_args()

    try:
        if not PAT:
            raise RuntimeError("AIRTABLE_PAT is not set")
        payload = build_from_airtable()
    except Exception as exc:  # noqa: BLE001 — fallback jest częścią kontraktu
        _safe_print(f"Airtable niedostępne ({exc})")
        payload = build_fallback_from_local()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    s = payload["summary"]
    _safe_print("")
    _safe_print(f"Zapisano: {args.out}")
    _safe_print(
        f"Regiony: {s['totalRegions']}, aktywne: {s['activeRegions']}, "
        f"miasta: {s['totalCities']}, niepewne: {s['uncertainCities']}"
    )
    for r in payload["regions"]:
        flag = "AKTYWNE" if r["isActive"] else "-"
        _safe_print(
            f"  [{flag}] {r['name']}: {r['cityCount']} miast, main={r['mainCities'][:4]}"
        )
    if payload["uncertainCities"]:
        _safe_print("Do weryfikacji:")
        for u in payload["uncertainCities"][:20]:
            _safe_print(f"  - {u}")


if __name__ == "__main__":
    main()

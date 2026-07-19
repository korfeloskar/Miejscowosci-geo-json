"""Buduje warstwę miejscowości z otwartego GitHub (PRNG) — bez Airtable.

Źródło:
  https://github.com/mbroton/polish-geonames (v0.3.0)
  → Państwowy Rejestr Nazw Geograficznych (dane.gov.pl), CC BY 4.0

Wyjścia:
  public/miejscowosci-prng.geojson   — wszystkie miasta + wsie (punkty)
  public/miasta-prng.geojson         — tylko miasta (lżejsze pod Framer)
  public/wojewodztwa-map-data.json   — 16 województw + listy miejscowości

  python build_miejscowosci_prng.py
  python build_miejscowosci_prng.py --download   # pobierz źródło jeśli brak
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXTERNAL_DIR = ROOT / "data" / "external"
SOURCE_JSON = EXTERNAL_DIR / "polish-geonames.json"
ATTRIBUTION = EXTERNAL_DIR / "ATTRIBUTION.txt"
PUBLIC = ROOT / "public"

SOURCE_URL = (
    "https://github.com/mbroton/polish-geonames/releases/download/"
    "v0.3.0/polish-geonames.json"
)
SOURCE_META = {
    "repo": "https://github.com/mbroton/polish-geonames",
    "release": "v0.3.0",
    "validAsOf": "2025-01-01",
    "upstream": (
        "https://dane.gov.pl/pl/dataset/780,"
        "panstwowy-rejestr-nazw-geograficznych-prng"
    ),
    "license": "CC BY 4.0",
    "entries": 44631,
}

# Kanoniczna lista 16 województw (display → id ascii + warianty w źródle).
WOJEWODZTWA_16: list[tuple[str, str, list[str]]] = [
    # (id, display, source province aliases lowercased)
    ("dolnoslaskie", "Dolnośląskie", ["dolnośląskie", "dolnoslaskie"]),
    ("kujawsko-pomorskie", "Kujawsko-Pomorskie", ["kujawsko-pomorskie"]),
    ("lubelskie", "Lubelskie", ["lubelskie"]),
    ("lubuskie", "Lubuskie", ["lubuskie"]),
    ("lodzkie", "Łódzkie", ["łódzkie", "lodzkie"]),
    ("malopolskie", "Małopolskie", ["małopolskie", "malopolskie"]),
    ("mazowieckie", "Mazowieckie", ["mazowieckie"]),
    ("opolskie", "Opolskie", ["opolskie"]),
    ("podkarpackie", "Podkarpackie", ["podkarpackie"]),
    ("podlaskie", "Podlaskie", ["podlaskie"]),
    ("pomorskie", "Pomorskie", ["pomorskie"]),
    ("slaskie", "Śląskie", ["śląskie", "slaskie"]),
    ("swietokrzyskie", "Świętokrzyskie", ["świętokrzyskie", "swietokrzyskie"]),
    ("warminsko-mazurskie", "Warmińsko-Mazurskie", ["warmińsko-mazurskie", "warminsko-mazurskie"]),
    ("wielkopolskie", "Wielkopolskie", ["wielkopolskie"]),
    ("zachodniopomorskie", "Zachodniopomorskie", ["zachodniopomorskie"]),
]

REGION_GROUP = {
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

MAIN_CITY_PRIORITY: dict[str, list[str]] = {
    "slaskie": [
        "Katowice", "Gliwice", "Zabrze", "Sosnowiec", "Bytom", "Tychy",
        "Ruda Śląska", "Chorzów", "Dąbrowa Górnicza", "Rybnik",
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


def province_index() -> dict[str, tuple[str, str]]:
    """alias → (id, display)."""
    out: dict[str, tuple[str, str]] = {}
    for rid, display, aliases in WOJEWODZTWA_16:
        for a in aliases:
            out[a.lower()] = (rid, display)
    return out


def download_source() -> None:
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Pobieram {SOURCE_URL}")
    req = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "Miejscowosci-geo-json/1.0"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        SOURCE_JSON.write_bytes(resp.read())
    ATTRIBUTION.write_text(
        "\n".join(
            [
                "Polish localities (miejscowości) — attribution",
                "",
                f"Repo:     {SOURCE_META['repo']}",
                f"Release:  {SOURCE_META['release']}",
                f"Valid as: {SOURCE_META['validAsOf']}",
                f"Entries:  {SOURCE_META['entries']}",
                f"License:  {SOURCE_META['license']}",
                f"Upstream: {SOURCE_META['upstream']}",
                "",
                "Parsed by mbroton/polish-geonames from PRNG (GUGiK / dane.gov.pl).",
                "Do not invent localities — rebuild from the release JSON only.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Zapisano {SOURCE_JSON} ({SOURCE_JSON.stat().st_size // 1024} KB)")


def load_rows() -> list[dict]:
    if not SOURCE_JSON.exists():
        raise FileNotFoundError(
            f"Brak {SOURCE_JSON} — uruchom: python build_miejscowosci_prng.py --download"
        )
    data = json.loads(SOURCE_JSON.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("Oczekiwano tablicy JSON w polish-geonames.json")
    return data


def feature_for(row: dict, woj_display: str, woj_id: str) -> dict | None:
    try:
        lat = float(row["lat"])
        lng = float(row["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    name = str(row.get("name") or "").strip()
    if not name:
        return None
    kind = str(row.get("type") or "").strip().lower()
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
        "properties": {
            "id": row.get("id"),
            "name": name,
            "nazwa": name,
            "miasto": name,
            "type": kind,
            "rodzaj": "miasto" if kind == "city" else "wieś",
            "wojewodztwo": woj_display,
            "wojewodztwoId": woj_id,
            "powiat": str(row.get("district") or "").strip(),
            "gmina": str(row.get("commune") or "").strip(),
        },
    }


def pick_main_cities(cities: list[str], woj_id: str, limit: int = 6) -> list[str]:
    preferred = MAIN_CITY_PRIORITY.get(woj_id, [])
    city_map = {c.lower(): c for c in cities}
    out: list[str] = []
    seen: set[str] = set()
    for p in preferred:
        hit = city_map.get(p.lower())
        if hit and hit.lower() not in seen:
            seen.add(hit.lower())
            out.append(hit)
        if len(out) >= limit:
            return out
    for c in sorted(cities, key=lambda x: x.lower()):
        if c.lower() in seen:
            continue
        seen.add(c.lower())
        out.append(c)
        if len(out) >= limit:
            break
    return out


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


def description_for(display: str, city_count: int, place_count: int, main: list[str]) -> str:
    mains = ", ".join(main[:3]) if main else display
    return (
        f"Województwo {display.lower()} — {place_count} miejscowości "
        f"({city_count} miast) wg PRNG. M.in.: {mains}."
    )


def build() -> dict:
    rows = load_rows()
    idx = province_index()
    unknown_province = Counter()

    all_features: list[dict] = []
    city_features: list[dict] = []

    by_woj_cities: dict[str, list[str]] = defaultdict(list)
    by_woj_places: dict[str, list[str]] = defaultdict(list)
    by_woj_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for row in rows:
        prov_raw = str(row.get("province") or "").strip().lower()
        mapped = idx.get(prov_raw)
        if not mapped:
            unknown_province[prov_raw or "(empty)"] += 1
            continue
        woj_id, woj_display = mapped
        feat = feature_for(row, woj_display, woj_id)
        if not feat:
            continue
        all_features.append(feat)
        name = feat["properties"]["name"]
        kind = feat["properties"]["type"]
        by_woj_places[woj_id].append(name)
        by_woj_counts[woj_id][kind] += 1
        if kind == "city":
            city_features.append(feat)
            by_woj_cities[woj_id].append(name)

    if unknown_province:
        print("UWAGA: nieznane province w źródle:", dict(unknown_province))

    PUBLIC.mkdir(parents=True, exist_ok=True)

    full_geo = {"type": "FeatureCollection", "features": all_features}
    cities_geo = {"type": "FeatureCollection", "features": city_features}

    full_path = PUBLIC / "miejscowosci-prng.geojson"
    cities_path = PUBLIC / "miasta-prng.geojson"
    # Compact JSON — Framer / MapLibre ładuje szybciej
    full_path.write_text(json.dumps(full_geo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    cities_path.write_text(
        json.dumps(cities_geo, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    regions: list[dict] = []
    for woj_id, display, _aliases in WOJEWODZTWA_16:
        cities = sorted(set(by_woj_cities[woj_id]), key=lambda x: x.lower())
        places = sorted(set(by_woj_places[woj_id]), key=lambda x: x.lower())
        counts = by_woj_counts[woj_id]
        main = pick_main_cities(cities, woj_id)
        regions.append(
            {
                "id": woj_id,
                "name": display,
                "slug": f"wojewodztwo-{woj_id}",
                "isActive": True,
                "cities": cities,
                "miejscowosci": places,
                "cityCount": len(cities),
                "miejscowosciCount": len(places),
                "villageCount": int(counts.get("village", 0)),
                "mainCities": main,
                "description": description_for(display, len(cities), len(places), main),
                "contactLabel": f"Zapytaj o obsługę w woj. {locative_adj(display)}",
                "regionGroup": REGION_GROUP.get(woj_id, "centrum"),
            }
        )

    payload = {
        "regions": regions,
        "summary": {
            "totalRegions": len(regions),
            "activeRegions": len(regions),
            "totalCities": sum(r["cityCount"] for r in regions),
            "totalMiejscowosci": sum(r["miejscowosciCount"] for r in regions),
            "totalFeatures": len(all_features),
        },
        "meta": {
            "source": SOURCE_META,
            "files": {
                "miejscowosciGeojson": "public/miejscowosci-prng.geojson",
                "miastaGeojson": "public/miasta-prng.geojson",
            },
            "notes": [
                "miejscowosci = wszystkie nazwy (miasta + wsie) z polish-geonames / PRNG.",
                "cities = tylko type=city.",
                "Warstwa mapy: miejscowosci-prng.geojson (pełna) lub miasta-prng.geojson (lżejsza).",
                "Źródło zewnętrzne GitHub — nie Airtable.",
            ],
        },
    }

    map_data_path = PUBLIC / "wojewodztwa-map-data.json"
    map_data_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "features": len(all_features),
        "cities": len(city_features),
        "full_kb": full_path.stat().st_size // 1024,
        "cities_kb": cities_path.stat().st_size // 1024,
        "map_data_kb": map_data_path.stat().st_size // 1024,
        "summary": payload["summary"],
        "regions": [(r["name"], r["cityCount"], r["miejscowosciCount"]) for r in regions],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Buduje miejscowości PRNG pod Framer")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Pobierz polish-geonames.json jeśli brak / nadpisz",
    )
    args = parser.parse_args()

    if args.download or not SOURCE_JSON.exists():
        download_source()

    stats = build()
    print("")
    print(f"miejscowosci-prng.geojson: {stats['features']} punktów ({stats['full_kb']} KB)")
    print(f"miasta-prng.geojson:       {stats['cities']} miast ({stats['cities_kb']} KB)")
    print(f"wojewodztwa-map-data.json: {stats['map_data_kb']} KB")
    print(f"summary: {stats['summary']}")
    for name, cities, places in stats["regions"]:
        print(f"  {name}: {places} miejscowości ({cities} miast)")


if __name__ == "__main__":
    main()

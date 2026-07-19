"""Kopiuje GeoJSON województw do public/ (podgląd HTML + GitHub raw).

  python prepare_wojewodztwa_map.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRAMER_SRC = ROOT / "framer" / "polska-wojewodztwa.geojson"
PUBLIC_OUT = ROOT / "public" / "polska-wojewodztwa.geojson"
POLSKA_WOJ_URL = (
    "https://raw.githubusercontent.com/andilabs/polska-wojewodztwa-geojson/master/"
    "polska-wojewodztwa.geojson"
)

NAZWA_PL = {
    "Lódzkie": "Łódzkie",
    "Lodzkie": "Łódzkie",
    "Swietokrzyskie": "Świętokrzyskie",
    "Wielkopolskie": "Wielkopolskie",
    "Kujawsko-Pomorskie": "Kujawsko-Pomorskie",
    "Malopolskie": "Małopolskie",
    "Dolnoslaskie": "Dolnośląskie",
    "Lubelskie": "Lubelskie",
    "Lubuskie": "Lubuskie",
    "Mazowieckie": "Mazowieckie",
    "Opolskie": "Opolskie",
    "Podlaskie": "Podlaskie",
    "Pomorskie": "Pomorskie",
    "Slaskie": "Śląskie",
    "Podkarpackie": "Podkarpackie",
    "Warminsko-Mazurskie": "Warmińsko-Mazurskie",
    "Zachodniopomorskie": "Zachodniopomorskie",
    "Greater Poland": "Wielkopolskie",
    "Kuyavian-Pomeranian": "Kujawsko-Pomorskie",
    "Lesser Poland": "Małopolskie",
    "Lower Silesian": "Dolnośląskie",
    "Lublin": "Lubelskie",
    "Lubusz": "Lubuskie",
    "Masovian": "Mazowieckie",
    "Opole": "Opolskie",
    "Podlachian": "Podlaskie",
    "Pomeranian": "Pomorskie",
    "Silesian": "Śląskie",
    "Subcarpathian": "Podkarpackie",
    "Warmian-Masurian": "Warmińsko-Mazurskie",
    "West Pomeranian": "Zachodniopomorskie",
    "Łódź": "Łódzkie",
    "Świętokrzyskie": "Świętokrzyskie",
}


def ensure_source() -> Path:
    if FRAMER_SRC.exists() and FRAMER_SRC.stat().st_size > 10_000:
        return FRAMER_SRC
    FRAMER_SRC.parent.mkdir(parents=True, exist_ok=True)
    print(f"Pobieram: {POLSKA_WOJ_URL}")
    req = urllib.request.Request(POLSKA_WOJ_URL, headers={"User-Agent": "PBS-WojewodztwaMap/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        FRAMER_SRC.write_bytes(resp.read())
    print(f"Zapisano {FRAMER_SRC} ({FRAMER_SRC.stat().st_size // 1024} KB)")
    return FRAMER_SRC


def polish_label(props: dict) -> str:
    raw = str(props.get("name") or props.get("NAME_1") or "").strip()
    return NAZWA_PL.get(raw, raw or "Województwo")


def main() -> None:
    src = ensure_source()
    data = json.loads(src.read_text(encoding="utf-8"))
    for feat in data.get("features", []):
        props = feat.setdefault("properties", {})
        label = polish_label(props)
        props["nazwa"] = label
        props["label"] = label

    PUBLIC_OUT.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    n = len(data.get("features", []))
    print(f"Województwa: {n}")
    print(f"Zapisano: {PUBLIC_OUT} ({PUBLIC_OUT.stat().st_size // 1024} KB)")
    print()
    print("Podgląd lokalny (wymaga prostego serwera HTTP — fetch nie działa z file://):")
    print("  python -m http.server 8765 --directory public")
    print("  http://127.0.0.1:8765/mapa-wojewodztw.html")
    print()
    print("Framer: wklej framer/WojewodztwaMap.tsx -> URL GeoJSON wojewodztw:")
    print("  https://raw.githubusercontent.com/korfeloskar/Miejscowosci-geo-json/master/public/polska-wojewodztwa.geojson")
    print("  (albo domyslny CDN andilabs w komponencie)")


if __name__ == "__main__":
    main()

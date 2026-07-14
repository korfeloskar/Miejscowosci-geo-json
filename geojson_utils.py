"""Wspólne narzędzia GeoJSON — sync kodów pocztowych i mapa miejscowości."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

CODE_RE = re.compile(r"^(\d{2}-\d{3})$")
CITY_LABEL_RE = re.compile(r"^\d{2}-\d{3}\s+(.+)$", re.IGNORECASE)

STREFA_BY_COLOR: dict[str, tuple[int, str]] = {
    "#FF0000": (0, "STREFA 0"),
    "#FFCD00": (1, "STREFA 1"),
    "#AEFF00": (2, "STREFA 2"),
    "#00FFF0": (3, "STREFA 3"),
    "#CD00FF": (4, "STREFA 4"),
    "#9C9CBD": (5, "STREFA 5"),
    "#3E7413": (6, "STREFA 6"),
}


def first_lookup(values: list | str | None) -> str:
    if values is None:
        return ""
    if isinstance(values, str):
        return values.strip()
    if isinstance(values, list):
        if not values:
            return ""
        return str(values[0]).strip()
    return str(values).strip()


def normalize_code(value: str) -> str | None:
    value = (value or "").strip()
    match = CODE_RE.match(value)
    if match:
        return match.group(1)
    match = re.match(r"^(\d{2}-\d{3})", value)
    return match.group(1) if match else None


def parse_city_name(label: str) -> str:
    label = (label or "").strip()
    match = CITY_LABEL_RE.match(label)
    if match:
        return match.group(1).strip().title()
    return label.title()


def strefa_rank(strefa_name: str, kolor: str) -> int:
    match = re.search(r"STREFA\s+(\d+)", strefa_name or "", re.IGNORECASE)
    if match:
        return int(match.group(1))
    color_key = (kolor or "").upper()
    if color_key in STREFA_BY_COLOR:
        return STREFA_BY_COLOR[color_key][0]
    return 999


def strefa_label(rank: int) -> str:
    for color, (zone_rank, label) in STREFA_BY_COLOR.items():
        if zone_rank == rank:
            return label
    return f"STREFA {rank}"


def color_for_rank(rank: int, fallback: str = "#A8A8A8") -> str:
    for color, (zone_rank, _label) in STREFA_BY_COLOR.items():
        if zone_rank == rank:
            return color
    return fallback


def format_price(value: str | int | float | None) -> str:
    """Cena z dokładnie 2 miejscami po przecinku, np. 24.90."""
    if value is None or value == "":
        return ""
    try:
        num = float(str(value).replace(",", ".").replace(" ", ""))
    except ValueError:
        return ""
    return f"{num:.2f}"


def polygon_coords(geometry: dict) -> list:
    gtype = geometry.get("type")
    if gtype == "Polygon":
        return [geometry["coordinates"]]
    if gtype == "MultiPolygon":
        return geometry["coordinates"]
    return []


def merge_geometries(geometries: list[dict]) -> dict | None:
    polys: list = []
    for geometry in geometries:
        polys.extend(polygon_coords(geometry))
    if not polys:
        return None
    if len(polys) == 1:
        return {"type": "Polygon", "coordinates": polys[0]}
    return {"type": "MultiPolygon", "coordinates": polys}


def merge_features(features: list[dict]) -> dict:
    if len(features) == 1:
        return features[0]
    polys: list = []
    for feat in features:
        polys.extend(polygon_coords(feat["geometry"]))
    base = dict(features[0])
    geometry = merge_geometries([f["geometry"] for f in features])
    if geometry:
        base["geometry"] = geometry
    return base


def index_geojson_by_code(path: Path) -> dict[str, list[dict]]:
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    by_code: dict[str, list[dict]] = defaultdict(list)
    for feat in data.get("features") or []:
        code = normalize_code(str(feat.get("properties", {}).get("Name", "")))
        if code:
            by_code[code].append(feat)
    return by_code

# Miejscowosci-geo-json

Poligony kodów pocztowych (PostCodesMaps) → Airtable → mapa choropleth na stronie www.

## Airtable

| Element | Wartość |
|---------|---------|
| Baza | `appILpWFNjZbljnQz` |
| Tabela | `🚗 Obsługiwane` (`tblnKU6URo3lHtSpW`) |
| Widok | [MIEJSCOWOŚCI grid](https://airtable.com/appILpWFNjZbljnQz/tblnKU6URo3lHtSpW/viwcbyFWPVPpLgxgq) |

Pola tworzone przez sync:

- **GeoJSON** — pojedynczy Feature (long text, max ~95k znaków)
- **GeoJSON status** — `ok` / `brak w PostCodesMaps (śląskie)` / `ok (plik, …)` / `mapa zbiorcza (…)`
- **GeoJSON plik** — załącznik (max 5 MB) dla dużych kodów i mapy zbiorczej

Rekord specjalny: **`=== MAPA ZBIORCZA ===`** — załącznik `obslugiwane-choropleth.geojson` (~5 MB).

## Wymagania

- Python 3.10+
- Zmienna środowiskowa **`AIRTABLE_PAT`** (Personal Access Token z dostępem do bazy)

```powershell
$env:AIRTABLE_PAT = "pat..."
```

## Komendy

```powershell
cd G:\Cursor\Miejscowosci-geo-json

# Audyt stanu w Airtable
python verify_geojson.py

# Pobierz GeoJSON śląskie z GitHub (PostCodesMaps)
python sync_postcodes_geojson.py --download-only

# Pełny sync → Airtable (tekst + załączniki + mapa zbiorcza)
python sync_postcodes_geojson.py

# Tylko podgląd bez zapisu
python sync_postcodes_geojson.py --dry-run

# Tylko wgranie mapy zbiorczej (po pełnym sync)
python sync_postcodes_geojson.py --upload-map-only
```

## Pliki lokalne

| Plik | Opis |
|------|------|
| `data/postcodes/24_SLASKIE_ALL_PC_4326.geojson` | Źródło PostCodesMaps (~13 MB, gitignore) |
| `data/postcodes/obslugiwane-choropleth.geojson` | Mapa zbiorcza 763 stref (~5 MB, gitignore) |
| `data/postcodes/sample_slaskie.geojson` | Mały przykład (w repo) |

## Źródło poligonów

[PostCodesMaps](https://github.com/GML22/PostCodesMaps) — PRG, woj. śląskie, EPSG:4326.

## Framer / strona www

Mapa choropleth korzysta z `obslugiwane-choropleth.geojson` (hosting/CDN) lub składa się z pól `GeoJSON` + `kolor` ze stref w CMS.

Projekt strony: `G:\Cursor\strona_www` (osobny repozytorium — ten projekt tylko sync GeoJSON).

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

# Mapa miejscowości (scalone poligony + nazwy) → Framer
python build_miejscowosci_map.py
python build_miejscowosci_map.py --upload   # + załącznik w Airtable

# Agregacja: wszystkie 16 województw ← kody z MIEJSCOWOŚCI
python sync_wojewodztwa_kody.py --dry-run
python sync_wojewodztwa_kody.py

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
| `public/miejscowosci-polska.geojson` | Mapa miejscowości — hostuj na GitHub raw (~5 MB) |
| `public/polska-wojewodztwa.geojson` | Mapa województw — hostuj na GitHub raw |
| `data/wojewodztwa_kody_report.json` | Raport agregacji 16 województw ← kody |

## Źródło poligonów

[PostCodesMaps](https://github.com/GML22/PostCodesMaps) — PRG, woj. śląskie, EPSG:4326.

## Framer / strona www

Mapa choropleth korzysta z `obslugiwane-choropleth.geojson` (hosting/CDN) lub składa się z pól `GeoJSON` + `kolor` ze stref w CMS.

### Mapa miejscowości (Code Component)

1. Wygeneruj GeoJSON: `python build_miejscowosci_map.py --upload`
2. W Framer: **Assets → Code → New Component** → wklej `framer/MiejscowosciMap.tsx`
3. Dodaj komponent na stronę; w **URL GeoJSON miejscowości** wklej link do pliku (patrz niżej)
4. Komponent jest responsywny (`width: 100%`, regulowana wysokość)

**Hosting GeoJSON — polecamy GitHub (stały URL, bez Framer Pro):**

1. `python build_miejscowosci_map.py` → zapisuje też `public/miejscowosci-polska.geojson`
2. Wypchnij na GitHub (repo **publiczne**):

```powershell
git add public/miejscowosci-polska.geojson
git commit -m "update mapa miejscowości"
git push
```

3. URL do Framera (zamień `TWOJ_USER` na login GitHub):

```
https://raw.githubusercontent.com/TWOJ_USER/Miejscowosci-geo-json/main/public/miejscowosci-polska.geojson
```

4. W komponencie **MapaMiejscowosci** → **URL GeoJSON miejscowości** → wklej powyższy link.

Po zmianach w Airtable: ponów krok 1–2 (ten sam URL, Framer odświeży po publish).

| Sposób | Uwagi |
|--------|--------|
| **GitHub raw** (zalecane) | Stały URL, darmowe, repo publiczne |
| **Airtable** załącznik | Link wygasa ~2 h — tylko test |
| **Framer Files** | Dashboard → domena → Files — wymaga Framer Pro |

Jeśli Framer odrzuci rozszerzenie `.geojson`, zmień nazwę na `miejscowosci-polska.json` przed uploadem.

Reguła kolorów: jedna miejscowość = jeden kolor; przy wielu strefach wygrywa **niższa strefa** (STREFA 0 → 6).

### Mapa województw (Code Component)

1. Przygotuj GeoJSON: `python prepare_wojewodztwa_map.py` → `public/polska-wojewodztwa.geojson`
2. Podgląd lokalny: otwórz `public/mapa-wojewodztw.html`
3. W Framer: **Assets → Code → New Component** → wklej `framer/WojewodztwaMap.tsx`
4. URL GeoJSON (repo archiwum, branch `master`):

```
https://raw.githubusercontent.com/korfeloskar/Miejscowosci-geo-json/master/public/polska-wojewodztwa.geojson
```

| Plik | Opis |
|------|------|
| `public/polska-wojewodztwa.geojson` | Obrysy 16 województw (GitHub raw) |
| `public/mapa-wojewodztw.html` | Podgląd MapLibre |
| `framer/WojewodztwaMap.tsx` | Komponent Framer |

### Agregacja województw (wszystkie 16)

Tabela **Województwa** dostaje linki do kodów z **MIEJSCOWOŚCI** (pełne 16 województw).

```powershell
python sync_wojewodztwa_kody.py --dry-run   # podgląd liczb
python sync_wojewodztwa_kody.py             # tworzy pole «Kody» + wpisuje posty
```

Źródło przypisania: istniejący lookup **Województwo** na MIEJSCOWOŚCI (hierarchia Gmina → Powiat → Województwo).

Projekt strony: `G:\Cursor\strona_www` (osobny repozytorium — ten projekt tylko sync GeoJSON).

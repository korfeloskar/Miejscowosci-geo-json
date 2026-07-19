/**
 * Mapa Polski — obrysowane województwa (GeoJSON).
 *
 * Framer: Assets → Code → New Code Component → wklej ten plik.
 * Wymaga pakietu: maplibre-gl (Framer doinstaluje przy imporcie).
 *
 * Stack i styl jak MiejscowosciMap — tło + granice + etykiety + hover.
 * Domyślny URL: lokalny plik w repo / GitHub raw / andilabs CDN.
 */

import { addPropertyControls, ControlType } from "framer"
import maplibregl from "maplibre-gl"
import { useEffect, useRef, useState } from "react"

const POLSKA_URL =
    "https://raw.githubusercontent.com/korfeloskar/Miejscowosci-geo-json/master/public/polska-wojewodztwa.geojson"

const POLAND_BOUNDS: maplibregl.LngLatBoundsLike = [
    [14.05, 49.0],
    [24.25, 54.95],
]

/** Poprawione polskie nazwy (źródło GeoJSON ma ASCII / angielskie warianty). */
const NAZWA_PL: Record<string, string> = {
    Lodzkie: "Łódzkie",
    "Lódzkie": "Łódzkie",
    Swietokrzyskie: "Świętokrzyskie",
    Wielkopolskie: "Wielkopolskie",
    "Kujawsko-Pomorskie": "Kujawsko-Pomorskie",
    Malopolskie: "Małopolskie",
    Dolnoslaskie: "Dolnośląskie",
    Lubelskie: "Lubelskie",
    Lubuskie: "Lubuskie",
    Mazowieckie: "Mazowieckie",
    Opolskie: "Opolskie",
    Podlaskie: "Podlaskie",
    Pomorskie: "Pomorskie",
    Slaskie: "Śląskie",
    Podkarpackie: "Podkarpackie",
    "Warminsko-Mazurskie": "Warmińsko-Mazurskie",
    Zachodniopomorskie: "Zachodniopomorskie",
    "Greater Poland": "Wielkopolskie",
    "Kuyavian-Pomeranian": "Kujawsko-Pomorskie",
    "Lesser Poland": "Małopolskie",
    "Lower Silesian": "Dolnośląskie",
    Lublin: "Lubelskie",
    Lubusz: "Lubuskie",
    Masovian: "Mazowieckie",
    Opole: "Opolskie",
    Podlachian: "Podlaskie",
    Pomeranian: "Pomorskie",
    Silesian: "Śląskie",
    Subcarpathian: "Podkarpackie",
    "Warmian-Masurian": "Warmińsko-Mazurskie",
    "West Pomeranian": "Zachodniopomorskie",
    Łódź: "Łódzkie",
    "Świętokrzyskie": "Świętokrzyskie",
}

function nazwaWoj(props: Record<string, unknown>): string {
    const raw = String(props.name || props.NAME_1 || "").trim()
    if (!raw) return "Województwo"
    return NAZWA_PL[raw] || raw
}

function withPolishLabels(geojson: {
    type: string
    features: Array<{ type: string; geometry: unknown; properties?: Record<string, unknown> | null }>
}) {
    return {
        type: "FeatureCollection" as const,
        features: geojson.features.map((f) => {
            const props = { ...(f.properties || {}) }
            const label = nazwaWoj(props)
            return {
                ...f,
                properties: {
                    ...props,
                    nazwa: label,
                    label,
                },
            }
        }),
    }
}

function popupHtml(props: Record<string, string | number>): string {
    const name = String(props.nazwa || props.label || props.name || "Województwo")
    return `<div style="font-weight:600">${name}</div>`
}

type Props = {
    polskaUrl: string
    height: number
    labelSize: number
    borderWidth: number
    showLabels: boolean
    borderRadius: number
    cacheVersion: string
}

function withCacheBust(url: string, version: string): string {
    if (!url || !version) return url
    const sep = url.includes("?") ? "&" : "?"
    return `${url}${sep}v=${encodeURIComponent(version)}`
}

export default function WojewodztwaMap(props: Props) {
    const {
        polskaUrl,
        height,
        labelSize,
        borderWidth,
        showLabels,
        borderRadius,
        cacheVersion,
    } = props

    const containerRef = useRef<HTMLDivElement>(null)
    const mapRef = useRef<maplibregl.Map | null>(null)
    const [error, setError] = useState("")
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        if (!containerRef.current || !polskaUrl) {
            setLoading(false)
            if (!polskaUrl) setError("Ustaw URL GeoJSON województw")
            return
        }

        let cancelled = false
        setError("")
        setLoading(true)

        const map = new maplibregl.Map({
            container: containerRef.current,
            style: {
                version: 8,
                glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
                sources: {},
                layers: [
                    {
                        id: "background",
                        type: "background",
                        paint: { "background-color": "#f7f7f8" },
                    },
                ],
            },
            bounds: POLAND_BOUNDS,
            fitBoundsOptions: { padding: 24 },
            attributionControl: false,
            dragRotate: false,
            pitchWithRotate: false,
            touchPitch: false,
        })

        mapRef.current = map
        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right")

        map.on("load", () => {
            const nav = map.getContainer().querySelector(".maplibregl-ctrl-top-right") as HTMLElement | null
            if (nav) {
                nav.style.margin = "20px 24px 0 0"
            }
        })

        const onResize = () => map.resize()
        window.addEventListener("resize", onResize)

        map.on("load", async () => {
            try {
                const url = withCacheBust(polskaUrl, cacheVersion)
                const res = await fetch(url)
                if (!res.ok) throw new Error(`Województwa: HTTP ${res.status}`)

                const raw = await res.json()
                if (cancelled) return
                const polska = withPolishLabels(raw)

                map.addSource("wojewodztwa", {
                    type: "geojson",
                    data: polska,
                    promoteId: "HASC_1",
                })
                map.addLayer({
                    id: "woj-fill",
                    type: "fill",
                    source: "wojewodztwa",
                    paint: {
                        "fill-color": [
                            "case",
                            ["boolean", ["feature-state", "hover"], false],
                            "#d4d4d8",
                            "#ececef",
                        ],
                        "fill-opacity": 1,
                    },
                })
                map.addLayer({
                    id: "woj-line",
                    type: "line",
                    source: "wojewodztwa",
                    paint: {
                        "line-color": "#11181F",
                        "line-width": borderWidth,
                        "line-opacity": 0.85,
                    },
                })

                if (showLabels) {
                    map.addLayer({
                        id: "woj-labels",
                        type: "symbol",
                        source: "wojewodztwa",
                        layout: {
                            "text-field": ["get", "nazwa"],
                            "text-size": labelSize,
                            "text-font": ["Open Sans Regular"],
                            "text-anchor": "center",
                            "text-allow-overlap": false,
                            "text-ignore-placement": false,
                            "text-padding": 4,
                            "text-max-width": 10,
                        },
                        paint: {
                            "text-color": "#11181F",
                            "text-halo-color": "#ffffff",
                            "text-halo-width": 1.5,
                        },
                    })
                }

                let hoveredId: string | number | undefined
                const popup = new maplibregl.Popup({
                    closeButton: false,
                    closeOnClick: false,
                    offset: 16,
                    className: "pbs-map-popup",
                    maxWidth: "240px",
                })

                map.on("mousemove", "woj-fill", (e) => {
                    if (!e.features?.length) return
                    const feature = e.features[0]
                    const id = feature.id
                    map.getCanvas().style.cursor = "pointer"

                    if (hoveredId !== undefined && hoveredId !== id && id !== undefined) {
                        map.setFeatureState({ source: "wojewodztwa", id: hoveredId }, { hover: false })
                    }
                    if (id !== undefined && id !== null) {
                        hoveredId = id
                        map.setFeatureState({ source: "wojewodztwa", id: hoveredId }, { hover: true })
                    }

                    const props = feature.properties
                    if (!props) return
                    popup
                        .setLngLat(e.lngLat)
                        .setHTML(popupHtml(props as Record<string, string | number>))
                        .addTo(map)
                })

                map.on("mouseleave", "woj-fill", () => {
                    map.getCanvas().style.cursor = ""
                    if (hoveredId !== undefined) {
                        map.setFeatureState({ source: "wojewodztwa", id: hoveredId }, { hover: false })
                        hoveredId = undefined
                    }
                    popup.remove()
                })

                setLoading(false)
            } catch (err) {
                if (!cancelled) {
                    setError(err instanceof Error ? err.message : "Błąd ładowania mapy")
                    setLoading(false)
                }
            }
        })

        return () => {
            cancelled = true
            window.removeEventListener("resize", onResize)
            map.remove()
            mapRef.current = null
        }
    }, [polskaUrl, labelSize, borderWidth, showLabels, cacheVersion])

    return (
        <div
            style={{
                width: "100%",
                height,
                position: "relative",
                borderRadius,
                overflow: "hidden",
                background: "#f7f7f8",
                fontFamily: "Inter, system-ui, sans-serif",
            }}
        >
            <link
                rel="stylesheet"
                href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"
            />
            <style>{`
                .pbs-map-popup .maplibregl-popup-content {
                    padding: 10px 12px;
                    border-radius: 10px;
                    font-size: 13px;
                    box-shadow: 0 8px 24px rgba(17, 24, 31, 0.12);
                }
                .pbs-map-popup.maplibregl-popup-anchor-bottom .maplibregl-popup-tip,
                .pbs-map-popup.maplibregl-popup-anchor-top .maplibregl-popup-tip,
                .pbs-map-popup.maplibregl-popup-anchor-left .maplibregl-popup-tip,
                .pbs-map-popup.maplibregl-popup-anchor-right .maplibregl-popup-tip {
                    margin-top: -1px;
                }
            `}</style>
            <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

            {loading && (
                <div
                    style={{
                        position: "absolute",
                        inset: 0,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        background: "rgba(247,247,248,0.85)",
                        color: "#11181F",
                        fontSize: 14,
                    }}
                >
                    Ładowanie mapy…
                </div>
            )}

            {error && (
                <div
                    style={{
                        position: "absolute",
                        inset: 0,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: 24,
                        textAlign: "center",
                        color: "#11181F",
                        fontSize: 14,
                        background: "#f7f7f8",
                    }}
                >
                    {error}
                </div>
            )}
        </div>
    )
}

WojewodztwaMap.defaultProps = {
    polskaUrl: POLSKA_URL,
    height: 560,
    labelSize: 12,
    borderWidth: 1.8,
    showLabels: true,
    borderRadius: 12,
    cacheVersion: "1",
}

addPropertyControls(WojewodztwaMap, {
    polskaUrl: {
        type: ControlType.String,
        title: "URL GeoJSON województw",
        defaultValue: POLSKA_URL,
        description: "polska-wojewodztwa.geojson (GitHub raw lub CDN)",
    },
    height: {
        type: ControlType.Number,
        title: "Wysokość",
        defaultValue: 560,
        min: 280,
        max: 1200,
        step: 20,
    },
    labelSize: {
        type: ControlType.Number,
        title: "Rozmiar etykiet",
        defaultValue: 12,
        min: 10,
        max: 22,
        step: 1,
    },
    borderWidth: {
        type: ControlType.Number,
        title: "Grubość obrysu",
        defaultValue: 1.8,
        min: 0.8,
        max: 4,
        step: 0.2,
    },
    showLabels: {
        type: ControlType.Boolean,
        title: "Etykiety województw",
        defaultValue: true,
    },
    borderRadius: {
        type: ControlType.Number,
        title: "Zaokrąglenie",
        defaultValue: 12,
        min: 0,
        max: 32,
        step: 2,
    },
})

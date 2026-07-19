/**
 * Mapa Polski — województwa + miejscowości (punkty PRNG).
 *
 * Framer: Assets → Code → New Code Component → wklej ten plik.
 * Wymaga pakietu: maplibre-gl (Framer doinstaluje przy imporcie).
 *
 * Dane (GitHub raw, branch master):
 *  - polska-wojewodztwa.geojson — obrysy 16 województw
 *  - miasta-prng.geojson — ~1020 miast (domyślnie, lekkie)
 *  - miejscowosci-prng.geojson — ~44k miast+wsi (pełna warstwa)
 *
 * Źródło miejscowości: mbroton/polish-geonames (PRNG, CC BY 4.0) — nie Airtable.
 */

import { addPropertyControls, ControlType } from "framer"
import maplibregl from "maplibre-gl"
import { useEffect, useRef, useState } from "react"

const POLSKA_URL =
    "https://raw.githubusercontent.com/korfeloskar/Miejscowosci-geo-json/master/public/polska-wojewodztwa.geojson"

const MIEJSCOWOSCI_URL =
    "https://raw.githubusercontent.com/korfeloskar/Miejscowosci-geo-json/master/public/miasta-prng.geojson"

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

function wojPopupHtml(props: Record<string, string | number>): string {
    const name = String(props.nazwa || props.label || props.name || "Województwo")
    return `<div style="font-weight:600">${name}</div>`
}

function miejscePopupHtml(props: Record<string, string | number>): string {
    const name = String(props.nazwa || props.name || props.miasto || "Miejscowość")
    const rodzaj = String(props.rodzaj || props.type || "")
    const woj = String(props.wojewodztwo || "")
    const powiat = String(props.powiat || "")
    const gmina = String(props.gmina || "")
    const lines = [
        `<div style="font-weight:600;margin-bottom:4px">${name}</div>`,
        rodzaj ? `<div style="opacity:.85">${rodzaj}</div>` : "",
        woj ? `<div style="opacity:.85">woj. ${woj}</div>` : "",
        powiat ? `<div style="opacity:.75">powiat ${powiat}</div>` : "",
        gmina ? `<div style="opacity:.75">gmina ${gmina}</div>` : "",
    ]
    return lines.filter(Boolean).join("")
}

type Props = {
    polskaUrl: string
    miejscowosciUrl: string
    showMiejscowosci: boolean
    showMiejscowosciLabels: boolean
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
        miejscowosciUrl,
        showMiejscowosci,
        showMiejscowosciLabels,
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
        map.addControl(
            new maplibregl.AttributionControl({
                compact: true,
                customAttribution:
                    'Miejscowości: <a href="https://github.com/mbroton/polish-geonames">PRNG / polish-geonames</a> (CC BY 4.0)',
            }),
            "bottom-right"
        )

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
                const wojUrl = withCacheBust(polskaUrl, cacheVersion)
                const res = await fetch(wojUrl)
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

                if (showMiejscowosci && miejscowosciUrl) {
                    const mUrl = withCacheBust(miejscowosciUrl, cacheVersion)
                    const mRes = await fetch(mUrl)
                    if (!mRes.ok) throw new Error(`Miejscowości: HTTP ${mRes.status}`)
                    const miejsca = await mRes.json()
                    if (cancelled) return

                    map.addSource("miejscowosci", {
                        type: "geojson",
                        data: miejsca,
                        cluster: true,
                        clusterMaxZoom: 10,
                        clusterRadius: 42,
                    })

                    map.addLayer({
                        id: "miejsca-clusters",
                        type: "circle",
                        source: "miejscowosci",
                        filter: ["has", "point_count"],
                        paint: {
                            "circle-color": "#11181F",
                            "circle-opacity": 0.72,
                            "circle-radius": [
                                "step",
                                ["get", "point_count"],
                                14,
                                25,
                                18,
                                100,
                                24,
                                500,
                                30,
                            ],
                        },
                    })

                    map.addLayer({
                        id: "miejsca-cluster-count",
                        type: "symbol",
                        source: "miejscowosci",
                        filter: ["has", "point_count"],
                        layout: {
                            "text-field": ["get", "point_count_abbreviated"],
                            "text-font": ["Open Sans Regular"],
                            "text-size": 11,
                        },
                        paint: {
                            "text-color": "#ffffff",
                        },
                    })

                    map.addLayer({
                        id: "miejsca-points",
                        type: "circle",
                        source: "miejscowosci",
                        filter: ["!", ["has", "point_count"]],
                        paint: {
                            "circle-color": [
                                "match",
                                ["get", "type"],
                                "city",
                                "#11181F",
                                "#52525b",
                            ],
                            "circle-radius": [
                                "match",
                                ["get", "type"],
                                "city",
                                4.5,
                                3,
                            ],
                            "circle-stroke-width": 1,
                            "circle-stroke-color": "#ffffff",
                            "circle-opacity": 0.9,
                        },
                    })

                    if (showMiejscowosciLabels) {
                        map.addLayer({
                            id: "miejsca-labels",
                            type: "symbol",
                            source: "miejscowosci",
                            filter: [
                                "all",
                                ["!", ["has", "point_count"]],
                                ["==", ["get", "type"], "city"],
                            ],
                            minzoom: 7,
                            layout: {
                                "text-field": ["get", "nazwa"],
                                "text-size": Math.max(10, labelSize - 2),
                                "text-font": ["Open Sans Regular"],
                                "text-offset": [0, 1.1],
                                "text-anchor": "top",
                                "text-optional": true,
                            },
                            paint: {
                                "text-color": "#11181F",
                                "text-halo-color": "#ffffff",
                                "text-halo-width": 1.2,
                            },
                        })
                    }

                    map.on("click", "miejsca-clusters", (e) => {
                        const features = map.queryRenderedFeatures(e.point, {
                            layers: ["miejsca-clusters"],
                        })
                        const clusterId = features[0]?.properties?.cluster_id
                        const source = map.getSource("miejscowosci") as maplibregl.GeoJSONSource
                        if (clusterId == null) return
                        source.getClusterExpansionZoom(clusterId, (err, zoom) => {
                            if (err || zoom == null || !features[0].geometry) return
                            const geom = features[0].geometry as {
                                type: string
                                coordinates: [number, number]
                            }
                            map.easeTo({
                                center: geom.coordinates,
                                zoom,
                            })
                        })
                    })
                }

                let hoveredId: string | number | undefined
                const popup = new maplibregl.Popup({
                    closeButton: false,
                    closeOnClick: false,
                    offset: 16,
                    className: "pbs-map-popup",
                    maxWidth: "260px",
                })

                map.on("mousemove", "woj-fill", (e) => {
                    if (!e.features?.length) return
                    // Nie nadpisuj popupu gdy kursor jest nad punktem miejscowości
                    if (showMiejscowosci && miejscowosciUrl) {
                        const overPoint = map.queryRenderedFeatures(e.point, {
                            layers: ["miejsca-points"].filter((id) => map.getLayer(id)),
                        })
                        if (overPoint.length) return
                    }
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
                        .setHTML(wojPopupHtml(props as Record<string, string | number>))
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

                if (showMiejscowosci && miejscowosciUrl) {
                    map.on("mousemove", "miejsca-points", (e) => {
                        if (!e.features?.length) return
                        map.getCanvas().style.cursor = "pointer"
                        const props = e.features[0].properties
                        if (!props) return
                        popup
                            .setLngLat(e.lngLat)
                            .setHTML(miejscePopupHtml(props as Record<string, string | number>))
                            .addTo(map)
                    })
                    map.on("mouseleave", "miejsca-points", () => {
                        map.getCanvas().style.cursor = ""
                        popup.remove()
                    })
                    map.on("mouseenter", "miejsca-clusters", () => {
                        map.getCanvas().style.cursor = "pointer"
                    })
                    map.on("mouseleave", "miejsca-clusters", () => {
                        map.getCanvas().style.cursor = ""
                    })
                }

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
    }, [
        polskaUrl,
        miejscowosciUrl,
        showMiejscowosci,
        showMiejscowosciLabels,
        labelSize,
        borderWidth,
        showLabels,
        cacheVersion,
    ])

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
    miejscowosciUrl: MIEJSCOWOSCI_URL,
    showMiejscowosci: true,
    showMiejscowosciLabels: true,
    height: 560,
    labelSize: 12,
    borderWidth: 1.8,
    showLabels: true,
    borderRadius: 12,
    cacheVersion: "2",
}

addPropertyControls(WojewodztwaMap, {
    polskaUrl: {
        type: ControlType.String,
        title: "URL GeoJSON województw",
        defaultValue: POLSKA_URL,
        description: "polska-wojewodztwa.geojson (GitHub raw)",
    },
    miejscowosciUrl: {
        type: ControlType.String,
        title: "URL GeoJSON miejscowości",
        defaultValue: MIEJSCOWOSCI_URL,
        description:
            "miasta-prng.geojson (~1k miast) lub miejscowosci-prng.geojson (~44k miast+wsi)",
    },
    showMiejscowosci: {
        type: ControlType.Boolean,
        title: "Pokaż miejscowości",
        defaultValue: true,
    },
    showMiejscowosciLabels: {
        type: ControlType.Boolean,
        title: "Etykiety miast",
        defaultValue: true,
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
    cacheVersion: {
        type: ControlType.String,
        title: "Cache version",
        defaultValue: "2",
        description: "Zwiększ po update danych (np. 3), żeby Framer pobrał świeże pliki",
    },
})

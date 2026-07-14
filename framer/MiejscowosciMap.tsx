/**
 * Mapa Polski — miejscowości obsługiwane (GeoJSON z Airtable).
 *
 * Framer: Assets → Code → New Code Component → wklej ten plik.
 * Wymaga pakietu: maplibre-gl (Framer doinstaluje przy imporcie).
 *
 * 1. python build_miejscowosci_map.py --upload
 * 2. URL GeoJSON — jedna z opcji (patrz README):
 *    - Airtable: rekord «=== MAPA MIEJSCOWOSCI ===» → załącznik → kopiuj link
 *    - Framer Dashboard → domena → zakładka Files → upload (plan Pro+)
 * 3. Wklej URL w property «URL GeoJSON miejscowości»
 */

import { addPropertyControls, ControlType } from "framer"
import maplibregl from "maplibre-gl"
import { useEffect, useRef, useState } from "react"

const POLSKA_URL =
    "https://raw.githubusercontent.com/andilabs/polska-wojewodztwa-geojson/master/polska-wojewodztwa.geojson"

const POLAND_BOUNDS: maplibregl.LngLatBoundsLike = [
    [14.05, 49.0],
    [24.25, 54.95],
]

const STREFY = [
    { rank: 0, label: "STREFA 0", color: "#FF0000" },
    { rank: 1, label: "STREFA 1", color: "#FFCD00" },
    { rank: 2, label: "STREFA 2", color: "#AEFF00" },
    { rank: 3, label: "STREFA 3", color: "#00FFF0" },
    { rank: 4, label: "STREFA 4", color: "#CD00FF" },
    { rank: 5, label: "STREFA 5", color: "#9C9CBD" },
    { rank: 6, label: "STREFA 6", color: "#3E7413" },
]

type Props = {
    dataUrl: string
    polskaUrl: string
    height: number
    labelSize: number
    showLegend: boolean
    borderRadius: number
}

export default function MiejscowosciMap(props: Props) {
    const {
        dataUrl,
        polskaUrl,
        height,
        labelSize,
        showLegend,
        borderRadius,
    } = props

    const containerRef = useRef<HTMLDivElement>(null)
    const mapRef = useRef<maplibregl.Map | null>(null)
    const [error, setError] = useState("")
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        if (!containerRef.current || !dataUrl) {
            setLoading(false)
            if (!dataUrl) setError("Ustaw URL GeoJSON miejscowości")
            return
        }

        let cancelled = false
        setError("")
        setLoading(true)

        const map = new maplibregl.Map({
            container: containerRef.current,
            style: {
                version: 8,
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

        const onResize = () => map.resize()
        window.addEventListener("resize", onResize)

        map.on("load", async () => {
            try {
                const [polskaRes, miastaRes] = await Promise.all([
                    fetch(polskaUrl),
                    fetch(dataUrl),
                ])
                if (!polskaRes.ok) throw new Error(`Polska: HTTP ${polskaRes.status}`)
                if (!miastaRes.ok) throw new Error(`Miejscowości: HTTP ${miastaRes.status}`)

                const polska = await polskaRes.json()
                const miasta = await miastaRes.json()
                if (cancelled) return

                map.addSource("polska", { type: "geojson", data: polska })
                map.addLayer({
                    id: "polska-fill",
                    type: "fill",
                    source: "polska",
                    paint: {
                        "fill-color": "#ececef",
                        "fill-opacity": 1,
                    },
                })
                map.addLayer({
                    id: "polska-line",
                    type: "line",
                    source: "polska",
                    paint: {
                        "line-color": "#11181F",
                        "line-width": 1.2,
                        "line-opacity": 0.35,
                    },
                })

                map.addSource("miasta", { type: "geojson", data: miasta })
                map.addLayer({
                    id: "miasta-fill",
                    type: "fill",
                    source: "miasta",
                    paint: {
                        "fill-color": ["get", "kolor"],
                        "fill-opacity": 0.72,
                        "fill-outline-color": "#11181F",
                    },
                })
                map.addLayer({
                    id: "miasta-line",
                    type: "line",
                    source: "miasta",
                    paint: {
                        "line-color": "#11181F",
                        "line-width": 0.6,
                        "line-opacity": 0.45,
                    },
                })
                map.addLayer({
                    id: "miasta-labels",
                    type: "symbol",
                    source: "miasta",
                    layout: {
                        "text-field": ["get", "miasto"],
                        "text-size": labelSize,
                        "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
                        "text-anchor": "center",
                        "text-allow-overlap": false,
                        "text-ignore-placement": false,
                        "text-padding": 2,
                    },
                    paint: {
                        "text-color": "#11181F",
                        "text-halo-color": "#ffffff",
                        "text-halo-width": 1.5,
                    },
                })

                map.on("mouseenter", "miasta-fill", () => {
                    map.getCanvas().style.cursor = "pointer"
                })
                map.on("mouseleave", "miasta-fill", () => {
                    map.getCanvas().style.cursor = ""
                })

                const popup = new maplibregl.Popup({
                    closeButton: false,
                    closeOnClick: false,
                    offset: 12,
                })

                map.on("mousemove", "miasta-fill", (e) => {
                    if (!e.features?.length) return
                    const props = e.features[0].properties
                    if (!props) return
                    map.getCanvas().style.cursor = "pointer"
                    popup
                        .setLngLat(e.lngLat)
                        .setHTML(
                            `<strong>${props.miasto}</strong><br/>${props.strefa}<br/><span style="opacity:.75">${props.kody_count} kodów pocztowych</span>`
                        )
                        .addTo(map)
                })
                map.on("mouseleave", "miasta-fill", () => {
                    map.getCanvas().style.cursor = ""
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
    }, [dataUrl, polskaUrl, labelSize])

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

            {showLegend && (
                <div
                    style={{
                        position: "absolute",
                        left: 12,
                        bottom: 12,
                        background: "rgba(255,255,255,0.94)",
                        border: "1px solid #e4e4e7",
                        borderRadius: 10,
                        padding: "10px 12px",
                        boxShadow: "0 4px 16px rgba(17,24,31,0.08)",
                        fontSize: 12,
                        lineHeight: 1.5,
                        color: "#11181F",
                        maxWidth: "calc(100% - 24px)",
                    }}
                >
                    <div style={{ fontWeight: 600, marginBottom: 6 }}>Strefy serwisu</div>
                    <div
                        style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
                            gap: 6,
                        }}
                    >
                        {STREFY.map((s) => (
                            <div
                                key={s.rank}
                                style={{ display: "flex", alignItems: "center", gap: 6 }}
                            >
                                <span
                                    style={{
                                        width: 12,
                                        height: 12,
                                        borderRadius: 3,
                                        background: s.color,
                                        border: "1px solid rgba(17,24,31,0.15)",
                                        flexShrink: 0,
                                    }}
                                />
                                <span>{s.label}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}

MiejscowosciMap.defaultProps = {
    dataUrl: "",
    polskaUrl: POLSKA_URL,
    height: 560,
    labelSize: 13,
    showLegend: true,
    borderRadius: 12,
}

addPropertyControls(MiejscowosciMap, {
    dataUrl: {
        type: ControlType.String,
        title: "URL GeoJSON miejscowości",
        description: "miejscowosci-polska.geojson (Airtable CDN lub Framer Assets)",
    },
    polskaUrl: {
        type: ControlType.String,
        title: "URL GeoJSON Polski",
        defaultValue: POLSKA_URL,
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
        defaultValue: 13,
        min: 10,
        max: 22,
        step: 1,
    },
    showLegend: {
        type: ControlType.Boolean,
        title: "Legenda stref",
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

"use client";

import { useEffect, useRef } from "react";
import {
  LngLatBounds,
  Map,
  Marker,
  NavigationControl,
  Popup,
  type GeoJSONSource,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { PlaceCandidate, RouteSnapshot } from "@/lib/types";

const STYLE = "https://tiles.openfreemap.org/styles/dark";

function lineData(coordinates: number[][]) {
  return {
    type: "Feature" as const,
    properties: {},
    geometry: { type: "LineString" as const, coordinates },
  };
}

function upsertLine(
  map: Map,
  sourceId: string,
  layerId: string,
  coordinates: number[][],
  color: string,
  width: number,
  dash?: number[],
) {
  const data = lineData(coordinates);
  const source = map.getSource(sourceId) as GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
    return;
  }
  map.addSource(sourceId, { type: "geojson", data });
  map.addLayer({
    id: layerId,
    type: "line",
    source: sourceId,
    paint: {
      "line-color": color,
      "line-width": width,
      "line-opacity": 0.9,
      ...(dash ? { "line-dasharray": dash } : {}),
    },
  });
}

export function RouteMap({
  corridor,
  selected,
  alternatives = [],
}: {
  corridor: RouteSnapshot | null;
  selected: PlaceCandidate | null;
  alternatives?: PlaceCandidate[];
}) {
  const root = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const markersRef = useRef<Marker[]>([]);

  useEffect(() => {
    if (!root.current || mapRef.current) return;
    const map = new Map({
      container: root.current,
      style: STYLE,
      center: [77.15, 28.56],
      zoom: 10.2,
      attributionControl: true,
    });
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    return () => {
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !corridor?.geometry?.length) return;

    const apply = () => {
      upsertLine(map, "corridor", "corridor-line", corridor.geometry, "#e8a14a", 4);
      const via = corridor.via_geometry || [];
      if (via.length > 1) {
        upsertLine(map, "via", "via-line", via, "#7ddec5", 3, [1.4, 1.2]);
      } else if (map.getSource("via")) {
        (map.getSource("via") as GeoJSONSource).setData(lineData([]));
      }
      const bounds = new LngLatBounds();
      for (const pair of corridor.geometry) {
        bounds.extend(pair as [number, number]);
      }
      for (const pair of via) {
        bounds.extend(pair as [number, number]);
      }
      if (selected?.lng != null && selected?.lat != null) {
        bounds.extend([selected.lng, selected.lat]);
      }
      if (!bounds.isEmpty()) {
        map.fitBounds(bounds, { padding: 48, duration: 600, maxZoom: 13 });
      }
    };

    if (map.loaded() && map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [corridor, selected]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    markersRef.current.forEach((marker) => marker.remove());
    const next: Marker[] = [];
    if (corridor) {
      next.push(
        new Marker({ color: "#7ddec5" })
          .setLngLat([corridor.origin_lng, corridor.origin_lat])
          .setPopup(new Popup().setText(corridor.origin_name))
          .addTo(map),
      );
      next.push(
        new Marker({ color: "#9a9388" })
          .setLngLat([corridor.dest_lng, corridor.dest_lat])
          .setPopup(new Popup().setText(corridor.destination_name))
          .addTo(map),
      );
    }
    if (selected?.lng != null && selected?.lat != null) {
      next.push(
        new Marker({ color: "#e8a14a" })
          .setLngLat([selected.lng, selected.lat])
          .setPopup(new Popup().setText(`${selected.name} · ${selected.area}`))
          .addTo(map),
      );
    }
    for (const alt of alternatives) {
      if (alt.lng == null || alt.lat == null) continue;
      next.push(
        new Marker({ color: "#5c564e" })
          .setLngLat([alt.lng, alt.lat])
          .setPopup(new Popup().setText(`${alt.name} · ${alt.area}`))
          .addTo(map),
      );
    }
    markersRef.current = next;
  }, [alternatives, corridor, selected]);

  return (
    <section className="panel relative min-h-[280px] overflow-hidden rounded-3xl">
      <div className="pointer-events-none absolute left-4 top-4 z-10 space-y-2">
        <div className="text-[11px] uppercase tracking-[0.18em] text-[#9a9388]">Corridor</div>
        {corridor ? (
          <div className="rounded-2xl border border-white/10 bg-black/45 px-3 py-2 text-xs text-[#f4efe6] backdrop-blur">
            <div className="font-medium">
              {corridor.origin_name} → {corridor.destination_name}
            </div>
            <div className="mt-1 text-[#cfc6b8]">
              {corridor.eta_minutes ? `${corridor.eta_minutes} min` : ""}
              {corridor.distance_km ? ` · ${corridor.distance_km} km` : ""}
              {corridor.avoid_tolls ? " · toll-avoiding requested" : ""}
            </div>
            {selected ? (
              <div className="mt-1 text-[#e8a14a]">
                Stop · {selected.name}
                {selected.verified && selected.detour_minutes != null ? ` · +${selected.detour_minutes} min` : ""}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
      <div ref={root} className="h-full min-h-[320px] w-full" />
      {!corridor ? (
        <p className="absolute inset-x-4 bottom-4 text-sm text-[#9a9388]">
          Waiting for the Gurgaon to Delhi route.
        </p>
      ) : null}
    </section>
  );
}

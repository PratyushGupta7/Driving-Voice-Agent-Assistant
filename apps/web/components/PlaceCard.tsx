import type { PlaceCandidate } from "@/lib/types";

export function PlaceCard({
  place,
  active,
  label,
}: {
  place: PlaceCandidate;
  active?: boolean;
  label?: string;
}) {
  return (
    <div
      className={`rounded-2xl px-3 py-2 text-sm ${
        active
          ? "border border-[#e8a14a]/40 bg-[#e8a14a]/10 text-[#f4efe6]"
          : "border border-white/8 bg-black/20 text-[#cfc6b8]"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-[#f4efe6]">{place.name}</span>
        {label ? <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#9a9388]">{label}</span> : null}
      </div>
      <div className="mt-1 text-xs text-[#9a9388]">
        {place.area}
        {place.verified && place.detour_minutes != null ? ` · +${place.detour_minutes} min` : ""}
        {place.parking === "yes" ? " · lot reported" : ""}
      </div>
      {place.reasons?.[0] ? <div className="mt-1 text-xs text-[#cfc6b8]">{place.reasons[0]}</div> : null}
    </div>
  );
}

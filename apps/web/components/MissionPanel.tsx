import { PlaceCard } from "@/components/PlaceCard";
import { VersionRail } from "@/components/VersionRail";
import type { MissionSnapshot, PlaceCandidate } from "@/lib/types";

function chip(label: string, on: boolean) {
  return (
    <span
      className={`rounded-full px-2 py-1 text-[10px] uppercase tracking-[0.12em] ${
        on ? "bg-[#e8a14a]/16 text-[#e8a14a]" : "border border-white/8 text-[#9a9388]"
      }`}
    >
      {label}
    </span>
  );
}

export function MissionPanel({
  snapshot,
  alternatives = [],
}: {
  snapshot: MissionSnapshot | null;
  alternatives?: PlaceCandidate[];
}) {
  const constraints = snapshot?.constraints;
  const gate = snapshot?.output_gate ?? "closed_for_input";
  const alts = snapshot?.alternatives?.length ? snapshot.alternatives : alternatives;

  return (
    <section className="panel rounded-3xl p-5">
      <div className="flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-[0.18em] text-[#9a9388]">Mission</div>
        {snapshot?.last_revision ? (
          <div className="font-mono text-[10px] text-[#cfc6b8]">{snapshot.last_revision}</div>
        ) : null}
      </div>
      {!snapshot || snapshot.status === "idle" ? (
        <p className="mt-3 text-sm leading-6 text-[#cfc6b8]">
          Ask for coffee, fuel, or a pharmacy. You can add parking, tolls, a landmark, or a
          destination while I am still talking.
        </p>
      ) : (
        <div className="mt-3 space-y-3">
          <div className="text-sm leading-6 text-[#f4efe6]">
            {snapshot.status === "cancelled"
              ? "Mission cancelled."
              : snapshot.status === "clarifying"
                ? "Need a clearer request."
                : `Looking for ${constraints?.category ?? "a place"} on the way.`}
          </div>
          {constraints?.origin_query ||
          constraints?.destination_query ||
          constraints?.landmark_query ||
          constraints?.brand_query ? (
            <div className="text-xs leading-5 text-[#cfc6b8]">
              {constraints.origin_query ? <div>Start · {constraints.origin_query}</div> : null}
              {constraints.destination_query ? <div>End · {constraints.destination_query}</div> : null}
              {constraints.landmark_query ? <div>Near · {constraints.landmark_query}</div> : null}
              {constraints.brand_query ? <div>Match · {constraints.brand_query}</div> : null}
              {constraints.prefer_along ? <div>Bias · {constraints.prefer_along}</div> : null}
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {chip("parking required", Boolean(constraints?.parking_required))}
            {chip("avoid tolls", Boolean(constraints?.avoid_tolls))}
            {constraints?.maximum_detour_minutes != null
              ? chip(`max ${constraints.maximum_detour_minutes} min`, true)
              : chip("no detour cap", false)}
          </div>
          {snapshot.selected ? <PlaceCard place={snapshot.selected} active label="keep?" /> : null}
          {snapshot.selected && alts.length
            ? alts.slice(0, 2).map((item, index) => (
                <PlaceCard key={item.id || item.name} place={item} label={`option ${index + 2}`} />
              ))
            : null}
          <VersionRail entries={snapshot.version_log ?? []} current={snapshot.mission_version} />
        </div>
      )}
      <div className="mt-4 grid grid-cols-2 gap-2 font-mono text-[11px] text-[#9a9388]">
        <div className="rounded-xl border border-white/8 px-3 py-2">
          version · {snapshot?.mission_version ?? 0}
        </div>
        <div className="rounded-xl border border-white/8 px-3 py-2">
          epoch · {snapshot?.output_epoch ?? 0}
        </div>
        <div className="col-span-2 rounded-xl border border-white/8 px-3 py-2">
          gate · {gate === "closed_for_input" ? "BARRIER_CLOSED" : gate.replaceAll("_", " ")}
          {snapshot?.last_barrier_ms != null ? ` · ${snapshot.last_barrier_ms}ms` : ""}
        </div>
      </div>
    </section>
  );
}

import type { ToolRow } from "@/lib/types";

function tone(decision: string): string {
  if (decision === "accepted") return "text-[#7ddec5]";
  if (decision === "stale_rejected" || decision === "failed" || decision === "cancel_requested") {
    return "text-[#f07167]";
  }
  if (decision === "running") return "text-[#e8a14a]";
  return "text-[#cfc6b8]";
}

function shown(row: ToolRow): string {
  return row.label || row.decision;
}

export function ToolTimeline({ rows }: { rows: ToolRow[] }) {
  const routeRows = rows.filter((row) => row.kind === "route");
  const placeRows = rows.filter((row) => row.kind !== "route");
  const stale = rows.filter((row) => row.decision === "stale_rejected").length;
  const accepted = rows.filter((row) => row.decision === "accepted").length;

  return (
    <section className="panel min-h-0 flex-1 overflow-hidden rounded-3xl p-5">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[11px] uppercase tracking-[0.18em] text-[#9a9388]">Fence race</div>
        <div className="font-mono text-[10px] text-[#9a9388]">
          stale {stale} · accepted {accepted}
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <Lane title="Route" rows={routeRows} />
        <Lane title="Place" rows={placeRows} />
      </div>
    </section>
  );
}

function Lane({ title, rows }: { title: string; rows: ToolRow[] }) {
  return (
    <div>
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-[#9a9388]">{title}</div>
      <div className="max-h-[220px] space-y-2 overflow-y-auto font-mono text-[11px] text-[#cfc6b8]">
        {rows.length === 0 ? (
          <p>Idle.</p>
        ) : (
          rows
            .slice()
            .reverse()
            .map((row) => (
              <div key={row.id} className="border-b border-white/6 pb-2">
                <div className="flex items-center justify-between gap-2">
                  <span>v{row.mission_version} · e{row.output_epoch}</span>
                  <span className={tone(row.decision)}>{shown(row)}</span>
                </div>
                <div className="mt-1 text-[#9a9388]">
                  {row.name ? `${row.name}${row.area ? ` · ${row.area}` : ""}` : row.kind}
                  {row.delay_ms != null ? ` · ${row.delay_ms}ms` : ""}
                  {row.delay_s != null && row.delay_ms == null ? ` · ${row.delay_s}s delay` : ""}
                </div>
              </div>
            ))
        )}
      </div>
    </div>
  );
}

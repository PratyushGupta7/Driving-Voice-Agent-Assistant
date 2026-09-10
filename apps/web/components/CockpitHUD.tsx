import type { CockpitStats, MissionSnapshot, ToolRow } from "@/lib/types";

function tone(kind: "ok" | "warn" | "live" | "mute"): string {
  if (kind === "ok") return "text-[#7ddec5]";
  if (kind === "warn") return "text-[#f07167]";
  if (kind === "live") return "text-[#e8a14a]";
  return "text-[#cfc6b8]";
}

function runtimeLabel(userState: string, agentState: string, gate: string, tools: ToolRow[]): string {
  if (userState === "BARRIER_CLOSED" || gate === "closed_for_input") return "BARRIER_CLOSED";
  if (tools.some((row) => row.decision === "running" || row.phase === "started")) return "SEARCHING";
  if (agentState === "speaking") return "SPEAKING";
  if (gate === "closed_for_end") return "CANCELLED";
  if (gate === "open") return "ACTIVE";
  return "LISTENING";
}

export function CockpitHUD({
  snapshot,
  cockpit,
  userState,
  agentState,
  tools,
}: {
  snapshot: MissionSnapshot | null;
  cockpit: CockpitStats | null;
  userState: string;
  agentState: string;
  tools: ToolRow[];
}) {
  const stats = cockpit ?? snapshot?.cockpit ?? null;
  const gate = snapshot?.output_gate ?? "closed_for_input";
  const label = runtimeLabel(userState, agentState, gate, tools);
  const stale = stats?.stale_rejects ?? tools.filter((row) => row.decision === "stale_rejected").length;
  const accepted = stats?.accepted_results ?? tools.filter((row) => row.decision === "accepted").length;
  const barrier = label === "BARRIER_CLOSED";
  const staleHot = stale > 0;
  const delayed = tools.some(
    (row) => (row.decision === "running" || row.phase === "started") && (row.delay_s ?? 0) >= 2,
  );
  const searching = Boolean(stats?.searching) || delayed;

  return (
    <section className={`panel rounded-3xl px-5 py-4 ${barrier ? "barrier-flash" : ""} ${staleHot ? "stale-hot" : ""}`}>
      {searching ? (
        <div className="mb-3 rounded-2xl border border-[#e8a14a]/40 bg-[#e8a14a]/10 px-3 py-2 text-sm text-[#f4efe6]">
          Stress case is live. A delayed search is running. Speak a new constraint — the old result
          must show <span className="font-mono text-[#f07167]">OBSOLETE</span> and Rime must not name it.
        </div>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-[11px] uppercase tracking-[0.18em] text-[#9a9388]">Fence cockpit</div>
        <div className={`font-mono text-sm font-semibold ${barrier ? tone("warn") : tone("live")}`}>{label}</div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-6">
        <Metric label="version" value={`v${snapshot?.mission_version ?? 0}`} />
        <Metric label="epoch" value={`e${snapshot?.output_epoch ?? 0}`} />
        <Metric
          label="stale"
          value={String(stale)}
          hint={staleHot ? "OBSOLETE" : "0 after barrier"}
          warn={staleHot}
        />
        <Metric label="accepted" value={String(accepted)} />
        <Metric
          label="ack"
          value={stats?.last_ack_ms != null ? `${stats.last_ack_ms}ms` : "—"}
        />
        <Metric
          label="barrier"
          value={snapshot?.last_barrier_ms != null ? `${snapshot.last_barrier_ms}ms` : "—"}
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-[#9a9388]">
        <span>
          nlu · {stats?.last_nlu_source ?? "rules"}
          {stats?.last_operation ? ` · ${stats.last_operation}` : ""}
          {stats?.last_nlu_ms != null ? ` · ${stats.last_nlu_ms}ms` : ""}
        </span>
        {stats?.last_stale_kind ? (
          <span className="text-[#f07167]">
            last obsolete · {stats.last_stale_kind} v{stats.last_stale_version} · e{stats.last_stale_epoch}
          </span>
        ) : (
          <span>last obsolete · none yet</span>
        )}
        <span>gate · {gate === "closed_for_input" ? "BARRIER_CLOSED" : gate.replaceAll("_", " ")}</span>
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
  hint,
  warn,
}: {
  label: string;
  value: string;
  hint?: string;
  warn?: boolean;
}) {
  return (
    <div className={`rounded-2xl border px-3 py-2 ${warn ? "border-[#f07167]/40 bg-[#f07167]/8" : "border-white/8"}`}>
      <div className="text-[10px] uppercase tracking-[0.14em] text-[#9a9388]">{label}</div>
      <div className={`mt-1 font-mono text-lg ${warn ? "text-[#f07167]" : "text-[#f4efe6]"}`}>{value}</div>
      {hint ? <div className={`text-[10px] ${warn ? "text-[#f07167]" : "text-[#9a9388]"}`}>{hint}</div> : null}
    </div>
  );
}

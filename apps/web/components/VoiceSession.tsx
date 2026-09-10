"use client";

import {
  BarVisualizer,
  LiveKitRoom,
  RoomAudioRenderer,
  StartAudio,
  useRoomContext,
  useVoiceAssistant,
} from "@livekit/components-react";
import { ConnectionState, RoomEvent } from "livekit-client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CockpitHUD } from "@/components/CockpitHUD";
import { MissionPanel } from "@/components/MissionPanel";
import { TalkControl } from "@/components/TalkControl";
import { ProviderBadges } from "@/components/ProviderBadges";
import { ToolTimeline } from "@/components/ToolTimeline";
import type {
  AgentEvent,
  CockpitStats,
  MissionSnapshot,
  PlaceCandidate,
  ProviderMap,
  RouteSnapshot,
  TokenResponse,
  ToolRow,
  TranscriptLine,
} from "@/lib/types";

const RouteMap = dynamic(() => import("@/components/RouteMap").then((mod) => mod.RouteMap), {
  ssr: false,
});

const AGENT_JOIN_TIMEOUT_MS = 20_000;

function statusTone(value: string): string {
  if (value === "BARRIER_CLOSED" || value === "OBSOLETE") return "text-[#f07167]";
  if (value === "speaking" || value === "LIVE" || value === "ACTIVE") return "text-[#7ddec5]";
  if (value === "thinking" || value === "connecting" || value === "SEARCHING") return "text-[#e8a14a]";
  if (value.includes("error") || value === "failed") return "text-[#f07167]";
  return "text-[#cfc6b8]";
}

function asSnapshot(payload: Record<string, unknown>): MissionSnapshot | null {
  if (!payload.session_id) return null;
  return {
    session_id: String(payload.session_id),
    mission_id: payload.mission_id ? String(payload.mission_id) : null,
    mission_version: Number(payload.mission_version ?? 0),
    output_epoch: Number(payload.output_epoch ?? 0),
    output_gate: String(payload.output_gate ?? "closed_for_input"),
    status: String(payload.status ?? "idle"),
    constraints: (payload.constraints as MissionSnapshot["constraints"]) ?? null,
    selected: (payload.selected as MissionSnapshot["selected"]) ?? null,
    alternatives: Array.isArray(payload.alternatives)
      ? (payload.alternatives as MissionSnapshot["alternatives"])
      : [],
    geo_mode: payload.geo_mode ? String(payload.geo_mode) : undefined,
    version_log: Array.isArray(payload.version_log)
      ? (payload.version_log as MissionSnapshot["version_log"])
      : [],
    last_revision: payload.last_revision ? String(payload.last_revision) : null,
    last_barrier_ms: payload.last_barrier_ms != null ? Number(payload.last_barrier_ms) : null,
    route: (payload.route as MissionSnapshot["route"]) ?? null,
    cockpit: (payload.cockpit as MissionSnapshot["cockpit"]) ?? null,
  };
}

function SessionInterior({
  onProviders,
  onAgentPresent,
}: {
  onProviders: (providers: ProviderMap) => void;
  onAgentPresent: (present: boolean) => void;
}) {
  const room = useRoomContext();
  const { state, audioTrack, agent, agentAttributes, agentTranscriptions } = useVoiceAssistant();
  const [userState, setUserState] = useState("listening");
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [snapshot, setSnapshot] = useState<MissionSnapshot | null>(null);
  const [corridor, setCorridor] = useState<RouteSnapshot | null>(null);
  const [tools, setTools] = useState<ToolRow[]>([]);
  const [alternatives, setAlternatives] = useState<PlaceCandidate[]>([]);
  const [agentPresent, setAgentPresent] = useState(false);
  const [releaseTick, setReleaseTick] = useState(0);
  const [cockpit, setCockpit] = useState<CockpitStats | null>(null);
  const seen = useRef(new Set<string>());

  useEffect(() => {
    const fromAttrs: ProviderMap = {};
    if (agentAttributes) {
      if (agentAttributes["stt.provider"]) fromAttrs.stt = agentAttributes["stt.provider"];
      if (agentAttributes["stt.model"]) fromAttrs.stt_model = agentAttributes["stt.model"];
      if (agentAttributes["tts.provider"]) fromAttrs.tts = agentAttributes["tts.provider"];
      if (agentAttributes["tts.model"]) fromAttrs.tts_model = agentAttributes["tts.model"];
      if (agentAttributes["tts.speaker"]) fromAttrs.tts_speaker = agentAttributes["tts.speaker"];
      if (agentAttributes["llm.provider"]) fromAttrs.llm = agentAttributes["llm.provider"];
      if (agentAttributes["llm.model"]) fromAttrs.llm_model = agentAttributes["llm.model"];
      if (agentAttributes["nlu.mode"]) fromAttrs.nlu = agentAttributes["nlu.mode"];
      if (agentAttributes["geo.mode"]) fromAttrs.geo = agentAttributes["geo.mode"];
    }
    if (Object.keys(fromAttrs).length) onProviders(fromAttrs);
  }, [agentAttributes, onProviders]);

  useEffect(() => {
    const present = Boolean(agent);
    setAgentPresent(present);
    onAgentPresent(present);
  }, [agent, onAgentPresent]);

  useEffect(() => {
    const onData = (
      payload: Uint8Array,
      _participant?: unknown,
      _kind?: unknown,
      topic?: string,
    ) => {
      if (topic && topic !== "mid-drive") return;
      try {
        const event = JSON.parse(new TextDecoder().decode(payload)) as AgentEvent;
        setEvents((current) => [...current.slice(-80), event]);
        if (event.type === "user_state") {
          setUserState(event.payload.barrier ? "BARRIER_CLOSED" : String(event.payload.new ?? "listening"));
        }
        if (event.type === "cockpit") {
          setCockpit(event.payload as CockpitStats);
        }
        if (event.type === "session_started") {
          const providers = event.payload.providers as ProviderMap | undefined;
          if (providers) onProviders(providers);
        }
        if (event.type === "mission_snapshot") {
          const next = asSnapshot(event.payload);
          if (next) {
            setSnapshot(next);
            if (next.cockpit) setCockpit(next.cockpit);
            if (next.alternatives?.length) setAlternatives(next.alternatives);
            else if (!next.selected) setAlternatives([]);
            if (next.route?.geometry?.length) setCorridor(next.route);
          }
        }
        if (event.type === "map_corridor") {
          setCorridor(event.payload as unknown as RouteSnapshot);
        }
        if (event.type === "map_update" && event.payload.decision === "accepted") {
          const route = event.payload.route as RouteSnapshot | undefined;
          if (route?.geometry) setCorridor(route);
          const alts = Array.isArray(event.payload.alternatives)
            ? (event.payload.alternatives as PlaceCandidate[])
            : [];
          setAlternatives(alts);
        }
        if (event.type === "tool_update") {
          const requestId = String(event.payload.request_id ?? event.seq);
          setTools((current) => {
            const row: ToolRow = {
              id: requestId,
              phase: String(event.payload.phase ?? ""),
              kind: String(event.payload.kind ?? "place_search"),
              decision: String(event.payload.decision ?? event.payload.phase ?? "running"),
              mission_version: Number(event.payload.mission_version ?? 0),
              output_epoch: Number(event.payload.output_epoch ?? 0),
              delay_ms: event.payload.delay_ms != null ? Number(event.payload.delay_ms) : undefined,
              delay_s: event.payload.delay_s != null ? Number(event.payload.delay_s) : undefined,
              name: event.payload.name != null ? String(event.payload.name) : null,
              area: event.payload.area != null ? String(event.payload.area) : null,
              error: event.payload.error != null ? String(event.payload.error) : undefined,
              provider: event.payload.provider != null ? String(event.payload.provider) : undefined,
              label: event.payload.label != null ? String(event.payload.label) : undefined,
            };
            const without = current.filter((item) => item.id !== requestId);
            return [...without, row].slice(-20);
          });
        }
        if (event.type === "turn_committed") {
          setReleaseTick((tick) => tick + 1);
        }
        if (event.type === "agent_utterance") {
          const text = String(event.payload.text ?? "").trim();
          if (text) {
            setLines((current) => [
              ...current.slice(-39),
              { id: `utterance-${event.seq}`, role: "agent", text, partial: false },
            ]);
          }
          if (event.payload.ack_ms != null) {
            setCockpit((current) => ({ ...(current ?? {}), last_ack_ms: Number(event.payload.ack_ms) }));
          }
        }
        if (event.type === "transcript_partial" || event.type === "transcript_final") {
          const text = String(event.payload.text ?? "");
          if (!text) return;
          setLines((current) => {
            const next = current.filter((line) => !(line.role === "driver" && line.partial));
            if (
              event.type === "transcript_final" &&
              next.some((line) => line.role === "driver" && !line.partial && line.text === text)
            ) {
              return next;
            }
            next.push({
              id: `${event.type}-${event.seq}`,
              role: "driver",
              text,
              partial: event.type === "transcript_partial",
            });
            return next.slice(-40);
          });
        }
      } catch {
        /* ignore malformed packets */
      }
    };

    room.on(RoomEvent.DataReceived, onData);
    return () => {
      room.off(RoomEvent.DataReceived, onData);
    };
  }, [onProviders, room]);

  useEffect(() => {
    for (const segment of agentTranscriptions) {
      if (!segment.text || seen.current.has(segment.id)) continue;
      if (!segment.final) continue;
      seen.current.add(segment.id);
      setLines((current) => {
        if (current.some((line) => line.role === "agent" && line.text === segment.text)) {
          return current;
        }
        return [...current.slice(-39), { id: segment.id, role: "agent", text: segment.text, partial: false }];
      });
    }
  }, [agentTranscriptions]);

  const latestPartial = agentTranscriptions.find((segment) => !segment.final)?.text;
  const lastAgent = [...lines].reverse().find((line) => line.role === "agent")?.text;
  const showPartial =
    Boolean(latestPartial) && !(lastAgent && latestPartial && lastAgent.startsWith(latestPartial.trim()));

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <CockpitHUD
        snapshot={snapshot}
        cockpit={cockpit}
        userState={userState}
        agentState={state}
        tools={tools}
      />
    <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1.1fr)_minmax(280px,0.9fr)]">
      <div className="flex min-h-0 flex-col gap-4">
        <RouteMap
          corridor={corridor}
          selected={snapshot?.selected ?? null}
          alternatives={snapshot?.selected ? alternatives : []}
        />
      <section className={`panel flex flex-col rounded-3xl p-5 ${userState === "BARRIER_CLOSED" || userState === "speaking" ? "barrier-flash" : ""}`}>
        <div className="mb-6 flex items-center justify-between text-[11px] uppercase tracking-[0.18em] text-[#9a9388]">
          <span>Voice path</span>
          <span className={statusTone(state)}>{state}</span>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-6">
          <div className="relative flex h-40 w-40 items-center justify-center">
            <div
              className={`absolute inset-0 rounded-full border ${
                state === "speaking" ? "border-[#e8a14a] shadow-[0_0_40px_rgba(232,161,74,0.25)]" : "border-white/10"
              }`}
            />
            <div className="text-center">
              <div className="font-mono text-xs text-[#e8a14a]">RIME</div>
              <div className="mt-1 text-sm text-[#cfc6b8]">{agentPresent ? "on air" : "joining…"}</div>
            </div>
          </div>
          <div className="w-full px-2">
            <BarVisualizer state={state} barCount={22} trackRef={audioTrack} options={{ minHeight: 8 }} />
          </div>
          <TalkControl releaseTick={releaseTick} />
          <div className="grid w-full grid-cols-2 gap-2 text-xs">
            <div className="rounded-2xl border border-white/8 bg-black/20 px-3 py-3">
              <div className="text-[10px] uppercase tracking-[0.16em] text-[#9a9388]">Driver VAD</div>
              <div className={`mt-1 font-medium ${statusTone(userState)}`}>{userState}</div>
            </div>
            <div className="rounded-2xl border border-white/8 bg-black/20 px-3 py-3">
              <div className="text-[10px] uppercase tracking-[0.16em] text-[#9a9388]">Agent</div>
              <div className={`mt-1 font-medium ${statusTone(state)}`}>{state}</div>
            </div>
          </div>
        </div>
      </section>
      </div>

      <section className="panel flex min-h-0 flex-col rounded-3xl p-5">
        <div className="mb-4 text-[11px] uppercase tracking-[0.18em] text-[#9a9388]">Conversation</div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {lines.length === 0 && (
            <p className="text-sm leading-6 text-[#9a9388]">
              Waiting for the first turn. Speak naturally — Mid-Drive listens while Rime is talking.
            </p>
          )}
          {lines.map((line) => (
            <div key={line.id} className={line.role === "driver" ? "text-left" : "text-right"}>
              <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.14em] text-[#9a9388]">
                {line.role}
                {line.partial ? " · partial" : ""}
              </div>
              <div
                className={`inline-block max-w-[92%] rounded-2xl px-3 py-2 text-sm leading-6 ${
                  line.role === "driver"
                    ? "bg-white/6 text-[#f4efe6]"
                    : "bg-[#e8a14a]/12 text-[#f4efe6]"
                } ${line.partial ? "italic opacity-80" : ""}`}
              >
                {line.text}
              </div>
            </div>
          ))}
          {showPartial && latestPartial ? (
            <div className="text-right text-sm italic text-[#cfc6b8]">{latestPartial}</div>
          ) : null}
        </div>
      </section>

      <aside className="flex min-h-0 flex-col gap-4">
        <MissionPanel snapshot={snapshot} alternatives={snapshot?.selected ? alternatives : []} />
        <ToolTimeline rows={tools} />
        <section className="panel min-h-0 overflow-hidden rounded-3xl p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[#9a9388]">Event stream</div>
          <div className="mt-3 max-h-[220px] space-y-2 overflow-y-auto font-mono text-[11px] text-[#cfc6b8]">
            {events.length === 0 ? (
              <p>No agent events yet.</p>
            ) : (
              events
                .slice()
                .reverse()
                .map((event) => (
                  <div key={`${event.session_id}-${event.seq}`} className="border-b border-white/6 pb-2">
                    <span className="text-[#e8a14a]">{event.type}</span>
                    {event.payload.barrier ? <span className="ml-2 text-[#f07167]">BARRIER_CLOSED</span> : null}
                    {event.payload.label && !event.payload.barrier ? (
                      <span className="ml-2 text-[#cfc6b8]">{String(event.payload.label)}</span>
                    ) : null}
                    {event.payload.decision ? (
                      <span className="ml-2 text-[#cfc6b8]">{String(event.payload.decision)}</span>
                    ) : null}
                  </div>
                ))
            )}
          </div>
        </section>
      </aside>
    </div>
    </div>
  );
}

export function VoiceSession() {
  const [token, setToken] = useState<TokenResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [micDenied, setMicDenied] = useState(false);
  const [providers, setProviders] = useState<ProviderMap>({});
  const [connection, setConnection] = useState<ConnectionState>(ConnectionState.Disconnected);
  const [agentPresent, setAgentPresent] = useState(false);
  const userEnded = useRef(false);

  const start = useCallback(async () => {
    setBusy(true);
    setError(null);
    userEnded.current = false;
    setAgentPresent(false);
    try {
      const permission = await navigator.mediaDevices.getUserMedia({ audio: true });
      permission.getTracks().forEach((track) => track.stop());
      const response = await fetch("/api/livekit-token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = (await response.json()) as TokenResponse & { error?: string };
      if (!response.ok) {
        throw new Error(data.error || "Could not mint a LiveKit token");
      }
      setToken(data);
    } catch (err) {
      if (err instanceof DOMException && err.name === "NotAllowedError") {
        setMicDenied(true);
        setError("Microphone permission was denied. Mid-Drive cannot run without it.");
      } else {
        setError(err instanceof Error ? err.message : "Failed to start session");
      }
    } finally {
      setBusy(false);
    }
  }, []);

  const end = useCallback(() => {
    userEnded.current = true;
    setToken(null);
    setConnection(ConnectionState.Disconnected);
    setAgentPresent(false);
  }, []);

  const onProviders = useCallback((next: ProviderMap) => {
    setProviders((current) => ({ ...current, ...next }));
  }, []);

  const onAgentPresent = useCallback((present: boolean) => {
    setAgentPresent(present);
  }, []);

  useEffect(() => {
    if (!token || agentPresent) return;
    const timer = window.setTimeout(() => {
      setError("The Mid-Drive worker did not join within 20 seconds. Is `python -m mid_drive.main start` running?");
    }, AGENT_JOIN_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [agentPresent, token]);

  const connected = useMemo(() => Boolean(token), [token]);

  return (
    <div className="flex min-h-screen flex-col px-5 py-6 md:px-8">
      <header className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="font-mono text-[11px] uppercase tracking-[0.28em] text-[#e8a14a]">
            DataForge · Rime
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">Mid-Drive</h1>
          <p className="mt-2 max-w-xl text-sm leading-6 text-[#9a9388]">
            Hands-busy driver. Interrupt mid-sentence. Stale tools cannot speak or move the map.
            Rime is the only voice.
          </p>
        </div>
        <ProviderBadges providers={providers} />
      </header>

      {!connected ? (
        <main className="panel mx-auto mt-10 w-full max-w-2xl rounded-[28px] p-8 text-left">
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#e8a14a]">
            Official Rime stress case
          </p>
          <h2 className="mt-2 text-xl font-semibold text-[#f4efe6]">
            Change the request while Rime is still talking or searching.
          </h2>
          <ul className="mt-4 space-y-2 text-sm leading-6 text-[#cfc6b8]">
            <li>User: a driver on Cyber Hub → Connaught Place. Hands stay on the wheel.</li>
            <li>Hard problem: interrupt, then fence the delayed old search so it cannot speak.</li>
            <li>Rime Coda / astra is the only spoken output. Removing speech removes the product.</li>
          </ul>
          <p className="mt-4 text-sm leading-6 text-[#9a9388]">
            Allow the microphone. The worker must already be running so Rime can greet you. Use
            open mic for the interrupt. After “Another one,” say tolls before the eight-second
            search finishes.
          </p>
          {micDenied ? (
            <p className="mt-4 text-sm text-[#f07167]">
              Enable microphone access in the browser and try again.
            </p>
          ) : null}
          {error ? <p className="mt-4 text-sm text-[#f07167]">{error}</p> : null}
          <button
            type="button"
            onClick={start}
            disabled={busy}
            className="mt-6 rounded-full bg-[#e8a14a] px-6 py-3 text-sm font-semibold text-[#1a1308] disabled:opacity-60"
          >
            {busy ? "Starting…" : "Start drive"}
          </button>
        </main>
      ) : token ? (
        <LiveKitRoom
          token={token.participant_token}
          serverUrl={token.server_url}
          connect
          audio
          video={false}
          onMediaDeviceFailure={() => {
            setMicDenied(true);
            setError("The browser could not open the microphone.");
          }}
          onError={(err) => setError(err.message)}
          onConnected={() => setConnection(ConnectionState.Connected)}
          onDisconnected={() => {
            if (userEnded.current) {
              end();
              return;
            }
            setError("The voice session dropped unexpectedly. Start a new drive.");
            setToken(null);
            setConnection(ConnectionState.Disconnected);
            setAgentPresent(false);
          }}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="mb-4 flex items-center justify-between text-xs text-[#9a9388]">
            <span>
              Room <span className="font-mono text-[#cfc6b8]">{token.room_name}</span>
            </span>
            <span className={statusTone(connection)}>{connection}</span>
            <button type="button" onClick={end} className="rounded-full border border-white/15 px-3 py-1">
              End
            </button>
          </div>
          {error ? <p className="mb-3 text-sm text-[#f07167]">{error}</p> : null}
          <SessionInterior onProviders={onProviders} onAgentPresent={onAgentPresent} />
          <RoomAudioRenderer />
          <StartAudio label="Enable audio playback" />
        </LiveKitRoom>
      ) : null}
    </div>
  );
}

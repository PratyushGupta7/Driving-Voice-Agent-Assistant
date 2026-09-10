import type { ProviderMap } from "@/lib/types";

const DEFAULTS: ProviderMap = {
  stt: "ElevenLabs",
  stt_model: "scribe_v2_realtime",
  tts: "Rime",
  tts_model: "coda",
  tts_speaker: "astra",
  tts_transport: "http-pcm",
  llm: "Azure OpenAI",
  llm_model: "gpt-4.1-mini",
  nlu: "rules",
  geo: "fixture",
};

export function ProviderBadges({ providers }: { providers: ProviderMap }) {
  const p = { ...DEFAULTS, ...providers };
  const items = [
    { k: "STT", v: `${p.stt} · ${p.stt_model}` },
    { k: "TTS", v: `${p.tts} ${p.tts_model} · ${p.tts_speaker}` },
    { k: "LLM", v: `${p.llm} · ${p.llm_model}` },
    { k: "NLU", v: p.nlu || "rules" },
    { k: "GEO", v: p.geo === "live" ? "OSM · OSRM · Overpass" : "fixture corridor" },
  ];

  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <span
          key={item.k}
          className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] tracking-wide text-[#f4efe6]"
        >
          <span className="font-mono text-[10px] text-[#e8a14a]">{item.k}</span>
          <span className="text-[#cfc6b8]">{item.v}</span>
        </span>
      ))}
    </div>
  );
}

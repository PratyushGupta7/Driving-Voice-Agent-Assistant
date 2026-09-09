"use client";

import { useLocalParticipant } from "@livekit/components-react";
import { useEffect, useState } from "react";

function publish(localParticipant: { publishData: (data: Uint8Array, opts: object) => Promise<void> }, payload: object) {
  const body = new TextEncoder().encode(JSON.stringify(payload));
  void localParticipant.publishData(body, { reliable: true, topic: "mid-drive-ptt" }).catch(() => undefined);
}

export function TalkControl({ releaseTick = 0 }: { releaseTick?: number }) {
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  const [mode, setMode] = useState<"ptt" | "open">("ptt");
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    const want = mode === "open" || armed;
    void localParticipant.setMicrophoneEnabled(want).catch(() => undefined);
  }, [armed, localParticipant, mode]);

  useEffect(() => {
    publish(localParticipant, { type: "talk_mode", mode });
  }, [localParticipant, mode]);

  useEffect(() => {
    if (!releaseTick || mode !== "ptt") return;
    setArmed(false);
  }, [mode, releaseTick]);

  const live = mode === "open" || (armed && isMicrophoneEnabled);

  return (
    <div className="flex w-full flex-col items-center gap-3">
      <button
        type="button"
        onClick={() => {
          if (mode === "open") return;
          setArmed((current) => {
            if (current) publish(localParticipant, { type: "ptt_commit" });
            return !current;
          });
        }}
        className={`w-full rounded-full px-5 py-3.5 text-sm font-semibold transition ${
          live
            ? "bg-[#f07167] text-[#1a1308] shadow-[0_0_28px_rgba(240,113,103,0.35)]"
            : "bg-[#e8a14a] text-[#1a1308]"
        } ${mode === "open" ? "cursor-default opacity-90" : ""}`}
      >
        {mode === "open" ? "Open mic · speaking is live" : live ? "Listening… tap to send" : "Tap to talk"}
      </button>
      <div className="flex items-center gap-2 text-[11px] text-[#9a9388]">
        <button
          type="button"
          onClick={() => {
            setMode("ptt");
            setArmed(false);
          }}
          className={`rounded-full px-3 py-1 ${
            mode === "ptt" ? "bg-white/10 text-[#f4efe6]" : "border border-white/10"
          }`}
        >
          Tap to talk
        </button>
        <button
          type="button"
          onClick={() => {
            setMode("open");
            setArmed(false);
          }}
          className={`rounded-full px-3 py-1 ${
            mode === "open" ? "bg-white/10 text-[#f4efe6]" : "border border-white/10"
          }`}
        >
          Open mic
        </button>
      </div>
      <p className="max-w-[16rem] text-center text-[11px] leading-4 text-[#9a9388]">
        {mode === "ptt"
          ? "Tap, finish the whole sentence, then tap Send. I will not answer mid-sentence."
          : "Always listening. Pause after the full sentence, then I answer."}
      </p>
    </div>
  );
}

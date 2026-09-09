"use client";

import { useMediaDeviceSelect, useRoomContext } from "@livekit/components-react";
import { useEffect, useMemo, useRef } from "react";

function isMacSpeaker(label: string): boolean {
  const name = label.toLowerCase();
  if (!name) return false;
  if (name.includes("headphone") || name.includes("airpod") || name.includes("headset") || name.includes("earbud")) {
    return false;
  }
  return (
    name.includes("macbook") ||
    name.includes("built-in") ||
    name.includes("internal speaker") ||
    name.includes("mac speaker") ||
    name.includes("speaker")
  );
}

export function SpeakerOutput() {
  const room = useRoomContext();
  const preferred = useRef(false);
  const { devices, activeDeviceId, setActiveMediaDevice } = useMediaDeviceSelect({
    kind: "audiooutput",
    requestPermissions: false,
  });

  const speaker = useMemo(() => devices.find((device) => isMacSpeaker(device.label)), [devices]);
  const usingSpeakers = Boolean(speaker && activeDeviceId === speaker.deviceId);

  useEffect(() => {
    void room.startAudio().catch(() => undefined);
  }, [room]);

  useEffect(() => {
    if (preferred.current || !speaker) return;
    preferred.current = true;
    void room.startAudio().catch(() => undefined);
    void setActiveMediaDevice(speaker.deviceId).catch(() => undefined);
  }, [room, setActiveMediaDevice, speaker]);

  const playOnSpeakers = () => {
    void room.startAudio().catch(() => undefined);
    if (speaker) {
      void setActiveMediaDevice(speaker.deviceId).catch(() => undefined);
    }
  };

  return (
    <div className="flex w-full flex-col items-center gap-2">
      <button
        type="button"
        onClick={playOnSpeakers}
        className={`w-full rounded-full px-4 py-2 text-xs font-semibold transition ${
          usingSpeakers || !speaker
            ? "bg-[#7ddec5]/16 text-[#7ddec5]"
            : "border border-white/12 text-[#f4efe6]"
        }`}
      >
        {usingSpeakers || !speaker ? "Playing on Mac speakers" : "Play on Mac speakers"}
      </button>
      <p className="max-w-[16rem] text-center text-[11px] leading-4 text-[#9a9388]">
        {speaker
          ? speaker.label
          : "Uses the Mac’s current output. Click once if the greeting is silent."}
      </p>
    </div>
  );
}

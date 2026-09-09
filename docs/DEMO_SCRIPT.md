# Demo script (≤ 5 minutes)

## 0:00 Problem

Drivers change requirements while an assistant is already speaking or searching. Delayed old work must not re-enter the conversation.

Show provider badges: ElevenLabs STT, Rime Coda / astra, Azure OpenAI, fixture corridor. The map should already show Cyber Hub → Connaught Place.

## 0:30 Create

Start drive. Rime greets. Driver: “Find a coffee shop near my route.”
Mission version 1. Short ack. Fixture search is immediate on v1. Rime names the lowest-detour match (Chai Point on the judged fixture) only after accept. It does not claim a parking lot.

## 1:15 Parking interrupt

While Rime is speaking or the next search is running: “Wait, it needs parking.”
Show VAD speaking, epoch increment, speech stop, version 2, parking chip.

## 1:45 Tolls + stale reject

“Avoid toll roads too.” Version 3 starts immediately. The delayed version 2 result (~8s) appears as `stale_rejected` on both the route and place tokens. Rime speaks only the v3 candidate: parking lot reported, toll-avoiding route requested. Ranked fixture result is Starbucks. The amber pin moves only on accept.

Optional: “Keep this one.” Then “the second one” or “why this one” / “how much extra time”. “Not that, another one” searches again. Optional: “near Cyber Hub”, “change destination to India Gate”, “nearer the start”.

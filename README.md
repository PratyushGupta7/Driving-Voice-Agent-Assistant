<p align="center">
  <strong>Mid-Drive</strong><br/>
  <em>Interruptible voice mission runtime — Cyber Hub → Connaught Place</em><br/>
  DataForge 2026 · Rime challenge
</p>

<p align="center">
  ElevenLabs STT · LiveKit full duplex · <strong>Rime Coda / astra</strong> · epoch-safe output fencing
</p>

---

## What this is

A **hands-busy driving copilot** for a fixed Gurgaon → Delhi corridor. You speak; **Rime** speaks back. The map and **fence cockpit** show mission version, output epoch, stale rejects, and barrier state — so judges can *see* interruption and obsolete async work getting dropped.

This is **not** a maps app with a play button. Remove speech and the product vanishes.

**Hard voice problems solved:**

- **Interruption and recovery** — VAD closes the output barrier at speech onset; queued Rime playout is interrupted; stale tool results cannot re-enter TTS or mission state.
- **Conversation continuity during tool work** — the driver can add constraints, ask status, or interrupt while an 8-second fixture search runs; delayed results are fenced, not applied to the wrong mission version.

Evidence pack: [`RIME_EVIDENCE.md`](RIME_EVIDENCE.md)

---

## Quick start

```bash
git clone https://github.com/PratyushGupta7/Driving-Voice-Agent-Assistant.git
cd "Driving-Voice-Agent-Assistant"

cp .env.example .env
# Fill: ELEVEN_API_KEY, RIME_API_KEY, AZURE_OPENAI_* (see Configuration hygiene)

cp apps/web/.env.local.example apps/web/.env.local

cd apps/agent && uv sync
cd ../web && npm install
```

**Three terminals:**

| # | Command |
|---|---------|
| 1 | `./scripts/dev-livekit.sh` |
| 2 | `cd apps/agent && uv run python -m mid_drive.main start` |
| 3 | `cd apps/web && npm run dev` |

Open **http://localhost:3000** → allow mic → **Start drive** → wait for Rime greeting → **Open mic** → say:

> “Find a coffee shop near my route.”

You should hear Rime ack, then **Chai Point**; cockpit shows mission `v1`, tokens `ACCEPTED`, pin on map.

**Preflight (before judging):**

```bash
cd apps/agent
uv run python -m mid_drive.preflight
uv run python -m mid_drive.evidence
```

---

## Architecture

```text
Browser (Next.js + MapLibre)
  │  WebRTC audio + data channel
  ▼
LiveKit Server (local)
  │  Silero VAD · ElevenLabs STT · SafeRimeTTS
  ▼
SessionActor (single-writer mission state)
  ├── output_epoch      ← bumps on VAD speech onset (safety fence)
  ├── mission_version   ← bumps on material constraint change (semantics)
  ├── ResultFence       ← rejects stale tool tokens
  └── MissionController ← rules-first NLU, template acks, orchestrator
        ▼
Fixture geo (default) or Nominatim + OSRM + Overpass (live)
```

```mermaid
sequenceDiagram
    participant Driver
    participant VAD
    participant Actor
    participant Tools
    participant Rime

    Driver->>Rime: Find coffee near my route
    Rime->>Tools: search (epoch 1)
    Tools-->>Rime: Chai Point accepted
    Rime->>Driver: Chai Point is on the way…

    Driver->>VAD: Wait, I need parking too
    VAD->>Actor: output_epoch++ · gate CLOSED
    Actor->>Rime: interrupt playout

    Driver->>Actor: Another one
    Tools->>Tools: v2 search (8s delay)

    Driver->>VAD: Avoid toll roads too
    VAD->>Actor: output_epoch++ · v3
    Tools-->>Actor: v3 Starbucks accepted
    Tools-->>Actor: v2 returns → STALE_REJECTED
    Rime->>Driver: Starbucks… parking lot… toll-avoiding route
```

**Two counters:**

| Counter | Increments when | Purpose |
|---|---|---|
| `output_epoch` | Silero VAD detects user speech | Invalidates in-flight TTS, tools, UI sinks **immediately** |
| `mission_version` | Completed turn with material constraint change | Tracks what the driver actually meant |

Cancellation is best-effort; **correctness is the fence**. Stale results remain auditable as `OBSOLETE` in the cockpit.

Key modules: `session_actor.py`, `result_fence.py`, `orchestrator.py`, `controller.py`, `evidence.py`.

---

## Third-party services

| Service | Role | Where configured |
|---|---|---|
| **Rime** | Primary TTS (all driver-facing speech) | `RIME_*` in `.env` |
| **ElevenLabs** | Realtime STT (`scribe_v2_realtime`) | `ELEVEN_API_KEY` |
| **Azure OpenAI** | LiveKit session LLM stub; preflight only on judged path | `AZURE_OPENAI_*` |
| **LiveKit** | WebRTC transport, VAD, turn handling | `LIVEKIT_*` (local server) |
| **OpenStreetMap stack** | Optional live geo (`GEO_MODE=live`) | Nominatim, OSRM, Overpass URLs |

Credentials stay **server-side** (agent worker + Next.js token route). The browser never receives Rime, ElevenLabs, or Azure keys.

**Active speech provider** is visible in the web UI provider badges and worker logs (`tts: Rime · coda · astra · http-pcm`).

---

## Exact Rime configuration (judged path)

| Setting | Value |
|---|---|
| Model ID | `coda` |
| Speaker | `astra` |
| Language | `eng` |
| Endpoint | `https://users.rime.ai/v1/rime-tts` |
| Catalog | `https://users.rime.ai/data/voices/all-v2.json` |
| Transport | **HTTP** (not WebSocket) |
| Audio format | `audio/pcm`, **24 kHz**, 20 ms aligned frames |
| Code path | `pipeline.build_tts()` → `SafeRimeTTS` |

Speaker is validated against the **live catalog** at preflight and worker prewarm. See [`RIME_EVIDENCE.md`](RIME_EVIDENCE.md) for the acceptance test and repeatable proof commands.

---

## Configuration hygiene

1. Copy [`.env.example`](.env.example) → `.env` at repo root. **Never commit `.env`.**
2. Secret fields use **empty placeholders** — fill locally only:
   - `ELEVEN_API_KEY`
   - `RIME_API_KEY`
   - `AZURE_OPENAI_API_KEY`
   - `AZURE_OPENAI_ENDPOINT` (template URL until you replace `YOUR_RESOURCE`)
3. `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` in `.env.example` match the **local** `livekit.yaml` dev server — not production secrets.
4. Judged demo defaults (already in `.env.example`):

   | Variable | Default | Why |
   |---|---|---|
   | `GEO_MODE` | `fixture` | Deterministic corridor + 8 s v2 delay |
   | `NLU_MODE` | `rules` | Phrase grammar; immediate acks |
   | `AZURE_SPEAK` | `false` | Rime-only spoken output on hot path |
   | `FIXTURE_V2_DELAY_S` | `8.0` | Stale-reject stress case |
   | `RIME_SPEAKER` | `astra` | Live-catalog validated |

5. Run organizer preflight before demo:

   ```bash
   cd apps/agent && uv run python -m mid_drive.preflight
   ```

Optional helper (local only): `python scripts/write_env.py` scaffolds `.env` from the example — it does not embed real keys.

---

## Demo video (≤ 5 min · scripted 3:30)

**Settings:** `GEO_MODE=fixture` · `NLU_MODE=rules` · `AZURE_SPEAK=false` · **Open mic** after greeting.

**Cue card:**

```text
 1. Find a coffee shop near my route.      → Chai Point (v1)
 2. Does it have parking?                  → inquire only, v1 unchanged
 3. [INTERRUPT] Wait, I need parking too.  → hold, pin stays on Chai Point
 4. Why this one?
 5. Another one.                           → 8 s v2 delay starts
 6. What's taking so long?
 7. Avoid toll roads too.                   → Starbucks v3 + OBSOLETE v2
 8. Compare them. · The second one.
 9. Actually, I need fuel. · Where is it?
10. Cockpit stale≥1 + uv run python -m mid_drive.evidence
```

**Fixture outcomes (deterministic):**

| Driver says | Rime names | Notes |
|---|---|---|
| Coffee, no parking | **Chai Point** | Alt: Third Wave |
| Coffee + parking (cold start) | **Blue Tokai** | |
| Coffee + parking + no tolls | **Starbucks** | After stress case |
| Fuel | **Indian Oil** | Category replace |
| Pharmacy | **Apollo Pharmacy** | |

**Parking hold:** after Chai Point, “I need parking too” reports no lot and **keeps the pin** until **Another one**.

**What to show judges:** normal E2E flow → deliberate stress (steps 5–7) → cockpit `BARRIER_CLOSED`, `OBSOLETE`, `stale ≥ 1` → evidence command output.

---

## Prove the claim

### Live UI (fence cockpit)

During the demo, expect:

- `BARRIER_CLOSED` on interrupt
- `stale ≥ 1` and `last obsolete v2` after toll beat
- `nlu · rules` on every turn
- Shop names on tool rows **only** when `ACCEPTED`

### Automated evidence

```bash
cd apps/agent
uv run python -m mid_drive.evidence
```

```json
{ "rounds": 3, "stale_admissions": 0, "stale_rejects": 3 }
```

Full write-up: [`RIME_EVIDENCE.md`](RIME_EVIDENCE.md)

### Tests

```bash
cd apps/agent
uv run pytest
```

131 tests — fence races, interrupt pitfalls, property harness, full demo path (`test_demo_video.py`).

---

## Known limitations

- Residual audio can remain in WebRTC/browser buffers after interrupt — not instantaneous silence
- HUD ack/barrier timings are **server-event** clocks, not measured acoustic p95
- Parking = OSM amenity **tag**, not live occupancy
- Toll avoidance = route **preference**, not a guarantee
- Phrase grammar covers the judged script; unsupported paraphrase may miss
- `GEO_MODE=live` depends on public OSM/OSRM rate limits and latency

---

## Failure behavior

| Failure | User-visible behavior | Recovery |
|---|---|---|
| Rime HTTP error / bad PCM | Utterance fails; logged; no silent provider swap | Retry once in `SafeRimeTTS`; check key + preflight |
| ElevenLabs STT down | No turn commits; partials may stall | Fix `ELEVEN_API_KEY`; check quota |
| Azure unreachable | Judged path unaffected (`NLU_MODE=rules`) | Optional services only |
| LiveKit worker missing | “Start drive” times out (~20 s) | Restart agent; free port **8081** |
| Stale tool returns | Fenced as `OBSOLETE`; never spoken as current | By design — see evidence CLI |
| Unsupported voice command | Template clarification prompt via Rime | Rephrase using cue-card patterns |
| `GEO_MODE=live` timeout | Spoken “still searching” / retry | Fall back to `fixture` for demo |

Never commit `.env`, key screenshots, or recordings containing secrets.

---

## Repository map

```text
apps/
  agent/     LiveKit worker — SessionActor, fence, NLU, Rime, orchestrator, evidence CLI
  web/       Next.js cockpit — map, CockpitHUD, provider badges, LiveKit token route
fixtures/
  gurgaon-delhi-v1.json   corridor + deterministic shops
scripts/
  dev-livekit.sh          local LiveKit server
  write_env.py            optional .env scaffolder (local)
RIME_EVIDENCE.md          hard claim, acceptance test, repeatable proof
.env.example              placeholders only — copy to .env
```

---

## Problem statement checklist

- [x] Voice-native product (speech is the interface)
- [x] Hard voice problem (interruption + continuity during tool work)
- [x] Rime as **primary** spoken output (not welcome-only)
- [x] Full duplex (interrupt while speaking and while tools run)
- [x] LiveKit Agents + browser WebRTC
- [x] README: setup, architecture, services, limitations, failure behavior, exact Rime config
- [x] `RIME_EVIDENCE.md` with repeatable command
- [x] Configuration hygiene (`.env.example`, preflight)
- [x] Active provider observable in UI
- [x] Secrets not in repo

---

<p align="center">
  <strong>Mid-Drive</strong> — driving makes the problem obvious.<br/>
  The output barrier, mission versioning, and stale-result fence are the engineering.
</p>

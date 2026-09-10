<p align="center">
  <strong>Mid-Drive</strong><br/>
  <em>I built a voice copilot that survives being interrupted — mid-sentence, mid-search, mid-drive.</em><br/>
  DataForge 2026 · Rime challenge · Cyber Hub → Connaught Place
</p>

<p align="center">
  <strong>131 tests</strong> · <strong>0 stale admissions</strong> · <strong>8 s stress delay</strong> · Rime Coda / astra · full duplex
</p>

---

## The moment that broke every demo I tried

I'm on the NH-48 corridor, one hand on the wheel, eyes on the road. I ask for coffee. The assistant starts talking. A second later I remember — *I need parking*. I cut it off.

Most voice agents do one of three things:

1. Keep playing the old answer in my ear.
2. Accept the new words but **apply the old search result** when it finally lands.
3. Cancel everything and make me start over.

That's not a driving copilot. That's a chatbot with a play button.

**Mid-Drive** is what I built instead: a hands-busy mission runtime where **Rime is the voice**, LiveKit carries full-duplex audio, and a fence I can actually *see* on screen stops dead work from hijacking live work.

Remove speech and the product disappears. That's intentional.

---

## What I'm claiming — and how I prove it

> Once my per-session actor linearizes the user-speech barrier, no artifact from an older output epoch can enter active mission state, new TTS input, or user-visible application output.

I'm solving two hard voice problems from the Rime brief:

| Problem | What I ship |
|---|---|
| **Interruption and recovery** | VAD closes the output barrier at speech onset; queued Rime playout stops; stale tool results can't re-enter TTS or mission state |
| **Conversation continuity during tool work** | I can add constraints, ask "what's taking so long?", or interrupt while an **8-second** fixture search runs — delayed results get fenced, not applied to the wrong version |

**The numbers behind the claim:**

| Stat | Value |
|---|---|
| Automated evidence rounds | **3** |
| Stale results admitted | **0** |
| Stale results rejected | **3** |
| Regression tests | **131** (`uv run pytest`) |
| Demo runtime | **3:30** (under the 5 min cap) |
| Fixture v2 search delay | **8.0 s** (`FIXTURE_V2_DELAY_S`) |
| Mission versions in stress demo | **v1 → v3** (coffee → parking → tolls) |

Repeatable proof: [`RIME_EVIDENCE.md`](RIME_EVIDENCE.md) · one command: `uv run python -m mid_drive.evidence`

---

## Run it in five minutes

I kept setup boring on purpose — three terminals, one corridor, deterministic fixture geo so judges get the same story every time.

```bash
git clone https://github.com/PratyushGupta7/Driving-Voice-Agent-Assistant.git
cd "Driving-Voice-Agent-Assistant"

cp .env.example .env
# I fill: ELEVEN_API_KEY, RIME_API_KEY, AZURE_OPENAI_*

cp apps/web/.env.local.example apps/web/.env.local

cd apps/agent && uv sync
cd ../web && npm install
```

| Terminal | What I run |
|---|---|
| 1 | `./scripts/dev-livekit.sh` |
| 2 | `cd apps/agent && uv run python -m mid_drive.main start` |
| 3 | `cd apps/web && npm run dev` |

Then I open **http://localhost:3000** → allow mic → **Start drive** → wait for Rime's greeting → flip **Open mic** → say:

> “Find a coffee shop near my route.”

If everything's wired: Rime acks immediately, names **Chai Point**, the map pin lands, and the cockpit shows mission **v1** with tokens marked **ACCEPTED**.

**Before I record or submit**, I always run:

```bash
cd apps/agent
uv run python -m mid_drive.preflight    # live Rime catalog + PCM sanity check
uv run python -m mid_drive.evidence     # fence proof → artifacts/evidence-fence.json
```

---

## How I designed it — two counters, one fence

Most agents track one "context." I split **safety** from **semantics** because drivers change their mind faster than tools finish.

```text
Browser (Next.js + MapLibre + fence cockpit)
  │  WebRTC audio + data channel
  ▼
LiveKit Server (local)
  │  Silero VAD · ElevenLabs STT · SafeRimeTTS
  ▼
SessionActor — single writer, no races
  ├── output_epoch      ← bumps the instant I start speaking (VAD onset)
  ├── mission_version   ← bumps when my constraint actually changes
  ├── ResultFence       ← rejects tokens from dead epochs
  └── MissionController ← rules-first NLU, template acks, orchestrator
        ▼
Fixture corridor (judged default) or live OSM stack
```

```mermaid
sequenceDiagram
    participant Me as Driver
    participant VAD
    participant Actor
    participant Tools
    participant Rime

    Me->>Rime: Find coffee near my route
    Rime->>Tools: search (epoch 1)
    Tools-->>Rime: Chai Point accepted
    Rime->>Me: Chai Point is on the way…

    Me->>VAD: Wait, I need parking too
    VAD->>Actor: output_epoch++ · BARRIER_CLOSED
    Actor->>Rime: interrupt playout

    Me->>Actor: Another one
    Note over Tools: v2 search — 8 s delay

    Me->>VAD: Avoid toll roads too
    VAD->>Actor: output_epoch++ · mission v3
    Tools-->>Actor: v3 Starbucks accepted
    Tools-->>Actor: v2 returns → STALE_REJECTED
    Rime->>Me: Starbucks… parking lot… toll-avoiding route
```

| Counter | When it moves | Why I need it |
|---|---|---|
| `output_epoch` | Silero VAD detects my speech | Kills in-flight TTS, tools, and UI sinks **immediately** — before transcription even finishes |
| `mission_version` | A completed turn changes a real constraint | Tracks what I *meant*, not just that I made a sound |

Cancellation is best-effort. **Correctness is the fence.** When v2 comes back late, the cockpit shows **OBSOLETE** — auditable, not silent.

Core code: `session_actor.py` · `result_fence.py` · `orchestrator.py` · `controller.py` · `evidence.py`

---

## My stack — and why each piece earns its place

| Layer | Choice | My reasoning |
|---|---|---|
| Transport | **LiveKit** (local server) | Full duplex in the browser; VAD-owned turns; interruption API I can actually hook |
| STT | **ElevenLabs Scribe v2 Realtime** | Partials for the UI; committed text drives NLU — I don't guess on half-heard words |
| TTS | **Rime Coda / astra** | Every driver-facing line on the judged path — acks, results, holds, status. Not just a welcome message |
| NLU | **Phrase grammar** (`NLU_MODE=rules`) | Immediate acks; no LLM roulette on the hot path |
| LLM | Azure gpt-4.1-mini | LiveKit session stub + preflight; **not** my spoken output path |
| Geo (judged) | `fixtures/gurgaon-delhi-v1.json` | Same shops, same delays, same OBSOLETE moment — every run |
| Geo (optional) | Nominatim + OSRM + Overpass | `GEO_MODE=live` when I want real Delhi/Gurgaon data |
| UI | Next.js + MapLibre + **CockpitHUD** | I built the HUD so judges don't have to trust my word — they watch the fence work |

### Third-party services

| Service | Role | Config |
|---|---|---|
| **Rime** | Primary spoken output | `RIME_*` |
| **ElevenLabs** | Realtime STT | `ELEVEN_API_KEY` |
| **Azure OpenAI** | Session stub / preflight | `AZURE_OPENAI_*` |
| **LiveKit** | WebRTC + VAD + turn handling | `LIVEKIT_*` |
| **OSM stack** | Optional live geo | `GEO_MODE=live` |

All API keys stay **server-side**. The browser gets a short-lived LiveKit JWT — never my Rime or ElevenLabs credentials.

The active speech provider is visible in the UI badges: **TTS · Rime · coda · astra · http-pcm**.

---

## Exact Rime config I ship (judged path)

I validate `astra` against the **live catalog** at preflight — not a stale speaker list baked into the app.

| Setting | Value |
|---|---|
| Model ID | `coda` |
| Speaker | `astra` |
| Language | `eng` |
| Endpoint | `https://users.rime.ai/v1/rime-tts` |
| Catalog | `https://users.rime.ai/data/voices/all-v2.json` |
| Transport | **HTTP** (`use_websocket=False`) |
| Audio format | `audio/pcm`, **24 kHz**, 20 ms aligned frames |
| Integration | `pipeline.build_tts()` → `SafeRimeTTS` |

`AZURE_SPEAK=false` on the judged path — Rime owns every spoken line. Full acceptance test and results: [`RIME_EVIDENCE.md`](RIME_EVIDENCE.md).

---

## Configuration hygiene

I treat secrets like fuel caps — necessary, never loose in the repo.

1. Copy [`.env.example`](.env.example) → `.env`. **I never commit `.env`.**
2. Empty placeholders for real keys: `ELEVEN_API_KEY`, `RIME_API_KEY`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`.
3. `LIVEKIT_*` in the example matches my **local** `livekit.yaml` dev server — not production.
4. Judged defaults (already set in `.env.example`):

   | Variable | Default | Why I keep it |
   |---|---|---|
   | `GEO_MODE` | `fixture` | Deterministic corridor + 8 s v2 delay |
   | `NLU_MODE` | `rules` | Grammar-first; fast acks |
   | `AZURE_SPEAK` | `false` | Rime-only on the hot path |
   | `FIXTURE_V2_DELAY_S` | `8.0` | The stress case that exposes stale rejects |
   | `RIME_SPEAKER` | `astra` | Live-catalog validated |

5. Preflight before demo: `cd apps/agent && uv run python -m mid_drive.preflight`

Optional: `python scripts/write_env.py` scaffolds `.env` locally — it never embeds real keys.

---

## My 3:30 demo — one drive, ten beats

**Settings I lock:** `GEO_MODE=fixture` · `NLU_MODE=rules` · `AZURE_SPEAK=false` · **Open mic** after greeting.

This is the story I tell on camera — normal flow first, then I deliberately break it:

```text
 1. Find a coffee shop near my route.      → Chai Point (v1)
 2. Does it have parking?                  → inquire only — v1 unchanged
 3. [INTERRUPT] Wait, I need parking too.  → hold; pin stays on Chai Point
 4. Why this one?
 5. Another one.                           → 8 s v2 delay starts
 6. What's taking so long?
 7. Avoid toll roads too.                   → Starbucks v3 · v2 goes OBSOLETE
 8. Compare them. · The second one.
 9. Actually, I need fuel. · Where is it?
10. Cockpit stale≥1 · run mid_drive.evidence on camera
```

**What judges should see on the HUD:**

- `BARRIER_CLOSED` the instant I interrupt (step 3)
- `OBSOLETE` on v2 when v3 wins (step 7)
- `stale ≥ 1` before I run evidence
- Shop names on tool rows **only** when `ACCEPTED`

**Deterministic fixture picks** (so I'm never improvising outcomes):

| I say | Rime names | Notes |
|---|---|---|
| Coffee, no parking | **Chai Point** | Alt: Third Wave |
| Coffee + parking (cold start) | **Blue Tokai** | |
| Coffee + parking + no tolls | **Starbucks** | After the stress case |
| Fuel | **Indian Oil** | Category replace |
| Pharmacy | **Apollo Pharmacy** | |

**Parking hold** (easy to mess up in rehearsal): after Chai Point, "I need parking too" reports no lot and **keeps the pin**. Blue Tokai doesn't appear until I say **Another one**.

---

## Proof I invite you to reproduce

### Watch the fence cockpit live

During steps 3 and 7, I'm not asking anyone to trust latency numbers I didn't measure. I'm showing **application state** — the same thing that gates Rime input.

### Run my evidence CLI

```bash
cd apps/agent
uv run python -m mid_drive.evidence
```

Expected output:

```json
{ "rounds": 3, "stale_admissions": 0, "stale_rejects": 3 }
```

Non-zero `stale_admissions` is a hard fail — the command exits with an error.

### Run the full test suite

```bash
cd apps/agent
uv run pytest
```

**131 tests** — fence races, 400-event property harness, interrupt pitfalls, and `test_demo_video.py` locking the entire 3:30 path.

---

## What I won't oversell

I'm precise here because unverified performance numbers earn zero credit in the brief.

- Residual audio can linger in WebRTC/browser buffers after interrupt — not magic instant silence
- HUD ack/barrier ms are **server-event** timestamps, not acoustic p95
- Parking comes from OSM amenity **tags**, not live lot occupancy
- Toll avoidance is a route **preference**, not a guarantee
- My phrase grammar covers the judged script; wild paraphrase may miss
- `GEO_MODE=live` depends on public API rate limits and real-world latency

---

## When things break — what I see and what I do

| Failure | What I experience | Fix |
|---|---|---|
| Rime HTTP error / bad PCM | Utterance fails; logged; no silent provider swap | Retry once in `SafeRimeTTS`; re-run preflight |
| ElevenLabs STT down | Turns stop committing | Check `ELEVEN_API_KEY` and quota |
| Azure unreachable | Judged path unaffected (`NLU_MODE=rules`) | Optional — ignore for demo |
| Agent not registered | "Start drive" times out (~20 s) | Restart worker; free port **8081** |
| Stale tool returns | Cockpit shows `OBSOLETE`; never spoken as current | Working as designed |
| Unsupported phrasing | Rime asks me to rephrase | Stick to cue-card patterns |
| Live geo timeout | "Still searching" / retry | Fall back to `fixture` |

I never commit `.env`, key screenshots, or demo recordings with secrets in them.

---

## Repository map

```text
apps/
  agent/     LiveKit worker — SessionActor, fence, NLU, Rime, evidence CLI
  web/       Next.js cockpit — map, CockpitHUD, provider badges
fixtures/
  gurgaon-delhi-v1.json   my Cyber Hub → CP corridor + shop picks
scripts/
  dev-livekit.sh          local LiveKit
  write_env.py            optional .env scaffolder
RIME_EVIDENCE.md          hard claim · acceptance test · repeatable proof
.env.example              placeholders only
```

---

## Submission checklist (Rime PS)

- [x] Voice-native — remove speech, product vanishes
- [x] Hard voice problem — interruption + continuity during tool work
- [x] Rime as **primary** spoken output (every turn, not welcome-only)
- [x] Full duplex — interrupt while Rime talks and while tools run
- [x] LiveKit Agents + browser WebRTC
- [x] README — setup, architecture, services, limitations, failure behavior, exact Rime config
- [x] `RIME_EVIDENCE.md` — claim, test, procedure, result, repeatable command
- [x] Configuration hygiene — `.env.example` placeholders, preflight passes
- [x] Active provider observable in UI
- [x] No secrets in repo

---

<p align="center">
  <strong>Mid-Drive</strong><br/>
  Driving makes the problem obvious. The output barrier, mission versioning,<br/>
  and stale-result fence are what I built to solve it — with Rime as the voice you'll actually hear.
</p>

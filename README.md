<p align="center">
  <strong>Mid-Drive</strong><br/>
  <em>We built a voice copilot that stays correct when you interrupt it — mid-sentence, mid-search, mid-drive.</em>
</p>

<p align="center">
  DataForge 2026 · Rime Challenge · Cyber Hub → Connaught Place
</p>

<p align="center">
  <code>131 tests</code> &nbsp;·&nbsp; <code>0 stale admissions</code> &nbsp;·&nbsp; <code>8 s stress delay</code> &nbsp;·&nbsp; <code>3:30 demo</code> &nbsp;·&nbsp; Rime Coda / astra · full duplex
</p>

---

## Why we built this

Picture the NH-48 run into Delhi. One hand on the wheel. Eyes forward. We ask for coffee — the assistant starts answering — and two seconds later we remember: **we need parking too**. We cut it off mid-sentence.

That single moment exposes everything wrong with most voice products.

| What usually happens | Why it fails on the road |
|---|---|
| Old audio keeps playing | We're hearing an answer we already rejected |
| New words land, **old search result wins** | A delayed API call overwrites what we actually asked for |
| Everything resets | We lose context and start from zero |

None of that is a copilot. That's a chatbot wearing a microphone.

**Mid-Drive** is our answer: a hands-busy **mission runtime** where speech *is* the interface, **Rime** carries every spoken line, and a **fence cockpit** on screen shows stale work getting rejected in real time — so nobody has to take our word for it.

Remove voice and the product collapses. That isn't a limitation. That's the point.

---

## Our hard claim — and the numbers behind it

> Once our per-session actor linearizes the user-speech barrier, no artifact from an older output epoch can enter active mission state, new TTS input, or user-visible application output.

We're proving two voice problems from the Rime brief — not as slides, as running software:

| Voice problem | What we ship |
|---|---|
| **Interruption and recovery** | VAD closes the output barrier at speech onset. Queued Rime playout stops. Stale tool results cannot re-enter TTS or mission state. |
| **Conversation continuity during tool work** | We add constraints, ask *"what's taking so long?"*, or interrupt while an **8-second** search runs — and delayed results get **fenced**, not applied to the wrong mission version. |

### By the numbers

| Metric | Result | How we verify |
|---|---|---|
| Regression tests | **131** | `uv run pytest` |
| Evidence rounds | **3** | `uv run python -m mid_drive.evidence` |
| Stale results admitted | **0** | Hard fail if non-zero |
| Stale results rejected | **3** | Logged in `artifacts/evidence-fence.json` |
| Demo runtime | **3:30** | Under the 5-minute submission cap |
| Stress search delay | **8.0 s** | `FIXTURE_V2_DELAY_S` — deliberate, reproducible |
| Mission arc in stress demo | **v1 → v3** | Coffee → parking hold → toll avoidance |
| Rime sample rate | **24 kHz** | HTTP PCM, 20 ms aligned frames |

Full acceptance test, procedure, and repeatable commands: [`RIME_EVIDENCE.md`](RIME_EVIDENCE.md)

---

## What judges see in 60 seconds

We optimized the first minute for clarity — not feature breadth.

1. **Start drive** at [localhost:3000](http://localhost:3000) → allow mic → wait for Rime's greeting.
2. Flip **Open mic** → say *"Find a coffee shop near my route."*
3. Rime acks immediately → names **Chai Point** → pin drops on the map.
4. Cockpit shows mission **v1**, tokens **ACCEPTED**, provider badge **Rime · coda · astra**.

That's the normal path. The stress path — interrupt + 8 s delay + constraint change — is where our fence earns its keep. We walk through it beat-by-beat in [Our demo script](#our-330-demo--one-drive-ten-beats).

---

## Run it locally

We kept setup deliberately boring: three terminals, one fixed corridor, deterministic fixture geo so every judge gets the same story.

```bash
git clone https://github.com/PratyushGupta7/Driving-Voice-Agent-Assistant.git
cd "Driving-Voice-Agent-Assistant"

cp .env.example .env
# Fill: ELEVEN_API_KEY, RIME_API_KEY, AZURE_OPENAI_*

cp apps/web/.env.local.example apps/web/.env.local

cd apps/agent && uv sync
cd ../web && npm install
```

| Terminal | Command |
|---|---|
| 1 · LiveKit | `./scripts/dev-livekit.sh` |
| 2 · Agent | `cd apps/agent && uv run python -m mid_drive.main start` |
| 3 · Web | `cd apps/web && npm run dev` |

**Before we record or submit**, we always run:

```bash
cd apps/agent
uv run python -m mid_drive.preflight    # live Rime catalog + PCM sanity check
uv run python -m mid_drive.evidence     # fence proof → artifacts/evidence-fence.json
```

Worker is healthy when logs show `registered worker … agent_name: mid-drive`.

---

## How it works — two counters, one fence

Most voice stacks track a single "context." We split **safety** from **semantics** because drivers revise faster than tools finish.

```text
Browser (Next.js + MapLibre + Fence Cockpit)
  │  WebRTC audio + data channel
  ▼
LiveKit Server (local)
  │  Silero VAD · ElevenLabs STT · SafeRimeTTS
  ▼
SessionActor — single writer, no races
  ├── output_epoch      ← bumps the instant the driver starts speaking (VAD onset)
  ├── mission_version   ← bumps when a real constraint changes
  ├── ResultFence       ← rejects tokens from dead epochs
  └── MissionController ← rules-first NLU, template acks, orchestrator
        ▼
Fixture corridor (judged default)  ·  or  ·  live OSM stack
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
    VAD->>Actor: output_epoch++ · BARRIER_CLOSED
    Actor->>Rime: interrupt playout
    Rime->>Driver: Got it — parking required…

    Driver->>Actor: Another one
    Note over Tools: v2 search — 8 s delay

    Driver->>VAD: Avoid toll roads too
    VAD->>Actor: output_epoch++ · mission v3
    Tools-->>Actor: v3 Starbucks accepted
    Tools-->>Actor: v2 returns → STALE_REJECTED
    Rime->>Driver: Starbucks… parking lot… toll-avoiding route
```

### The two counters

| Counter | When it moves | What it protects |
|---|---|---|
| `output_epoch` | Silero VAD detects driver speech | In-flight TTS, tools, and UI sinks — **immediately**, before transcription finishes |
| `mission_version` | Completed turn with a material constraint change | What the driver *meant*, not just that they made a sound |

```text
ACTIVE (mission v2, epoch 3)
  │
  │ driver starts speaking — VAD fires
  ▼
BARRIER_CLOSED (still v2, epoch 4)     ← old work dies here
  │
  │ completed turn: "avoid tolls"
  ▼
ACTIVE (mission v3, epoch 4)             ← new search, new tokens
```

Cancellation is best-effort. **Correctness is the fence.** When v2 returns late, the cockpit shows **OBSOLETE** — auditable, never silent.

Core modules: `session_actor.py` · `result_fence.py` · `orchestrator.py` · `controller.py` · `evidence.py`

---

## Our stack

| Layer | Choice | Why we picked it |
|---|---|---|
| Transport | **LiveKit** (local server) | Full duplex in-browser; VAD-owned turns; interruption API we can hook into |
| VAD | Silero | Speech onset → epoch bump before STT finishes |
| STT | **ElevenLabs Scribe v2 Realtime** | Partials for UI; committed text drives NLU — no guessing on half-heard words |
| TTS | **Rime Coda / astra** | Every driver-facing line on the judged path — acks, results, holds, status |
| NLU | **Phrase grammar** (`NLU_MODE=rules`) | Immediate acks; no LLM roulette on the hot path |
| LLM | Azure gpt-4.1-mini | LiveKit session stub + preflight only — **not** our spoken output |
| Geo (judged) | `fixtures/gurgaon-delhi-v1.json` | Same shops, same 8 s delay, same OBSOLETE moment — every run |
| Geo (optional) | Nominatim + OSRM + Overpass | `GEO_MODE=live` for real Delhi/Gurgaon data |
| UI | Next.js + MapLibre + **CockpitHUD** | We built the HUD so the fence is visible, not asserted |
| Store | SQLite + JSONL session logs | Atomic fence decisions + audit trail |

### Third-party services

| Service | Role | Config |
|---|---|---|
| **Rime** | Primary spoken output — every turn | `RIME_*` |
| **ElevenLabs** | Realtime STT | `ELEVEN_API_KEY` |
| **Azure OpenAI** | Session stub / preflight | `AZURE_OPENAI_*` |
| **LiveKit** | WebRTC + VAD + turn handling | `LIVEKIT_*` |
| **OSM stack** | Optional live geo | `GEO_MODE=live` |

All API keys stay **server-side**. The browser receives a short-lived LiveKit JWT — never our Rime, ElevenLabs, or Azure credentials.

Active speech provider is visible in the UI: **TTS · Rime · coda · astra · http-pcm**.

---

## Exact Rime configuration (judged path)

We validate `astra` against the **live catalog** at preflight — not a stale speaker list baked into the app.

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

`AZURE_SPEAK=false` on the judged path — **Rime owns every spoken line.** Acceptance test and results: [`RIME_EVIDENCE.md`](RIME_EVIDENCE.md).

---

## Configuration hygiene

We treat secrets like fuel caps — necessary, never loose in the repo.

1. Copy [`.env.example`](.env.example) → `.env`. **We never commit `.env`.**
2. Empty placeholders for real keys: `ELEVEN_API_KEY`, `RIME_API_KEY`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`.
3. `LIVEKIT_*` in the example matches our **local** `livekit.yaml` dev server — not production credentials.
4. Judged defaults (already in `.env.example`):

   | Variable | Default | Why |
   |---|---|---|
   | `GEO_MODE` | `fixture` | Deterministic corridor + 8 s v2 delay |
   | `NLU_MODE` | `rules` | Grammar-first; fast acks |
   | `AZURE_SPEAK` | `false` | Rime-only on the hot path |
   | `FIXTURE_V2_DELAY_S` | `8.0` | Stress case that exposes stale rejects |
   | `RIME_SPEAKER` | `astra` | Live-catalog validated |

5. Preflight before demo: `cd apps/agent && uv run python -m mid_drive.preflight`

Optional: `python scripts/write_env.py` scaffolds `.env` locally — it never embeds real keys.

---

## Our 3:30 demo — one drive, ten beats

**Locked settings:** `GEO_MODE=fixture` · `NLU_MODE=rules` · `AZURE_SPEAK=false` · **Open mic** after greeting.

We tell one story on camera: a normal drive that deliberately breaks under stress — then recovers cleanly.

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

### HUD checkpoints (what we point the camera at)

| Beat | What the cockpit must show |
|---|---|
| Step 3 — interrupt | `BARRIER_CLOSED` the instant we cut Rime off |
| Step 7 — toll change | `OBSOLETE` on v2; mission jumps to **v3** |
| Step 10 — proof | `stale ≥ 1`; evidence CLI prints `stale_admissions: 0` |
| Every turn | `nlu · rules`; shop names on tool rows **only** when `ACCEPTED` |

### Deterministic fixture outcomes

| Driver says | Rime names | Notes |
|---|---|---|
| Coffee, no parking | **Chai Point** | Alt: Third Wave |
| Coffee + parking (cold start) | **Blue Tokai** | |
| Coffee + parking + no tolls | **Starbucks** | After the stress case |
| Juice, no parking | **Fresh Juice Corner** | Same 9-line demo as coffee |
| Juice + parking (cold start) | **Raw Pressery** | |
| Juice + parking + no tolls | **The Juicery** | After the stress case |
| Fuel | **Indian Oil** | Category replace |
| Pharmacy | **Apollo Pharmacy** | |

**Parking hold** (we rehearse this): after Chai Point, *"I need parking too"* reports no lot and **keeps the pin**. Blue Tokai doesn't appear until **Another one**.

---

## How we map to the judge rubric

| Bucket | Points | What we demonstrate | Where |
|---|---:|---|---|
| Voice necessity | 25 | Mission created and revised entirely by speech — never touch the map | Browser demo, beats 1–9 |
| Hard voice engineering | 25 | VAD barrier, dual counters, stale tool rejection | **Fence cockpit** — `BARRIER_CLOSED`, `OBSOLETE`, `stale ≥ 1` |
| Rime experience | 20 | Coda / astra, HTTP PCM 24 kHz, every spoken line | Provider badges + audible responses |
| Evidence | 20 | Reproducible fence proof, 131 tests | `mid_drive.evidence` + pytest |
| Demo clarity | 10 | One corridor, deterministic fixture, honest wording | 3:30 cue card above |

---

## Proof you can reproduce

### 1 · Watch the fence cockpit

During beats 3 and 7, we're not asking anyone to trust latency numbers we didn't measure. We're showing **application state** — the same gate that controls Rime input.

### 2 · Run our evidence CLI

```bash
cd apps/agent
uv run python -m mid_drive.evidence
```

Expected:

```json
{ "rounds": 3, "stale_admissions": 0, "stale_rejects": 3 }
```

Non-zero `stale_admissions` is a hard fail — the command exits with an error.

### 3 · Run the full test suite

```bash
cd apps/agent
uv run pytest
```

**131 tests** — fence races, 400-event property harness, interrupt pitfalls, and `test_demo_video.py` locking the entire 3:30 path.

---

## What we won't oversell

We're precise here because unverified performance numbers earn zero credit in the brief.

- Residual audio can linger in WebRTC/browser buffers after interrupt — not instantaneous silence
- HUD ack/barrier ms are **server-event** timestamps, not measured acoustic p95
- Parking comes from OSM amenity **tags**, not live lot occupancy
- Toll avoidance is a route **preference**, not a guarantee
- Our phrase grammar covers the judged script; free-form paraphrase may miss
- `GEO_MODE=live` depends on public API rate limits and real-world latency

---

## When things break

| Failure | What you'll see | Fix |
|---|---|---|
| Rime HTTP error / bad PCM | Utterance fails; logged; no silent provider swap | Retry once in `SafeRimeTTS`; re-run preflight |
| ElevenLabs STT down | Turns stop committing | Check `ELEVEN_API_KEY` and quota |
| Azure unreachable | Judged path unaffected (`NLU_MODE=rules`) | Optional — ignore for demo |
| Agent not registered | "Start drive" times out (~20 s) | Restart worker; free port **8081** |
| Stale tool returns | Cockpit shows `OBSOLETE`; never spoken as current | Working as designed |
| Unsupported phrasing | Rime asks to rephrase | Use cue-card patterns |
| Live geo timeout | "Still searching" / retry | Fall back to `fixture` |

We never commit `.env`, key screenshots, or demo recordings containing secrets.

---

## Repository map

```text
apps/
  agent/     LiveKit worker — SessionActor, fence, NLU, Rime, evidence CLI
  web/       Next.js cockpit — map, CockpitHUD, provider badges
fixtures/
  gurgaon-delhi-v1.json   Cyber Hub → Connaught Place corridor + shop picks
scripts/
  dev-livekit.sh          local LiveKit server
  write_env.py            optional .env scaffolder (local only)
RIME_EVIDENCE.md          hard claim · acceptance test · repeatable proof
.env.example              placeholders only — copy to .env
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
  <strong>Mid-Drive</strong><br/><br/>
  Driving makes the problem obvious.<br/>
  The output barrier, mission versioning, and stale-result fence are what we built to solve it —<br/>
  with <strong>Rime</strong> as the voice you'll actually hear on the road.
</p>

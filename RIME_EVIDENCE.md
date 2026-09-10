# RIME_EVIDENCE — Mid-Drive

DataForge 2026 · Rime hackathon submission evidence pack.

This file satisfies the problem-statement requirement: **hard voice claim**, **acceptance test**, **procedure**, **result**, **limitations**, and a **repeatable command**.

---

## 1. Hard voice claim

**Voice problem paths (chosen):**

1. **Interruption and recovery** — stop queued TTS and local playout promptly; fence obsolete model and tool results so they cannot re-enter the conversation.
2. **Conversation continuity during tool work** — keep the session responsive while lookups run; let the driver add constraints, ask status, interrupt, or cancel without losing context.

**Application claim (what we prove):**

> Once the per-session actor linearizes the user-speech barrier, no artifact from an older output epoch can enter active mission state, new TTS input, or user-visible application output.

Full duplex is treated as a property of the **complete application** (VAD → actor → tools → fence → Rime), not the TTS model alone.

---

## 2. Acceptance test

This matches the **official full-duplex test example** from the Rime problem statement:

1. Introduce a **fixed delay** into a tool call (`FIXTURE_V2_DELAY_S=8` on the second place search).
2. While the agent is **speaking or waiting**, **interrupt** and **change one part of the request** (add parking, then avoid tolls).
3. Verify:
   - queued Rime audio **stops** (LiveKit interruption + epoch bump),
   - the updated instruction reaches the application (mission version advances),
   - **stale tool results are not spoken as current** (fence marks `stale_rejected`; cockpit shows `OBSOLETE`),
   - background work is **cancelled or reconciled** (v2 search fenced even if cancelled mid-flight),
   - the **final spoken response** reflects the latest mission (Starbucks with parking + toll-avoidance, not Chai Point or Blue Tokai from stale epochs).

**Pass criteria:** `stale_admissions = 0` across three automated rounds; live demo shows `stale ≥ 1` on the fence cockpit after the toll beat.

---

## 3. Procedure

### A. Organizer Rime preflight (required)

```bash
cd apps/agent
cp ../../.env.example ../../.env   # fill ELEVEN_API_KEY, RIME_API_KEY, AZURE_OPENAI_*
uv run python -m mid_drive.preflight
```

Expect: live catalog fetch, speaker `astra` validated, HTTP PCM sample written to `artifacts/preflight-rime.pcm`.

### B. Automated fence evidence (repeatable)

```bash
cd apps/agent
uv run python -m mid_drive.evidence
```

Writes `artifacts/evidence-fence.json`. Exits non-zero if any stale result is admitted.

### C. Live stress path (demo recording)

Three terminals:

```bash
./scripts/dev-livekit.sh
cd apps/agent && uv run python -m mid_drive.main start
cd apps/web && npm run dev
```

Open **http://localhost:3000** → **Start drive** → **Open mic**, then:

```text
 1. Find a coffee shop near my route.
 2. Does it have parking?
 3. [INTERRUPT] Wait, I need parking too.
 4. Why this one?
 5. Another one.                    ← starts 8 s v2 delay
 6. What's taking so long?
 7. Avoid toll roads too.            ← v3 wins; v2 must show OBSOLETE
```

Observe provider badges: **TTS · Rime coda · astra · http-pcm**. Cockpit should show `BARRIER_CLOSED` on interrupt and `stale ≥ 1` after step 7.

### D. Test suite (regression lock)

```bash
cd apps/agent
uv run pytest -q
```

Includes `test_evidence.py`, `test_demo_video.py`, interrupt/race property tests.

---

## 4. Result

**Last run** (`uv run python -m mid_drive.evidence`):

```json
{
  "claim": "Once the per-session actor linearizes the user-speech barrier, no artifact from an older output epoch can enter active mission state, new TTS input, or user-visible application output.",
  "rounds": 3,
  "stale_admissions": 0,
  "stale_rejects": 3
}
```

| Round | Live decision | Stale decision   | Spoken shop | Stale admitted |
|------:|---------------|------------------|-------------|----------------|
| 1     | accepted      | stale_rejected   | Starbucks   | no             |
| 2     | accepted      | stale_rejected   | Starbucks   | no             |
| 3     | accepted      | stale_rejected   | Starbucks   | no             |

**Judged voice path** (3 rounds): final shop **Starbucks**, mission **v3**, parking + toll-avoidance held; parking-hold line does **not** prematurely name Blue Tokai.

Artifact: `artifacts/evidence-fence.json` (committed path: regenerate locally; file is gitignored if under `artifacts/`).

---

## 5. Limitations (honest)

| Topic | What we claim | What we do **not** claim |
|---|---|---|
| Fence proof | Application state + TTS input cannot admit stale epoch artifacts | Acoustic stop latency (ms p95) |
| Interrupt | VAD closes barrier at speech onset; LiveKit discards uninterruptible audio | Instant silence in browser/WebRTC buffers |
| Tool delay | Fixture v2 sleeps 8 s; orchestrator fences cancelled tasks | Real Nominatim/OSRM latency under load |
| Parking / tolls | OSM amenity tags + route preference in fixture/live geo | Live lot occupancy or toll guarantee |
| NLU | Phrase grammar covers judged script (`NLU_MODE=rules`) | Free-form paraphrase outside grammar |
| Azure | Optional NLU/speak (`AZURE_SPEAK=false` on judged path) | Azure is not primary spoken output |

**Unverified performance numbers receive no credit** (per PS). We do not quote unmeasured latency p95.

---

## 6. Exact Rime configuration (shipped path)

Validated against the **live catalog at run time** (`mid_drive.preflight` + `rime_catalog.py`).

| Setting | Value |
|---|---|
| Model ID | `coda` |
| Speaker | `astra` |
| Language | `eng` |
| Endpoint | `https://users.rime.ai/v1/rime-tts` |
| Catalog | `https://users.rime.ai/data/voices/all-v2.json` |
| Transport | **HTTP** (`use_websocket=False`) |
| Audio format | `audio/pcm` (`audioFormat=pcm`) |
| Sample rate | **24000 Hz** |
| Frame alignment | 20 ms PCM frames before playout |
| Integration | LiveKit Agents plugin → `SafeRimeTTS` (`apps/agent/src/mid_drive/rime_tts.py`) |

**Primary spoken output:** Rime renders every driver-facing utterance on the judged path (acks, search results, holds, status). Azure OpenAI is wired to the LiveKit session stub and preflight only; `AZURE_SPEAK=false` keeps templates on the ack hot path.

**Active provider observable:** browser provider badges (`apps/web/components/ProviderBadges.tsx`) and worker startup logs.

**Fallbacks disclosed:** if Rime HTTP returns non-PCM or empty body, the worker retries once then fails the utterance (logged; no silent provider swap).

---

## 7. Repeatable commands (summary)

```bash
# 1. Preflight (organizer Rime check)
cd apps/agent && uv run python -m mid_drive.preflight

# 2. Fence evidence (primary proof artifact)
cd apps/agent && uv run python -m mid_drive.evidence

# 3. Full regression
cd apps/agent && uv run pytest -q
```

Fixture reference: `fixtures/gurgaon-delhi-v1.json` · delay knob: `FIXTURE_V2_DELAY_S=8.0` in `.env`.

# Acceptance test

Defined before the demo. This is the judged claim.

## Hard claim

Once the per-session actor linearizes the user-speech barrier, no artifact from an older output epoch can enter active mission state, new TTS input, or user-visible application output. Existing audible speech stops within a measured latency distribution.

Do not claim instantaneous silence, automatic cancellation of every tool, or that a final STT segment is always a complete semantic turn.

## Phase 1 gate

A driver can start a browser session, speak, and hear **Rime Coda / astra** respond over LiveKit. ElevenLabs Scribe v2 Realtime is the active STT. Provider labels are visible. Secrets never leave the server.

## Phase 5 / 6 gate

The live actor is the fence source of truth: a matching token can accept even if SQLite is behind, and a lagging DB row cannot admit a stale token. Duplicate completions are stale. An empty STT turn after barge-in asks the driver to repeat. Echo of the last Rime line is ignored. Rime HTTP PCM is rejected when the body is not speech-shaped audio.

## Phase 4 gate (current)

The Gurgaon–Delhi corridor is drawn from real OSRM geometry (or a baked downsample in fixture mode). Route and place work share one output epoch and are fenced separately. An accepted place gets a pin; a via-verified path may draw a second line. Stale tool rows never move the pin or name a shop. Live mode does not invent a fixture shop when Overpass is empty. Spoken minutes require via-verify (or curated fixture evidence). `GEO_MODE=live` falls back to the saved corridor only on transport failure, and Rime says so.

## Phase 2 gate

Completed turns update a durable mission. VAD onset increments `output_epoch` and closes the output gate before transcription. Fixture search for mission version 2 is delayed. A later revision makes that result `stale_rejected`. Rime only speaks an accepted latest-mission result. Parking is spoken as an amenity tag, not occupancy. Tolls are a requested preference.

```bash
cd apps/agent && uv run pytest
```

## Judged stress case

1. Inject a fixed delay into a place/route tool.
2. While Rime is speaking or the tool is running, interrupt and change one constraint (parking, then tolls).
3. Verify:
   - queued Rime audio stops promptly
   - the new instruction reaches application state
   - the delayed old result is `STALE_REJECTED`
   - Rime’s next utterance matches the latest mission only

## Repeatable command

```bash
uv run --project apps/agent mid-drive-preflight
```

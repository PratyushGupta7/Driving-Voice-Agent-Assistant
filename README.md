# Mid-Drive

Voice-first driving copilot for the DataForge 2026 Rime challenge.

> Once the per-session actor linearizes the user-speech barrier, no artifact from an older output epoch can enter active mission state, new TTS input, or user-visible application output.

This is **not** “a maps assistant with a play button.” The driving task exists so judges can *see* full-duplex interruption, mission versions, and stale-tool rejection. Rime is the only primary spoken output.

**Current:** A version-safe full-duplex mission runtime. Phase 2 fence is the source of truth. Phase 3/4 geo ranks real corridor geometry, via-verifies minutes, and never invents a shop. The cockpit shows versions, the route/place fence race, and only accepted pins. You can pick the second option, ask why, or change destination without breaking the epoch rules.

## Requirements

- macOS or Linux
- Python 3.11+ (`uv`)
- Node 20+
- [LiveKit Server](https://docs.livekit.io/transport/self-hosting/local/) (`brew install livekit`)
- ElevenLabs, Rime, and Azure OpenAI credentials

**Clone, keys, three processes, and the 15-line live script:** [CLONE_AND_TEST.md](CLONE_AND_TEST.md).

## Setup

```bash
cp .env.example .env
# fill ELEVEN_API_KEY, RIME_API_KEY, AZURE_OPENAI_*
cp apps/web/.env.local.example apps/web/.env.local

cd apps/agent && uv sync
cd ../web && npm install
```

Local LiveKit keys in `.env.example` match `livekit.yaml` (`middrive` + a 32-byte HMAC). Do not use the 6-byte `--dev` pair `devkey`/`secret`.

## Run (three processes)

```bash
# 1. LiveKit
./scripts/dev-livekit.sh

# 2. Agent worker
cd apps/agent
uv run python -m mid_drive.main start

# 3. Web
cd apps/web
npm run dev
```

Open http://localhost:3000, allow the microphone, click **Start drive**.

Preflight (catalog + Rime PCM + Azure + ElevenLabs account):

```bash
cd apps/agent
uv run python -m mid_drive.preflight
uv run pytest
```

## How this satisfies the problem statement

| PS requirement | How we meet it |
|---|---|
| Voice-native product | Hands-busy driver; removing speech removes the product |
| Hard voice problem | VAD barrier increments `output_epoch` before any await; SQLite CAS rejects stale tool work |
| Rime is primary TTS | Coda / astra / HTTP PCM 24 kHz; labels always visible |
| Live catalog | Startup and preflight fetch `all-v2.json` |
| Full duplex | Mic stays open while Rime speaks and while tools run |
| Evidence | `RIME_EVIDENCE.md`, JSONL session logs, preflight command |
| Secrets | Server-side only; `.env.example` has placeholders |
| Demo ≤ 5 min | Script in `docs/DEMO_SCRIPT.md` (filled as phases land) |
| LiveKit recommended | Local LiveKit Agents worker, not a chatbot play button |

## Assumptions

- Fixed route: Cyber Hub, Gurugram → Connaught Place, Delhi
- Categories: coffee / fuel / pharmacy
- Fixture geo is the judged default. v2 searches sleep 8s so a later revision can reject them. `GEO_MODE=live` is the real Nominatim / OSRM / Overpass path.
- Spoken parking is an amenity tag. Spoken minutes exist only after a via-verified route, or from curated fixture evidence.
- Local LiveKit, not LiveKit Cloud
- Azure `gpt-4.1-mini` is on the LiveKit session as a silent stub and for preflight. Turns are parsed by the phrase grammar in `revision.py`.

## Repo

```
CLONE_AND_TEST.md   Full onboard: what ships, keys, live script
apps/web            Next.js cockpit + token endpoint
apps/agent          LiveKit worker + mission actor / fence
fixtures/           Deterministic Gurgaon–Delhi place evidence
eval/               Race harness (later)
docs/               Acceptance test, provider freeze, limitations
```

## Security

Never commit `.env`, screenshots of keys, or recordings that show secrets. Rotate any key that was pasted into chat.

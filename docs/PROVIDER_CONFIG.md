# Provider configuration

Frozen for the local judged path. Startup still fetches the live Rime catalog and refuses a missing speaker.

| Layer | Provider | Exact setting |
|---|---|---|
| Transport | LiveKit Server 1.13.x (local) | `ws://127.0.0.1:7880` |
| VAD | Silero (LiveKit plugin) | 16 kHz, min speech 100 ms, min silence 320 ms, activation 0.55 |
| Turn detection | VAD only | `inference.TurnDetector` requires LiveKit Cloud; not used locally |
| STT | ElevenLabs | `scribe_v2_realtime`, `en`, timestamps on, `no_verbatim=false` |
| LLM | Azure OpenAI | deployment `gpt-4.1-mini` on the LiveKit session only (StopResponse; does not classify turns) |
| NLU | Phrase parser | `apps/agent/src/mid_drive/revision.py`; Azure is not on the spoken turn path |
| TTS | Rime | `coda` / `astra` / `eng` / HTTP PCM / 24 kHz / `audioFormat=pcm`; JSON/HTML rejected; PCM is played only in complete 20 ms frames |
| Geo (judged) | Fixture adapter | `fixtures/gurgaon-delhi-v1.json`; v2 delay 8s |
| Geo (live) | Nominatim + OSRM + Overpass | `GEO_MODE=live`; via-verify uses the same `exclude=toll` as baseline |
| Default endpoints | Configurable queries | `ROUTE_ORIGIN`, `ROUTE_DESTINATION` |

Rime HTTP endpoint: `https://users.rime.ai/v1/rime-tts`  
Catalog: `https://users.rime.ai/data/voices/all-v2.json`

Interruption: adaptive resume is **off**. Preemptive generation is **off**.

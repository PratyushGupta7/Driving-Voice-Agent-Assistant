# Architecture

```
Browser (Next.js)
  mic ──LiveKit WebRTC──► livekit-server (local)
  data topic `mid-drive` ◄── session events
  MapLibre corridor + via line + accepted pin only

Python worker (LiveKit Agents 1.8)
  Silero VAD
  ElevenLabs scribe_v2_realtime
  Azure OpenAI gpt-4.1-mini (LiveKit session stub + preflight only)
  Phrase NLU (`revision.parse_turn`) — not Azure on the turn path
  Rime Coda HTTP PCM 24 kHz / astra
  SessionActor (sync VAD barrier; two counters)
  Mission reducer + SQLite CAS fence
  Concurrent route token + place_search token (same epoch)
  Providers: Nominatim, OSRM (identical settings for baseline/via), Overpass
  Fixture adapter for the judged delay path
  EventBus → JSONL + data packets
```

## Two counters

- `mission_version` increments on a material constraint change.
- `output_epoch` increments on every VAD onset and never decrements.

A tool result may enter selected state, Rime input, or the map only when both counters and the latest request id still match and the output gate is open.

## Geo plan

1. Optional fixture delay (judged path only).
2. Geocode origin / destination if the driver named them; otherwise use `ROUTE_ORIGIN` / `ROUTE_DESTINATION`.
3. Issue `route` and `place_search` tokens in the same epoch.
4. OSRM baseline. Fence the route. Cache it when accepted.
5. Overpass (or fixture) along the polyline. Re-filter using current constraints.
6. Via-verify the top candidates with the same `exclude=toll` setting as the baseline. Skip unverified rows. Do not invent minutes.
7. Fence the place. Speak and pin only on accept. Alternatives come from that same accepted result.

Reuse (in-memory, session-scoped):

- Category change → new places.
- Parking / detour / landmark → reuse route + cached places, re-rank, re-verify.
- Avoid tolls, origin, or destination change → new route and places.

## Product loop

The driver can revise constraints, pick the first or second accepted option, and ask why / extra time / parking / compare. Those turns do not invent a new shop. Session prefs remember an explicit parking or toll request for the next create in the same drive.

Ranking uses segment-projected distance to the corridor, progress along the route, optional brand match, and via-verified minutes. Nominatim is biased to India / NCR but not locked to a landmark list.

## Honesty

- Live empty ≠ fixture Blue Tokai.
- Transport failure may use the saved corridor, and Rime says so.
- Parking is an OSM / fixture tag, or a parking node within 80 m, otherwise unknown.
- Tolls are `exclude=toll`, not a guarantee.

Secrets stay on the server. The browser receives only a short-lived LiveKit JWT that dispatches agent `mid-drive`.

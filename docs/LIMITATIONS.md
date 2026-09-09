# Limitations

- Audible audio can remain in WebRTC / browser buffers after the agent interrupts its speech handle.
- A committed ElevenLabs segment is not always the user’s full semantic turn.
- Silero VAD can false-trigger on coughs, echo, or a passenger. Those close the output epoch without changing mission version.
- Application-owned tools are cancelled best-effort. Correctness is the result fence, not cancellation.
- Rime HTTP `clear` is not used on this path; interruption is LiveKit playout + a new epoch.
- Toll avoidance on live OSRM is a preference (`exclude=toll`), not a guarantee. Fixture mode is deterministic.
- Parking is an OSM / fixture amenity tag, not live occupancy. Live mode treats nearby `amenity=parking` within 80 m as a lot report; otherwise unknown. Unknown is filtered out when parking is required.
- Spoken detour minutes are via-verified OSRM extras, or curated fixture evidence. Haversine is ranking-only and is never spoken.
- Live “no match” is spoken as no match. Fixture shops are not substituted unless Nominatim / OSRM / Overpass fail as transport.
- Fixture coordinates for most shops are neighborhood-accurate, not surveyed storefront GPS. Starbucks Cyber Hub is a Nominatim hit.
- Public Nominatim / OSRM / Overpass rate limits can force the spoken fixture fallback.
- Local LiveKit keys are for the demo machine only. Use the 32-byte HMAC in `livekit.yaml`, not `devkey`/`secret`.
- Turns are classified by a phrase grammar, not Azure. Odd paraphrases can still land on `unrelated` or `ambiguous`; the reducer will not invent a shop.

# Mid-Drive scenario book

Fifteen voice tests against the product as it ships today. Default is `GEO_MODE=fixture` (judged path). Start a drive first. Rime greets:

> I'm with you on the Gurgaon to Delhi drive. What do you need along the way?

The map should already show Cyber Hub → Connaught Place with an ETA / km HUD. Provider badges should read ElevenLabs, Rime Coda / astra, Azure OpenAI, fixture corridor. The greeting is uninterruptible so speaker echo cannot freeze it on “I'm with you on”. Speak after it finishes.

**Tap to talk** starts with the mic off. Tap, finish the **whole** sentence, then tap **Send**. The agent will not answer on “Find a coffee” while you are still talking. If you forget Send after a complete line, it waits about two seconds of silence, then answers. **Open mic** is the better mode for interrupting mid-sentence.

Speak naturally. Expected speech is the meaning Rime should produce, not a word-for-word STT transcript. Names appear only after a place token is `accepted`.

Turns are parsed by a **deterministic phrase grammar**, not Azure. Azure OpenAI stays on the LiveKit session as a silent stub and for preflight. A live session that shows `nlu: llm_first` or `revision_parsed source=azure` is an old worker — restart it.

---

## 1. Create a coffee stop

**What it tests:** Mission create, version 1, fence, ranked fixture pick, no invented parking.

**Say:** “Find a coffee shop near my route.”

**Expect immediately:**
- Ack: “Looking for coffee on the way.”
- Mission **version 1**, gate **open**, parking chip off, avoid-tolls chip off.
- Fence race: `route` and `place_search` go `running` (no extra wait on v1).

**Expect after accept:**
- Rime names **Chai Point** (lowest fixture detour, 3 min). It does **not** say a parking lot is available.
- Typical shape: “Chai Point in NH 48 lay-by is on the way. The extra time is about three minutes. I also have Third Wave Coffee. Should I keep this one?”
- Amber pin on Chai Point. Alternative card may show Third Wave.
- Tool rows: both `accepted`. Shop name appears only on the accepted place row.

---

## 2. Interrupt with parking (report the current shop)

**What it tests:** Constraint add, parking chip, honest lot on the place already in play. No auto-replan.

**When:** After Chai Point is accepted (Rime may still be speaking scenario 1).

**Say:** “Wait, it needs parking.” or “Wait, I need parking too.”

Either phrasing is a constraint change. The agent must ack and report the current shop. It must not stay silent on a partial caption. It must **not** jump to Blue Tokai. “Does Chai Point have parking?” alone is an inquire (same lot fact, no chip). If you mix both (“I need parking — does Chai Point have parking?”), parking required still wins as a constraint, but with a selected shop it still only reports the lot.

**Expect immediately:**
- Driver VAD → **speaking**. Voice panel flashes. Rime audio stops promptly (not instant silence).
- **Epoch +1**. **Version 2**. Parking chip on. **Pin stays on Chai Point.**
- Ack: “Got it — parking required. Chai Point does not have a parking lot.”
- No new route or place tokens. No “looking again.” No Blue Tokai name.

**To search for a lot instead:** say “Another one.” That starts a version-2 parking search (fixture **~8s** delay). If that search is allowed to finish, Rime names **Blue Tokai**, not Starbucks.

---

## 3. Tolls while a parking search is still in flight (stale reject)

**What it tests:** Hard claim. Old epoch / old version cannot speak or move the map.

**When:** After scenario 2, say **“Another one.”** so the version-2 parking search is sleeping. Within a few seconds, while those tokens are still `running`:

**Say:** “Avoid toll roads too.”

If you skip “Another one” and say tolls right after the parking report, version 3 searches immediately. Rime still names Starbucks. There is no delayed v2 row to reject.

**Expect immediately:**
- **Version 3**. Avoid-tolls chip on. Epoch increments again.
- Ack: “Okay — requesting a toll-avoiding route.”
- New tokens `running` (no extra wait). Version rail: `coffee` → `coffee · parking` → `coffee · parking · no tolls`.

**Expect when v3 accepts:**
- Rime names **Starbucks** (parking yes, 6 min, ahead of Blue Tokai at 7).
- Speech includes “This place reports a parking lot.” and “I requested a toll-avoiding route.”
- Extra time “about six minutes.” May also say “I also have Blue Tokai Coffee Roasters.”
- Pin moves to Starbucks only on `accepted`.

**Expect when v2 finally returns (~8s):**
- v2 route and place rows show **`stale_rejected`**.
- No shop name on those rows.
- Pin does not jump. Rime does not name the v2 shop.

---

## 4. Confirm the current stop

**What it tests:** Confirm does not replan or bump version.

**Say:** “Keep this one.”

**Expect:**
- “Okay, keeping that one.”
- Same selected place. Same version. Epoch increments (you spoke). No new fence race.
- Pin stays.

**If you say this with no accepted place:** “I do not have a place to keep yet.”

---

## 5. Pick the second accepted option

**What it tests:** Select among already-fenced alternatives. No new search. No invented third shop.

**When:** After scenario 3, while Starbucks is selected and Blue Tokai is an alternative.

**Say:** “The second one.” (or “Go with Blue Tokai.”)

**Expect:**
- Selected becomes **Blue Tokai Coffee Roasters**. Starbucks moves to alternatives.
- Rime describes Blue Tokai (parking lot reported, toll-avoiding requested, extra time about seven minutes).
- Pin moves to Blue Tokai.
- Version unchanged. No new search.

---

## 6. Ask why / time / parking (inquire)

**What it tests:** Follow-ups use accepted mission state only. Honest amenity wording.

After a place is accepted, say these as separate turns:

| Say | Expect |
|---|---|
| “Why this one?” | “I picked {name} because …” using a stored reason (parking, detour, landmark). Does not invent ratings. After Chai Point: extra time about 3 minutes, or “closest verified match.” |
| “How much extra time?” | “The extra time for {name} is about {n} minutes.” If unverified: it says it does not have a verified extra time. |
| “Does it have parking?” | Chai Point: “Chai Point is tagged as having no parking lot.” Third Wave: no tag. Starbucks / Blue Tokai / Apollo / Indian Oil: “{name} reports a parking lot. That is not live occupancy.” Never “a space is available.” If an alt exists, it may add a second lot sentence. |
| “What’s the other option?” | “The next option is {alt} in {area}. About {n} extra minutes.” No alt: “I do not have another accepted option. Say another one and I will search again.” |
| “Where is it?” | “{name} is in {area}.” |
| “Are they open?” | Fixture shops have no hours: “I do not have hours for {name}.” |
| “Compare them.” | Names selected versus first alt and both extra times if verified. With avoid-tolls and no measured route delta: also “I requested a toll-avoiding route. I do not have a measured comparison yet.” |

Version does not change. No new pin from a stale tool.

---

## 7. “Another one” searches again

**What it tests:** `next` rejects the current offered set and replans without a version bump.

**Say:** “Not that, another one.”

**Expect:**
- Ack: “Looking for another.”
- Version unchanged. Epoch increments. Pin clears.
- New route + place tokens. Skipped IDs include the place you just had **and** its shown alternatives.
- Skip IDs include the **selected shop and every alternative that was shown**. After scenario 1 the fixture offers all four coffees, so the first “another one” empties coffee and Rime says **no match**. After a parking search it only offered Blue Tokai + Starbucks, so one skip empties those too.
- That empty result is honest, not a silent Blue Tokai.

Prefer scenario 5 (“the second one”) when you still want a named alternative. Do not use “another one” if you want Third Wave after Chai Point.

---

## 8. Replace category

**What it tests:** Material revision, version bump, new place list, cache miss on category.

**Say:** “Actually, I need fuel.” (or “Need a petrol pump.”)

**Expect:**
- Version +1. Ack: “Switching to fuel.”
- Coffee pin clears.
- After accept: **Indian Oil** near Hero Honda Chowk. Extra time about four minutes if verified.
- Fuel chip / mission text shows fuel, not coffee.

---

## 9. Ambiguous request

**What it tests:** Clarifying status. No fake category. No shop name.

**Say:** “Find something near me.” or “Find coffee or fuel.”

**Expect:**
- No category: “Coffee, fuel, or a pharmacy?”
- Two categories (“Find coffee or fuel.”): “Coffee, fuel, or a pharmacy — which one?”
- Status **clarifying**. Constraints do not change.
- No pin. No place token `accepted` with a name.

---

## 10. Backchannel and cough (barrier without a revision)

**What it tests:** Epoch advances, version does not. False / unrelated speech must not cancel a good mission.

**When:** After a place is accepted and Rime is idle or speaking.

**Say:** “Uh-huh.” or cough loud enough to trip VAD, then stay quiet.

**Expect:**
- Epoch +1. Gate closes then reopens. Version unchanged. Constraints unchanged.
- Rime does **not** re-say the last line on a cough / “uh-huh”. That echo loop was the loud-noise bug. A true LiveKit **false interruption** may recover the line under a **new** epoch (it does not resume old audio).
- If the cough cancelled an in-flight search and nothing is selected, a search restarts. It must not speak a stale token.
- “Uh-huh” is not cancel. “Stop avoiding tolls” is a toll change, not cancel.

---

## 11. Cancel, then a new mission with remembered parking

**What it tests:** Terminal cancel, new mission id, session preference.

**Say:** “Cancel the search.”

**Expect:**
- “Okay, I cancelled that.”
- Status **cancelled**. Gate **closed for end**. Pin gone. Version rail stops.
- Standalone “stop” / “forget it” also cancel. “Stop avoiding tolls” does **not**.

**Then say:** “Find a pharmacy.”

**Expect:**
- New `mission_id`. Version **1** of the new mission.
- Because you required parking earlier this drive, the next **create** applies that pref: “Looking for pharmacy on the way. I'll keep requiring parking.”
- After accept: **Apollo Pharmacy** on MG Road (fixture has a parking lot tag). Not a coffee shop.
- Same pref on “Find a coffee shop” after cancel: it searches **with parking**, so Rime names **Blue Tokai**, not Chai Point.

---

## 12. Landmark and destination from speech

**What it tests:** Geocoded constraints, not a hardcoded landmark table. Route reuse rules.

**Say, on an active coffee mission:** “Find coffee near Cyber Hub.”

**Expect:**
- Version +1. Ack: “Preferring places near Cyber Hub.” Mission panel: `Near · Cyber Hub`.
- **Fixture ranking does not geocode.** The judged script still picks **Chai Point** (or Blue Tokai / Starbucks only if parking is already on). Live mode is what actually ranks by Nominatim distance.
- “Near my route” / “on the way” must **not** become a landmark.

**Then say:** “Change destination to India Gate.”

**Expect:**
- Version +1. “Heading toward India Gate.”
- Fixture **replans on the same baked corridor**. HUD stays Cyber Hub → Connaught Place. Constraint text shows India Gate.
- Live mode geocodes India Gate and updates the HUD after the route token accepts. If Nominatim cannot find it: “I could not find that destination on the map, so I did not change the route.” It must not silently keep a fake India Gate pin.
- “Take me to a pharmacy” is a **category** change, not a destination called “a pharmacy.”

---

## 13. Nearer the start vs a named brand

**What it tests:** Progress-along-route bias and brand filter without a chain list.

**Say:** “Nearer the start.”

**Expect:**
- Version +1. “I'll stay nearer the start.” (Destination: “I'll stay nearer the destination.”)
- Same corridor. **Fixture script still wins**, so the named shop stays **Chai Point**. Progress bias only matters in live ranking or when script scores tie. Pin only after accept.

**Reset or stay on coffee, then say:** “Find coffee called Blue Tokai.”

**Expect:**
- Brand constraint `Blue Tokai`. Only names that contain that text survive.
- After accept: **Blue Tokai Coffee Roasters**, even if Chai Point has a shorter raw detour.
- If nothing matches the spoken name: no match sentence, no invented shop.

---

## 14. Detour cap that nothing satisfies

**What it tests:** Honest empty result. No haversine minutes. No fixture substitution.

**Say:** “Find coffee with parking within 3 minutes.”

**Expect:**
- Constraints: coffee, parking required, max 3 minutes.
- Fixture shops with parking are 6 and 7 minutes → **no candidate**.
- Rime: “I could not find a matching place with those constraints along this corridor.”
- No amber shop pin. Map may still show the corridor.

**Then say:** “Closer.” or “That’s too far.” when a detour cap already exists.

**Expect:** Cap tightens by 2 minutes (floor 3). If none existed, cap becomes 5.

---

## 15. Off-topic talk, empty turn, and live-mode honesty

**What it tests:** Unrelated turns, StopResponse on empty STT, live fallback rules.

**A. Say:** “How’s the weather on the ring road?”

**Expect:** No mission change. No shop name. Rime stays quiet unless a cancelled search needs a restart.

**B. Empty / noise-only completed turn**

**Expect:** If that empty turn follows a barge-in that cut Rime: “I stopped. Please repeat the change.” Once. Version unchanged. Otherwise no mutation. Agent always raises `StopResponse`. An STT echo of the last Rime line is ignored (no new search, no re-say).

**C. Live mode (`GEO_MODE=live`) — only if you flipped the env and restarted the agent**

| Situation | Expect |
|---|---|
| Overpass returns no match | “I could not find a matching place…” **not** fixture Blue Tokai. |
| Nominatim / OSRM / Overpass time out | “Live maps did not answer in time, so I used the saved corridor.” then the fixture sentence. `fallback_used` on the tool row. |
| Via-verify fails for a shop | That shop is skipped. Minutes are omitted unless via succeeded. |
| OSM has `opening_hours` | May speak “OpenStreetMap lists hours as …”. Never “open now” unless that tag is actually there. |

---

## Quick matrix

| # | Say | Version | Fence | Named shop |
|---|---|---|---|---|
| 1 | Find coffee near my route | 1 | accept immediately | Chai Point |
| 2 | It needs parking / I need parking too | 2 | none | Chai Point (no lot) |
| 3 | Another one, then avoid tolls | 3 | v3 accept, v2 stale | Starbucks |
| 4 | Keep this one | same | none | same |
| 5 | The second one | same | none | Blue Tokai |
| 6 | Why / extra time / parking | same | none | current only |
| 7 | Another one | same | new search | maybe none |
| 8 | Actually fuel | +1 | new search | Indian Oil |
| 9 | Find something | no change | none | none |
| 10 | Uh-huh / cough | epoch only | maybe restart | no stale name |
| 11 | Cancel, then pharmacy | new mission | new search | Apollo Pharmacy |
| 12 | Near Cyber Hub / India Gate | +1 each | replan | fenced only |
| 13 | Nearer the start / called Blue Tokai | +1 | replan | match only |
| 14 | Parking within 3 minutes | +1 | accept empty | none |
| 15 | Weather / live timeout | no / fallback | — | never invented |

---

## Remaining official phases

Phases **0–4** are in the repo (local LiveKit, OSM instead of Google, SQLite instead of Postgres). Parts of **5–7** already landed because the fence, dual tokens, acks, reuse table, and cockpit were required to make 2–4 real. This is what is still left if we follow the original plan.

### Phase 5 — Concurrent orchestration and result fencing (landed this pass)

**In:** Dual tokens, actor-as-truth fence (DB cannot reject a matching live actor), skip `execute_plan` when both tokens are already stale, consume-on-accept so a duplicate completion is stale, `STARTED` / `OBSOLETE` / `CANCEL_REQUESTED` labels, scripted races, seeded 400-schedule property harness.

**Still later:** A 10k-schedule soak if judges want volume, not more fencing rules.

**Exit:** Zero stale admissions after the barrier. `uv run pytest` includes `test_races.py`.

### Phase 6 — Interruption and recovery UX (landed this pass)

**In:** Immediate acks, reuse table, false-interruption recover under a new epoch, empty-turn “I stopped. Please repeat the change.”, STT echo ignore, no backchannel re-say, one utterance at a time, safer Rime HTTP PCM (format + reject JSON/WAV-as-PCM), VAD slightly less hair-trigger.

**Still later:** A live recording of the full v1 → v2 → v3 judged conversation (phase 8).

**Exit:** Parking-then-tolls still holds. Rime must not play loud garbage. Delayed v2 never enters v3 speech.

### Phase 7 — Observability UI (partial)

**Already in:** VAD/agent state, transcripts, version / epoch / gate, version rail, fence race, provider badges, map HUD, accepted pin only.

**Still to implement:**
- Explicit status words: `BARRIER_CLOSED`, `OBSOLETE`, `CANCEL_REQUESTED`.
- On-screen counters: ack latency, stale admissions = 0, recovery success.
- Acoustic stop latency (that is phase 8 data, not a label we should invent).

**Exit:** A judge can see stale reject without opening JSONL.

### Phase 8 — Evaluation and acoustic measurement (not started)

**Will implement:**
- Server timings with monotonic clocks (VAD → interrupt, turn → ack TTS, tool → fence).
- Two-channel recordings (user vs Rime) and a committed analysis script.
- Quiet + car-noise trials (warm-ups + ≥30 measured), median / p90 / p95, failed trials kept.
- Pre-registered targets only, never claimed until measured (quiet stop p95 ≤ 350 ms, and the rest from the plan).

**Exit:** Every demo number comes from raw artifacts. Acoustic vs server-proxy numbers stay separate.

### Phase 9 — Hardening, deployment, submission (not started)

**Will implement:**
- STT stream reset that keeps mission state and asks the driver to repeat.
- Rime failure that never relabels another TTS as Rime.
- Spoken route / parking-unknown failures in the official wording.
- Reviewer runbook, access instructions, secret scrub, optional demo token gate.
- Submission pack: claim, limitations, evidence, demo script, this scenario book.

**Exit:** A clean reviewer can clone, set env, start three processes, and reproduce the judged path.

---

---

## Extra fixture cases (run these next)

Reset between groups: **End drive**, or cancel and start a fresh coffee when the setup says so. Tap to talk: finish the sentence, then Send. These lines are what the parser and `fixture_plan` do today, not guesses.

### After Chai Point (scenario 1 accepted)

| Say | Version | Search | Rime |
|---|---|---|---|
| “The first one.” | same | none | Re-describes Chai Point. Asks if you want to keep it. |
| “The second one.” / “Go with Third Wave.” | same | none | **Third Wave Coffee** in DLF Phase 2, about five minutes. No parking sentence (parking chip is off). |
| “The third one.” | same | none | “I do not have that option yet. Ask me to search first.” (only first + first alt are a guaranteed select; third is index 3.) |
| “The second one.” after fuel (only Indian Oil) | same | **yes** | Missing index 2 is treated as skip: “Looking for another.” Then **no match** (only one fuel shop). |
| “Another one.” | same | yes | Rejects Chai Point **and** the shown alts (all four coffees). **No match.** Use “the second one” for Third Wave. |
| “Keep this one.” | same | none | “Okay, keeping that one.” |
| “Yeah.” | same | none | Backchannel. Quiet. Epoch only. |
| “Where is it?” | same | none | “Chai Point is in NH 48 lay-by.” |
| “Are they open?” | same | none | “I do not have hours for Chai Point.” |
| “Compare them.” | same | none | “Chai Point versus Third Wave Coffee. Chai Point is about three extra minutes, Third Wave Coffee about five.” |
| “Avoid toll roads too.” | +1 | yes | Still **Chai Point** (script slot 0). Adds “I requested a toll-avoiding route.” |
| “Closer.” | +1 | yes | Detour cap **5**. Chai Point stays (3). Alt is only Third Wave (5). Blue Tokai / Starbucks drop. |
| “Find chai.” / “Sign a coffee shop near my route.” | create-or-same coffee | yes if new | Coffee, not a brand named chai. Chai Point. |
| “Parking chahiye.” / “Yeh wala.” / “Koi aur.” | +1 / same / same | none / none / yes | Hindi: add parking (hold + no-lot line) / confirm / next. |

### Parking without jumping to Blue Tokai

| Say | Expect |
|---|---|
| “Find coffee with parking.” from a **cold** start | Version **1**, searches immediately (no 8s). **Blue Tokai**, alt Starbucks. “This place reports a parking lot.” |
| “Find coffee with parking.” after Chai Point | Same as “I need parking too”: **hold**, chip on, “Chai Point does not have a parking lot.” No Blue Tokai. |
| “Don't need parking.” after the chip is on | “Okay — parking is optional.” **Replans.** Chai Point again. |
| “Parking is optional.” | Same as don't-need. |
| After hold, “Another one.” | Version stays **2**, **~8s**, then **Blue Tokai** (lot-tagged alts stay in play; Chai Point / Third Wave are skipped). |
| Then “Another one.” again | Skips Blue Tokai + Starbucks → **no match.** |

### Category switches and prefs

| Say | Expect |
|---|---|
| “Need a petrol pump.” / “I need gas.” | Fuel. **Indian Oil**, about four minutes. No leftover brand (pump/gas are not a shop name). |
| “Find a medical store.” | **Apollo Pharmacy**, about eight minutes. |
| “Actually, I need fuel.” after coffee | “Switching to fuel.” Pin clears. Indian Oil. |
| “Take me to a pharmacy.” | Category replace, **not** a destination. Apollo. |
| Cancel, then “Find a coffee shop.” after you had required parking | Pref reapplies. **Blue Tokai**, plus “I'll keep requiring parking.” |

### Brand, cap, and empty

| Say | Expect |
|---|---|
| “Find coffee called Blue Tokai.” / “Find coffee Blue Tokai.” | **Blue Tokai** only. Chai Point is filtered out. |
| “Find coffee called Starbucks.” | **Starbucks** only. |
| “Find coffee with parking within 3 minutes.” | Empty. Honest no-match sentence. |
| “Find coffee within 3 minutes.” (no parking) | **Chai Point** only (3). No Third Wave. |
| “That's too far.” after a 5-minute cap | Cap becomes **3**. If Chai Point is in play and already 3, it can stay after replan. |

### Traps (do not file as STT bugs)

- Acks keep at most **three** clauses. “Find coffee near Cyber Hub with parking within 5 minutes” will speak coffee + landmark + parking and **drop** the detour clause even though the cap is stored.
- Fixture **landmark / origin / destination** change the mission text, not the baked HUD or the judged shop order.
- “The second one” with **no** alternative starts a new search. “The third one” does not.
- Greeting is uninterruptible. An STT echo of the last Rime line is ignored.

Do not start phase 8 numbers or phase 9 packaging until you want that next. The book plus the extra cases above are what is running on http://localhost:3000.

from __future__ import annotations

import re

from .models import InquireKind, MissionConstraints, PlaceCandidate, RouteSnapshot, SessionPrefs

GREETING = "I'm with you on the Gurgaon to Delhi drive. What do you need along the way?"
ECHO_HOLDOFF_S = 0.40

_TTS_JUNK = re.compile(r"[#*`>_\[\]{}|]+")
_MULTI_SPACE = re.compile(r"\s+")
_ECHO_KEEP = re.compile(r"[^a-z0-9 ]+")

_SMALL = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
    20: "twenty",
    25: "twenty five",
    30: "thirty",
}


def spoken_number(value: int) -> str:
    return _SMALL.get(value, str(value))


def sanitize_tts_text(text: str) -> str:
    """Keep Rime on spoken words. Empty/junk must never become a PCM request."""
    cleaned = _TTS_JUNK.sub(" ", text or "")
    cleaned = cleaned.replace("http://", " ").replace("https://", " ")
    cleaned = _MULTI_SPACE.sub(" ", cleaned).strip()
    if not re.search(r"[A-Za-z]", cleaned):
        return ""
    if len(cleaned) > 420:
        cleaned = cleaned[:420].rsplit(" ", 1)[0].strip()
    return cleaned


def looks_like_echo(heard: str, spoken: str | None) -> bool:
    if not spoken or not heard:
        return False
    a = _ECHO_KEEP.sub(" ", heard.lower())
    b = _ECHO_KEEP.sub(" ", spoken.lower())
    a = _MULTI_SPACE.sub(" ", a).strip()
    b = _MULTI_SPACE.sub(" ", b).strip()
    if len(a) < 8:
        return False
    if a == b:
        return True
    # Driver repeating the start of the last Rime line (greeting freeze).
    if b.startswith(a) and len(a) >= 12:
        return True
    if a.startswith(b) and len(b) >= 12:
        return True
    # Long overlap only. Short confirms ("Keep this one") sit inside Rime questions.
    if len(a) >= 24 and a in b:
        return True
    if len(b) >= 24 and b in a:
        return True
    return False


def format_none() -> str:
    return "I could not find a matching place with those constraints along this corridor."


def format_candidate(
    constraints: MissionConstraints,
    candidate: PlaceCandidate,
    alternatives: list[PlaceCandidate] | None = None,
) -> str:
    bits = [f"{candidate.name} in {candidate.area} is on the way."]
    if candidate.verified and candidate.detour_minutes:
        bits.append(f"The extra time is about {spoken_number(candidate.detour_minutes)} minutes.")
    elif candidate.reasons:
        bits.append(candidate.reasons[0].rstrip(".") + ".")
    if constraints.parking_required:
        if candidate.parking == "yes":
            bits.append("This place reports a parking lot.")
        elif candidate.parking == "no":
            bits.append("This place is tagged as having no parking lot.")
        else:
            bits.append("I do not have a parking tag for this place.")
    if constraints.avoid_tolls:
        bits.append("I requested a toll-avoiding route.")
    if candidate.opening_hours:
        bits.append(f"OpenStreetMap lists hours as {candidate.opening_hours}.")
    if candidate.provenance in {"overpass", "osm"}:
        bits.append("That is from OpenStreetMap, not live occupancy.")
    alts = alternatives or []
    if alts:
        other = alts[0]
        if constraints.parking_required and other.parking == "yes":
            bits.append(f"I also have {other.name}, and that one reports a lot too.")
        elif constraints.parking_required and other.parking == "no":
            bits.append(f"I also have {other.name}, but that one does not report a lot.")
        else:
            bits.append(f"I also have {other.name}.")
    bits.append("Should I keep this one?")
    return " ".join(bits)


def format_ack(
    patch_ops: list[str],
    constraints: MissionConstraints,
    applied_pref: bool = False,
) -> str:
    parts = [item for item in patch_ops if item]
    if applied_pref and constraints.parking_required:
        parts.append("I'll keep requiring parking.")
    if not parts:
        parts.append("Still on it.")
    return " ".join(parts[:3])


def format_inquire(
    kind: InquireKind,
    constraints: MissionConstraints | None,
    selected: PlaceCandidate | None,
    alternatives: list[PlaceCandidate],
    route: RouteSnapshot | None,
) -> str:
    if selected is None and kind != "compare":
        return "I do not have a place in play yet."
    if kind == "why" and selected:
        if selected.reasons:
            return f"I picked {selected.name} because {selected.reasons[0]}."
        return f"{selected.name} was the best match I could verify on this corridor."
    if kind == "eta" and selected:
        if selected.verified and selected.detour_minutes:
            return f"The extra time for {selected.name} is about {spoken_number(selected.detour_minutes)} minutes."
        return "I do not have a verified extra time for this stop yet."
    if kind == "parking" and selected:
        if selected.parking == "yes":
            line = f"{selected.name} reports a parking lot. That is not live occupancy."
        elif selected.parking == "no":
            line = f"{selected.name} is tagged as having no parking lot."
        else:
            line = f"I do not have a parking tag for {selected.name}."
        if alternatives:
            other = alternatives[0]
            if other.parking == "yes":
                line += f" {other.name} reports a lot as well."
            elif other.parking == "no":
                line += f" {other.name} is tagged as having no lot."
        return line
    if kind == "hours" and selected:
        if selected.opening_hours:
            return f"OpenStreetMap lists hours as {selected.opening_hours}."
        return f"I do not have hours for {selected.name}."
    if kind == "where" and selected:
        return f"{selected.name} is in {selected.area}."
    if kind == "other":
        if alternatives:
            other = alternatives[0]
            extra = ""
            if other.verified and other.detour_minutes:
                extra = f" About {spoken_number(other.detour_minutes)} extra minutes."
            return f"The next option is {other.name} in {other.area}.{extra}"
        return "I do not have another accepted option. Say another one and I will search again."
    if kind == "compare":
        bits: list[str] = []
        if selected and alternatives:
            left = selected
            right = alternatives[0]
            bits.append(f"{left.name} versus {right.name}.")
            if left.detour_minutes is not None and right.detour_minutes is not None and left.verified and right.verified:
                bits.append(
                    f"{left.name} is about {spoken_number(left.detour_minutes)} extra minutes, "
                    f"{right.name} about {spoken_number(right.detour_minutes)}."
                )
        if route and route.avoid_tolls and route.toll_compare_minutes:
            bits.append(
                f"Avoiding tolls adds about {spoken_number(route.toll_compare_minutes)} minutes to the whole drive."
            )
        if constraints and constraints.avoid_tolls and not (route and route.toll_compare_minutes):
            bits.append("I requested a toll-avoiding route. I do not have a measured comparison yet.")
        return " ".join(bits) if bits else "I do not have two accepted options to compare."
    return "I am not sure which detail you want."


def ack_clauses(patch, constraints: MissionConstraints) -> list[str]:
    parts: list[str] = []
    if patch.operation == "create":
        parts.append(f"Looking for {constraints.category} on the way.")
    elif patch.operation == "replace" and patch.category:
        parts.append(f"Switching to {constraints.category}.")
    if patch.origin_query:
        parts.append(f"Starting from {patch.origin_query}.")
    if patch.destination_query:
        parts.append(f"Heading toward {patch.destination_query}.")
    if patch.landmark_query:
        parts.append(f"Preferring places near {patch.landmark_query}.")
    if patch.brand_query:
        parts.append(f"I'll look for {patch.brand_query}.")
    if patch.prefer_along == "start":
        parts.append("I'll stay nearer the start.")
    elif patch.prefer_along == "end":
        parts.append("I'll stay nearer the destination.")
    if patch.parking_required is True:
        parts.append("Got it — parking required.")
    elif patch.parking_required is False:
        parts.append("Okay — parking is optional.")
    if patch.avoid_tolls is True:
        parts.append("Okay — requesting a toll-avoiding route.")
    elif patch.avoid_tolls is False:
        parts.append("Okay — tolls are allowed.")
    if patch.maximum_detour_minutes is not None:
        parts.append(f"Keeping the detour under {spoken_number(constraints.maximum_detour_minutes or 0)} minutes.")
    return parts


def format_prefs_note(prefs: SessionPrefs) -> str:
    bits: list[str] = []
    if prefs.parking_required is True:
        bits.append("parking")
    if prefs.avoid_tolls is True:
        bits.append("toll-avoiding")
    return ", ".join(bits)

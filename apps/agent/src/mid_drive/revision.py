from __future__ import annotations

import re

from .models import MissionConstraints, MissionPatch

_CANCEL_ALONE = re.compile(r"^(stop|cancel|forget it|never mind|nvm)\.?$", re.I)
_CANCEL_MISSION = re.compile(
    r"\b(cancel (the )?(search|mission|that)|stop (searching|looking)|forget (the )?(search|mission))\b",
    re.I,
)
_PARKING_ON = re.compile(
    r"\b((it )?needs parking|parking required|with parking|has to have parking|"
    r"need(?:s)? parking|need(?:s)? a (parking )?lot|want parking|must have parking|"
    r"parking chahiye|parking too|parking as well|also (need )?parking|"
    r"and parking|also a lot|require[sd]? parking)\b",
    re.I,
)
_PARKING_OFF = re.compile(
    r"\b(no parking|without parking|parking not required|don't need parking|dont need parking|"
    r"don'?t want parking|do not want parking|"
    r"drop (the )?parking|parking is optional|don't need a lot)\b",
    re.I,
)
_TOLLS_OFF = re.compile(
    r"\b(avoid (the )?tolls?|no tolls?|without (?:a |any )?tolls?|toll[- ]roads? too|"
    r"toll[- ]free|non[- ]toll)\b",
    re.I,
)
_TOLLS_ON = re.compile(
    r"\b(allow tolls?|tolls? (are )?(ok|okay|fine)|tolls? again|stop avoiding tolls?)\b",
    re.I,
)
_DETOUR = re.compile(r"\b(?:(?:max(?:imum)?|under|within)\s+)?(\d{1,2})\s*(?:min|mins|minutes)\b", re.I)
_DETOUR_WORD = re.compile(
    r"\b(?:(?:max(?:imum)?|under|within)\s+)?(one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:min|mins|minutes)\b",
    re.I,
)
_WORD_MINUTES = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_CLOSER = re.compile(r"\b(too far|shorter detour|less of a detour)\b", re.I)
_CLOSER_BARE = re.compile(r"\b(closer|nearer)\b", re.I)
_COFFEE = re.compile(r"\b(coffee|caf[eé]|barista|espresso|chai|caffeine|latte|cappuccino)\b", re.I)
_THIRSTY = re.compile(r"\b(i(?:'m| am) thirsty|need (?:a )?(?:drink|caffeine)|need caffeine)\b", re.I)
_FUEL = re.compile(
    r"\b(fuel|gas station|petrol pump|petrol station|filling station|petrol|diesel|gas)\b",
    re.I,
)
_LOW_FUEL = re.compile(r"\b(low on (?:gas|fuel|petrol)|tank is low|running (?:on )?empty)\b", re.I)
_PHARMACY = re.compile(r"\b(pharmacy|chemist|drugstore|medicine|medical store)\b", re.I)
_HUNGRY = re.compile(r"\b(i(?:'m| am) hungry|need food|something to eat)\b", re.I)
_BACKCHANNEL = re.compile(r"^(uh-?huh|mm-?hm+|yeah|yep|yup|ok(?:ay)?|right|sure|acha|accha)\.?$", re.I)
_FIND = re.compile(
    r"\b(find|look for|search|need|want|get|stop for|pull over(?: for)?|sign a|grab)\b",
    re.I,
)
_CONFIRM = re.compile(
    r"\b(keep (this|that|it)|that (one )?works|sounds good|we('ll| will) take (it|this|that)|"
    r"take that one|go with (this|that)|yes,? keep|first one is fine|we'll take this|"
    r"yeh wala|this one works|this is fine|that'?s fine|works for me|that'?s perfect)\b",
    re.I,
)
_NEXT = re.compile(
    r"\b(another one|another option|not that|somewhere else|next one|different (one|place)|"
    r"skip (this|that|it)|try another|koi aur|"
    r"don'?t want (that|this)(?: one)?|not this one)\b",
    re.I,
)
_ALONG_ROUTE = re.compile(
    r"\b(near (my |the )?route|along (my |the )?route|on the way|along the way)\b",
    re.I,
)
_DEST = re.compile(
    r"\b(?:change destination to|destination (?:is|to)|head to|take me to|reroute to|new destination)\s+(.+)$",
    re.I,
)
_ORIGIN = re.compile(r"\b(?:start(?:ing)? (?:from|at)|leave from)\s+(.+)$", re.I)
_LANDMARK = re.compile(r"\b(?:near|towards|toward|after|before|around)\s+(.+)$", re.I)
_GENERIC_PLACE = re.compile(
    r"^(me|us|my|mine|here|there|it|the route|my route|route|the way|my way|"
    r"the start|the end|the destination)$",
    re.I,
)
_PREFER_START = re.compile(
    r"\b(near(?:er)? the (start|beginning|origin)|closer to (the )?(start|beginning|origin)|near the start)\b",
    re.I,
)
_PREFER_END = re.compile(
    r"\b(near(?:er)? the (end|destination|finish)|closer to (the )?(end|destination|finish)|near the destination)\b",
    re.I,
)
_SELECT_ORDINAL = re.compile(
    r"\b(?:the )?(first|1st|pehla|pehli|second|2nd|doosra|doosri|third|3rd|teesra|"
    r"other one|option\s*([123])|number\s*([123]))\b",
    re.I,
)
_SELECT_NAME = re.compile(
    r"\b(?:go with|pick|choose)\s+(?!this|that|it)(.+)$",
    re.I,
)
_CALLED = re.compile(r"\b(?:called|named)\s+(.+)$", re.I)
_INQUIRE_WHY = re.compile(
    r"\b(why (this|that)|why did you pick|why this one|why pick|"
    r"which one did you (pick|choose)|tell me about (it|this|that))\b",
    re.I,
)
_INQUIRE_ETA = re.compile(
    r"\b(how (much )?(extra |more )?time|how long (a )?detour|extra minutes|"
    r"how far(?: is it| out of the way)?)\b",
    re.I,
)
_INQUIRE_PARK = re.compile(
    r"\b(does (?:it|[a-z0-9 .'-]{1,32}) have parking|any parking|parking there|"
    r"have parking|is there parking|what about parking|any lot)\b",
    re.I,
)
_INQUIRE_HELP = re.compile(
    r"\b(what can you do|how does this work|what do you (do|support))\b",
    re.I,
)
_INQUIRE_STATUS = re.compile(
    r"\b(where are we|what'?s (our |the )?status|how'?s the drive|mission status)\b",
    re.I,
)
_INQUIRE_WAIT = re.compile(
    r"\b(what'?s taking|taking so long|still looking|still searching|any update|"
    r"you still (looking|searching))\b",
    re.I,
)
_INQUIRE_OTHER = re.compile(r"\b(what('s| is) the other|other option|what else)\b", re.I)
_INQUIRE_COMPARE = re.compile(r"\b(compare|versus|vs\.?|difference)\b", re.I)
_INQUIRE_HOURS = re.compile(r"\b(hours|open|closing)\b", re.I)
_INQUIRE_WHERE = re.compile(
    r"\b(where(?:'s| is) (it|that)|which area|"
    r"where(?:'s| is) (?:the )?(?:coffee|shop|place|stop|one))\b",
    re.I,
)
_INQUIRE_FOUND = re.compile(
    r"\b(what did you find|what have you found|what did you get|did you find (one|it|anything))\b",
    re.I,
)
_FILLER = re.compile(
    r"\b(um+|uh+|ah+|like|please|yaar|ya+|hmm+|can you|could you|will you|just)\b",
    re.I,
)
_STOP = {
    "find",
    "look",
    "for",
    "search",
    "need",
    "want",
    "get",
    "stop",
    "pull",
    "over",
    "a",
    "an",
    "the",
    "me",
    "us",
    "i",
    "we",
    "shop",
    "store",
    "place",
    "please",
    "near",
    "my",
    "route",
    "along",
    "on",
    "way",
    "with",
    "parking",
    "toll",
    "tolls",
    "avoid",
    "minutes",
    "min",
    "coffee",
    "cafe",
    "café",
    "chai",
    "fuel",
    "gas",
    "petrol",
    "pump",
    "station",
    "filling",
    "diesel",
    "pharmacy",
    "chemist",
    "medical",
    "drugstore",
    "barista",
    "espresso",
    "called",
    "named",
    "and",
    "too",
    "also",
    "it",
    "needs",
    "wait",
    "sign",
    "is",
    "there",
    "does",
    "have",
    "yes",
    "keep",
    "actually",
    "roads",
    "road",
    "required",
    "optional",
    "allow",
    "again",
    "under",
    "within",
    "max",
    "maximum",
    "something",
    "one",
    "maybe",
    "dont",
    "don't",
    "drop",
    "lot",
    "nearest",
    "nearer",
    "closest",
    "quick",
    "nearby",
    "good",
    "best",
    "cheap",
    "some",
    "any",
    "drink",
    "drinks",
    "help",
    "please",
    "perfect",
    "caffeine",
    "latte",
    "cappuccino",
    "thirsty",
    "hungry",
    "food",
    "tank",
    "empty",
    "grab",
}


def _categories(text: str) -> list[str]:
    found: list[str] = []
    if _COFFEE.search(text) or _THIRSTY.search(text):
        found.append("coffee")
    if _FUEL.search(text) or _LOW_FUEL.search(text):
        found.append("fuel")
    if _PHARMACY.search(text):
        found.append("pharmacy")
    return found


def _clip_place(raw: str) -> str:
    clipped = re.split(r"[.!?]", raw, maxsplit=1)[0]
    clipped = re.split(r"\b(?:with|that|and|but)\b", clipped, maxsplit=1)[0]
    return clipped.strip().rstrip(".,")


def _clean(text: str) -> str:
    stripped = _FILLER.sub(" ", text)
    return " ".join(stripped.split())


def _ordinal(match: re.Match[str]) -> int:
    token = (match.group(1) or match.group(2) or match.group(3) or "").lower()
    if token in {"first", "1st", "pehla", "pehli", "1"}:
        return 1
    if token in {"second", "2nd", "doosra", "doosri", "other one", "2"}:
        return 2
    if token in {"third", "3rd", "teesra", "3"}:
        return 3
    if token.startswith("option"):
        return int(match.group(2) or 1)
    if token.startswith("number"):
        return int(match.group(3) or 1)
    return 1


def _leftover_brand(text: str) -> str | None:
    words = [word for word in re.findall(r"[A-Za-z][\w']*", text) if word.lower() not in _STOP]
    if 1 <= len(words) <= 4:
        joined = " ".join(words).strip()
        if joined and not _GENERIC_PLACE.match(joined):
            return joined
    return None


def parse_turn(text: str, current: MissionConstraints | None) -> MissionPatch:
    """Deterministic revision parser. None-fields mean 'not mentioned'."""
    raw = " ".join(text.strip().split())
    if not raw:
        return MissionPatch(operation="unrelated")
    # Filler strip removes "can you" / "could you". Match help on the raw line.
    if _INQUIRE_HELP.search(raw):
        return MissionPatch(operation="inquire", inquire_kind="help")
    if _INQUIRE_STATUS.search(raw):
        return MissionPatch(operation="inquire", inquire_kind="status")
    cleaned = _clean(raw)
    if not cleaned:
        return MissionPatch(operation="unrelated")
    if _BACKCHANNEL.match(cleaned):
        return MissionPatch(operation="unrelated")
    if _CANCEL_ALONE.match(cleaned) or _CANCEL_MISSION.search(cleaned):
        return MissionPatch(operation="cancel")
    if current is not None and _CONFIRM.search(cleaned):
        return MissionPatch(operation="confirm")
    if current is not None and _NEXT.search(cleaned):
        return MissionPatch(operation="next")

    parking: bool | None = None
    if _PARKING_OFF.search(cleaned):
        parking = False
    elif _PARKING_ON.search(cleaned):
        parking = True

    if current is not None:
        if _INQUIRE_WAIT.search(raw) or _INQUIRE_WAIT.search(cleaned):
            return MissionPatch(operation="inquire", inquire_kind="status")
        if _INQUIRE_WHY.search(cleaned):
            return MissionPatch(operation="inquire", inquire_kind="why")
        if _INQUIRE_ETA.search(cleaned):
            return MissionPatch(operation="inquire", inquire_kind="eta")
        if _INQUIRE_PARK.search(cleaned) and parking is None:
            return MissionPatch(operation="inquire", inquire_kind="parking")
        if _INQUIRE_OTHER.search(cleaned):
            return MissionPatch(operation="inquire", inquire_kind="other")
        if _INQUIRE_COMPARE.search(cleaned):
            return MissionPatch(operation="inquire", inquire_kind="compare")
        if _INQUIRE_HOURS.search(cleaned) and not _FIND.search(cleaned):
            return MissionPatch(operation="inquire", inquire_kind="hours")
        if _INQUIRE_WHERE.search(cleaned):
            return MissionPatch(operation="inquire", inquire_kind="where")
        if _INQUIRE_FOUND.search(cleaned):
            return MissionPatch(operation="inquire", inquire_kind="why")
        ordinal = _SELECT_ORDINAL.search(cleaned)
        if ordinal and not _FIND.search(cleaned):
            return MissionPatch(operation="select", select_index=_ordinal(ordinal))
        named = _SELECT_NAME.search(cleaned)
        if named:
            return MissionPatch(operation="select", select_name=_clip_place(named.group(1)))

    cats = _categories(cleaned)
    if len(cats) > 1:
        return MissionPatch(
            operation="ambiguous",
            clarification_question="Coffee, fuel, or a pharmacy — which one?",
        )
    category = cats[0] if cats else None

    avoid_tolls: bool | None = None
    if _TOLLS_ON.search(cleaned):
        avoid_tolls = False
    elif _TOLLS_OFF.search(cleaned):
        avoid_tolls = True

    destination = None
    origin = None
    landmark = None
    dest_match = _DEST.search(cleaned)
    if dest_match:
        dest_raw = _clip_place(dest_match.group(1))
        if dest_raw and not _GENERIC_PLACE.match(dest_raw) and not _categories(dest_raw):
            destination = dest_raw
    origin_match = _ORIGIN.search(cleaned)
    if origin_match:
        origin_raw = _clip_place(origin_match.group(1))
        if origin_raw and not _GENERIC_PLACE.match(origin_raw) and not _categories(origin_raw):
            origin = origin_raw
    landmark_match = _LANDMARK.search(cleaned)
    if landmark_match and not _ALONG_ROUTE.search(cleaned) and not _PREFER_START.search(cleaned) and not _PREFER_END.search(cleaned):
        raw = _clip_place(landmark_match.group(1))
        if raw and not _GENERIC_PLACE.match(raw) and raw != destination and raw != origin:
            landmark = raw

    prefer_along = None
    if _PREFER_START.search(cleaned):
        prefer_along = "start"
    elif _PREFER_END.search(cleaned):
        prefer_along = "end"

    detour = None
    if _CLOSER.search(cleaned) or (_CLOSER_BARE.search(cleaned) and prefer_along is None and landmark is None):
        if current and current.maximum_detour_minutes is not None:
            detour = max(3, current.maximum_detour_minutes - 2)
        else:
            detour = 5
    else:
        detour_match = _DETOUR.search(cleaned)
        if detour_match:
            detour = int(detour_match.group(1))
        else:
            word_match = _DETOUR_WORD.search(cleaned)
            if word_match:
                detour = _WORD_MINUTES.get(word_match.group(1).lower())

    brand = None
    called = _CALLED.search(cleaned)
    if called:
        brand = _clip_place(called.group(1))
    elif _FIND.search(cleaned) and parking is None:
        leftover = _leftover_brand(cleaned)
        if leftover and leftover.lower() not in {category or "", (current.category if current else "")}:
            if leftover != landmark:
                brand = leftover

    mentioned = any(
        value is not None
        for value in (
            category,
            parking,
            avoid_tolls,
            detour,
            landmark,
            destination,
            origin,
            brand,
            prefer_along,
        )
    )
    if not mentioned:
        if _HUNGRY.search(cleaned) or _FIND.search(cleaned):
            return MissionPatch(
                operation="ambiguous",
                clarification_question="Coffee, fuel, or a pharmacy?",
            )
        return MissionPatch(operation="unrelated")

    fields = dict(
        category=category,
        parking_required=parking,
        avoid_tolls=avoid_tolls,
        maximum_detour_minutes=detour,
        landmark_query=landmark,
        destination_query=destination,
        origin_query=origin,
        brand_query=brand,
        prefer_along=prefer_along,
    )

    if current is None:
        if category is None:
            return MissionPatch(
                operation="ambiguous",
                clarification_question="Coffee, fuel, or a pharmacy?",
                **{key: value for key, value in fields.items() if key != "category"},
            )
        return MissionPatch(operation="create", **fields)

    if category and category != current.category:
        return MissionPatch(operation="replace", **fields)

    if category == current.category:
        fields["category"] = None
    return MissionPatch(operation="add", **fields)

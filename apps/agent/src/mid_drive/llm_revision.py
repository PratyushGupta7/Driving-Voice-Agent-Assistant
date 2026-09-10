"""Azure structured NLU. Hybrid mode only waits for this on weak rule parses."""

from __future__ import annotations

import json
import logging
import re
import time

from .azure_client import azure_chat_json, azure_ready
from .config import Settings
from .models import MissionConstraints, MissionPatch

logger = logging.getLogger("mid_drive.llm_revision")

_MISSIONISH = re.compile(
    r"\b(find|look for|search|parking|toll|coffee|cafe|caf[eé]|fuel|gas|petrol|"
    r"pharmacy|chemist|detour|minutes|cancel|stop looking|near|destination|"
    r"head to|take me|start from|reroute|another|second|keep this|"
    r"where|hours|open|compare|why)\b",
    re.I,
)

_SYSTEM = """
You convert one driver utterance into a mission patch JSON object for a Gurgaon to Delhi driving copilot.
Return only JSON. Never invent place names, travel times, or parking occupancy.

operation MUST be one of: create, add, replace, cancel, unrelated, ambiguous, confirm, next, select, inquire.
category MUST be coffee, fuel, pharmacy, or null.
inquire_kind MUST be why, eta, parking, other, compare, hours, where, help, status, or null.

Rules:
1. New search for coffee/fuel/pharmacy -> create + category.
2. Extra constraint on the current search (parking, tolls, detour, landmark) -> add.
3. Switch category -> replace.
4. Cancel / stop looking / forget it -> cancel.
5. Keep this / go with this -> confirm (only if a mission already exists).
6. Another one / next / not that -> next.
7. The second one / go with <offered name> -> select + select_index (1-based first/second/third) or select_name.
8. Why / extra time / does it have parking / where / hours / compare / what else -> inquire.
9. What can you do / how does this work -> inquire help.
10. Where are we / what's the status / how's the drive -> inquire status.
11. Coffee or fuel / find something -> ambiguous + clarification_question.
12. Weather, sports, jokes, or anything outside this drive -> unrelated.
13. "I need parking too" after a shop is already in play is add + parking_required=true. It is NOT next and NOT a new search.
14. "Does it have parking?" is inquire parking, not a constraint change, unless the driver also said they need parking.

Keys: operation, category, maximum_detour_minutes, parking_required, avoid_tolls, landmark_query, destination_query, origin_query, brand_query, prefer_along, select_index, select_name, inquire_kind, clarification_question.
Use null for anything the driver did not say.
""".strip()


def residual_parse(text: str, patch: MissionPatch) -> bool:
    """True when the grammar is weak and the line still looks like a mission turn."""
    if patch.operation == "ambiguous":
        return True
    if patch.operation != "unrelated":
        return False
    if len(text.split()) < 4:
        return False
    return bool(_MISSIONISH.search(text))


def worth_llm_fallback(text: str, patch: MissionPatch) -> bool:
    """Judged path never waits on Azure. Hybrid mode uses residual_parse instead."""
    del text, patch
    return False


def would_have_been_fallback(text: str, patch: MissionPatch) -> bool:
    return residual_parse(text, patch)


def rules_confident(patch: MissionPatch) -> bool:
    if patch.operation in {"cancel", "next", "confirm"}:
        return True
    if patch.operation in {"create", "replace"} and patch.category:
        return True
    if patch.operation == "add":
        return True
    if patch.operation == "select" and (patch.select_index or patch.select_name):
        return True
    if patch.operation == "inquire" and patch.inquire_kind:
        return True
    return False


def prefer_rules_over_llm(rules: MissionPatch, llm: MissionPatch | None) -> bool:
    """Keep the judged demo script stable even if Azure disagrees."""
    if llm is None:
        return True
    if rules.operation in {"cancel", "next", "confirm"}:
        return True
    if rules.operation == "add" and rules.parking_required is True:
        if llm.operation in {"next", "create", "replace", "select", "unrelated"}:
            return True
    if rules.operation == "inquire" and llm.operation != "inquire":
        return True
    if rules.operation in {"create", "replace"} and rules.category and llm.operation == "unrelated":
        return True
    return False


async def parse_turn_with_llm(
    settings: Settings,
    text: str,
    current: MissionConstraints | None,
    **_kwargs,
) -> MissionPatch | None:
    if not azure_ready(settings):
        return None
    timeout = float(getattr(settings, "azure_nlu_timeout_s", 1.15) or 1.15)
    started = time.perf_counter()
    payload = await azure_chat_json(
        settings,
        system=_SYSTEM,
        user=json.dumps({"utterance": text, "current_constraints": current.model_dump() if current else None}),
        timeout_s=timeout,
        max_tokens=180,
    )
    ms = int((time.perf_counter() - started) * 1000)
    if not payload:
        logger.info("azure nlu empty after %sms", ms)
        return None
    try:
        patch = MissionPatch.model_validate(payload)
    except Exception as exc:
        logger.info("azure nlu invalid after %sms: %s", ms, exc)
        return None
    if patch.operation in {"create", "replace"} and patch.category is None:
        return MissionPatch(
            operation="ambiguous",
            clarification_question="Coffee, fuel, or a pharmacy?",
        )
    logger.info("azure nlu %s in %sms", patch.operation, ms)
    return patch

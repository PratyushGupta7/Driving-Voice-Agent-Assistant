from __future__ import annotations

from .models import MissionConstraints, MissionPatch, ReduceResult, SessionPrefs
from .speech import ack_clauses, format_ack


def _merge_optional(current: str | None, incoming: str | None) -> str | None:
    return current if incoming is None else incoming


def reduce_mission(
    current: MissionConstraints | None,
    patch: MissionPatch,
    prefs: SessionPrefs | None = None,
) -> ReduceResult:
    prefs = prefs or SessionPrefs()

    if patch.operation == "unrelated":
        return ReduceResult(changed=False, constraints=current, speak_now=False, replan=False)

    if patch.operation == "select":
        return ReduceResult(
            changed=False,
            constraints=current,
            speak_now=True,
            replan=False,
            select_index=patch.select_index,
            select_name=patch.select_name,
        )

    if patch.operation == "inquire":
        return ReduceResult(
            changed=False,
            constraints=current,
            speak_now=True,
            replan=False,
            inquire_kind=patch.inquire_kind,
        )

    if patch.operation == "confirm":
        return ReduceResult(
            changed=False,
            constraints=current,
            acknowledgement="Okay, keeping that one.",
            speak_now=True,
            replan=False,
        )

    if patch.operation == "next":
        return ReduceResult(
            changed=False,
            constraints=current,
            acknowledgement="Looking for another.",
            speak_now=True,
            replan=True,
        )

    if patch.operation == "ambiguous":
        question = patch.clarification_question or "Coffee, juice, fuel, or a pharmacy?"
        return ReduceResult(
            changed=False,
            constraints=current,
            status="clarifying",
            acknowledgement=question,
            speak_now=True,
        )

    if patch.operation == "cancel":
        return ReduceResult(
            changed=True,
            constraints=current,
            status="cancelled",
            acknowledgement="Okay, I cancelled that.",
            speak_now=True,
            replan=False,
        )

    applied_pref = False
    if patch.operation == "create" or current is None:
        if patch.category is None:
            return ReduceResult(
                changed=False,
                constraints=current,
                status="clarifying",
                acknowledgement="Coffee, juice, fuel, or a pharmacy?",
                speak_now=True,
            )
        parking = patch.parking_required
        if parking is None and prefs.parking_required is True:
            parking = True
            applied_pref = True
        # Tolls stay explicit. Silent reapply would change the fixture pick
        # (Starbucks vs Blue Tokai) after a cancelled parking+tolls mission.
        avoid = patch.avoid_tolls
        created = MissionConstraints(
            category=patch.category,
            maximum_detour_minutes=patch.maximum_detour_minutes,
            parking_required=bool(parking),
            avoid_tolls=bool(avoid),
            landmark_query=patch.landmark_query,
            destination_query=patch.destination_query,
            origin_query=patch.origin_query,
            brand_query=patch.brand_query,
            prefer_along=patch.prefer_along,
        )
        return ReduceResult(
            changed=True,
            constraints=created,
            acknowledgement=format_ack(ack_clauses(patch, created), created, applied_pref),
            speak_now=True,
            replan=True,
        )

    merged = current.model_copy(
        update={
            "category": patch.category or current.category,
            "maximum_detour_minutes": (
                current.maximum_detour_minutes
                if patch.maximum_detour_minutes is None
                else patch.maximum_detour_minutes
            ),
            "parking_required": (
                current.parking_required if patch.parking_required is None else patch.parking_required
            ),
            "avoid_tolls": current.avoid_tolls if patch.avoid_tolls is None else patch.avoid_tolls,
            "landmark_query": _merge_optional(current.landmark_query, patch.landmark_query),
            "destination_query": _merge_optional(current.destination_query, patch.destination_query),
            "origin_query": _merge_optional(current.origin_query, patch.origin_query),
            "brand_query": _merge_optional(current.brand_query, patch.brand_query),
            "prefer_along": current.prefer_along if patch.prefer_along is None else patch.prefer_along,
        }
    )
    changed = merged != current
    return ReduceResult(
        changed=changed,
        constraints=merged,
        acknowledgement=format_ack(ack_clauses(patch, merged), merged) if changed else None,
        speak_now=changed,
        replan=changed,
    )

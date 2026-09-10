from types import SimpleNamespace

import pytest

from mid_drive.models import MissionConstraints, MissionPatch, PlaceCandidate
from mid_drive.nlu import nlu_mode, resolve_patch, sanitize_patch
from mid_drive.revision import parse_turn


def _chai() -> PlaceCandidate:
    return PlaceCandidate(
        id="c",
        name="Chai Point",
        area="NH 48",
        category="coffee",
        parking="no",
    )


def test_nlu_mode_is_always_rules() -> None:
    assert nlu_mode(SimpleNamespace(nlu_mode="llm_first")) == "rules"
    assert nlu_mode(SimpleNamespace()) == "rules"


def test_sanitize_does_not_rewrite_intent() -> None:
    patch = MissionPatch(operation="inquire", inquire_kind="parking", parking_required=True)
    cleaned = sanitize_patch(patch, "Does it have parking?")
    assert cleaned.operation == "inquire"
    assert cleaned.inquire_kind == "parking"


def test_sanitize_drops_invented_brand() -> None:
    patch = MissionPatch(operation="add", parking_required=True, brand_query="Starbucks")
    cleaned = sanitize_patch(patch, "Wait, I need parking too.", offered=[_chai()])
    assert cleaned.operation == "add"
    assert cleaned.parking_required is True
    assert cleaned.brand_query is None


def test_sanitize_keeps_spoken_brand() -> None:
    patch = MissionPatch(operation="create", category="coffee", brand_query="Blue Tokai Coffee")
    cleaned = sanitize_patch(patch, "Find Blue Tokai on the way.")
    assert cleaned.brand_query == "Blue Tokai Coffee"


def test_sanitize_keeps_offered_select_name() -> None:
    patch = MissionPatch(operation="select", select_index=2, select_name="Third Wave Coffee")
    cleaned = sanitize_patch(
        patch,
        "The second one.",
        offered=[
            _chai(),
            PlaceCandidate(
                id="t",
                name="Third Wave Coffee",
                area="DLF Phase 2",
                category="coffee",
                parking="unknown",
            ),
        ],
    )
    assert cleaned.operation == "select"
    assert cleaned.select_index == 2
    assert cleaned.select_name == "Third Wave Coffee"


@pytest.mark.asyncio
async def test_resolve_patch_is_rules_even_if_azure_would_differ(monkeypatch) -> None:
    async def fake_llm(*_args, **_kwargs) -> MissionPatch:
        return MissionPatch(operation="next", parking_required=True)

    monkeypatch.setattr("mid_drive.nlu.parse_turn", lambda text, current: parse_turn(text, current))
    monkeypatch.setattr("mid_drive.llm_revision.parse_turn_with_llm", fake_llm)
    current = MissionConstraints(category="coffee")
    patch, source, latency_ms = await resolve_patch(
        SimpleNamespace(nlu_mode="llm_first"),
        "Wait, I need parking too.",
        current,
        offered=[_chai()],
    )
    assert source == "rules"
    assert patch.operation == "add"
    assert patch.parking_required is True
    assert latency_ms >= 0

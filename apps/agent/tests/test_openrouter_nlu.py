import pytest
import pytest_asyncio
from mid_drive.config import Settings
from mid_drive.models import MissionConstraints
from mid_drive.nlu import resolve_patch, nlu_mode
from mid_drive.llm_revision import parse_turn_with_openrouter

OPENROUTER_KEY = "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"

@pytest.fixture
def openrouter_settings():
    return Settings(
        eleven_api_key="test_key",
        rime_api_key="test_key",
        openrouter_api_key=OPENROUTER_KEY,
        openrouter_model="openai/gpt-4o-mini",
    )

def test_nlu_mode_openrouter(openrouter_settings):
    assert nlu_mode(openrouter_settings) == "openrouter"

@pytest.mark.asyncio
async def test_openrouter_parse_create(openrouter_settings):
    patch = await parse_turn_with_openrouter(
        openrouter_settings,
        "Find a coffee shop near my route",
        current=None,
    )
    assert patch is not None
    assert patch.operation in {"create", "replace"}
    assert patch.category == "coffee"

@pytest.mark.asyncio
async def test_openrouter_resolve_patch_integration(openrouter_settings):
    patch, source = await resolve_patch(
        openrouter_settings,
        "I need parking too",
        current=MissionConstraints(category="coffee"),
    )
    assert source == "openrouter"
    assert patch is not None
    assert patch.parking_required is True

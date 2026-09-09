from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / ".env.example").exists() and (candidate / "apps").is_dir():
            return candidate
    return here.parents[4]


REPO_ROOT = _find_repo_root()
AGENT_ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    """Load repo-root `.env` first, then any agent-local override."""
    load_dotenv(REPO_ROOT / ".env", override=False)
    load_dotenv(AGENT_ROOT / ".env", override=False)
    load_dotenv(AGENT_ROOT / ".env.local", override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    livekit_url: str = "ws://127.0.0.1:7880"
    livekit_api_key: str = "middrive"
    livekit_api_secret: str = "abc75afd7b78117bf2466956612c189cc9b810dbd9d2178c5995b3bcc5203050"
    agent_name: str = "mid-drive"

    eleven_api_key: str
    rime_api_key: str
    rime_model: str = "coda"
    rime_speaker: str = "astra"
    rime_language: str = "eng"
    rime_sample_rate: int = 24000
    rime_endpoint: str = "https://users.rime.ai/v1/rime-tts"
    rime_catalog_url: str = "https://users.rime.ai/data/voices/all-v2.json"

    azure_openai_api_key: str = "dummy_key"
    azure_openai_endpoint: str = "https://dummy.openai.azure.com/"
    azure_openai_deployment: str = "gpt-4.1-mini"
    azure_openai_api_version: str = "2025-01-01-preview"

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"

    geo_mode: str = "fixture"
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    osrm_url: str = "https://router.project-osrm.org"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    route_origin: str = "Cyber Hub, Gurugram"
    route_destination: str = "Connaught Place, New Delhi"
    nominatim_countrycodes: str = "in"
    nominatim_viewbox: str = "76.70,28.95,77.60,28.28"
    artifacts_dir: Path = Field(default=REPO_ROOT / "artifacts")
    database_path: Path = Field(default=REPO_ROOT / "artifacts" / "mid_drive.db")

    @property
    def provider_labels(self) -> dict[str, str]:
        return {
            "stt": "ElevenLabs",
            "stt_model": "scribe_v2_realtime",
            "tts": "Rime",
            "tts_model": self.rime_model,
            "tts_speaker": self.rime_speaker,
            "tts_language": self.rime_language,
            "tts_transport": "http-pcm",
            "tts_sample_rate": str(self.rime_sample_rate),
            "llm": "Azure OpenAI",
            "llm_model": self.azure_openai_deployment,
            "nlu": "rules",
            "geo": self.geo_mode,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_env()
    return Settings()

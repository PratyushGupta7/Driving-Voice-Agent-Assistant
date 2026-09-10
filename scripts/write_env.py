"""Write a local .env from the shell environment. Never print secret values."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing {name}")
    return value


def main() -> None:
    body = f"""# Generated locally. Do not commit.
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_HTTP_URL=http://127.0.0.1:7880
LIVEKIT_API_KEY={os.environ.get("LIVEKIT_API_KEY", "middrive")}
LIVEKIT_API_SECRET={os.environ.get("LIVEKIT_API_SECRET", "abc75afd7b78117bf2466956612c189cc9b810dbd9d2178c5995b3bcc5203050")}
AGENT_NAME=mid-drive

ELEVEN_API_KEY={require("ELEVEN_API_KEY")}

RIME_API_KEY={require("RIME_API_KEY")}
RIME_MODEL=coda
RIME_SPEAKER=astra
RIME_LANGUAGE=eng
RIME_SAMPLE_RATE=24000
RIME_ENDPOINT=https://users.rime.ai/v1/rime-tts

AZURE_OPENAI_API_KEY={require("AZURE_OPENAI_API_KEY")}
AZURE_OPENAI_ENDPOINT={os.environ.get("AZURE_OPENAI_ENDPOINT", "https://dataforgeopenai6377.openai.azure.com/")}
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini
AZURE_OPENAI_API_VERSION=2025-01-01-preview

DEMO_ACCESS_TOKEN=

GEO_MODE=fixture
NOMINATIM_URL=https://nominatim.openstreetmap.org
OSRM_URL=https://router.project-osrm.org
OVERPASS_URL=https://overpass-api.de/api/interpreter

DATABASE_URL=sqlite+aiosqlite:///./artifacts/mid_drive.db
"""
    (ROOT / ".env").write_text(body)
    web_env = f"""LIVEKIT_URL=http://127.0.0.1:7880
LIVEKIT_API_KEY={os.environ.get("LIVEKIT_API_KEY", "middrive")}
LIVEKIT_API_SECRET={os.environ.get("LIVEKIT_API_SECRET", "abc75afd7b78117bf2466956612c189cc9b810dbd9d2178c5995b3bcc5203050")}
NEXT_PUBLIC_LIVEKIT_URL=ws://127.0.0.1:7880
NEXT_PUBLIC_AGENT_NAME=mid-drive
DEMO_ACCESS_TOKEN=
"""
    web_dir = ROOT / "apps" / "web"
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / ".env.local").write_text(web_env)
    print("wrote .env and apps/web/.env.local (secrets not printed)")


if __name__ == "__main__":
    main()

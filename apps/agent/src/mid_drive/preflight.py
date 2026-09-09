"""Provider preflight: catalog, Rime PCM, Azure chat. Does not print secrets."""

from __future__ import annotations

import sys

import httpx

from .config import REPO_ROOT, get_settings, load_env
from .rime_catalog import cache_catalog
from .rime_pcm import pcm_from_rime_body, pcm_looks_like_speech


def _check_rime(settings) -> None:
    speakers = cache_catalog(settings)
    print(f"rime catalog: {settings.rime_model}/{settings.rime_language} has {len(speakers)} voices")
    print(f"rime speaker: {settings.rime_speaker} (live)")
    response = httpx.post(
        settings.rime_endpoint,
        headers={
            "Authorization": f"Bearer {settings.rime_api_key}",
            "Accept": "audio/pcm",
            "Content-Type": "application/json",
        },
        json={
            "text": "I'm with you on the Gurgaon to Delhi drive.",
            "speaker": settings.rime_speaker,
            "modelId": settings.rime_model,
            "lang": settings.rime_language,
            "audioFormat": "pcm",
            "samplingRate": settings.rime_sample_rate,
        },
        timeout=45.0,
    )
    response.raise_for_status()
    audio = pcm_from_rime_body(response.content, response.headers.get("content-type"))
    if not pcm_looks_like_speech(audio):
        raise RuntimeError("Rime PCM failed the speech sanity check")
    out = REPO_ROOT / "artifacts" / "preflight-rime.pcm"
    out.write_bytes(audio)
    print(
        f"rime http-pcm: {len(audio)} bytes, content-type={response.headers.get('content-type')} "
        f"sample_rate={settings.rime_sample_rate} -> {out}"
    )


def _check_azure(settings) -> None:
    url = (
        settings.azure_openai_endpoint.rstrip("/")
        + f"/openai/deployments/{settings.azure_openai_deployment}/chat/completions"
        + f"?api-version={settings.azure_openai_api_version}"
    )
    response = httpx.post(
        url,
        headers={"api-key": settings.azure_openai_api_key, "Content-Type": "application/json"},
        json={
            "messages": [
                {"role": "system", "content": "Reply with exactly: azure-ok"},
                {"role": "user", "content": "ping"},
            ],
            "max_completion_tokens": 16,
            "temperature": 0,
        },
        timeout=45.0,
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"]
    print(f"azure openai: {settings.azure_openai_deployment} said {text!r}")


def _check_eleven(settings) -> None:
    response = httpx.get(
        "https://api.elevenlabs.io/v1/user",
        headers={"xi-api-key": settings.eleven_api_key},
        timeout=20.0,
    )
    response.raise_for_status()
    print("elevenlabs: account reachable")


def main() -> None:
    load_env()
    settings = get_settings()
    print("preflight: env loaded")
    _check_eleven(settings)
    _check_rime(settings)
    _check_azure(settings)
    print("preflight: ok")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"preflight: failed: {exc}", file=sys.stderr)
        raise

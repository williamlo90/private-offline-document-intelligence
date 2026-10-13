"""One-time pinned-model warm-up for the isolated offline Compose lab."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import urllib.error
import urllib.request


MARKER = Path("/tmp/private-documents-model-ready")
PROFILE = Path("/run/secrets/ollama-profile.json")
BASE = "http://127.0.0.1:11439"


def request(path: str, body: dict | None = None, timeout: int = 15) -> dict:
    payload = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=payload,
                                 headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
            raise RuntimeError("Unexpected Ollama response")
        data = response.read(32769)
        if len(data) > 32768:
            raise RuntimeError("Oversized readiness response")
    result = json.loads(data)
    if not isinstance(result, dict):
        raise RuntimeError("Invalid readiness response")
    return result


def main() -> int:
    if MARKER.is_file():
        return 0
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    tags = request("/api/tags")
    models = tags.get("models", [])
    if not isinstance(models, list) or not any(
        row.get("name") == profile["model"] and row.get("digest") == profile["digest"]
        and row.get("details", {}).get("format") == "gguf"
        for row in models if isinstance(row, dict)
    ):
        raise RuntimeError("Pinned Ollama model is unavailable")
    result = request("/api/generate", {
        "model": profile["model"], "prompt": "Return JSON with ready=true.",
        "format": {"type": "object", "properties": {"ready": {"type": "boolean"}},
                   "required": ["ready"]},
        "stream": False, "keep_alive": 0,
        "options": {"temperature": 0, "num_predict": 24, "num_ctx": 1024},
    }, timeout=120)
    if result.get("done") is not True or result.get("done_reason") != "stop" or result.get("model") != profile["model"]:
        raise RuntimeError("Model warm-up did not complete")
    if not isinstance(json.loads(result.get("response", "")), dict):
        raise RuntimeError("Invalid warm-up JSON")
    MARKER.write_text(profile["digest"] + "\n", encoding="ascii")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, RuntimeError, urllib.error.URLError) as error:
        print(f"model_not_ready: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)

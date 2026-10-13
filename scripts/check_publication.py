"""Fail publication if a tracked file crosses the local/private boundary."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {"local", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache"}
FORBIDDEN_NAMES = {".env", "id_rsa", "id_ed25519"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db", ".log"}
SECRET_MARKERS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9_]{30,}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{30,}"),
)


def main() -> None:
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).split(b"\0")
    failures: list[str] = []
    count = 0
    for raw in names:
        if not raw:
            continue
        relative = Path(raw.decode("utf-8"))
        count += 1
        if any(part in FORBIDDEN_PARTS for part in relative.parts) or relative.name in FORBIDDEN_NAMES or relative.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"forbidden tracked path: {relative}")
            continue
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"missing tracked file: {relative}")
            continue
        if path.stat().st_size > 10 * 1024 * 1024:
            failures.append(f"oversized tracked file: {relative}")
        if path.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".md", ".yaml", ".yml", ".toml", ".sql", ".txt"}:
            content = path.read_bytes()
            if any(pattern.search(content) for pattern in SECRET_MARKERS):
                failures.append(f"secret marker in: {relative}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Publication boundary passed: {count} tracked files")


if __name__ == "__main__":
    main()

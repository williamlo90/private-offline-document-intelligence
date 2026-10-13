"""Check repository-local Markdown links without contacting the network."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\((<[^>]+>|[^)]+)\)")


def main() -> None:
    tracked = subprocess.check_output(["git", "ls-files", "-z", "*.md"], cwd=ROOT).split(b"\0")
    missing: list[str] = []
    checked = 0
    for raw in tracked:
        if not raw:
            continue
        source = ROOT / raw.decode("utf-8")
        content = source.read_text(encoding="utf-8")
        for match in LINK.finditer(content):
            destination = match.group(1).strip("<>").split(" ", 1)[0]
            parsed = urlsplit(destination)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            checked += 1
            target = (source.parent / unquote(parsed.path)).resolve()
            if not target.is_relative_to(ROOT.resolve()) or not target.exists():
                line = content.count("\n", 0, match.start()) + 1
                missing.append(f"{source.relative_to(ROOT)}:{line}: {destination}")
    if missing:
        raise SystemExit("Broken repository links:\n" + "\n".join(missing))
    print(f"Markdown links passed: {checked} local targets")


if __name__ == "__main__":
    main()

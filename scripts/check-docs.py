"""Verify local Markdown links and heading anchors in the project documentation."""
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    checked = 0
    for source in [ROOT / "AGENTS.md", ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]:
        text = source.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if re.match(r"[a-z]+://", target) or target.startswith("mailto:"):
                continue
            filename, _, anchor = unquote(target).partition("#")
            destination = (source.parent / filename).resolve() if filename else source
            assert destination.is_file(), f"{source}: missing {target}"
            if anchor:
                headings = re.findall(r"^#+\s+(.+)$", destination.read_text(encoding="utf-8"), re.MULTILINE)
                anchors = {re.sub(r"[^\w\- ]", "", h.strip().lower()).replace(" ", "-") for h in headings}
                assert anchor in anchors, f"{source}: missing anchor {target}"
            checked += 1
    print(f"Passed {checked} local Markdown links/anchors.")


if __name__ == "__main__":
    main()

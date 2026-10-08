"""Offline demonstration and file-based review-only assessment."""

import argparse
import json
from pathlib import Path
import sys

from .core import ContractError, assess


def _read(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Field Accord FA-01 offline assessment")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Evaluate the synthetic no-authority example")
    review = sub.add_parser("assess", help="Assess three local JSON files, without execution")
    for name in ("intent", "capability", "proposal"):
        review.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "demo":
            examples = Path(__file__).resolve().parent.parent / "examples"
            paths = [examples / name for name in ("intent.json", "capability.json", "proposal.json")]
        else:
            paths = [args.intent, args.capability, args.proposal]
        receipt = assess(*(_read(path) for path in paths))
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if receipt["decision"] == "REVIEW_REQUIRED" else 3
    except (OSError, ValueError, ContractError) as exc:
        print(f"Field Accord assessment refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

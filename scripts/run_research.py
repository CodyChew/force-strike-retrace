from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from force_strike_lab.config import load_config
from force_strike_lab.research import run_research


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Force Strike research.")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "configs" / "m30_forex_basket.json"))
    parser.add_argument("--pull", action="store_true", help="Pull MT5 data before running research.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    result = run_research(config, project_root=PROJECT_ROOT, pull_first=bool(args.pull))
    print("Force Strike research complete")
    print(f"- report: {result['report_path']}")
    print(f"- candidates: {result['candidate_count']}")
    print(f"- trades: {result['trade_count']}")
    print(f"- top_candidate: {result['top_candidate']}")


if __name__ == "__main__":
    main()


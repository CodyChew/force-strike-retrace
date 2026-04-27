from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from force_strike_lab.config import load_config
from force_strike_lab.mt5_data import pull_mt5_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pull MT5 rates data for Force Strike research.")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "configs" / "m30_forex_basket.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    result = pull_mt5_data(config, project_root=PROJECT_ROOT)
    print("MT5 pull complete")
    print(f"- timeframe: {result['timeframe']}")
    print(f"- files: {len(result['files'])}")
    for row in result["files"]:
        print(f"- {row['symbol']}: rows={row['rows']} path={row['csv_path']}")


if __name__ == "__main__":
    main()


from __future__ import annotations

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "contracts/viewer/v1/schema.json"
TARGETS = [
    ROOT / "packages/engine/src/gi_racesim/common/viewer-schema.json",
    ROOT / "apps/site/public/schema.json",
]


def main() -> None:
    for target in TARGETS:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE, target)


if __name__ == "__main__":
    main()

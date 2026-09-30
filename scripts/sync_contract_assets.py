from __future__ import annotations

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/viewer/v1"
COPIES = (
    (CONTRACT / "schema.json", ROOT / "packages/engine/src/gi_racesim/common/viewer-schema.json"),
    (CONTRACT / "schema.json", ROOT / "apps/site/public/schema.json"),
    (CONTRACT / "fixtures/synthetic-race.json", ROOT / "apps/site/public/fixtures/synthetic-race.json"),
)


def main() -> None:
    for source, target in COPIES:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


if __name__ == "__main__":
    main()

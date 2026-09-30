from __future__ import annotations

import json
from pathlib import Path

from gi_racesim.common.contract import read_bundle


def read_contract_fixture(repo_root: str | Path) -> dict:
    path = Path(repo_root) / "contracts" / "viewer" / "v1" / "fixtures" / "synthetic-race.json"
    return read_bundle(path)

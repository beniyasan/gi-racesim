from __future__ import annotations

import os
from pathlib import Path
import tempfile

from gi_racesim.common.contract import canonical_json, validate_bundle


def write_bundle(bundle: dict, destination: str | Path) -> Path:
    """Validate then atomically write a UTF-8 JSON bundle.

    The destination is an export artifact, not a database and not a network
    operation. Existing files are replaced only after validation succeeds.
    """
    validate_bundle(bundle)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(canonical_json(bundle))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return path

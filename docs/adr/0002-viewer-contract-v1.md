# ADR 0002: Mac-to-viewer JSON contract v1

Status: accepted for the initial integration slice.

The Mac-side engine writes a validated JSON result bundle and the viewer
validates the same bundle before rendering it. A bundle carries its schema,
input time, code/data/model identifiers, origin, and quality notes. A viewer
must reject an unknown schema or missing provenance rather than guessing.

The first transport is a manually selected JSON file. Automatic authenticated
sync and Sites deployment are intentionally deferred until the Sites execution
path is verified in WORK-002.

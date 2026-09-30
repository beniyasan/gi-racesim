# Viewer contract v1

This is the handoff format from the Mac-side engine to the viewer. The
authoritative schema is `contracts/viewer/v1/schema.json`; Python and browser
tests use the same fixture in `contracts/viewer/v1/fixtures/`.

## Provenance

- `origin=synthetic`: a fixture or display test. It may use the reserved zero
  commit and a null `model_id`, but it must say that it is synthetic.
- `origin=baseline_prediction` or `learned_prediction`: a prediction result.
  It requires a real producer commit and a model identifier.
- `observations`: measured values are stored in a separate section. They are
  not replaced with prediction values.

`as_of` is the input cutoff and must precede the race start. `generated_at` is
when the bundle was created. `mode=prospective` additionally requires the
bundle to be generated before the start time.

## Display data

Each representative trial carries a complete lap endpoint list and a corner
list. A corner accounts for every declared gate either in a group or in
`unobserved_gate_numbers`. A missing runner is accompanied by
`unknown_reason`. Group member order is only shown when the source explicitly
provides an inner-to-outer order; the viewer does not invent a longitudinal
order from gate numbers.

The aggregate lap section stores p10/p50/p90 and sample count. It is not a
single physically-realized trajectory. The viewer labels representative trials
and aggregate values separately.

## Import rules

The initial transport is manual UTF-8 JSON import with a 5 MiB limit. Unknown
schema versions and malformed bundles are rejected before rendering. Automatic
authenticated sync, D1/R2 persistence, and Sites access tests belong to
WORK-002 and WORK-005 after the actual Sites project path is verified.

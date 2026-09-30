# Viewer contract v1

This contract is the handoff boundary between the Mac-side engine and the
viewer. The engine writes a JSON bundle; the viewer validates the bundle before
rendering it.

`origin` is mandatory. `synthetic` is kept separate from `baseline_prediction`
and `learned_prediction`; measured values have their own `observations`
section, and `quality` must explain observation and prediction limits. A missing
value stays missing; the viewer does not infer a continuous trajectory or a
betting recommendation.

The JSON Schema documents the public shape. The Python and browser validators
enforce the safety-critical subset without requiring a network or third-party
package.

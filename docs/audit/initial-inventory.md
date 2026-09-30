# Initial inventory

Date: 2026-09-30 (UTC execution environment)

The supplied source artifacts were materialized locally before implementation:

- `gi_scrape_sim_v3.zip`: existing offline gate, normalization, X/Y builder and tests.
- `gi_racesim_workplan_v1.zip`: WORK-000〜012, architecture, templates and first-work prompt.

SHA-256 of the supplied archives:

- `gi_scrape_sim_v3.zip`: `c5809858f2969621b9fc785d04fe1b7e40006a20ea05e735991013bd14b7f887`
- `gi_racesim_workplan_v1.zip`: `dd93029693c833666992cf5f2161d15c4862af03c28aa126cef0c12faa96bf3b`

The source package reports that its bundled code performs zero network requests,
does not contain a live HTTP adapter, does not train a model, and does not have
a Site UI. Those limits are preserved in this repository.

The current execution environment is Linux x86_64 with Python 3.12 and Node
24.19. It is not the target MacBook. Mac hardware, macOS launchd, and the local
Codex/Claude Code/Devin installations therefore remain unverified and are not
claimed as completed by this audit.

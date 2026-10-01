# macOS operations

The Mac runtime is deliberately separate from this development worktree. The
production state belongs under `~/Library/Application Support/GIRaceSim/`.

LaunchAgent registration is not part of the initial commit. Before enabling it,
use a reviewed, immutable checkout and run the mock restart/double-start tests.
The launch job may invoke a short `claim` operation, but it must not run a
network request unless the persistent gate grants the single permit.

`com.giracesim.collector.plist.template` is a registration template only. It
omits the external-HTTP opt-in and must be edited for the reviewed checkout
before a human performs any launchd registration.

# Local import test

This commit supplies the browser-side slice for the later Sites import test.
Serve `apps/site` with a local HTTP server, select **合成fixtureを表示**, and
confirm that the origin, input time, lap quantiles, quality notes, and
representative corner groups render. Select the same JSON through the file
control to exercise the manual import path.

The local slice does not prove Sites authentication, persistence, D1/R2
bindings, or cross-device revisit. Those checks remain explicitly unperformed
until WORK-002 establishes the actual Sites execution path.

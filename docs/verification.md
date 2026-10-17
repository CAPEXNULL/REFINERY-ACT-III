# Public CPU package verification

Verified on 2026-10-17. This report covers the exported CPU application and contest materials. It is not a new diagnostic experiment or industrial acceptance claim.

| Check | Result |
| --- | --- |
| Fresh Python 3.13 install from public requirements | PASS |
| Selected existing runtime tests and public HTTP boundary tests, Windows | 55 passed |
| Linux audit integrity, writer lock and origin checks in Docker | 16 passed |
| Linux image build | PASS |
| Recorded-replay browser checks | 19 passed; zero page errors |
| Real CPU HTTP scenario, configuration A / cooling loss | Correct diagnosis; four conditional action forecasts available |
| Component mass residual, that scenario | 1.42e-13 mol |
| Energy residual, that scenario | -9.17e-10 J |
| Protected physical/diagnostic source files | Nine original files preserved byte for byte |
| Frozen model | Original bytes preserved |
| Secrets and private-path review of public payload | Independent review passed |
| AMD Token Factory inference | Not performed; participant access and official API parameters pending |

The actual calculation shown in the video took 113.9 seconds of wall time on the recording host. The edited video explicitly omits the middle of that waiting period. Model time is different from computation time; neither this video nor the four-second simulated horizon demonstrates a real-plant detection deadline.

The permanent interactive demo replays a sanitized, actual synthetic calculation. It runs no new backend calculation and no AMD inference. The temporary live CPU workspace runs calculations while its host and tunnel remain available.

Reproduce the exported tests locally with `python -m pytest -q tests`. Run the application with `python -m amd.server` and open `/industry`.

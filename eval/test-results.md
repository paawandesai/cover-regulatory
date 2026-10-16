# Test results

Run 2026-10-16 on the `engine-corrections` branch, on the development machine against the loaded database.

| Suite | Where | Tests | Passed | What it checks |
|---|---|---|---|---|
| Unit | `backend/tests/unit/` | 34 | 34 | APN and zone parsing, LAMC chunking, section references, the extraction checks (quote in chunk, number in quote), prompt delimiter escaping, and project-input checks and the summary |
| Golden parcels | `backend/tests/golden/` | 11 cases | 11 | Every value the engine shows on 11 self-selected parcels (vacant, built-up, through lot, specific plan, Hillside + Coastal + fire, conditioned zone, and three stop states), plus each case's status, flags and labels. Expected values were calculated from the code text, not taken from the engine (see `cases.yaml`) |
| Adversarial | `backend/tests/adversarial/`, cases in `eval/adversarial/` | 4 | 4 | Injected document text, a fake exemption, model-set status, and feedback trying to change a rule |
| API | `backend/tests/api/` | 16 | 16 | Admin auth, invite gate, noindex, health without secrets, verification never changing a status, AI review only on pending rules, building outlines with attribution, address lookup, unknown APN, project inputs, and marking feedback reviewed without touching rules |
| Frontend | `frontend/src/__tests__/` | 7 | 7 | Value formatting and labels |
| **Total** | | **72** | **72** | |

CI (GitLab) runs the secrets scan, lint, type checks, a production build, the unit tests and the frontend tests on every push, and publishes JUnit reports. The golden, adversarial-feedback and API suites need the loaded database. The database holds hand-saved regulation text that stays out of git, so those suites skip in CI and are run locally before each merge.

Retrieval quality and latency are reported in the README (Measured results) and `eval/retrieval/results.md`.

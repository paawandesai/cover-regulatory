# Test results

Run 2026-10-16 on main plus MR !14, on the development machine against the loaded database.

| Suite | Where | Tests | Passed | What it checks |
|---|---|---|---|---|
| Unit | `backend/tests/unit/` | 26 | 26 | APN and zone parsing, LAMC chunking, section references, the extraction checks (quote in chunk, number in quote) and prompt delimiter escaping |
| Golden parcels | `backend/tests/golden/` | 8 cases | 8 | All 66 values the engine shows on 8 self-selected parcels, plus each case's stop status and flags. Expected values were calculated from the code text, not taken from the engine (see `cases.yaml`) |
| Adversarial | `backend/tests/adversarial/`, cases in `eval/adversarial/` | 4 | 4 | Injected document text, a fake exemption, model-set status, and feedback trying to change a rule |
| API | `backend/tests/api/` | 12 | 12 | Admin auth, invite gate, noindex, health without secrets, verification never changing a status, AI review only on pending rules, building outlines with attribution |
| Frontend | `frontend/src/__tests__/` | 7 | 7 | Value formatting and labels |
| **Total** | | **57** | **57** | |

CI (GitLab) runs the secrets scan, lint, type checks, a production build, the unit tests and the frontend tests on every push, and publishes JUnit reports. The golden, adversarial-feedback and API suites need the loaded database. The database holds hand-saved regulation text that stays out of git, so those suites skip in CI and are run locally before each merge.

Retrieval quality and latency are reported in the README (Measured results) and `eval/retrieval/results.md`.

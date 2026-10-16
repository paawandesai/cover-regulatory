# Test results

Run 2026-10-16 on the `wave3` branch, on the development machine against the loaded database.

| Suite | Where | Tests | Passed | What it checks |
|---|---|---|---|---|
| Unit | `backend/tests/unit/` | 52 | 52 | APN and zone parsing (R1 variation and Hillside zone strings), LAMC chunking, section references, the extraction checks (quote in chunk, number in quote), prompt delimiter escaping, project-input checks and the summary, struck-through text, rate limits, section links, the prevailing front-yard group rule, floor-area exemptions, the plane break, and slope bands from elevation |
| Golden parcels | `backend/tests/golden/` | 11 cases + 6 | 17 | Every value the engine shows on 11 self-selected parcels (vacant, built-up, through lot, specific plan, Hillside + Coastal + fire with the slope-band floor area, conditioned zone, and three stop states), plus each case's status, flags and labels. Six more resolve real lots as other cases: Height District 1-SS, the R1F, R1R and R1V variation tables, a flat Coastal Zone lot, and a lot newly in a Very High fire zone on CAL FIRE's 2025 map. Two cases also pin the ADU height near transit, checked against the Caltrans service directly. Expected values were calculated from the code text, not taken from the engine (see `cases.yaml`) |
| Adversarial | `backend/tests/adversarial/`, cases in `eval/adversarial/` | 4 | 4 | Injected document text, a fake exemption, model-set status, and feedback trying to change a rule |
| API | `backend/tests/api/` | 17 | 17 | Admin auth, the sign-in rate limit, invite gate, noindex, health without secrets, verification never changing a status, AI review only on pending rules, building outlines with attribution, address lookup, unknown APN, project inputs, and marking feedback reviewed without touching rules |
| Frontend | `frontend/src/__tests__/` | 7 | 7 | Value formatting and labels |
| **Total** | | **97** | **97** | |

CI (GitLab) runs the secrets scan, lint, type checks, a production build, the unit tests and the frontend tests on every push, and publishes JUnit reports. The golden, adversarial-feedback and API suites need the loaded database. The database holds hand-saved regulation text that stays out of git, so those suites skip in CI and are run locally before each merge.

Retrieval quality and latency are reported in the README (Measured results) and `eval/retrieval/results.md`.

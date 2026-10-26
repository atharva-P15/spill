# SPILL — Code Change Impact Predictor

Predict the ripple effect before you commit.

SPILL is a working Windows-local Python repository analysis application. It combines static import graphs, bounded Git co-change history, a trained CPU GraphSAGE model, and actual proposed-code compatibility checks. It never pushes changes or executes external repository code.

## Implemented features

- Registration, Argon2 password hashes, eight-hour JWT sessions, per-user repository and report ownership.
- Public/private GitHub connection using HTTPS and optional encrypted personal access tokens.
- Isolated managed clones, refresh, disconnect, file browsing, dependency snapshots, and saved reports.
- Local Monaco editor, reset, side-by-side diff, proposed changes that leave the clone unchanged.
- Import and reverse-dependency analysis, relative imports, src-layout packages, module aliases, imported symbols, and historical co-changes.
- Two-layer trainable GraphSAGE, offline training, checkpoint loading, baselines, chronological evaluation, and held-out/cold-start evaluation.
- Evidence-based risk classification; ranked files with actual dependency paths and compatibility evidence.
- React Flow graphs with selectable nodes, filtering, structural/history styles, and impact highlighting.
- Backend-driven dashboard, analysis history, model metrics, responsive dark UI, and a trusted demonstration runner.

## Stack and architecture

Frontend: React 18, Vite 6, JavaScript, Tailwind CSS 4, React Router 7, Axios, Monaco, React Flow, Recharts, and Lucide.

Backend: Python 3.11, FastAPI, Pydantic, SQLAlchemy, SQLite, PyJWT, Argon2, Fernet encryption, HTTPX, and GitPython.

Analysis: PyTorch 2.7.0 CPU, a directly implemented GraphSAGE mean aggregator, NetworkX, NumPy, and scikit-learn. No PyTorch Geometric installation is necessary. Pandas is included for dataset work.

The browser calls FastAPI through Vite's local /api proxy. SQLite stores users, repositories, graph snapshots, nodes, edges, reports, impacted-file records, and model metadata. Git clones live under runtime/workspaces. The model loads once at backend startup; connecting a repository never retrains it.

Graph edges point from importer to imported module. Reverse traversal identifies potential downstream impact. Model ranking and change-specific risk are separate outputs.

## Prerequisites

Tested on Windows with Python 3.11.9, Node.js 24.19.0, npm 11, and Git 2.55.0. Use 64-bit Python 3.11 and Node 22.12+ or Node 24. No CUDA is needed. Allow approximately 3 GB for the environment, training clones, and optional browser test downloads.

Check:

~~~powershell
py -3.11 --version
node --version
npm.cmd --version
git --version
~~~

If Python 3.11 is missing and Python Install Manager is available:

~~~powershell
py install 3.11
~~~

## Installation on Windows 11

Open PowerShell:

~~~powershell
Set-Location D:\DL\project\SPILL
powershell -ExecutionPolicy Bypass -File .\scripts\spill.ps1 install
~~~

The script creates .venv, installs pinned dependencies and CPU PyTorch, installs the frontend from its package lock, generates local secrets, and initializes SQLite. All commands fail with an error if a required step fails.

The supplied trained checkpoint is ready to use. You do not need to retrain for normal use.

Manual equivalent:

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install pip==26.2.2 setuptools==83.0.0
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m pip install torch==2.7.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe scripts\configure.py
.\.venv\Scripts\python.exe scripts\init_db.py
Set-Location frontend
npm.cmd ci
Set-Location ..
~~~

## Environment configuration

Run every backend/ML command from the SPILL directory. scripts/configure.py creates the root .env with cryptographically random values and never overwrites existing secrets.

| Variable | Purpose / default |
| --- | --- |
| SPILL_JWT_SECRET | Required: at least 32 characters, generated automatically. Changing it invalidates sessions. |
| SPILL_ENCRYPTION_KEY | Required: Fernet key generated automatically. Keep it to decrypt saved GitHub tokens. |
| SPILL_DATA | Optional: runtime directory, defaults to SPILL/runtime. Prefer an absolute path when overriding. |
| SPILL_MODEL | Optional: checkpoint path, defaults to ml/checkpoints/graphsage.pt. |
| SPILL_CORS | Optional: comma-separated exact allowed browser origins. Defaults to localhost:5173 and 127.0.0.1:5173 with http. |
| VITE_API_URL | Optional frontend/.env setting. Defaults to /api via the Vite proxy. |

Root .env.example lists the settings. backend/.env.example explains the same root configuration. Never commit .env or runtime/. Local secrets and tokens are not included in API responses, including validation errors. Tokens are encrypted in SQLite and passed to Git through the child process environment, never URL arguments or persisted Git configuration. Protect the local Windows account and .env: encryption does not protect against someone who can read both the key and database.

## Database setup

~~~powershell
.\.venv\Scripts\python.exe scripts\init_db.py
~~~

The backend also initializes the schema on startup using SQLAlchemy create_all. This is the documented initial-schema procedure, not a migration framework. It preserves existing records; future incompatible schema changes need an explicit migration or a separately backed-up fresh data directory. The database is runtime/spill.db. Foreign keys and WAL mode are enabled.

## Start the application

Terminal 1:

~~~powershell
Set-Location D:\DL\project\SPILL
powershell -ExecutionPolicy Bypass -File .\scripts\spill.ps1 backend
~~~

Terminal 2:

~~~powershell
Set-Location D:\DL\project\SPILL
powershell -ExecutionPolicy Bypass -File .\scripts\spill.ps1 frontend
~~~

Open [SPILL](http://127.0.0.1:5173). The API runs at [localhost:8000](http://127.0.0.1:8000); interactive endpoint documentation is at [API docs](http://127.0.0.1:8000/docs).

Both servers bind to loopback. Keep this a local application; internet-facing hosting, HTTPS termination, operational rate limits, and multi-worker job coordination are outside this release. Press Ctrl+C in each terminal to stop it.

## Connecting GitHub

1. Register and sign in.
2. Choose Add repository, enter an HTTPS github.com/owner/repository URL.
3. Public repositories usually need no token. GitHub API rate limits can still require one.
4. For private access, create a fine-grained GitHub token, select the intended resource owner and repository, and grant **Contents: Read-only**. Metadata read permission is included by GitHub. Organization policy may require approval.
5. Paste the token and choose Connect & analyze.
6. Disconnect from the overview to delete the managed clone, stored token, snapshots, and associated reports.

See GitHub's [personal access token documentation](https://docs.github.com/en/enterprise-cloud%40latest/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) and [fine-grained permissions reference](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens).

Cloning is limited to 250 commits of a single default branch, 120 seconds, and a monitored 150 MB workspace budget, with a final size check. Repositories reported over 150,000 KB are rejected before cloning. No submodules or LFS payloads are fetched. Source files are limited to 256 KB each and 1,200 Python files. Static analysis ignores common dependency/build/cache directories and symlinks outside the workspace. Non-Python codebases receive a clear unsupported message.

Public GitHub connection was tested live with pallets/itsdangerous. Private-token transport, encryption, redaction, and ownership were tested locally; an actual private repository was not tested because no private token was supplied.

## Using SPILL

1. Register or log in.
2. Connect a repository or load the included demo.
3. Inspect its graph and choose Analyze change.
4. Select a Python file. Monaco displays its actual contents.
5. Edit the proposal and optionally inspect Diff or reset it.
6. Select Predict impact.
7. Review the classification, ranked files, concrete evidence, graph, and original/proposed diff.
8. Reopen reports from Analysis history.

A stale base commit is rejected after refresh. Old reports retain the original graph snapshot and code diff. No operation writes proposals back to the clone or GitHub.

### Interpret the result correctly

- **LOW:** comment, whitespace, or docstring-only changes. “Low estimated risk. No breaking changes detected by the available checks.”
- **MEDIUM:** executable AST changes without a proven incompatibility. This deliberately conservative rule covers uncertain logic and interface changes.
- **HIGH:** invalid proposed Python syntax, removed imported/referenced symbols, or an incompatible statically identifiable call to a changed function.

No risk threshold is based on file count. A numerical GraphSAGE score is an **uncalibrated learned impact score**, not the probability of breaking functionality. The candidate table contains all files reachable by reverse dependencies or a historical co-change edge, sorted by the trained model. No score threshold silently removes candidates.

The demo's very small files receive low raw model scores because their features differ substantially from the larger training files. They still appear in the ranking. The same rankings appear for a comment and a signature change because the impact head models file relationships; the actual proposed edit drives the separate compatibility assessment. A low score never overrides a detected violation.

## Training data, model, and reproducibility

### Acquire and prepare real data

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\spill.ps1 prepare
~~~

This downloads bounded histories from [Click](https://github.com/pallets/click), [Flask](https://github.com/pallets/flask), and [ItsDangerous](https://github.com/pallets/itsdangerous) if absent, then prepares the dataset. No downloaded Python code is executed or installed.

ml/data/manifest.json records exact repository heads, earliest included commits, counts, and supervision assumptions for this run. A later default clone can produce a different dataset as upstream repositories change. To reproduce the saved run exactly, obtain the recorded commits and use those local repositories; do not treat a new HEAD as the original dataset.

For existing local training repositories:

~~~powershell
.\.venv\Scripts\python.exe -m ml.prepare --repos C:\datasets\click C:\datasets\flask C:\datasets\itsdangerous --limit 300
~~~

Preparation reads Git tree objects without checking out or running old code. It works offline when those histories are already available. No synthetic labels are substituted on network failure.

### Labels and leakage controls

After a 24-commit warm-up, every fourth first-parent commit is a proposal event. Up to two modified Python files are used as changed-file anchors. Inputs use the previous commit's source tree and earlier history only. Candidate labels indicate modifications in the event commit or the following two commits.

Unobserved pairs are **uncertain controls**, not confirmed unaffected files. All available positive and unobserved candidate pairs are included (exhaustive candidate selection rather than stochastic subsampling); unobserved controls receive 0.25 loss weight. The current dataset fits easily in memory.

Click/Flask events are split chronologically 60/20/20 by commit position. Four-commit stride keeps three-commit target windows non-overlapping. Anchors from the same event stay in the same split. The entire ItsDangerous repository is held out. Later chronological test examples may use earlier observed test-period history, as a rolling prediction system would; future outcomes are never used for the current graph.

Feature normalization is fit on training nodes only. Git initial commits and commits touching over 30 current Python files do not contribute to co-change features. Historical edges require at least two observations and use count / sqrt(file_frequency_a * file_frequency_b). Normal inference bounds history to 250 commits.

These labels indicate future maintenance activity, including unrelated work. They do not identify causal bugs or confirmed corrective commits. Correlated anchors and a small repository sample limit the strength of conclusions.

### Train and evaluate

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\spill.ps1 train
~~~

Architecture: two mean GraphSAGE layers, hidden size 64, ReLU, dropout 0.2. Structural and historical neighborhood means have separate channels; structural messages are bidirectional while dependency explanations preserve directed imports. Pair embeddings concatenate source, candidate, absolute difference, and four structural/history pair features. An MLP produces a sigmoid ranking score.

Nine node features encode log-scaled size, functions, classes, imports, in/out degree, complexity, modification frequency, and history availability. Each training example is also trained with historical features and edges disabled. Adam uses learning rate 0.001, weight decay 0.0001, gradient clipping, weighted binary cross-entropy, and seed 42. Validation PR-AUC selects the checkpoint with patience 8 (maximum 60 epochs).

Saved artifacts:

- ml/checkpoints/graphsage.pt: actual trained weights, schema, configuration, normalization, and metadata.
- ml/checkpoints/metadata.json: training trace, selected epoch, dataset hash, and evaluation.
- ml/checkpoints/evaluation.json: all metrics and baseline comparisons.
- ml/data/dataset.json: local prepared graph examples (ignored in Git).
- ml/data/manifest.json: dataset provenance.

For standalone evaluation without retraining:

~~~powershell
.\.venv\Scripts\python.exe -m ml.evaluate
~~~

Missing checkpoints produce an explicit 503 for prediction; there is no fake-score fallback.

### Actual evaluation

The run used 49 training, 22 validation, 33 chronological test, and 26 held-out examples. Epoch 13 was selected after 21 training epochs. Chronological test: 2,430 pairs, 218 weak positives.

| Method | Precision | Recall | F1 | ROC-AUC | PR-AUC | Precision@5 | Recall@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GraphSAGE | 0.268 | 0.560 | 0.362 | 0.804 | 0.282 | 0.321 | 0.276 |
| Structural baseline | 0.102 | 0.431 | 0.165 | 0.539 | 0.106 | 0.139 | 0.100 |
| Historical baseline | 0.364 | 0.037 | 0.067 | 0.640 | 0.161 | 0.194 | 0.198 |

Precision/recall/F1 use a conventional 0.5 score threshold for evaluation only; this is neither a calibrated probability cutoff nor an application risk rule. PR-AUC is sklearn average precision. Ranking metrics average across proposal groups, with K capped at candidate count.

GraphSAGE cold-start test ROC-AUC: 0.793; PR-AUC: 0.298. Held-out ItsDangerous ROC-AUC: 0.680; PR-AUC: 0.365 (314 pairs, 67 positives). Full metrics for all methods and splits are in evaluation.json. Undefined binary metrics return null. These results are research-scale estimates of future file modification, not production failure prediction.

## Reproducible demonstrations

With both servers running:

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\spill.ps1 demo
~~~

The runner creates/logs into a local demo account, connects a fresh copy of the eight-file demo through the production API, submits both proposals, checks classifications/rankings, and executes the bundled trusted tests in temporary copies.

The random demo password is stored locally in runtime/demo-login.json. To use the same account in the browser, read that file locally. It is ignored by Git. Prefer registering your own account for normal use.

Actual outcomes:

| Proposal | Assessment | Ranked candidate files | Trusted tests |
| --- | --- | --- | --- |
| Added comment in auth.py | LOW | services.py, tests/test_auth.py, main.py | 5 passed |
| Renamed username/password parameters to email/otp | HIGH | services.py, tests/test_auth.py, main.py | 3 failed, 2 passed (expected) |

The bad variant preserves dependent keyword callers, which really fail with TypeError. Its raw impact scores are 0.000988, 0.000867, and 0.000719 in the displayed order. These are genuine checkpoint outputs, not hand-assigned values. Risk is determined independently.

The full API responses and actual pytest output are saved in docs/demo-report.json. The separate live public-repository smoke result is docs/github-smoke-report.json.

### Trusted execution boundary

Only demo/demo_runner.py can execute the two bundled good/bad variants. It copies the bundled fixture, replaces auth.py with a bundled variant, disables pytest plugin autoload, and runs tests with a 30-second timeout. This is a controlled trusted-fixture workflow, **not an OS sandbox**. Arbitrary repository test execution is deliberately disabled. The browser offers proposals; it does not offer arbitrary code execution.

## Tests and browser verification

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\spill.ps1 test
powershell -ExecutionPolicy Bypass -File .\scripts\spill.ps1 demo
powershell -ExecutionPolicy Bypass -File .\scripts\spill.ps1 browser
~~~

The test command runs backend tests, frontend unit tests, and a production build. Browser testing needs the running backend/frontend and a prior demo run to create its local login. The browser command installs Chromium if needed.

Backend coverage includes registration/login/JWT, ownership, encrypted-token connection contracts, source browsing, relative/absolute imports, graph construction, historical extraction, reverse traversal, cold starts, AST changes, signatures, syntax, real GraphSAGE gradients/checkpoint loading, prediction/history APIs, stale snapshots, refresh/disconnect, token redaction, traversal rejection, leakage boundaries, and both trusted test variants.

Playwright exercises real UI registration, login, demo connection, graph rendering, actual Monaco typing, diff, good/bad results, evidence, history, metrics, logout, and mobile overflow. It also rejects browser runtime exceptions.

Evidence:

- docs/backend-tests.xml — backend pytest report.
- docs/browser-test-results.json — Playwright report.
- docs/screenshots/ — dashboard, repository, editor, good/bad predictions, graph, and mobile screenshots.
- docs/python-audit.json and docs/npm-audit.json — dependency audit snapshots.

## API map

All repository, prediction, and model routes require a bearer JWT. Ownership is checked on every resource.

| Area | Routes |
| --- | --- |
| Auth | POST /api/auth/register, POST /api/auth/login, GET /api/auth/me |
| Repository | GET/POST /api/repositories, POST /api/repositories/demo |
| Management | GET/DELETE /api/repositories/{id}, POST /api/repositories/{id}/refresh |
| Source | GET /api/repositories/{id}/files, /file?path=..., /graph |
| Prediction | POST /api/repositories/{id}/predictions |
| History | GET /api/predictions, GET /api/predictions/{id} |
| Engine | GET /api/model, GET /api/health |

Prediction body: file, modified (Python source text), base_commit. Pydantic validates inputs and response schemas. The request limit is 1 MB. Errors do not expose stack traces, plaintext credentials, or validation input values.

## Known limits and honest fallbacks

- Python 3.11 AST syntax only. Dynamic imports, runtime monkey-patching, deep re-export chains, star-import resolution, and full type/data-flow analysis are not solved.
- Basic class definitions and class-body diffs are captured. Method dispatch, inheritance, and constructor compatibility are not exhaustively resolved; such semantic edits fall back to MEDIUM unless another concrete check proves incompatibility.
- Statically identifiable imported-function calls are checked. Starred argument expansion is uncertain and is not declared incompatible.
- Imports found inside conditionals are potential dependencies, not proof the branch executes.
- Large repositories and histories are deliberately bounded; graph display shows at most 100 filtered nodes. A grid layout favors responsiveness over optimal graph drawing.
- Model inputs can be out of distribution, especially tiny repositories. Scores are uncalibrated; no learned breaking-change classifier is claimed.
- Connection and analysis are synchronous operations serialized within the local backend process. This release is intended for a single local server, not a multi-worker service.
- Generated directories are excluded by known names, not perfect generated-code detection.
- Private GitHub end-to-end behavior still needs verification with your own permitted token.
- Monaco ships as a large lazy-loaded local bundle; a production-build size advisory is expected. It does not require a CDN.
- No arbitrary code test sandbox, GitHub write access, hosted deployment, password recovery/email service, or multi-language support is claimed.

## Troubleshooting

**PowerShell blocks scripts:** use the provided powershell -ExecutionPolicy Bypass -File command, which affects that invocation. npm.cmd avoids npm.ps1 policy problems.

**Python version mismatch:** create .venv with py -3.11. Do not install the Python dependencies into Python 3.14. If DLL loading fails, install Microsoft's current Visual C++ x64 runtime and use 64-bit Python.

**PyTorch wheel/CUDA problems:** use the exact CPU-index command above. See the [official PyTorch installation guidance](https://pytorch.org/get-started/locally/).

**GitHub 404/access failures:** verify the owner/repository, token repository selection, read permissions, expiration, organization approval, API rate limits, and network access. A private 404 may mean insufficient permission.

**Model missing or schema mismatch:** run prepare and train, then restart the backend. Only load locally trusted checkpoints. A missing model never silently produces predictions.

**Cannot decrypt a token after changing .env:** restore the matching encryption key, or disconnect and reconnect the repository with a new token.

**Port already in use:** stop the earlier SPILL process. The frontend uses strict port 5173 so it will not silently change addresses. Backend port is 8000.

**Dependency errors:** use the venv executable and npm ci. All direct package versions are pinned; frontend transitive versions are in package-lock.json. backend/requirements.lock.txt records the verified Python environment (including development auditing tools).

**Browser dependencies missing:** run npx.cmd playwright install chromium from frontend. Browser tests use a real Chromium process and require local servers.

**TestClient deprecation warning:** the current Starlette release warns that HTTPX test transport is deprecated in favor of httpx2. The pinned HTTPX transport remains functional and all API tests pass; it is not a failing test.

**Unexpected LOW:** LOW means the available checks found no executable AST change. It is never a safety guarantee. Review the diff and run your own relevant tests in a trusted environment.

## Project layout

~~~text
SPILL/
  backend/app/       FastAPI, auth, schemas, SQLite, repository services, change checks
  frontend/src/      React UI, Monaco lifecycle, React Flow, styles and unit tests
  frontend/e2e/      Playwright browser workflow
  ml/                Graph building, model, dataset preparation, training, evaluation
  ml/checkpoints/    Trained checkpoint and actual evaluation metadata
  demo/              Eight-file fixture, good/bad proposals, trusted runner
  tests/             Engine/API/security and demo tests
  scripts/           Windows task runner, secrets and database initialization
  docs/              Verification results, screenshots, and API demonstration reports
  runtime/           Ignored local SQLite, encrypted credentials, and managed clones
~~~


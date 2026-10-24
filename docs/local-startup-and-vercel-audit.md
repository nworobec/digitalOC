# Local startup and Vercel audit — October 20, 2026

## Scope and validation

Local server restart, HTTP checks, production compilation with `CI=true`, existing frontend/backend test suites, and source/config inspection. No Vercel account configuration, deployed build logs, or live browser workflow was inspected. Findings below distinguish observed local problems from deployment risks.

- Frontend: http://127.0.0.1:3000 — compiled successfully, HTTP 200.
- Dashboard API: http://127.0.0.1:5001 — health and metadata HTTP 200; `/evaluateOptions` HTTP 200 with two options.
- Production build: `CI=true npm run build` succeeded.
- Frontend: 29 tests passed across 9 suites.
- Backend: 84 tests passed.
- Legacy API port 5000: startup completed; homepage HTTP 200. Prediction POST `/suggestPlay` returned HTTP 500 (details below).

## Captured logs

These files are local temporary files, not repository artifacts. Server logs continue to receive output while the processes run; test/build logs are snapshots.

- `/private/tmp/digitaloc-frontend.log`
- `/private/tmp/digitaloc-dashboard.log`
- `/private/tmp/digitaloc-legacy.log`
- `/private/tmp/digitaloc-production-build.log`
- `/private/tmp/digitaloc-frontend-tests.log`
- `/private/tmp/digitaloc-backend-tests.log`
- `/private/tmp/digitaloc-smoke-checks.json`
- `/private/tmp/digitaloc-inference-check.json`

## Confirmed legacy inference failure

The live `/suggestPlay` smoke request (KC vs BUF, second-and-six, 45 yards to goal) returned HTTP 500. The traceback ends at `backend/model_trainers/run_model.py:347`:

```text
ValueError: Missing predictions for targets: ['run_gap', 'run_location', 'offense_formation', 'personnel_off']
```

Request ID: `12c522d844364b34a1cae4308625a803`. The loaded run artifact hash logged by the service is `cb665e3c5b117699`. This demonstrates that the downloaded release artifact does not satisfy the current candidate predictor's expected outputs. Align the release artifact schema with the predictor and verify real inference before deploying the legacy flow. Unit tests passing did not detect this live release-artifact mismatch. The dashboard comparison endpoint on port 5001 passed independently.

Final legacy probe results are in `/private/tmp/digitaloc-legacy-smoke.json`; the earlier general smoke file records the temporary connection refusal during loading. The legacy log also contains a pandas DataFrame fragmentation performance warning, which is separate from the fatal missing-target error. No model/schema fix was made in this logging task.

## Observed warnings and runtime issues

1. **Legacy model library mismatch.** Python 3.12 has scikit-learn 1.8.0, while downloaded estimators identify training version 1.7.2. Startup emits `InconsistentVersionWarning`. Use a separate environment matching the artifacts' training dependencies, or retrain/re-export under the deployment environment. Requirements are currently unpinned. Do not silently downgrade the environment shared with the dashboard model.
2. **Startup downloads.** `backend/app.py` downloads six model artifacts during import, before it can serve HTTP. The first port-5000 probe was refused while model loading continued. This creates network, memory, and cold-start risks. Cache/package versioned models and log per-artifact load timing in a follow-up change.
3. **Frontend maintenance warnings.** Browserslist data is old; webpack dev-server reports deprecated setup hooks. These did not prevent the CI-mode production build.
4. **Earlier compile failure fixed locally.** The duplicate/overlapping Results page update handler is fixed and the tests pass. The certificate fix uses certifi while retaining TLS verification. Both fixes must be included in a deployment commit; a working local tree is not proof the deployed revision contains them.

## Deployment findings

### High priority: frontend API URLs

Dashboard requests default to `http://127.0.0.1:5001`; legacy requests default to `http://localhost:5000`. In production these addresses target the visitor's computer. Configure public HTTPS URLs using `REACT_APP_DASHBOARD_API_URL` and `REACT_APP_BACKEND_URL` before building. CRA embeds these settings at build time, so changing them requires a new build. Check both Production and Preview scopes. Never put credentials in `REACT_APP_*` values.

Reference: https://create-react-app.dev/docs/adding-custom-environment-variables/

### High priority: dashboard CORS

The backend defaults to allowing only localhost:3000 and 127.0.0.1:3000. A request with Origin `https://digital-oc-sigma.vercel.app` returned no Access-Control-Allow-Origin header in this local configuration. Set `DIGITALOC_ALLOWED_ORIGINS` on the API host to the exact intended frontend origins, comma-separated. Production/preview values were not inspected remotely.

### High priority if deploying the backend to Vercel: persistence

The dashboard writes sessions and reviews to local SQLite under `backend/instance`. Vercel Functions do not provide persistent local storage for this database. Moving it to `/tmp` would not make sessions durable. Keep the backend on a host with durable storage, or migrate persistence to a hosted database before moving it into functions.

Reference: https://vercel.com/kb/guide/is-sqlite-supported-in-vercel

### Model and data provisioning

The dashboard baseline artifact is gitignored and must be provisioned separately; a clean deployment without it reports model unavailable. Historical CSV data occupies approximately 680 MB locally. If packaging a Python function, explicitly control included files and verify artifact/dependency sizes against runtime limits. Do not assume the complete local backend directory will fit or load efficiently.

Reference: https://vercel.com/docs/functions/limitations

### Frontend project root and client routing

The npm project is in `frontend/`, with build command `npm run build` and output `build`. A repository-root npm build without a root-directory setting would fail because there is no root package.json. No tracked vercel.json or local .vercel project linkage was found. Confirm the CRA preset and test direct navigation/reload on `/dashboard`, `/preview`, `/situation`, and `/result`. Configure a SPA fallback if the deployed project does not supply one. Its absence in the repository alone does not prove deployed routing is broken.

References: https://vercel.com/docs/frameworks/frontend/create-react-app and https://vercel.com/docs/routing/rewrites

### Production API operation

`python app.py` launches Flask debug mode; it is a local-development command. Use a production WSGI entry point for a hosted legacy API. Dashboard session endpoints currently have no authentication or session-level access controls; add those before exposing real team records publicly.

### Results page response-shape risk

The scouting panel directly dereferences `scoutingReport.pbp_tendency` and maps nested arrays. A truthy but incomplete scouting report can crash that panel. Current tests do not cover malformed scouting reports; add response validation or guarded rendering before relying on the legacy panel in production.

## Recommendation

Deploy the frontend to Vercel with explicit HTTPS API settings. Keep the Python services and durable database on a suitable backend host, provision tested model versions, and verify CORS and direct-route reloads against a preview deployment. Local passing tests are not confirmation of remote deployment health.

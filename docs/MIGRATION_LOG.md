# Migration Log

## Phase 0 — safety net and claim inventory

Date: 2026-09-29

### Repository safety

- Tag `demo-v1-synthetic` was created at the pre-migration `main` commit and pushed to `origin`.
- Branch `migration/real-data` was created from that commit and is the active branch.
- The supplied `MIGRATION_PLAN.md` and `SIH26059_Documentation.md` remain unchanged inputs.

### Baseline tests

Command: `cd backend && pytest tests/test_api.py -v`

The first local attempt required installing missing Python dependencies (`slowapi`, `loguru`, `pydantic-settings`, and related requirements). The successful exact test output is preserved in `docs/baseline-test-output.txt`:

```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-8.4.1, pluggy-1.6.0
collecting ... collected 33 items
...
============================= 33 passed in 18.25s =============================
```

All 33 tests passed.

### Demo screenshot status

`docker compose up --build` initially failed because `docker-compose.yml` had duplicate top-level `services`, `volumes`, and `networks` mappings. After the minimal repair retaining the explicit demo-mode service definition, Docker could not connect to the local Docker Desktop Linux engine (`npipe:////./pipe/dockerDesktopLinuxEngine`; daemon not running). Therefore the eight screenshots could not be produced in this environment and no screenshot has been fabricated. The required destination `docs/screens/demo-v1/` is reserved for the capture once Docker is available.

### Numeric claim inventory to reproduce or remove in Phase 12

Every item below is transcribed from `README.md`, `PROJECT_PLAN.md`, `DATA_SOURCES.md`, or `MODEL_EVALUATION.md`; none is treated as validated real-data evidence.

- Synthetic/demo seed: `42`; demo training set: `8,100` samples; held-out split: `20%`; time split stated as `80/20`.
- Sea-ice RF: `50` estimators, max depth `8`, `16` features; horizons `24h`, `48h`, `72h`, and `7 days`/`168h`.
- Sea-ice table: 24h MAE/RMSE/skill `0.0088/0.0126/0.811`; 48h `0.0069/0.0100/0.827`; 72h `0.0088/0.0130/0.811`; README headline skills `0.81`, `0.83`, `0.81`; MODEL_EVALUATION also claims 24h skill `0.52`.
- Iceberg errors (km): `1h 1.8/1.8`, `6h 5.2/6.1`, `12h 9.8/11.4`, `24h 18.3/22.7`, `48h 31.5/38.2`, `72h 44.1/52.8`.
- Iceberg model constants: wind drag `3%`; uncertainty `2 km + 0.42 km/h × hours`; README rounds this to approximately `0.4 km/h`; horizons are `1h`, `6h`, `12h`, `24h`, `48h`, `72h`.
- Risk bands: Low `0.00–0.25` / observed `0.05–0.23`; Moderate `0.25–0.50` / `0.26–0.48`; High `0.50–0.75` / `0.51–0.73`; Extreme `0.75–1.00` / `0.76–0.95`.
- Risk weights: sea ice `0.35`, iceberg `0.30`, weather `0.20`, ocean `0.15`.
- Routing: A* on an 8-connected grid; resolution `1.0° ≈ 111 km`; `2,000` max iterations; typical solve `<2 seconds`; coverage `80°S–55°S`; README says `25×360` cells; proposed production resolution `0.1°–0.25°` and evaluation notes `0.25°`.
- Route comparison: shortest `820 km`, `37` fuel, High, `1.00`; safest `940 km`, `43` fuel, Low, `1.12`; fuel-efficient `870 km`, `39` fuel, Moderate, `0.94`; balanced `890 km`, `40` fuel, Moderate, `1.05`.
- Agent latency/token claims: rule-based `<0.5s`, `2–4` tool calls; GPT-4o-mini `2–5s`, `3–6`; Gemini Flash `1–4s`, `3–5`; Groq `0.5–2s`, `3–6`.
- Coverage/data claims: NSIDC grid `25 km`; ERA5 `0.25°`, hourly, `1940–present`; Copernicus Marine `0.083°`, daily, `10-day` forecast; G02202 daily `1978–present`; demo SIC grid `100×100`; Antarctic crop `lat < –50°`; live iceberg list updated `1–2×/week`; route risk simulation steps `10`, `15–20`, `22–25`, and `30`; A-76A dimensions `135×26 km`; historical iceberg coverage through approximately `2022`; model requirement `5+ years` of NSIDC data.
- Repository/test claims: Python `3.11+`, FastAPI `0.104+`, PostgreSQL `15`, PostGIS `3.3`, SQLAlchemy `2.0`, React `18`, `33` API tests, `9` tables, `11` routers, `10` agent tools, and eight frontend pages.
- Time claims in the demo procedure: dashboard `0:00`, sea ice `1:00`, icebergs `2:00`, route planner `3:00`, AI `3:45`, simulation `4:30`, total five-minute demo.

Phase 12 must reproduce these from scripts/result files or remove them; hand-entered README values are not evidence.

### Phase 0 deviation

The compose repair is recorded here because the checked-in file was not parseable despite the documented Docker workflow. Screenshot capture remains blocked by the unavailable Docker daemon. No synthetic screenshots or substitute runtime evidence were created.


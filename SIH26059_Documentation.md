# SIH 2026 — Problem Statement 26059

## AI-Enabled Antarctic Sea-Ice, Iceberg Trajectory, and Navigation Decision Support System

*Build Documentation — Part 1 of 3: Overview, Problem Analysis, Architecture, Data, and Model Design*

| Field | Detail |
| ----- | ----- |
| Problem Statement ID | 26059 |
| Organization | Ministry of Earth Sciences (MoES) — National Centre for Polar and Ocean Research (NCPOR) |
| Category | Software |
| Theme | Transportation & Logistics |
| Deadline | 30 September 2026 |
| Official brief | Develop an AI/ML-enabled decision support platform capable of forecasting Antarctic sea-ice concentration, predicting iceberg trajectories, and identifying safe and fuel-efficient navigation routes for research vessels using satellite, oceanographic and meteorological datasets. |

> **How this document set is organised.**
> **Part 1** (this file section) explains the problem, the architecture, the data, and the model design.
> **Part 2** is the **Implementation Plan**: exact repository layout, interfaces, algorithms, and acceptance tests. Hand it to a coding agent as the source of truth.
> **Part 3** is the **Phase-Wise Build Prompts**: copy-paste prompts, one per build phase, each pointing back to Part 2.
> Commit the whole file to the repository as `docs/IMPLEMENTATION_PLAN.md` on Day 1 so every phase prompt can say "see §X" and the agent reads it directly instead of relying on conversation memory.

---

# 1. Executive Summary

This system helps a research-vessel navigator answer four questions before committing a ship to a route in Antarctic waters:

1. **What does the ice look like now?** (sea-ice concentration, tracked icebergs, wind, currents)
2. **What will it look like over the next several days?** (sea-ice concentration forecast, iceberg drift forecast)
3. **Where is it dangerous for *my* ship?** (ice risk for a given ice class, with uncertainty)
4. **What route balances safety, time, and fuel?** (two or three ranked route options, each explained)

It is a **human-in-the-loop decision-support tool**, not an autonomous navigation system. It recommends; the master decides. Every screen says so, and every forecast carries an uncertainty statement.

## 1.1 What makes this problem hard, honestly

1. **Beating a trivial baseline is genuinely difficult.** Sea-ice concentration changes slowly. At a one-day lead, "tomorrow equals today" (*persistence*) is already very close to optimal. A model that reports a low error but loses to persistence has learned nothing useful. At least one public prototype for this very problem statement reports that its trained forecaster is beaten by persistence at the leads it tested (this is that project's own reported result, not something verified here). This project treats **skill against persistence, not raw error, as the headline metric** (§8).
2. **Most of the domain is trivially easy.** On a Southern Ocean grid, most cells are either open water or solid pack, and in one public prototype for this problem statement the large majority of the domain was trivially predictable. The exact share for *your* domain is something Phase 2 must measure and report, not assume. A single averaged error score can hide the only region that matters, the marginal ice zone. Every metric here is therefore **stratified by ice regime** (§8.3).
3. **Iceberg data is sparse.** The live tracked-iceberg list holds only a few dozen large tabular bergs, updated once or twice a week. Fragments and growlers, the smaller bergs that are actually dangerous to a hull, are not tracked. The system must say so rather than imply full coverage.
4. **Three heterogeneous data sources on three different grids and clocks.** Satellite passive-microwave sea ice (polar stereographic grid), ERA5 wind (regular lat/lon), and ocean currents (a third grid) must be regridded, time-aligned, and unit-checked. Silent unit and projection bugs are the most likely way this project produces a plausible-looking but wrong result.
5. **Data leakage is easy to commit and hard to see.** A random train/test split over a daily time series leaks the future into training. The whole evaluation design (§8.2) is built to make leakage structurally difficult.
6. **Routing must be safe by construction.** A route planner that silently falls back to a fake or stale ice field is worse than one that refuses. The system refuses (§7.4).

## 1.2 What this document is honest about

* **Every accuracy number in the final submission comes from a held-out evaluation this project runs itself**, against stated baselines, with stated sample sizes. No number is quoted from an upstream model card or a paper.
* **"Real data" and "real time" are different claims.** Reanalysis products (ERA5, GLORYS) lag real time by days to months. The system states the timestamp of every layer it shows. If a layer is stale or unavailable, the interface says so instead of substituting an estimate.
* **Not everything here is machine learning, and that is correct.** The ice risk index implements a published regulatory standard. The fuel model implements a physical relationship. Neither has learned parameters, and neither is presented as "AI." Replacing a regulatory standard with a neural network would make the system worse, not more advanced.
* **No simulated data sources.** Where data is missing, the API returns an explicit `unavailable` marker.

## 1.3 What this project does differently from the public prototypes

Several public repositories already address this problem statement. They generally share one architecture: a sea-ice forecaster, an iceberg drift model, and an A* route planner behind a map dashboard. Building the same thing again does not score well. This project's deliberate differentiators are:

| Differentiator | Why it matters |
| ----- | ----- |
| **Persistence-relative evaluation as the headline** (skill score, stratified by ice regime) | Exposes whether the model has learned anything. Most prototypes report raw MAE, which is dominated by trivial open water. |
| **Direct multi-horizon sea-ice model** (predict +1…+7 days in one pass, not rolled out autoregressively) | Autoregressive rollout compounds error; a direct model does not. |
| **Physics-anchored residual iceberg model** (drift = physics baseline + learned correction) | Uses the data we have, without pretending a few dozen bergs can train a deep network. |
| **Sea-ice/iceberg coupling** (berg speed depends on whether it is locked in pack ice) | Bergs in dense pack drift with the ice; bergs in open water drift with current and wind. |
| **Uncertainty from held-out error, by ice regime** | A navigator needs to know where the model is weak. |
| **Hard-constraint routing** (ice-class limits, no-go zones, refuse-on-missing-data) | Safety behaviour a jury can test live. |
| **Route explanation** (why this route, what the risk drivers are) | Decision support, not a black box. |

---

# 2. Problem Definition

## 2.1 Why this exists

India's Antarctic research voyages (Bharati and Maitri stations) move through a changing and poorly forecast ice environment. Route decisions still lean heavily on expert judgement reading current ice charts, which describe the present rather than predict the near future. The cost of a wrong call ranges from lost days and burned fuel to a vessel beset in ice or damaged by a berg.

## 2.2 The specific gap

* Ice charts show **today**. Planning needs **the next several days**.
* Iceberg information is sparse, infrequently updated, and gives a position rather than a drift forecast.
* Wind, current, and ice data live in separate portals with different formats and grids.
* There is no single decision view that turns forecasts into ranked, explained route options for a particular ship.

## 2.3 Users

| User | What they need |
| ----- | ----- |
| **Voyage planner** (ashore, NCPOR) | Multi-day outlook, route comparison before departure |
| **Ship's master / navigator** | Current picture, short-range forecast, route options with reasons |
| **Reviewer / scientist** | Model performance, data lineage, limitations |

## 2.4 Constraints the build must respect

1. **Human-in-the-loop only.** No feature may present itself as autonomous control.
2. **Never fabricate.** Missing data yields `unavailable`, never an invented value.
3. **State provenance.** Every layer carries a source, a timestamp, and a resolution.
4. **Report uncertainty.** Every forecast is shown with a stated error envelope.
5. **Open, freely-downloadable data only.**
6. **Reproducible.** Every reported number regenerates from a script.
7. **Degrade safely.** If a forecast model is unavailable, routing refuses rather than using a weaker substitute silently.

## 2.5 Jury-facing questions this design is built to answer

| Question | Where the answer lives |
| ----- | ----- |
| Who actually faces this problem today? | §2.1: NCPOR planners and masters on Bharati/Maitri voyages |
| This already exists. Why yours? | §1.3: persistence-relative evaluation, direct multi-horizon model, hard-constraint routing |
| How do you know the model works? | §8: skill against persistence, stratified by ice regime, with sample sizes |
| What if your data is missing or stale? | §7.4: refuse-on-missing-data, `unavailable` markers |
| Is this safe to use at sea? | §1.2 and §7: decision support only, hard constraints, uncertainty always shown |

---

# 3. System Architecture

## 3.1 Layered view

```
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 5 — PRESENTATION                                              │
│ Map dashboard · forecast slider · route comparison · uncertainty     │
│ · data-status panel · model-evaluation page                          │
└───────────────────────────────▲─────────────────────────────────────┘
                                │ REST (FastAPI)
┌───────────────────────────────┴─────────────────────────────────────┐
│ LAYER 4 — DECISION                                                  │
│ Ice-risk engine (ship-class aware) · cost-grid builder ·             │
│ time-dependent route planner · fuel estimator · route explainer      │
└───────────────────────────────▲─────────────────────────────────────┘
                                │
┌───────────────────────────────┴─────────────────────────────────────┐
│ LAYER 3 — PREDICTION                                                │
│ (a) Sea-ice concentration forecaster (direct multi-horizon)          │
│ (b) Iceberg drift model (physics baseline + learned residual)        │
│ (c) Uncertainty tables (held-out error by ice regime)                │
└───────────────────────────────▲─────────────────────────────────────┘
                                │
┌───────────────────────────────┴─────────────────────────────────────┐
│ LAYER 2 — HARMONISATION                                             │
│ Common analysis grid · regridding · time alignment · unit checks ·   │
│ land mask · missing-data flags · provenance metadata                 │
└───────────────────────────────▲─────────────────────────────────────┘
                                │
┌───────────────────────────────┴─────────────────────────────────────┐
│ LAYER 1 — INGESTION                                                 │
│ Sea ice (OSI SAF / NSIDC) · ERA5 wind & temperature · ocean currents │
│ (Copernicus Marine) · iceberg positions (BYU / USNIC) · bathymetry   │
└─────────────────────────────────────────────────────────────────────┘
```

## 3.2 Design principles (non-negotiable, applied in every phase)

1. **Baselines first.** No model is trained until persistence and climatology baselines exist and are evaluated on the same split. A model is only "good" if it beats them.
2. **Time-based splits only.** Train, validation, and test sets are contiguous, non-overlapping time blocks with a gap between them. Random splits are forbidden.
3. **One analysis grid.** Everything is regridded to a single documented grid before any modelling. The grid, its projection, and its land mask are defined once.
4. **Units are asserted, not assumed.** Every ingest function checks and records units. Wind is m/s, currents are m/s, concentration is a 0–1 fraction (or 0–100, but one, declared everywhere), positions are decimal degrees.
5. **Never fabricate.** No synthetic fill for missing data, anywhere in the serving path. Training-time augmentation, if used, is tagged and reported separately.
6. **Provenance on every array.** Source, product ID, retrieval date, valid time, and resolution travel with the data.
7. **Uncertainty is a first-class output.** No forecast leaves the API without an error envelope.
8. **Refuse rather than mislead.** If the ice field for a requested time is unavailable, the route planner raises an explicit error.
9. **Deterministic and reproducible.** Fixed seeds, pinned dependencies, and scripts that regenerate every reported number.
10. **Every claim is tested.** Any statement in the README has a script that reproduces it.

---

# 4. Data Program

## 4.1 Dataset inventory

| Need | Source | Access | Role | Notes |
| ----- | ----- | ----- | ----- | ----- |
| Sea-ice concentration (daily, Southern Hemisphere) | Copernicus Marine, OSI SAF global sea-ice concentration / edge / type / drift, product `SEAICE_GLO_SEAICE_L4_NRT_OBSERVATIONS_011_001` | Free Copernicus Marine account | **Primary ML target** | Near-real-time observational analysis, not a forecast. Verify exact record start and grid from the product manual before downloading. |
| Sea-ice long history | NSIDC passive-microwave sea-ice concentration (SMMR, SSM/I, SSMIS, AMSR2) | Free NASA Earthdata login | Longer training record, independent cross-check | Different grid and algorithm than OSI SAF, so **do not mix in one training set without documenting the offset**. |
| Sea-ice extent (long, low-dimensional) | NSIDC Sea Ice Index daily extent CSV | Public | Sanity checks, climatology | Summary product, not a training grid. |
| Wind (10 m u/v), 2 m temperature | ERA5 reanalysis (Copernicus Climate Data Store) | Free CDS account | Forcing for iceberg drift and ice advection features | Reanalysis, so lags real time. **Never present as a live forecast.** |
| Surface ocean currents (u/v) | Copernicus Marine global physics products (analysis/forecast and multi-year reanalysis) | Free Copernicus Marine account | Drift forcing | Confirm exact product ID, depth level, and variable names when downloading. |
| Iceberg positions | BYU Scatterometer Climate Record Pathfinder consolidated Antarctic iceberg database (historical) and USNIC live list | Public download | Iceberg drift training and live positions | Historical database is far richer than the live table. The live list is only a few dozen large bergs, updated weekly. |
| Sea-surface temperature (optional) | Copernicus Climate Change Service satellite SST record | Free CDS account | Optional ancillary feature | Not required for the core build. |
| Bathymetry / land mask | GEBCO or similar | Public | Grounding and land exclusion for routing | Needed to keep routes off the coast. |

> **Verify before you rely on it.** Product names, IDs, date ranges, and grid definitions above come from the project's earlier data survey and from the providers' public documentation. Before Phase 1 begins, run the dataset-verification step in §10 (Phase 0 of the build) and record the *actual* grid size, projection, date range, variable names, and fill values in `docs/DATA_LINEAGE.md`. Do not trust any number in this document over the file you downloaded.

## 4.2 Honest data limitations

| Limitation | Consequence | How the system responds |
| ----- | ----- | ----- |
| Iceberg live list is sparse (tens of bergs) and updated 1–2×/week | Cannot forecast fragments; drift targets are noisy | State coverage on the map; report drift error with sample size; do not claim complete iceberg detection |
| Iceberg positions are snapshots, not velocities | Velocity must be derived by differencing | Derived-velocity step documented with the time gap as a feature; discard pairs with large gaps |
| Reanalysis lags real time | Serving "current" conditions needs a different source than training | Timestamp every layer; refuse or flag when the newest available data is older than a set threshold |
| OSI SAF and NSIDC use different algorithms | Concentration values differ slightly between products | Train and evaluate on one product only; use the other as an independent check |
| Passive-microwave concentration is unreliable near the coast and in melt season | Noisy target in exactly some of the most relevant areas | Apply the provider's status/quality flags; report error by season |
| No dated ice-thickness data in the core stack | Cannot model ice strength directly | Use concentration and (where available) ice type as proxies; state this in the risk explanation |

## 4.3 The common analysis grid

All layers are regridded to one grid before modelling.

* **Projection:** an Antarctic polar stereographic projection (EPSG:3031 or the NSIDC south polar stereographic grid, EPSG:3412). Choose one in Phase 0 and record it. Sea-ice products are natively in this family, so this minimises resampling of the primary target.
* **Resolution:** match the sea-ice product's native grid where possible. Regrid wind and currents *to* it, not the reverse.
* **Domain:** the Southern Ocean sector relevant to India's voyages plus a margin, defined once in `config/domain.yaml`. A regional crop keeps training tractable.
* **Land mask:** one fixed mask derived from the sea-ice product's land flag, cross-checked against bathymetry.
* **Time axis:** daily, UTC, with a documented convention for what "day D" means for each product.

## 4.4 Data-quality checks (run automatically on every ingest)

1. Units and value ranges (for example, concentration within 0–1, wind speed below a plausible physical maximum).
2. Fill-value and flag handling (mask, never zero-fill).
3. Coordinate sanity (grid spacing, monotonic axes, projection attributes present).
4. Temporal continuity (gaps reported, never silently interpolated).
5. Cross-product consistency (for example, ERA5 wind direction convention checked against a known case).

---

# 5. Iceberg Data Handling

## 5.1 Two datasets, two roles

* **Historical database (training).** Hundreds of thousands of position records across decades. Used to derive drift examples.
* **Live list (serving).** A few dozen large tabular bergs, updated weekly. Used as the starting positions for a forecast.

## 5.2 Deriving drift training examples

For each iceberg track, take consecutive position pairs `(t0, p0)` and `(t1, p1)` with a bounded time gap. The example is:

* **Inputs (features):** starting position, month, ERA5 wind and ocean current sampled at the start position and time, local sea-ice concentration, distance to coast or ice edge, recent prior velocity where the previous gap is short enough.
* **Target:** displacement (east, north) over the interval, normalised to a per-day velocity.

Rules:
* Discard pairs whose time gap exceeds a stated maximum, because long gaps hide the drift path.
* Discard pairs implying physically impossible speeds (calving or break-up events register as position jumps).
* Split by **iceberg identity and time**, never by row, so the same berg cannot appear in both train and test.
* Convert longitude with care at the dateline (use sine/cosine encoding for features, and compute displacement in a projected metric space, not in raw degrees).

## 5.3 What is honest to claim

With tens of thousands of usable position pairs from the historical record, a lightweight model is defensible. A deep sequence network trained on a handful of live bergs is not. The drift model is therefore a **physics baseline plus a small learned residual** (§6.2), and results are reported against a constant-velocity baseline with sample sizes.

---

# 6. Model Design

## 6.1 Sea-ice concentration forecaster

**Goal:** forecast daily concentration maps for leads +1 to +7 days.

**Framing:** spatiotemporal image-to-image regression. Given the last *N* daily concentration maps (plus optional forcing fields), predict the maps at each lead.

**Recommended architecture (in order of build):**

| Step | Model | Purpose |
| ----- | ----- | ----- |
| 1 | **Persistence** | Baseline: forecast(lead) = today |
| 2 | **Climatology** | Baseline: day-of-year mean concentration |
| 3 | **Damped persistence / anomaly persistence** | Baseline: persist the anomaly and relax it toward climatology; often hard to beat |
| 4 | **Per-pixel gradient-boosted or linear model on lagged features** | Cheap learned model; frequently competitive |
| 5 | **Direct multi-horizon U-Net** (input: last N days + forcing; output: one map per lead in a single forward pass) | The main deep model |

**Why direct multi-horizon, not autoregressive rollout.** An autoregressive model feeds its own output back in for each additional day. Small errors compound, and by the fifth to seventh day the forecast is often worse than climatology. A direct model outputs every lead in one pass, so errors do not compound through recursion. It is the correct design for leads beyond +1.

**Inputs to consider:** past concentration maps; ERA5 10 m wind (ice advection); ERA5 2 m temperature (freeze and melt); day-of-year encoded as sine and cosine; land mask; optionally ocean current.

**Loss:** predict the *change* from persistence (residual learning) rather than the absolute field. This makes "do nothing" the default and forces the network to earn every departure from it. Weight the loss toward the marginal ice zone so the trivial open-water majority does not dominate training.

**Training discipline:**
* Time-based split with a gap of at least the maximum lead between blocks.
* Normalisation statistics computed on the training block only.
* Fixed seeds; the checkpoint hash and training config are stored with the model.
* Report skill against persistence and against damped persistence at every lead, stratified by regime (§8).

## 6.2 Iceberg drift model

**Physics baseline.** A large iceberg drifts under the combined action of ocean current, wind drag, and (when embedded in pack ice) the motion of the surrounding ice. A widely used simplified relation is that the berg velocity is approximately the surface current plus a small fraction of the wind velocity. Treat the wind coefficient as a fitted parameter, not a constant taken on trust.

**Learned residual.** Train a small model (gradient-boosted trees or a small MLP) to predict the *difference* between the observed displacement and the physics-baseline displacement, from the features in §5.2. The final forecast is baseline plus residual.

**Coupling to sea ice.** Include local sea-ice concentration as a feature and as a gate. In dense pack ice, a berg tends to move with the ice; in open water, it responds to current and wind. Let the model learn the transition from the data instead of hard-coding it.

**Uncertainty.** Report the held-out RMS position error at the relevant lead, and draw the forecast as a circle whose radius is that error. A forecast position is the centre of a circle, not a point.

**Multi-day forecast.** For leads beyond one interval, step the model forward using forecast wind and current at each step. State clearly that error grows with lead and report it per lead.

## 6.3 Baselines the iceberg model must beat

| Baseline | Definition |
| ----- | ----- |
| Stationary | Berg does not move |
| Constant velocity | Last observed velocity persists |
| Physics only | Current plus wind-drag term, no learning |

The learned residual is only worth shipping if it beats all three on held-out data.

## 6.4 Ice-risk engine (not machine learning)

Implements a published regulatory approach: a risk index built from ice concentration and ice type, combined with the vessel's ice class, to decide whether transit is permitted, permitted with caution, or prohibited. Implementation notes:

* Encode the index tables as data, not code, so they can be audited.
* Use the ship's ice class as a required input; risk is meaningless without it.
* Where ice-type data is unavailable for a cell or date, fall back to the more conservative interpretation and flag it.
* Verify the exact table values against the published standard before coding them. **Do not reproduce values from memory.**

## 6.5 Fuel estimator (not machine learning)

A physical approximation: fuel use scales with distance and with a speed-dependent power demand, and ice reduces achievable speed. Use a transparent, documented formula with stated assumptions and an explicit note that it is an estimate for comparing routes, not an engine model. Only relative comparisons between candidate routes are meaningful.

## 6.6 Route planner

**Approach.** Build a cost grid from forecast ice risk, forecast iceberg exclusion zones, and distance, then search with a time-aware A* (or Dijkstra) so the cost of a cell depends on when the ship would arrive there.

**Hard constraints (routes never violate these):**
* Cells where the ice-risk engine says "prohibited" for the ship's class are impassable.
* Land and shallow cells are impassable.
* A safety buffer around forecast iceberg positions, sized from the drift model's uncertainty radius.

**Soft costs (traded off):** distance, time, estimated fuel, ice-risk exposure.

**Outputs:** typically three options, for example *fastest*, *safest*, *balanced*. Each returns the path, estimated time, estimated fuel, maximum and mean risk along the route, and a short generated explanation of the main risk drivers.

**Refusal rule.** If the ice field for any required time is unavailable, or the start or goal is impassable, the planner raises a typed error with a human-readable reason. It never falls back to climatology or to an assumed-open ocean.

---

# 7. Serving Architecture and Safety Behaviour

## 7.1 Backend

A FastAPI service exposes forecasts, icebergs, risk, routing, uncertainty, and system status. Models load at startup and report their own health.

## 7.2 Required API surface

| Endpoint | Purpose |
| ----- | ----- |
| `GET /api/system-status` | State of every component and the timestamp of the data behind each layer |
| `GET /api/ice/current` | Latest concentration map with provenance |
| `GET /api/ice/forecast?lead=N` | Forecast map at lead N with the error envelope |
| `GET /api/icebergs` | Tracked bergs with position, observation time, and coverage disclaimer |
| `GET /api/icebergs/forecast?lead=N` | Forecast positions with uncertainty radius |
| `GET /api/risk?ice_class=…&lead=N` | Risk grid for a ship class |
| `POST /api/route` | Route options for a start, goal, ice class, and departure time |
| `GET /api/uncertainty` | Held-out error by ice regime and lead |
| `GET /api/model-status` | Per-model health, hash, and evaluation summary |

## 7.3 Frontend

A map-first dashboard: layer toggles (ice, risk, icebergs, wind, currents), a forecast-day slider, a route-comparison panel, an always-visible data-status strip showing source and age for each layer, and a model-evaluation page. Every forecast layer shows its uncertainty. A persistent banner states that the tool is decision support only.

## 7.4 Safety behaviours (all testable)

| Behaviour | Test |
| ----- | ----- |
| Missing ice field returns `unavailable`, not a value | Delete a day of data, call the endpoint |
| Routing raises on missing forecast | Request a route with no ice data |
| Impassable start or goal is rejected with a reason | Place start on land or in prohibited ice |
| Stale data is flagged | Set the clock past the freshness threshold |
| Forecast beyond validated lead is refused | Request a lead greater than the maximum evaluated |
| Uncertainty accompanies every forecast response | Schema test on all forecast endpoints |

---

# 8. Evaluation Design

## 8.1 Principle

A model is judged by whether it **beats simple baselines on held-out data, in the regions that matter**, with sample sizes reported.

## 8.2 Splits (leakage prevention)

* Contiguous time blocks: train, then a gap, then validation, then a gap, then test.
* Gap length at least the largest forecast lead.
* Normalisation and thresholds fitted on train only.
* Iceberg data split by berg identity and time.
* The test block is frozen: touched once, for the final report.

## 8.3 Stratification by ice regime

Report every sea-ice metric separately for:

| Regime | Concentration |
| ----- | ----- |
| Open water | below 0.15 |
| Marginal ice zone | 0.15–0.50 |
| Pack | 0.50–0.85 |
| Consolidated | above 0.85 |

Also report the ice-edge band separately (cells near the 0.15 contour), and error by season. A single overall number is not reported alone.

## 8.4 Sea-ice metrics

| Metric | Purpose |
| ----- | ----- |
| MAE and RMSE per lead, per regime | Magnitude of error |
| **Skill score vs persistence**: `1 − MAE_model / MAE_persistence` | Positive means the model beats persistence |
| Skill vs damped persistence and climatology | Stronger baselines |
| Integrated ice-edge error (IIEE) | Area of ice-edge misplacement |
| Sample counts | Every table states n |

## 8.5 Iceberg metrics

| Metric | Purpose |
| ----- | ----- |
| Position error (RMS, median, 90th percentile) per lead | Magnitude |
| Skill vs constant velocity and vs physics-only | Whether learning helps |
| Fraction within 5 / 10 / 25 km | Operational usefulness |
| Sample counts and number of distinct bergs | Honest sample size |

## 8.6 Routing metrics

| Metric | Purpose |
| ----- | ----- |
| Hard-constraint violation rate | Must be exactly zero |
| Route length, time, fuel versus straight line | Cost of safety |
| Refusal correctness | Refuses when it should |
| Runtime per request | Usability |

## 8.7 The rule for reporting

If a model does not beat its baseline at a lead or in a regime, the README **says so**, and the system either does not offer that forecast or labels it as no better than persistence. A negative result reported honestly is a stronger submission than an inflated one.


---
---

# Implementation Plan — SIH 26059

*Part 2 of 3: Build Specification*

> **Audience.** This section is written to be handed directly to a coding agent (for example Claude Code) or a development team. It resolves ambiguity into concrete decisions: file names, interfaces, data shapes, algorithms, edge cases, and acceptance tests.
> **Source of truth.** Part 1 of this document. Where Part 1 explains *why*, this section specifies *what to build*.
> **Paired section.** Part 3 breaks this plan into prompts to feed an agent one phase at a time. Phase prompts refer back here as "per §X."

---

## 0. How to Use This Section

Read it once in full before Phase 0. The layout:

| § | Content |
| ----- | ----- |
| 1 | Resolved technology stack and non-negotiable principles |
| 2 | Repository structure (exact) |
| 3 | Configuration and the common analysis grid |
| 4 | Ingestion layer |
| 5 | Harmonisation layer |
| 6 | Baselines and the evaluation harness (built before any model) |
| 7 | Sea-ice forecaster |
| 8 | Iceberg drift model |
| 9 | Ice-risk engine |
| 10 | Fuel estimator |
| 11 | Route planner |
| 12 | Backend API |
| 13 | Frontend |
| 14 | Uncertainty tables |
| 15 | Testing strategy |
| 16 | Reproducibility and the verification script |
| 17 | Documentation deliverables and README requirements |
| 18 | Risk register |
| 19 | Glossary |

---

## 1. Resolved Technology Stack and Principles

### 1.1 Stack

| Concern | Choice | Reason |
| ----- | ----- | ----- |
| Language (backend, ML) | Python 3.10+ | Ecosystem for geospatial and ML |
| Array / geospatial | `numpy`, `xarray`, `netCDF4` or `h5netcdf`, `pyproj`, `rasterio` (if needed), `scipy` | Standard for NetCDF and regridding |
| Regridding | `xarray` interpolation, or `xesmf` if installable, with `scipy` fallback | Deterministic and testable |
| Classical ML | `scikit-learn`, `lightgbm` or `HistGradientBoosting` | Iceberg residual, per-pixel baseline |
| Deep learning | `PyTorch` | U-Net for sea-ice forecasting |
| Data validation | `pydantic` | Typed schemas for API and config |
| Backend | `FastAPI` + `uvicorn` | Typed, fast, auto-docs |
| Frontend | React + TypeScript + MapLibre GL (or Leaflet) | Map-first UI, free tile options |
| Experiment tracking | Plain JSON/CSV result files committed with the repo, plus optional `mlflow` | Reproducibility without heavy infrastructure |
| Testing | `pytest`, `hypothesis` (property tests), `vitest` or `jest` for frontend | |
| Packaging | `pyproject.toml`, pinned `requirements.lock` | Reproducible installs |

> **Version note.** Do not assume a library version. In Phase 0, install, record the resolved versions in `requirements.lock`, and confirm each imports and works. If a listed library will not install on the target machine, substitute an equivalent and record the decision in `docs/DECISIONS.md`.

### 1.2 Non-negotiable principles

1. **Baselines before models.** Nothing is trained until §6 exists and produces numbers.
2. **Time-based splits.** No random splits anywhere. A test in CI fails if train and test time ranges overlap.
3. **One analysis grid**, defined once in configuration.
4. **Units asserted at ingest**, recorded in metadata, and re-checked at model input.
5. **Never fabricate.** No synthetic data in the serving path. Any training-time augmentation is tagged `synthetic=true` and reported separately.
6. **Provenance on every dataset object** (source, product ID, valid time, retrieval time, resolution, units).
7. **Every forecast carries an uncertainty object.**
8. **Refuse rather than mislead** (typed errors, §11.6).
9. **Every reported number regenerates from a script** and is checked by `verify.py` (§16).
10. **Decision support only.** Wording, banners, and API responses never imply autonomous control.

### 1.3 Explicit scope boundaries

Stated so nobody discovers them late:

* **Not real-time control.** The system supports planning and monitoring, not steering.
* **Not full iceberg detection.** It uses tracked large bergs, not SAR-based detection of small bergs. If SAR detection is added as a stretch goal, it must be labelled as such.
* **Reanalysis-driven.** The historical evaluation uses reanalysis and archive data. Live serving uses the freshest data available and labels its age.
* **Ice thickness not modelled.** Concentration and type serve as proxies. The interface says so.

---

## 2. Repository Structure (exact)

```
sih26059/
├── README.md
├── pyproject.toml
├── requirements.lock
├── Makefile
├── verify.py
├── config/
│   ├── domain.yaml              # analysis grid, domain bounds, projection
│   ├── data_sources.yaml        # product IDs, variables, expected ranges
│   ├── ship_classes.yaml        # ice classes, speed/power parameters
│   ├── risk_tables.yaml         # risk-index tables (as data)
│   └── serving.yaml             # freshness thresholds, max validated lead
├── data/
│   ├── raw/                     # downloaded originals (git-ignored)
│   ├── interim/                 # regridded, aligned (git-ignored)
│   ├── processed/               # model-ready arrays (git-ignored)
│   └── README.md                # how to obtain each dataset
├── docs/
│   ├── IMPLEMENTATION_PLAN.md   # this file
│   ├── DATA_LINEAGE.md          # every dataset, raw → model input
│   ├── DECISIONS.md             # every deviation from this plan, with reason
│   ├── EVALUATION.md            # generated from result JSON
│   ├── ROUTE_COST.md            # the cost function, every term and weight
│   ├── FALLBACK.md              # what happens when data or a model is missing
│   └── models/
│       ├── sea_ice_model_card.md
│       └── iceberg_model_card.md
├── src/sih26059/
│   ├── __init__.py
│   ├── config.py                # loads and validates YAML into pydantic models
│   ├── grid.py                  # AnalysisGrid: projection, coords, land mask
│   ├── provenance.py            # Provenance dataclass, attach/read helpers
│   ├── errors.py                # typed exceptions (§11.6)
│   ├── ingest/
│   │   ├── seaice.py
│   │   ├── era5.py
│   │   ├── currents.py
│   │   ├── icebergs.py
│   │   ├── bathymetry.py
│   │   └── checks.py            # unit/range/flag/continuity checks
│   ├── harmonise/
│   │   ├── regrid.py
│   │   ├── align.py
│   │   └── dataset_builder.py   # builds train/val/test arrays
│   ├── splits.py                # time-block splits + leakage assertions
│   ├── baselines/
│   │   ├── seaice_baselines.py  # persistence, climatology, damped persistence
│   │   └── iceberg_baselines.py # stationary, constant-velocity, physics-only
│   ├── evaluation/
│   │   ├── metrics.py           # MAE, RMSE, skill, IIEE
│   │   ├── regimes.py           # ice-regime masks and stratification
│   │   ├── seaice_eval.py
│   │   ├── iceberg_eval.py
│   │   └── report.py            # writes result JSON + EVALUATION.md
│   ├── models/
│   │   ├── seaice_unet.py       # direct multi-horizon U-Net
│   │   ├── seaice_pixel.py      # per-pixel gradient-boosted model
│   │   ├── iceberg_physics.py   # physics baseline
│   │   ├── iceberg_residual.py  # learned residual
│   │   └── registry.py          # load/save with hash + config
│   ├── training/
│   │   ├── train_seaice.py
│   │   └── train_iceberg.py
│   ├── risk/
│   │   ├── risk_index.py
│   │   └── ice_class.py
│   ├── fuel/
│   │   └── fuel_model.py
│   ├── routing/
│   │   ├── cost_grid.py
│   │   ├── astar.py
│   │   ├── smooth.py
│   │   ├── explain.py
│   │   └── planner.py
│   └── api/
│       ├── main.py
│       ├── schemas.py
│       ├── deps.py
│       └── routes/
│           ├── ice.py
│           ├── icebergs.py
│           ├── risk.py
│           ├── route.py
│           ├── uncertainty.py
│           └── status.py
├── scripts/
│   ├── download_data.py
│   ├── verify_datasets.py       # Phase 0 gate
│   ├── build_dataset.py
│   ├── run_baselines.py
│   ├── train_seaice.py
│   ├── train_iceberg.py
│   ├── evaluate_all.py
│   └── export_models.py
├── models_out/                  # trained artifacts + manifest.json (small ones committed)
├── results/                     # evaluation JSON committed for verify.py
├── tests/
│   ├── unit/
│   ├── property/
│   ├── integration/
│   └── fixtures/                # tiny NetCDF and CSV samples
└── web/
    ├── package.json
    └── src/
        ├── App.tsx
        ├── api/client.ts
        ├── map/MapView.tsx
        ├── map/layers/           # ice, risk, icebergs, wind, currents
        ├── panels/ForecastSlider.tsx
        ├── panels/RoutePanel.tsx
        ├── panels/DataStatusStrip.tsx
        ├── panels/UncertaintyPanel.tsx
        ├── pages/ModelEvaluation.tsx
        └── components/DecisionSupportBanner.tsx
```

---

## 3. Configuration and the Common Analysis Grid

### 3.1 `config/domain.yaml`

Defines, once:

* `projection`: an EPSG code or PROJ string for the Antarctic polar stereographic projection chosen in Phase 0.
* `grid`: x/y origin, spacing (metres), and shape, matching the sea-ice product's native grid.
* `bounds`: the geographic box of interest, expressed in projected coordinates.
* `land_mask_source`: which product flag defines land.
* `time`: `frequency: daily`, `timezone: UTC`, and the convention for "valid day."

### 3.2 `AnalysisGrid` (in `grid.py`)

```python
class AnalysisGrid:
    projection: pyproj.CRS
    x: np.ndarray            # projected easting, metres, monotonic
    y: np.ndarray            # projected northing, metres, monotonic
    land_mask: np.ndarray    # bool [y, x], True = land
    def lonlat_to_xy(self, lon, lat) -> tuple[np.ndarray, np.ndarray]: ...
    def xy_to_lonlat(self, x, y) -> tuple[np.ndarray, np.ndarray]: ...
    def contains(self, x, y) -> np.ndarray: ...
    def cell_area_km2(self) -> np.ndarray: ...   # projected cells are not equal-area in general
```

**Requirements.**
* Round-trip test: `lonlat → xy → lonlat` recovers input within a stated tolerance across the domain, including near the dateline.
* Cell-area correction: any area-weighted metric (for example IIEE) uses `cell_area_km2`, not a constant.
* Provide a helper that converts a projected displacement (metres) to great-circle kilometres for reporting.

### 3.3 `Provenance` (in `provenance.py`)

```python
@dataclass(frozen=True)
class Provenance:
    source: str            # e.g. "Copernicus Marine / OSI SAF"
    product_id: str
    variable: str
    units: str
    valid_time: datetime | None
    retrieved_at: datetime
    resolution_m: float | None
    native_grid: str
    notes: str = ""
```

Every ingested array and every API response derived from data carries one.

---

## 4. Ingestion Layer

### 4.1 Common contract

Each ingest module exposes:

```python
def fetch(start: date, end: date, cfg: SourceConfig) -> list[Path]: ...   # downloads originals
def load(paths: list[Path]) -> xr.Dataset: ...                            # standardised Dataset
def validate(ds: xr.Dataset, cfg: SourceConfig) -> ValidationReport: ...  # §4.6
```

* `fetch` is idempotent: skip files that already exist and pass a size check.
* `load` returns a Dataset with **standard variable names, declared units, and a `Provenance` in `attrs`**.
* Credentials come from environment variables, never from the repository.

### 4.2 `ingest/seaice.py`

* Read the sea-ice concentration variable, the status/quality flag, and the land flag.
* Convert percent to a 0–1 fraction if the source is in percent. Assert the final range.
* Mask, never zero-fill, cells that the flags mark as unreliable or land.
* Record the exact native grid and projection attributes read from the file in `DATA_LINEAGE.md`.

### 4.3 `ingest/era5.py`

* 10 m u and v wind components, 2 m temperature.
* Convert temperature to a single declared unit.
* ERA5 is on a regular lat/lon grid, so regridding to the analysis grid happens in §5.
* **Wind vector rotation.** ERA5 u (eastward) and v (northward) are geographic components. When the analysis grid is polar stereographic, the components must be **rotated into grid-aligned components** before use. This is a classic silent bug. Implement `rotate_to_grid(u, v, lon)` and test it at several longitudes (§15).

### 4.4 `ingest/currents.py`

* Surface eastward and northward current components at the shallowest available level.
* Same vector-rotation requirement as wind.
* Confirm the product's variable names, depth level, and land-fill convention when first downloaded.

### 4.5 `ingest/icebergs.py`

* Parse the historical consolidated database into a normalised table: `berg_id, timestamp (UTC), lon, lat, source_sensor, quality_flag`.
* Parse the live list into the same schema.
* Normalise longitude to a single convention and handle the dateline.
* Drop records with missing coordinates; report how many.
* Preserve berg identity across records, since identity drives the split.

### 4.6 `ingest/checks.py`

Automatic checks returning a `ValidationReport` (list of findings with severity):

| Check | Severity on failure |
| ----- | ----- |
| Units declared and match config | error |
| Value range within physical bounds | error |
| Fill values masked, not present as data | error |
| Coordinate axes monotonic with expected spacing | error |
| Temporal gaps | warning, with list of missing dates |
| Projection attributes present | error |
| Duplicate timestamps | error |

The build fails on any error-level finding.

---

## 5. Harmonisation Layer

### 5.1 `harmonise/regrid.py`

* `regrid_to_grid(ds, grid, method)` maps ERA5 and currents onto the analysis grid.
* Use area-conserving or bilinear interpolation as appropriate; document the choice per variable in `DATA_LINEAGE.md`.
* Cells over land stay masked.
* Test: regrid a smooth analytic field and compare to the analytic value on the target grid (tolerance stated).

### 5.2 `harmonise/align.py`

* Aligns all layers to the daily UTC time axis.
* Where a product is sub-daily (ERA5 hourly), aggregate with a stated rule (for example daily mean) and record it.
* Never interpolate across gaps in the primary target. Gaps are reported and the affected samples excluded.

### 5.3 `harmonise/dataset_builder.py`

Builds model-ready tensors.

For the sea-ice model, each sample is:

```
X: [T_in, C, H, W]   # last T_in days of: concentration, wind_u, wind_v, temp2m, (current_u, current_v optional)
static: [S, H, W]    # land mask, (optional) distance to coast
doy: [2]             # sin/cos day-of-year
Y: [L, H, W]         # concentration at leads 1..L
mask: [H, W]         # valid ocean cells for the loss
```

* `T_in` (input history length) and `L` (maximum lead, default 7) are configuration values.
* A sample is emitted only if all its inputs **and** all its targets exist. Otherwise it is dropped and counted.
* Normalisation statistics are computed from the training block only and stored with the artifact.

---

## 6. Baselines and the Evaluation Harness (built before any model)

### 6.1 `splits.py`

```python
@dataclass(frozen=True)
class TimeSplit:
    train: tuple[date, date]
    val:   tuple[date, date]
    test:  tuple[date, date]
    gap_days: int

def make_time_split(dates, val_frac, test_frac, gap_days) -> TimeSplit: ...
def assert_no_leakage(split: TimeSplit, max_lead: int) -> None: ...
```

* `assert_no_leakage` verifies that no target window (t … t+lead) of a training sample overlaps any validation or test input or target window. It raises on violation.
* The test block should include **every season** (at least one full annual cycle). Do not choose a test block that is only summer or only winter.
* For icebergs, a separate `make_berg_split` splits by berg identity and time.

### 6.2 `baselines/seaice_baselines.py`

```python
def persistence(x_last: np.ndarray, lead: int) -> np.ndarray: ...
def climatology(train_dates, train_fields, target_dates) -> np.ndarray: ...   # day-of-year mean, train only
def damped_persistence(x_last, clim, lead, tau) -> np.ndarray: ...
    # clim + (x_last - clim_today) * exp(-lead / tau), tau fitted on train only
```

* Climatology uses **training data only**. Verify with a test that changing test-period data does not change climatology output.
* `tau` in damped persistence is fitted on train and reported.

### 6.3 `baselines/iceberg_baselines.py`

```python
def stationary(p0) -> Position: ...
def constant_velocity(p0, v_prev, dt) -> Position: ...
def physics_only(p0, current, wind, dt, wind_coeff) -> Position: ...
```

* `wind_coeff` is fitted on train only.

### 6.4 `evaluation/metrics.py`

```python
def mae(y, yhat, mask) -> float: ...
def rmse(y, yhat, mask) -> float: ...
def skill_vs(baseline_err: float, model_err: float) -> float: ...   # 1 - model/baseline
def iiee(y, yhat, mask, area_km2, thresh=0.15) -> float: ...        # km^2 of misplaced ice edge
def position_error_km(true_xy, pred_xy) -> np.ndarray: ...
def bootstrap_ci(values, n=1000, seed=0) -> tuple[float, float]: ...
```

* `skill_vs` handles a zero baseline error without dividing by zero (return `nan` and flag).
* Provide bootstrap confidence intervals so a small positive skill is not over-read.

### 6.5 `evaluation/regimes.py`

```python
REGIMES = {"open": (0.0, 0.15), "mizt": (0.15, 0.50), "pack": (0.50, 0.85), "consolidated": (0.85, 1.0001)}
def regime_masks(reference_field) -> dict[str, np.ndarray]: ...
def edge_band_mask(reference_field, width_cells) -> np.ndarray: ...
```

* Regimes are defined from the **reference field at forecast issue time** (the input the forecaster saw), not from the target, so the stratification is not itself a leak.

### 6.6 Phase gate

`scripts/run_baselines.py` must run end-to-end and write `results/baselines.json` containing every baseline, at every lead, in every regime, with n. Only then may model training begin.

---

## 7. Sea-Ice Forecaster

### 7.1 Interface

```python
class SeaIceForecaster(Protocol):
    max_lead: int
    def predict(self, x: SeaIceInput) -> SeaIceForecast: ...

@dataclass
class SeaIceForecast:
    fields: np.ndarray            # [L, H, W], concentration 0..1, NaN on land
    issue_time: datetime
    valid_times: list[datetime]
    provenance: Provenance
    model_id: str
    model_hash: str
```

### 7.2 Models, in build order

1. `seaice_pixel.py`: per-pixel gradient-boosted model on lagged local features (own history, neighbourhood mean, wind, temperature, day-of-year). Predicts the *change from persistence* per lead. A strong, cheap baseline for the deep model.
2. `seaice_unet.py`: direct multi-horizon U-Net.

### 7.3 U-Net specification

* **Input:** `[T_in * C_dyn + S_static + 2, H, W]` channels (history, forcing, static, day-of-year broadcast).
* **Output:** `[L, H, W]`, the *residual to add to the most recent concentration map*, so the default prediction is persistence.
* **Final activation:** none; add residual to the persistence field, then clamp to `[0, 1]`.
* **Land handling:** input land cells set to a fixed sentinel plus the land-mask channel; the loss ignores land.
* **Loss:** masked L1 (or Huber) on the *concentration* prediction, with a per-cell weight that up-weights the marginal ice zone and the ice-edge band. The weighting scheme is a configuration value and is reported.
* **Regularisation:** weight decay, dropout in the bottleneck, early stopping on validation skill (not validation loss alone).
* **Patch training:** crop random spatial patches for training to fit memory, but evaluate on the full domain.
* **Reproducibility:** fixed seeds, deterministic flags where feasible, config and git hash stored in the artifact.

### 7.4 Training discipline

* Train on the train block; select hyper-parameters on the validation block; touch the test block **once**.
* Early-stopping criterion: validation skill vs persistence in the marginal ice zone at the median lead.
* If the model does not beat persistence on validation, **do not tune indefinitely.** Record the negative result (§7.6).

### 7.5 Known failure modes to test for

| Failure | Check |
| ----- | ----- |
| Model outputs values outside `[0, 1]` | Clamp and assert |
| Model degrades to noise over open water | Open-water error must not exceed persistence |
| Model hallucinates ice over land | Land cells must be NaN |
| Non-finite loss during training | Detect, log, halt; document cause |
| Seasonal bias | Report skill by season |
| Ice-edge smoothing (blurry edge) | Report IIEE and edge-band MAE |

### 7.6 Outcome handling (decided before training)

| Outcome | What the system ships |
| ----- | ----- |
| Model beats persistence and damped persistence in the marginal ice zone at lead L | Serve that model at lead L with its measured error envelope |
| Model beats climatology but not persistence at lead L | Serve **persistence** at lead L, labelled as such, plus the model as an "experimental" layer if desired |
| Model beats neither | Serve the best baseline at that lead, labelled honestly; README reports the negative result |

The **maximum served lead** is the largest lead at which the shipped forecast has a measured, published error. The API refuses longer leads (§12).

---

## 8. Iceberg Drift Model

### 8.1 Data preparation

Following Part 1 §5.2:

1. Build consecutive-position pairs per berg with a bounded time gap (`max_gap_days` in config).
2. Convert positions to projected metric coordinates; compute displacement in metres.
3. Drop pairs implying speed above a physical ceiling (config value) and record the count.
4. Sample ERA5 wind, current, sea-ice concentration and distance to ice edge at the start position and time (mean over the interval where sensible).
5. Split with `make_berg_split` (by berg identity and time).

### 8.2 Interface

```python
@dataclass
class IcebergForecast:
    berg_id: str
    lead_days: list[float]
    positions_lonlat: np.ndarray        # [K, 2]
    uncertainty_radius_km: np.ndarray   # [K]
    observed_at: datetime
    provenance: Provenance
    model_id: str
```

### 8.3 Physics baseline (`iceberg_physics.py`)

```python
def drift_velocity(current_uv, wind_uv, wind_coeff) -> np.ndarray:
    return current_uv + wind_coeff * wind_uv
```

* `wind_coeff` is fitted by least squares on the training pairs (report the fitted value and its confidence interval).
* Step forward with a stated integration scheme (forward Euler at the pair time step is acceptable; state it).

### 8.4 Learned residual (`iceberg_residual.py`)

* Target: observed displacement minus physics-baseline displacement (two components).
* Features: local ice concentration, distance to ice edge, month (sin/cos), speed of the previous interval if available, current and wind speeds, position in projected coordinates.
* Model: `HistGradientBoostingRegressor` per component, or a small MLP. Start with gradient boosting.
* An optional first-stage gate classifies *moving vs stationary* (grounded or locked bergs). If used, report gate accuracy and how many training pairs it removes.

### 8.5 Multi-step forecasting

* Step forward interval by interval using forecast wind and current at each step.
* Report error at each lead separately. Expect error to grow with lead.
* The uncertainty radius at each lead is the held-out RMS position error at that lead (or its 90th percentile, stated).

### 8.6 Acceptance criteria

| Criterion | Requirement |
| ----- | ----- |
| Split integrity | No berg appears in more than one split (asserted in test) |
| Beats constant-velocity | Skill > 0 with bootstrap CI reported; otherwise reported as negative |
| Beats physics-only | Same |
| Sample size stated | Number of pairs and distinct bergs in every table |
| Fitted wind coefficient reported | Value plus confidence interval |

---

## 9. Ice-Risk Engine

### 9.1 Purpose

Given concentration (and ice type where available) and a vessel's ice class, return a risk level per cell.

### 9.2 Data-driven tables

`config/risk_tables.yaml` holds the risk-index values as data, keyed by ice class and ice category. Code reads the table. **Fill the table from the published standard's actual values.** Do not reproduce them from memory. Record the source document and version in `docs/DECISIONS.md`. If the exact table cannot be obtained, implement the engine against a clearly-labelled placeholder table and state prominently in the README that the placeholder is not the regulatory table.

### 9.3 Interface

```python
class RiskLevel(IntEnum):
    OPEN = 0
    LOW = 1
    CAUTION = 2
    HIGH = 3
    PROHIBITED = 4

def risk_grid(concentration, ice_type, ice_class, uncertainty=None) -> np.ndarray: ...
def is_passable(risk) -> np.ndarray: ...   # PROHIBITED → False
```

### 9.4 Rules

* Unknown ice type → treat conservatively and flag the cell.
* Concentration uncertainty raises risk: when the model's regime error is large, evaluate the risk at the upper plausible concentration (`concentration + error_p90`, clamped) so the planner is cautious where the forecast is weak.
* Property tests: risk is non-decreasing in concentration for fixed class and type; a stronger ice class never has a higher risk than a weaker one for the same ice.

---

## 10. Fuel Estimator

* Transparent formula in `fuel_model.py`, documented in `docs/ROUTE_COST.md`.
* Inputs: segment length, ice class parameters, local concentration, optionally wind.
* Model: achievable speed falls with concentration (piecewise or smooth, parameters in `ship_classes.yaml`); power demand is a function of speed; fuel is power × time × specific consumption.
* All constants are configuration values with stated provenance or stated as assumptions.
* **The estimator is for comparing routes**, and outputs are labelled "relative estimate." Never present absolute tonnes as a prediction without stating the assumptions.
* Property tests: fuel is non-decreasing in distance; heavier ice never reduces fuel for the same distance in the same class.

---

## 11. Route Planner

### 11.1 Cost grid (`cost_grid.py`)

For a departure time, build per-time-slice cost grids from:

* forecast concentration → ice risk (§9),
* iceberg exclusion buffers from the drift forecast (buffer radius = uncertainty radius plus a configured safety margin),
* land and shallow-water mask (impassable),
* distance term.

The cost of entering a cell depends on the estimated *arrival time*, which selects the forecast slice.

### 11.2 Search (`astar.py`)

* Time-dependent A* on the analysis grid (8-connected).
* Admissible heuristic (great-circle or projected straight-line distance times the minimum unit cost).
* Cell cost = `w_dist * distance + w_time * time + w_fuel * fuel + w_risk * risk_penalty`.
* Cells with `PROHIBITED` risk, land, shallow water, or inside an iceberg buffer are **infinite cost** (never traversed).
* Weights differ per option: *fastest* (low `w_risk`), *safest* (high `w_risk`), *balanced*.
* If arrival time exceeds the last available forecast slice, the planner either stops with a typed error or continues on the last slice **only if** configuration explicitly allows it, and the response is flagged `beyond_forecast_horizon`.

### 11.3 Smoothing (`smooth.py`)

* Douglas–Peucker simplification followed by a smoothing pass.
* **Every smoothed segment is re-checked against the hard constraints.** If smoothing would cross an impassable cell, keep the unsmoothed segment. A smoothed route may never violate a hard constraint.

### 11.4 Output

```python
@dataclass
class RouteOption:
    label: str                       # "fastest" | "safest" | "balanced"
    waypoints_lonlat: np.ndarray
    distance_km: float
    duration_h: float
    fuel_relative: float
    max_risk: RiskLevel
    mean_risk: float
    beyond_forecast_horizon: bool
    explanation: list[str]           # generated, short, factual
    warnings: list[str]
```

### 11.5 Explanation (`explain.py`)

Generate short factual statements from the route's own data, for example the segment with the highest risk and its concentration, the closest approach to a forecast iceberg, or the reason this option differs from the fastest. **No free-form generative text about the ocean.** Each sentence is templated from numbers the planner computed.

### 11.6 Typed errors (`errors.py`)

```python
class DataUnavailable(Exception): ...
class ForecastHorizonExceeded(Exception): ...
class NoPassableRoute(Exception): ...
class StartOrGoalImpassable(Exception): ...
class StaleData(Exception): ...
```

The API maps each to an HTTP status and a human-readable reason. None is caught and turned into a default route.

### 11.7 Acceptance criteria

| Criterion | Requirement |
| ----- | ----- |
| Hard-constraint violations | Exactly zero across a randomised test suite (property test) |
| Refuses with missing ice field | Raises `DataUnavailable` |
| Rejects impassable start/goal | Raises `StartOrGoalImpassable` |
| No route through closed ice | Raises `NoPassableRoute` rather than a violating path |
| Smoothing safe | Property test: smoothed path never enters an impassable cell |
| Determinism | Same inputs produce the same route |

---

## 12. Backend API

### 12.1 Conventions

* Pydantic schemas in `api/schemas.py`. Every forecast response includes `provenance`, `issue_time`, `valid_time`, `model_id`, and an `uncertainty` object.
* `max_validated_lead` is read from `results/` and `config/serving.yaml`. Requests beyond it return HTTP 422 with a reason.
* A freshness threshold (config) marks a layer `stale` when its newest data is older than the threshold; the response includes `stale: true` and the age.

### 12.2 Endpoints

As listed in Part 1 §7.2, each with a request schema, a response schema, and example payloads in `docs/API.md`.

### 12.3 `GET /api/system-status`

Returns, per component (each ingest source, each model, the risk engine, the planner): `state` (`ok | degraded | unavailable`), the newest valid time, the age, and the reason for any degraded state.

### 12.4 Model loading

`models/registry.py` loads each artifact, verifies its SHA-256 against `models_out/manifest.json`, runs a tiny smoke inference, and records the outcome. A model that fails its check is marked `unavailable`; the API never silently substitutes another.

---

## 13. Frontend

### 13.1 Behaviour specifications

* **Map.** Ice concentration layer, risk layer, iceberg markers with uncertainty circles, wind and current vectors (toggles), and routes.
* **Forecast slider.** Steps through leads up to `max_validated_lead`, and cannot go past it.
* **Data-status strip.** Always visible: one chip per layer with source and age; amber when stale, red when unavailable.
* **Route panel.** Inputs: start, goal, ship class, departure time. Shows up to three options with distance, duration, relative fuel, max risk, warnings, and the explanation list. Selecting an option highlights it on the map.
* **Uncertainty panel.** Shows held-out error by regime for the visible forecast layer.
* **Decision-support banner.** Persistent, unmissable, not dismissible.
* **Model-evaluation page.** Renders the evaluation tables from the results JSON, including baselines and the skill scores.
* **Failure states.** When the API returns `unavailable`, the UI shows a clear message and draws no fabricated layer.

### 13.2 Accessibility and clarity

Colour scales must be colour-blind safe; risk is conveyed by colour **and** pattern or label; units are always shown.

---

## 14. Uncertainty Tables

`GET /api/uncertainty` returns, for each forecast type, lead, and regime: expected error (MAE), 90th percentile error, and sample size, read from the held-out evaluation JSON. These are statements of past model error in similar conditions. They are **not** calibrated probabilistic forecasts, and the documentation says so.

---

## 15. Testing Strategy (priority order)

1. **`scripts/verify_datasets.py`** (Phase 0 gate): every dataset opens, has expected variables, units, grid, and date range.
2. **Grid round-trip and cell-area tests.**
3. **Vector rotation tests** (wind and current) at several longitudes against hand-computed cases.
4. **Split tests:** `assert_no_leakage` passes on real splits and *fails* on a deliberately leaky split.
5. **Baseline tests:** climatology independent of test data; persistence exact; damped persistence bounded between persistence and climatology.
6. **Metric tests:** known-answer cases for MAE, RMSE, skill, IIEE; zero-baseline handling.
7. **Dataset-builder tests:** sample count, missing-target dropping, normalisation fitted on train only.
8. **Model smoke tests:** forward pass shape, output range, land is NaN.
9. **Risk-engine property tests** (monotonicity in concentration and ice class).
10. **Fuel-model property tests.**
11. **Routing property tests** (hypothesis): zero hard-constraint violations over random start/goal pairs and random ice fields; smoothing never crosses impassable cells; determinism.
12. **Refusal tests:** each typed error is raised in its trigger scenario and mapped correctly by the API.
13. **API schema tests:** every forecast response has provenance and uncertainty.
14. **Integration test:** ingest fixture → build dataset → baselines → predict → risk → route, on a tiny fixture grid.
15. **Frontend tests:** slider cannot exceed the validated lead; unavailable data renders a message, not a layer.
16. **`verify.py`:** documented numbers match result JSON (§16).

CI runs 2–14 and 16 on every commit against small fixtures. Full-data training runs are manual.

---

## 16. Reproducibility and the Verification Script

`verify.py`:

1. Runs the fast test suite.
2. Loads each model artifact, verifies its hash, and smoke-tests it.
3. Extracts every performance figure quoted in `README.md` (marked with a machine-readable tag such as `<!--metric:seaice.mizt.lead3.skill-->`) and compares it with the result JSON. **A mismatch fails the run.**
4. With `--recompute`, re-derives the evaluation from the checkpoint and compares to committed results.

Rule: **performance numbers exist in one place, the result JSON.** The README and the evaluation page read from it.

---

## 17. Documentation Deliverables and README Requirements

### 17.1 Documents

`DATA_LINEAGE.md`, `ROUTE_COST.md`, `FALLBACK.md`, `DECISIONS.md`, `EVALUATION.md` (generated), and two model cards (`sea_ice_model_card.md`, `iceberg_model_card.md`).

### 17.2 Model card contents

Intended use; explicitly unintended use; training data and period; split definition; architecture; metrics against every baseline, by regime and lead, with n; known failure modes; how to reproduce.

### 17.3 README must contain

1. One-paragraph description and the decision-support-only statement.
2. What this system does differently (§1.3 of Part 1), stated factually.
3. The headline results: skill against persistence, by regime and lead, **including any negative results**.
4. The iceberg results with sample size and number of bergs.
5. The maximum served lead and why.
6. Data sources with retrieval dates and licences.
7. An honest **What This System Does NOT Do** section, checked against what was actually built.
8. Setup and run instructions.
9. `./verify.py` instructions.
10. Acknowledgement of data providers and any reference implementations consulted.

---

## 18. Risk Register

| Risk | Likelihood | Impact | Mitigation |
| ----- | ----- | ----- | ----- |
| Deep model does not beat persistence | **High** | High | Baselines first; outcome table (§7.6); residual formulation; direct multi-horizon; ship honest negative result |
| Silent unit or projection bug (wind rotation) | Medium | High | Rotation tests; unit assertions; cross-check against a known case |
| Data leakage in splits | Medium | High | `assert_no_leakage` in CI; berg-identity split |
| Download volume and time | High | Medium | Regional crop; short training window first; cache raw; script every download |
| Account or credential delays | Medium | Medium | Create Copernicus, CDS, and Earthdata accounts on Day 1 |
| Iceberg live feed unavailable or format changes | Medium | Medium | Historical database is the training source; live list is optional at serve time; fail to `unavailable` |
| Risk-index table not obtained exactly | Medium | Medium | Data-driven table; labelled placeholder; state clearly in README |
| Non-finite loss in training | Medium | Medium | Gradient clipping, mixed-precision guard, NaN detection and halt |
| Compute limits | Medium | Medium | Patch training, small U-Net, per-pixel model as fallback |
| Time overrun | High | High | Phase gates; a shippable system exists after each phase from Phase 6 on |

---

## 19. Glossary

| Term | Meaning |
| ----- | ----- |
| Persistence | Forecast equal to the latest observation |
| Climatology | Day-of-year average from the training period |
| Damped persistence | Anomaly persisted and relaxed toward climatology |
| Skill score | `1 − error_model / error_baseline`; positive means better than baseline |
| Marginal ice zone (MIZ) | Partially ice-covered transition zone, concentration roughly 0.15–0.50 |
| IIEE | Integrated ice-edge error: area where model and truth disagree on ice presence |
| Direct multi-horizon | Model predicts all leads in one pass |
| Autoregressive rollout | Model feeds its own forecast back in to reach later leads |
| Reanalysis | Model-assimilated historical reconstruction; lags real time |
| Ice class / Polar Class | A vessel's rated capability in ice |
| Residual learning | Predicting the difference from a baseline rather than the raw value |
| Hard constraint | A condition the planner must never violate |
| Provenance | Source, product, time, units, and resolution attached to data |


---
---

# Phase-Wise Build Prompts — SIH 26059

*Part 3 of 3: Copy-Paste Prompts for a Coding Agent*

**How to use this section.** Each phase below is a self-contained prompt for a coding agent (Claude Code or similar). Run them **in order**. Later phases assume earlier phases are complete, tested, and committed. Before Phase 0, confirm that the Implementation Plan (Part 2) is committed at `docs/IMPLEMENTATION_PLAN.md`. Every prompt refers to it as the authority instead of repeating its content.

**Standing instruction (paste once at the start of the session; it is not a phase):**

> You are building the system specified in `docs/IMPLEMENTATION_PLAN.md` in this repository. Read that file in full before starting any phase. Follow its architecture and non-negotiable principles exactly. In particular: (1) build and evaluate baselines before training any model (§1.2, §6); (2) use time-based splits only, and never a random split (§6.1); (3) assert and record units at ingest, and rotate wind and current vectors into the analysis grid (§4.3, §4.4); (4) never fabricate or substitute data in the serving path, and return an explicit `unavailable` instead (§1.2, §11.6); (5) the planner must never violate a hard constraint, including after smoothing (§11.3); (6) never report a number that was not produced by a script in this repository and stored in `results/` (§16); (7) the tool is decision support only and must never imply autonomous control. Where a prompt says "per §X," that is a section of the Implementation Plan, which is authoritative. After each phase, run the tests and fix failures before moving on, then commit with a message that names the phase. If a phase's exit criteria are not met, do not proceed. Say so explicitly and explain what is blocking. If you must deviate from the plan, record the deviation and the reason in `docs/DECISIONS.md` rather than deviating silently. Do not invent dataset variable names, product IDs, table values, or numeric constants: read them from the real files or the published sources, and say so when you cannot.

---

## Phase 0 — Environment, Accounts, and Dataset Verification

**Goal:** Prove, before any modelling code exists, that every dataset the plan depends on can actually be downloaded, opened, and interpreted, and record what is *actually* in the files. This phase exists because the most likely way to lose days on this project is to discover late that a dataset has a different grid, unit, variable name, or date range than assumed.

**Prompt:**

> Set up the project and verify all data sources, per `docs/IMPLEMENTATION_PLAN.md` §1, §3, and §4. Do not write any model code in this phase.

> 1. Create the repository skeleton exactly as in §2 (empty modules with a docstring stating which phase implements them are acceptable). Create `pyproject.toml`, and install dependencies in a virtual environment. Record the *resolved* versions in `requirements.lock`. If any library in §1.1 will not install, choose an equivalent and record the decision in `docs/DECISIONS.md`.
> 2. Write `scripts/download_data.py` supporting these sources, each behind a flag, each idempotent (skip files already present that pass a size check), each reading credentials from environment variables and never from files in the repository: (a) Copernicus Marine sea-ice concentration product for the Southern Hemisphere; (b) ERA5 10 m u/v wind and 2 m temperature from the Copernicus Climate Data Store; (c) Copernicus Marine global ocean surface currents; (d) the BYU consolidated Antarctic iceberg database and the USNIC live iceberg list; (e) a bathymetry / land dataset. For the very first pass, download **a small window only** (for example one month) so verification is fast. Write a clear `data/README.md` explaining how to create each account and set each environment variable.
> 3. Write `scripts/verify_datasets.py`. For every downloaded dataset it must open the file and **print and record**: the actual variable names; units attribute; dimensions and shape; coordinate names and spacing; projection or grid-mapping attributes; the date range present; the fill value and any quality or status flag variables; and the value range after masking. Do not assume any of these. Read them from the files.
> 4. Use the verification output to make and record these decisions in `docs/DATA_LINEAGE.md` and `config/domain.yaml`: (a) the analysis-grid projection (choose the sea-ice product's native polar stereographic grid unless there is a stated reason not to); (b) the exact grid origin, spacing, and shape; (c) the regional domain of interest; (d) how "day D" is defined for each product; (e) the unit convention for concentration (fraction 0–1) and the conversion needed from each source.
> 5. Answer these questions **from the files, not from memory**, and put the answers in `DATA_LINEAGE.md`: What is the earliest and latest available date for each product? Is the sea-ice concentration in percent or fraction? What are the wind components' sign conventions? What depth level do the currents correspond to? How are land and missing values encoded in each file? How many distinct iceberg tracks and position records exist in the historical database, and over what years? How many bergs are on the live list right now, and when was it last updated?
> 6. Flag any discrepancy between the plan and the real data (for example a variable named differently, a product with a shorter record than assumed, or a live list format that differs from the historical one) in `docs/DECISIONS.md` and propose how the plan should adapt. Do not silently work around discrepancies.
> 7. Create small fixture files in `tests/fixtures/` (a few days, a small spatial crop, and a short iceberg CSV) from the real data, for use by fast tests in later phases. Document their provenance.

> **Exit criteria.** `scripts/verify_datasets.py` runs cleanly and produces a complete report for every source. `DATA_LINEAGE.md` records the real grid, units, date ranges, and conventions. `domain.yaml` is filled in from real values. Any discrepancy is written down. If a required dataset cannot be obtained at all, stop and say so. Commit as "Phase 0: environment, accounts, and dataset verification."

---

## Phase 1 — Core Library: Grid, Provenance, Config, Ingest, and Data Checks

**Goal:** A tested library that loads every dataset into standardised, unit-checked, provenance-tagged form on the analysis grid, with vector rotation done correctly and every data-quality check automated.

**Prompt:**

> Implement the ingestion and harmonisation core per `docs/IMPLEMENTATION_PLAN.md` §3, §4, and §5.

> 1. Implement `config.py` (load and validate the YAML files with pydantic), `errors.py` (all typed exceptions from §11.6), and `provenance.py` (§3.3).
> 2. Implement `AnalysisGrid` in `grid.py` per §3.2, reading the values recorded in `config/domain.yaml`. Include `lonlat_to_xy`, `xy_to_lonlat`, `contains`, `cell_area_km2`, and a projected-displacement-to-kilometres helper. Write tests: a round-trip test across the domain including near the dateline, and a cell-area test showing area varies with position in the projected grid.
> 3. Implement the ingest modules `seaice.py`, `era5.py`, `currents.py`, `icebergs.py`, and `bathymetry.py` per §4. Each must expose `fetch`, `load`, and `validate`. `load` must return a Dataset with standard variable names, declared units, and a `Provenance` in `attrs`. In `seaice.py`, convert to a 0–1 fraction if needed, assert the range, and mask (never zero-fill) flagged and land cells. In `icebergs.py`, produce a normalised table with `berg_id, timestamp, lon, lat`, handle the dateline, preserve berg identity, and report how many records were dropped and why.
> 4. Implement `ingest/checks.py` per §4.6: units match config; value ranges are physical; fill values are masked; axes are monotonic with expected spacing; projection attributes are present; duplicate timestamps are an error; temporal gaps are a warning with the list of missing dates. The build must fail on any error-level finding.
> 5. Implement `harmonise/regrid.py` and `harmonise/align.py` per §5.1 and §5.2. **Implement the wind and current vector rotation into grid-aligned components** (`rotate_to_grid`). This is a known silent-bug source. Test it: hand-compute the expected rotated components at several longitudes (for example at longitude 0, 90, 180, and -90) for a pure eastward and a pure northward unit vector, and assert your function matches. Write the test before the implementation.
> 6. Test the regridding by regridding a smooth analytic field (for example a low-order polynomial in projected coordinates) from a coarse lat/lon grid onto the analysis grid and comparing with the analytic value; state the tolerance.
> 7. Write unit tests for every check in `checks.py` using deliberately broken fixtures (wrong units, out-of-range values, unmasked fill, non-monotonic axis, duplicate timestamp) and confirm each is caught.
> 8. Generate a per-source summary and write it to `docs/DATA_LINEAGE.md` (extending Phase 0's): native grid, regridding method, aggregation rule (for example hourly ERA5 to daily mean), and known limitations.

> **Exit criteria.** All tests pass on fixtures. Every ingest returns standardised, provenance-tagged data. Vector rotation is tested against hand-computed values. Regridding is tested against an analytic field. Broken fixtures are caught. Commit as "Phase 1: grid, provenance, ingest, and data-quality checks."

---

## Phase 2 — Splits, Baselines, Metrics, and the Evaluation Harness (No Models Yet)

**Goal:** Build the yardstick before building anything to be measured. By the end of this phase the project can say exactly how good "do nothing" is, everywhere and at every lead, which sets the bar every later model must clear.

**Prompt:**

> Implement splits, baselines, metrics, regimes, and the evaluation harness per `docs/IMPLEMENTATION_PLAN.md` §6. Do not train any model in this phase.

> 1. Implement `splits.py`: `make_time_split`, `assert_no_leakage`, and `make_berg_split`, per §6.1. The test block must include at least one full annual cycle. Write tests: `assert_no_leakage` passes on a correct split and **raises** on a deliberately leaky split (for example overlapping target windows, or a gap shorter than the maximum lead). For icebergs, assert no berg identity appears in more than one split.
> 2. Implement the sea-ice baselines per §6.2: persistence, climatology (**training data only**), and damped persistence with `tau` fitted on the training block. Write tests: persistence is exact; climatology output is unchanged if test-period data is altered (proving no leakage); damped persistence at lead 0 equals persistence and at very large lead approaches climatology.
> 3. Implement the iceberg baselines per §6.3: stationary, constant-velocity, and physics-only with `wind_coeff` fitted on train only. Physics-only needs the iceberg training pairs, so first implement the pair-building step described in §8.1 in a reusable function (bounded time gap, projected displacement in metres, speed ceiling, counts of discarded pairs). Write tests on synthetic tracks with known drift.
> 4. Implement `evaluation/metrics.py` per §6.4: MAE, RMSE, skill score (handle a zero baseline without dividing by zero), IIEE using cell areas from `AnalysisGrid`, position error in kilometres, and bootstrap confidence intervals. Write known-answer tests for every metric.
> 5. Implement `evaluation/regimes.py` per §6.5. Regimes are defined from the field **at forecast issue time**, not from the target. Write a test proving the stratification does not depend on the target field.
> 6. Implement `harmonise/dataset_builder.py` per §5.3 so the same builder serves baselines and models. A sample is emitted only if all its inputs and all its targets exist; dropped samples are counted and reported. Normalisation statistics are computed from the training block only.
> 7. Implement `evaluation/report.py` and `scripts/run_baselines.py`. The script must run end to end and write `results/baselines.json` containing: every baseline, at every lead 1 to `L`, in every regime plus the ice-edge band, with the sample count, and also error by season. Also write a first `docs/EVALUATION.md` generated from that JSON.
> 8. Look at the baseline numbers and write a short note in `docs/EVALUATION.md` interpreting them: how good is persistence at lead 1? How quickly does it degrade with lead? Where is the error concentrated? This tells you where a model could plausibly add value.

> **Exit criteria.** The leakage test fails on a leaky split and passes on a correct one. All baselines and metrics are unit-tested. `results/baselines.json` exists and covers every lead, regime, and season with sample counts. The interpretation note is written. Do not proceed to model training until this is true. Commit as "Phase 2: splits, baselines, metrics, and evaluation harness."

---

## Phase 3 — Sea-Ice Forecaster

**Goal:** Train sea-ice forecasters and evaluate them honestly against the Phase 2 baselines, deciding for each lead what the system will actually serve.

**Prompt:**

> Implement and evaluate the sea-ice forecasters per `docs/IMPLEMENTATION_PLAN.md` §7. Follow the build order: the cheap learned model first, then the U-Net.

> 1. Implement `models/seaice_pixel.py` per §7.2: a per-pixel gradient-boosted model on lagged local features (own history, neighbourhood statistics, wind, temperature, day-of-year), predicting the **change from persistence** for each lead. Subsample pixels for training so it fits in memory, but evaluate on the full domain. Evaluate it with the Phase 2 harness against every baseline, by regime and lead.
> 2. Implement `models/seaice_unet.py` per §7.3: a direct multi-horizon U-Net whose output is the residual added to the most recent concentration map, so the default prediction is persistence. Use a masked loss that ignores land and up-weights the marginal ice zone and the ice-edge band (make the weighting a config value and report it). Use patch training, and evaluate on the full domain. Clamp outputs to `[0, 1]`. Set land cells to NaN in the output.
> 3. Implement `training/train_seaice.py` and `scripts/train_seaice.py`. Fix seeds. Store the config, git hash, normalisation statistics, and training-split dates with the checkpoint. Add NaN/non-finite-loss detection that halts training and logs the step, and gradient clipping. Use early stopping on **validation skill against persistence in the marginal ice zone at the median lead**, not on loss alone.
> 4. Train on the train block, tune on the validation block, and evaluate on the test block **once**. Save all results to `results/seaice_eval.json`, including for each model, each lead, each regime and the ice-edge band: MAE, RMSE, skill vs persistence, skill vs damped persistence, skill vs climatology, IIEE, sample count, and bootstrap confidence intervals. Also report skill by season.
> 5. Run the failure-mode checks from §7.5: outputs within `[0, 1]`; open-water error not worse than persistence; land cells NaN; ice-edge sharpness via IIEE and edge-band MAE; seasonal bias.
> 6. Apply the outcome rules in §7.6 mechanically, per lead. Write the result into `config/serving.yaml` as `served_model_by_lead` (one of `unet`, `pixel`, `persistence`, `damped_persistence`) and set `max_validated_lead`. If no learned model beats persistence in the marginal ice zone at some lead, then serve persistence at that lead **and record the negative result plainly** in `docs/EVALUATION.md` and the model card. Do not tune endlessly to force a positive result.
> 7. Write `docs/models/sea_ice_model_card.md` per §17.2.
> 8. Export the chosen artifacts to `models_out/` with a `manifest.json` containing the SHA-256 of each artifact and a small round-trip sample (a fixed input and its expected output) so a later loader can verify it.

> **Exit criteria.** `results/seaice_eval.json` exists with the full breakdown. `serving.yaml` reflects the measured outcome per lead. Failure-mode checks pass. The model card states both the wins and the limits, including any negative result. Exported artifacts have hashes and round-trip samples. Commit as "Phase 3: sea-ice forecaster, honestly evaluated."

---

## Phase 4 — Iceberg Drift Model

**Goal:** A physics-anchored drift model with a learned residual, evaluated against three baselines on berg-identity-split held-out data, with honest sample sizes and an uncertainty radius per lead.

**Prompt:**

> Implement and evaluate the iceberg drift model per `docs/IMPLEMENTATION_PLAN.md` §8.

> 1. Using the pair-building function from Phase 2, build the full iceberg training set per §8.1. For each pair, sample ERA5 wind, ocean current, sea-ice concentration, and distance to the ice edge at the start position and time (documenting whether you use the value at the start or the mean over the interval). Convert positions to projected coordinates and compute displacement in metres. **Rotate wind and current vectors into grid-aligned components.** Report how many pairs were discarded for time-gap, speed-ceiling, and missing-forcing reasons.
> 2. Split with `make_berg_split` (by berg identity and time). Assert in a test that no berg appears in more than one split. Report the number of pairs and distinct bergs in each split.
> 3. Implement `models/iceberg_physics.py` per §8.3 and fit `wind_coeff` by least squares on the training pairs. Report the fitted value with a bootstrap confidence interval. State the integration scheme used.
> 4. Implement `models/iceberg_residual.py` per §8.4. The target is the observed displacement minus the physics-baseline displacement (two components). Start with gradient boosting. Evaluate whether an optional moving/stationary gate helps, and report its accuracy and how many training pairs it removes. Keep it only if it helps on validation.
> 5. Implement multi-step forecasting per §8.5, stepping interval by interval with the forcing available at each step. Report position error at each lead separately. Use the held-out RMS position error (and the 90th percentile) at each lead as the uncertainty radius, and store those radii in `results/iceberg_eval.json`.
> 6. Evaluate against stationary, constant-velocity, and physics-only baselines on the held-out set. Report RMS, median, and 90th-percentile position error; fraction within 5, 10, and 25 km; skill vs each baseline with bootstrap confidence intervals; and the number of pairs and distinct bergs. Write results to `results/iceberg_eval.json`.
> 7. Apply the acceptance criteria in §8.6. If the learned residual does not beat both constant-velocity and physics-only with a confidence interval that excludes zero, report that plainly, ship the better baseline, and explain in the model card.
> 8. Handle the live list separately: write a loader that turns the live list into starting positions for a forecast, and that returns an explicit "coverage" statement (number of bergs tracked, date of last update, and the plain-language note that small fragments are not tracked). Do not present the live list as complete iceberg detection.
> 9. Write `docs/models/iceberg_model_card.md` per §17.2 and export the artifact to `models_out/` with hash and round-trip sample.

> **Exit criteria.** `results/iceberg_eval.json` contains errors per lead, uncertainty radii, skill against all three baselines, and sample sizes. Berg-identity split is asserted. The model card states the limits, including sparse coverage. Commit as "Phase 4: iceberg drift model with physics baseline and learned residual."

---

## Phase 5 — Ice-Risk Engine and Fuel Estimator

**Goal:** The two deterministic, non-ML components that turn forecasts into decisions, built as auditable, data-driven, property-tested modules.

**Prompt:**

> Implement the risk engine and the fuel estimator per `docs/IMPLEMENTATION_PLAN.md` §9 and §10.

> 1. Implement `config/ship_classes.yaml` with a small set of representative ice classes (for example a non-ice-strengthened vessel and a few ice-classed vessels) including the parameters the fuel model needs. Every constant must carry a comment stating its source or stating "assumption." Do not present an invented number as a published value.
> 2. Implement `config/risk_tables.yaml` and `risk/risk_index.py` per §9. **The risk-index values must come from the published standard, not from memory.** Search for the current published guidance the plan refers to, read the actual table, and transcribe it. Record the document title, version, and date in `docs/DECISIONS.md`. If you cannot obtain the real table, implement against a table clearly labelled `PLACEHOLDER` in the YAML and in the code, make the API and the frontend display a visible "placeholder risk table" warning, and state it prominently in the README. Do not present a placeholder as regulatory.
> 3. Implement `risk_grid`, `is_passable`, and the `RiskLevel` enum per §9.3. Unknown ice type is treated conservatively and flagged. Implement the uncertainty-aware mode from §9.4: evaluate risk at `concentration + error_p90` (clamped) using the held-out error for that regime from `results/seaice_eval.json`, so the planner is more cautious where the forecast is weak.
> 4. Write property tests with `hypothesis`: risk is non-decreasing in concentration for a fixed ice class and type; a stronger ice class never yields higher risk than a weaker class for identical ice; the uncertainty-aware risk is never lower than the plain risk.
> 5. Implement `fuel/fuel_model.py` per §10 with the documented formula, and write `docs/ROUTE_COST.md` explaining each term, its units, and its assumptions. Output is labelled "relative estimate."
> 6. Write property tests: fuel is non-decreasing in distance; for the same distance and class, heavier ice never reduces fuel; fuel is non-negative and finite.
> 7. Add a short worked example to `docs/ROUTE_COST.md` with real numbers computed by the code (not hand-typed), so the document and the code cannot drift.

> **Exit criteria.** Property tests pass. The risk table is either the real published one with a recorded citation, or is loudly labelled as a placeholder everywhere it surfaces. Fuel outputs are labelled as relative. Commit as "Phase 5: ice-risk engine and fuel estimator."

---

## Phase 6 — Route Planner with Hard Constraints

**Goal:** A time-dependent route planner that is safe by construction, refuses rather than misleads, and explains its recommendations.

**Prompt:**

> Implement the route planner per `docs/IMPLEMENTATION_PLAN.md` §11.

> 1. Implement `routing/cost_grid.py` per §11.1: per-time-slice cost grids from forecast concentration (through the risk engine), iceberg exclusion buffers (radius equals the drift model's uncertainty radius at that lead plus a configured safety margin), the land and shallow-water mask, and a distance term. A cell's cost depends on the estimated arrival time, which selects the forecast slice.
> 2. Implement `routing/astar.py` per §11.2: time-dependent A* on the analysis grid, 8-connected, with an admissible heuristic. Cells that are prohibited-risk, land, shallow, or inside an iceberg buffer have **infinite cost and are never entered.** Provide three weight presets (fastest, safest, balanced) in config.
> 3. Implement `routing/smooth.py` per §11.3: Douglas–Peucker simplification then smoothing. **Re-check every smoothed segment against the hard constraints; if a smoothed segment would enter an impassable cell, keep the unsmoothed segment.** A smoothed route must never violate a hard constraint.
> 4. Implement `routing/explain.py` per §11.5: **templated** sentences built only from numbers the planner computed (highest-risk segment and its concentration; closest approach to a forecast iceberg; how this option differs from the fastest). No free-form generated text.
> 5. Implement `routing/planner.py` returning up to three `RouteOption` objects per §11.4. Use the typed errors from §11.6: `DataUnavailable` when an ice field needed at any arrival time is missing; `ForecastHorizonExceeded` when the route would extend beyond the last valid forecast slice and configuration does not allow continuing on the last slice; `StartOrGoalImpassable`; `NoPassableRoute`; `StaleData`. **None of these is caught and converted into a default route.** If configuration explicitly allows continuing beyond the horizon, flag the option `beyond_forecast_horizon: true` and add a visible warning.
> 6. Write the property tests with `hypothesis` (this is the most important test set in the project): over randomised ice fields, iceberg positions, and start/goal pairs, assert **zero** hard-constraint violations in any returned route, smoothed or not; assert determinism (same inputs, same route); assert that an unreachable goal raises `NoPassableRoute`; assert that missing ice data raises `DataUnavailable`; assert that a start on land raises `StartOrGoalImpassable`.
> 7. Add integration tests on the tiny fixture grid running the whole chain: ingest fixture, forecast (baseline is fine for the test), risk, planner. Also add a few hand-built scenarios with known-correct answers (a channel that is the only passable path; an iceberg buffer that forces a detour; a closed-ice barrier with no route).
> 8. Measure planner runtime on a realistic grid size and record it in `results/routing_perf.json`. If a request is too slow to be usable interactively, optimise (coarser search grid, early termination) without weakening the hard constraints.
> 9. Write `docs/FALLBACK.md` describing exactly what the system does when each dependency is missing, and why climatology is **deliberately not** a routing fallback.

> **Exit criteria.** The zero-violation property test passes across many random cases. Every typed error has a triggering test. Smoothing cannot cross impassable cells. Runtime is recorded. `FALLBACK.md` is written. Commit as "Phase 6: route planner with hard constraints and refusal behaviour."

---

## Phase 7 — Backend API

**Goal:** A typed FastAPI service that exposes everything, attaches provenance and uncertainty to every forecast, refuses out-of-range requests, and reports its own health honestly.

**Prompt:**

> Implement the backend per `docs/IMPLEMENTATION_PLAN.md` §12 and §14.

> 1. Implement `api/schemas.py` with pydantic models. Every forecast response includes `provenance`, `issue_time`, `valid_time`, `model_id`, and an `uncertainty` object. Add a schema test that iterates every forecast endpoint's response model and fails if any lacks provenance or uncertainty.
> 2. Implement `models/registry.py` per §12.4: load each artifact, verify its SHA-256 against `models_out/manifest.json`, run the stored round-trip sample as a smoke test, and record the result. A failed model is marked `unavailable`. The API must **never** silently substitute a different model.
> 3. Implement the endpoints listed in Part 1 §7.2 under `api/routes/`. Read `served_model_by_lead` and `max_validated_lead` from `config/serving.yaml`. A request for a lead beyond `max_validated_lead` returns HTTP 422 with a plain-language reason.
> 4. Implement the freshness logic: each data layer has a newest-valid-time and an age. When the age exceeds the configured threshold, the response carries `stale: true` and the age in hours. Test it by mocking the clock.
> 5. Implement `GET /api/system-status` per §12.3: for every component, a `state` (`ok`, `degraded`, or `unavailable`), the newest valid time, the age, and the reason for any degraded state.
> 6. Implement `GET /api/uncertainty` per §14, reading the held-out error tables from `results/`. State in the response body that these are past-error statistics, **not calibrated probabilities.**
> 7. Implement the mapping from each typed exception to an HTTP status and message. Write a test per exception proving the mapping, and a test proving no route request that triggers an error ever returns a route.
> 8. Generate `docs/API.md` with example requests and responses produced by actually calling the running service (not hand-written).
> 9. Confirm that no endpoint returns simulated or default data in place of missing data. Add a test that deletes a day of fixture data and asserts the affected endpoint returns an explicit `unavailable` marker.

> **Exit criteria.** All endpoint, schema, freshness, refusal, and mapping tests pass. `system-status` reports honestly, including for a deliberately broken model artifact. `docs/API.md` is generated from real calls. Commit as "Phase 7: backend API with provenance, uncertainty, and refusal behaviour."

---

## Phase 8 — Frontend Decision Dashboard

**Goal:** A map-first interface that makes the honest behaviour visible: data age, uncertainty, refusal, and the decision-support-only framing are impossible to miss.

**Prompt:**

> Implement the frontend per `docs/IMPLEMENTATION_PLAN.md` §13.

> 1. Scaffold `web/` with React, TypeScript, and MapLibre GL (or Leaflet). Use a free basemap that works for polar regions; confirm it renders correctly at high southern latitudes and note any distortion in `docs/DECISIONS.md`.
> 2. Implement the typed API client in `api/client.ts`, generated from or checked against the backend schemas so the two cannot drift.
> 3. Implement `MapView.tsx` with layers for sea-ice concentration, risk, iceberg markers with uncertainty circles, wind and current vectors (toggles), and routes. Use colour-blind-safe scales. Convey risk with both colour and a label or pattern. Always show units.
> 4. Implement `ForecastSlider.tsx`: steps through leads up to `max_validated_lead` from the API and **cannot be moved past it.** Show, for the selected lead, which model is being served (for example "persistence" or "U-Net") so the user can see when a baseline is being served instead of a learned model.
> 5. Implement `DataStatusStrip.tsx`: one chip per layer with source and age; amber when stale; red when unavailable. Always visible.
> 6. Implement `RoutePanel.tsx`: inputs for start, goal, ship class, and departure time; shows up to three options with distance, duration, relative fuel, maximum risk, warnings, and the explanation list; selecting an option highlights it. When the API refuses, show the reason in plain language and draw nothing. If the risk table is a placeholder, show a persistent warning.
> 7. Implement `UncertaintyPanel.tsx` showing held-out error by regime for the visible layer, with the note that this is past error, not a probability.
> 8. Implement `DecisionSupportBanner.tsx`: persistent, prominent, not dismissible, stating that the tool supports human decision-making and does not control the vessel.
> 9. Implement `pages/ModelEvaluation.tsx` rendering the evaluation tables from the results JSON, including every baseline and the skill scores by regime and lead, with sample sizes. It must display negative results as clearly as positive ones.
> 10. Implement failure states: whenever the API returns `unavailable`, the UI shows a clear message and draws no fabricated layer.
> 11. Write frontend tests: the slider cannot exceed the validated lead; an `unavailable` response renders a message and no layer; the banner cannot be dismissed; a refused route shows the reason and no path.
> 12. Take screenshots of the key states (normal, stale data, unavailable data, refused route) and save them under `docs/screens/`.

> **Exit criteria.** Frontend tests pass. All four failure and edge states render correctly. The evaluation page shows negative results plainly. Screenshots are committed. Commit as "Phase 8: decision dashboard with visible uncertainty and refusal."

---

## Phase 9 — Reproducibility, Hardening, and the Final Honesty Pass

**Goal:** Every claim in the final submission is backed by a script and a result file; the system is exercised end to end; and the README says exactly what is true.

**Prompt:**

> Complete verification, hardening, and documentation per `docs/IMPLEMENTATION_PLAN.md` §15, §16, and §17.

> 1. Implement `verify.py` per §16: run the fast tests; load each model artifact, check its hash, and smoke-test it; extract every performance figure in `README.md` tagged with a machine-readable metric marker and compare it to `results/*.json` (**a mismatch fails the run**); with `--recompute`, re-derive the evaluation from the checkpoints and compare to the committed results.
> 2. Audit the codebase against each non-negotiable principle in §1.2. For each one, point to the test that enforces it. If any principle has no test, add one now.
> 3. Run a **leakage audit**: try to break the evaluation on purpose. Train a model on a leaky split and confirm the evaluation harness or `assert_no_leakage` flags it. Confirm the frozen test block was used only for final reporting (check the commit history and result timestamps).
> 4. Run an **end-to-end scenario walkthrough** on real data and save the transcript: (a) request a forecast at a supported lead and confirm provenance and uncertainty are present; (b) request an unsupported lead and confirm refusal; (c) request a route in easy conditions and confirm three options with explanations; (d) request a route through conditions that force a detour around a forecast iceberg buffer; (e) request a route with a goal in prohibited ice and confirm it is refused; (f) delete a day of data and confirm the API reports `unavailable` and routing refuses.
> 5. Run a robustness check on the routing property tests with a much larger number of random cases than the fast CI run, and record the count and that zero violations were found.
> 6. Write the final `README.md` per §17.3: the one-paragraph description and the decision-support-only statement; what this system does differently; **the headline results, including any negative results, as skill against persistence by regime and lead with sample sizes**; the iceberg results with the number of pairs and distinct bergs; the maximum served lead and why; data sources with retrieval dates and licences; a **"What This System Does NOT Do"** section checked item by item against what was actually built (not copied from the plan); setup and run instructions; `./verify.py` instructions; acknowledgements of data providers and any reference implementations you consulted.
> 7. Finalise the two model cards and `EVALUATION.md` (generated). Confirm every number in them comes from `results/`.
> 8. Search the repository for leftover stubs, `TODO: Phase N` comments, `NotImplementedError`, and placeholder values (especially a placeholder risk table). Resolve each, or list it in the README's limitations section. Do not leave anything silently unfinished.
> 9. Do a final read-through of every user-facing string in the API and frontend, and remove anything that implies autonomous control, certainty, or completeness that the system does not have.

> **Exit criteria.** `verify.py` passes (including a deliberate test that it fails on a doctored number). The leakage audit demonstrates the harness catches leakage. The end-to-end scenarios all behave as specified. The README contains only numbers that trace to `results/`, states negative results plainly, and lists real limitations. Commit as "Phase 9: verification, hardening, and final documentation."

---

## Appendix A — Quick-Reference Phase Summary

| Phase | Deliverable | Depends on | Relative risk |
| ----- | ----- | ----- | ----- |
| 0 | Environment, accounts, verified datasets, real grid and units recorded | — | **High** (data surprises) |
| 1 | Grid, provenance, ingest, data checks, vector rotation | 0 | Medium |
| 2 | Splits, baselines, metrics, evaluation harness | 1 | Medium |
| 3 | Sea-ice forecaster, honestly evaluated | 2 | **High** (may not beat persistence) |
| 4 | Iceberg drift model (physics + residual) | 1, 2 | Medium |
| 5 | Ice-risk engine and fuel estimator | 3 | Low–Medium (risk-table sourcing) |
| 6 | Route planner with hard constraints | 3, 4, 5 | Medium |
| 7 | Backend API | 3–6 | Low |
| 8 | Frontend dashboard | 7 | Low–Medium |
| 9 | Verification, hardening, final docs | 1–8 | Low |

**Where the risk really sits.** Phase 0 is the earliest risk because everything depends on data that may differ from assumptions. Phase 3 is the largest technical risk because a sea-ice forecaster that does not beat persistence is a real and likely outcome; the plan is built so that this outcome still produces an honest, shippable system (§7.6) instead of a failure. Phase 6 carries the highest safety stakes, which is why its hard-constraint test is the most heavily emphasised in the plan.

**A shippable system exists after Phase 7.** Phases 8 and 9 make it usable and defensible. If time runs short, cut scope from the frontend's polish, not from Phase 9's verification.

## Appendix B — Suggested Time Budget

Calendar time depends on the team, compute, and download speeds, so use this only as a relative guide for *where to spend attention*:

| Share of effort | Phases |
| ----- | ----- |
| ~15% | Phase 0–1 (data and ingest; download time is the hidden cost) |
| ~15% | Phase 2 (baselines and evaluation harness; do not skimp) |
| ~25% | Phase 3–4 (models) |
| ~15% | Phase 5–6 (risk, fuel, routing) |
| ~15% | Phase 7–8 (API and dashboard) |
| ~15% | Phase 9 (verification and honest documentation) |

## Appendix C — Pre-Submission Checklist

* [ ] Every number in the README is tagged and matches `results/*.json` (`verify.py` passes).
* [ ] Negative results (if any) are stated in the README and shown on the evaluation page.
* [ ] The maximum served lead is justified by measured results.
* [ ] The risk table is the published one, or is loudly labelled a placeholder everywhere.
* [ ] Routing has zero hard-constraint violations across the large random test.
* [ ] Missing data produces `unavailable`, and routing refuses.
* [ ] The decision-support-only banner is present and not dismissible.
* [ ] Data sources, retrieval dates, and licences are listed.
* [ ] "What This System Does NOT Do" reflects reality, not the plan.
* [ ] No stubs, TODOs, or placeholder values remain unlisted.

*(End of document. Part 1 explains the problem and design, Part 2 is the build specification, Part 3 is the phase prompts.)*

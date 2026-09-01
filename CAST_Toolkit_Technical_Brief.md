# CAST Toolkit — Technical Reference

Detailed companion to `CAST_Brief.md`. Describes the software as it currently stands: branch `final`, latest commit `a00e455` (6 Aug 2026).

Related documents: `README.md` (implementation handbook, currently lagging the code — see §7) and the user manual at <https://kamiz15.github.io/castbook-quarto/>.

---

## 1. Summary

CAST (Contamination Assessment and Site-management Tool) is a browser-based platform for the preliminary assessment of contaminated groundwater sites, aimed at steady-state, reaction-limited BTEX-type plumes. It couples a site database, six analytical and two empirical plume-length models, a MODFLOW 6 flow-and-transport model in two orientations, an analytic-element-method (AEM) transport model with an inverse parameter-estimation mode, and a general data-analysis workbench behind a single web interface. Every model runs from manually entered parameters or auto-filled site records, in single-scenario or multi-site comparison mode, and every run exports a branded PDF report. The platform runs as a four-service container stack, executes long-running simulations asynchronously through a job queue, and is covered by an automated regression suite that pins the numerical models to independently produced reference results.

---

## 2. Toolboxes

### 2.1 Site data

- **Reference database**: 112 contaminated sites (`static/original.csv`), searchable, sortable, paginated. Open to any visitor — **no login required**, and the default data source for every model.
- **Per-user database** (MySQL): manual entry, bulk CSV upload (capped at 10 000 rows per upload), row deletion, whole-database clear, duplicate prevention.
- **CSV import** accepts human-readable header aliases, normalises case and punctuation, strips BOM markers, and maps blanks, `N/A`, `null` and `-` to SQL `NULL`.
- **Export**: user database and reference database as CSV, XLSX or PDF, plus Copy and Print.
- **Stored per site**: `site_unit`, `compound`, `aquifer_thickness`, `plume_length`, `plume_width`, `hydraulic_conductivity`, `electron_donor`, `electron_acceptor_o2`, `electron_acceptor_no3`.
- **Statistical views**: bar chart (user vs. reference plume lengths), histogram, box plot, and a separate dispersivity dataset page at `/dispersivity-data`.

### 2.2 Analytical models

Six models, implemented in `analytical_models.py` and `bioscreen_model.py`. The forms below are exactly what the code evaluates.

**Liedl et al. (2005) — 2-D vertical** · `liedl_lmax()`

$$L_{max}=\frac{4M^{2}}{\pi^{2}\alpha_{Tv}}\ln\left[\frac{4}{\pi}\cdot\frac{\gamma C_D^{\circ}+C_A^{\circ}}{C_A^{\circ}}\right]$$

**Liedl et al. (2011) — 3-D** · `liedl3d_lmax()` — root of

$$\mathrm{erf}\left(\frac{W}{\sqrt{4\alpha_{Th}L}}\right)\exp\left[-\alpha_{Tv}L\left(\frac{\pi}{2M}\right)^{2}\right]=\frac{\pi}{4}\cdot\frac{\gamma C_{thres}+C_A^{\circ}}{\gamma C_D^{\circ}+C_A^{\circ}}$$

Solved by Newton iteration (100-iteration cap, tolerance 1e-6) from a bracketed initial guess derived from three closed-form bounds, so no starting value is asked of the user. Inputs violating $0<\tfrac{\pi}{4}\,\mathrm{ratio}<1$ raise an explicit error rather than returning a spurious root.

**Chu et al. (2005) — 2-D horizontal** · `chu_lmax()`

$$L_{max}=\frac{\pi W^{2}}{16\,\alpha_{Th}}\left(\frac{\gamma C_D^{\circ}}{C_A^{\circ}-\epsilon}\right)^{2}$$

**Ham et al. (2004) — 2-D horizontal** · `ham_lmax()`

$$L_{max}=\frac{Q^{2}}{4\pi\alpha_{T}}\left(\frac{\gamma C_D^{\circ}}{C_A^{\circ}}\right)^{2}$$

**Cirpka et al. (2005)** · `cirpka_lmax()`

$$L_{max}=\frac{S_w^{2}}{16\,\alpha_{Th}\left[\mathrm{erf}^{-1}(c_f)\right]^{2}},\qquad c_f=\frac{C_A}{\gamma C_D+C_A}$$

Also returns a numerical domain length $L_D = 1.5\,L_{max}$, used to size the numerical model automatically (overridable).

**BIOSCREEN-AT (Karanovic et al., 2007)** · `bio()`, `bio_with_curve()`

The 3-D transient analytical solution, integrated numerically by **Gauss–Legendre quadrature** (user-selectable number of Gauss points) under a $\tau^{4}$ substitution of the time integral, rather than by fixed-step summation. Returns both $L_{max}$ and the full centreline concentration curve.

Every model is defended by explicit input guards — positive dispersivities, positive acceptor concentration, valid logarithm and error-function arguments — that produce a readable HTTP 400 rather than a server error.

### 2.3 Empirical models

Implemented in `empirical_models.py`.

**Maier & Grathwohl** · `maier_lmax()`

$$L_{max}=0.5\,\frac{M^{2}}{\alpha_{Tv}}\left(\frac{\gamma C_D}{C_A}\right)^{0.3}$$

**Birla et al. (2020), with recharge** · `birla_lmax()`

$$L_{max}=\left(1-0.047\,M^{0.404}R^{1.883}\right)\frac{4M^{2}}{\pi^{2}\alpha_{Tv}}\ln\left[\frac{4}{\pi}\cdot\frac{\gamma C_D+C_A}{C_A}\right]$$

### 2.4 Numerical model — MODFLOW 6

Implemented in `numerical_models.py` via **FloPy**, running **MODFLOW 6 GWF (flow)** and **GWT (transport)** as separate simulations coupled through **FMI** — GWF writes heads and budget, GWT consumes them.

Both orientations use the **transformed-concentration** formulation (after Yadav et al., 2014), so the bi-component instantaneous reaction is simulated as a conservative transport problem; the plume boundary is the chosen threshold $C_0$ (the shipped reference cases use $C_0 = 8$).

| | Vertical cross-section (x,z) | Horizontal plan view (x,y) |
|---|---|---|
| Entry point | `run_numerical_model()` | `run_numerical_model_horizontal()` |
| Grid | `nrow = 1`, `delc = 1` | full row/column grid |
| Source | donor cells $(k,0,5)$ for $k\in[1,n_{lay})$ at $\gamma C_D + C_A$; acceptor $C_A$ across the top layer | source rows centred in $y$ at column 5, donor $\gamma C_D + 2C_A$; acceptor $C_A$ on top and bottom rows |
| Plume length | mask index: $L_{max}=\max\{i: C\ge C_0\}\cdot\Delta r$, returning 0 if no cell qualifies | contour geometry at $C_0$, giving a sub-cell estimate |

Shared behaviour:

- Boundary and solver setup: fixed-head left/right, confined NPF, IMS solver, TDIS time stepping, OC output control.
- The user supplies the discretisation **explicitly** — `Lx`, `Ly`/`Lz`, `ncol`, `nrow`/`nlay`, `source` — plus `prsity`, `al`, `at`, `atv`, `gamma`, `C_D`, `C_A`, `C0`, `h1`, `h2`, `hk`, `perlen`. Domain sizing is deliberately **not** derived from an analytical $L_{max}$; that coupling was removed because it silently changed numerical results.
- Runtime guards: pre-run cell-count cap (`NUMERICAL_MAX_CELLS`, default 40 000), optional per-process solver timeout, time-step count derived from a Courant criterion, and Péclet/Courant values reported with the result.
- Simulation output is retained so **profile plots** and **decreasing-concentration gradient-vector fields** can be derived on demand from an existing run, without re-solving.
- Raw MODFLOW binaries (`.hds`, `.ucn`) are downloadable alongside the figures.

### 2.5 AEM toolbox

Package `aem/`, exposed at `/aem`. Provenance from the file headers: written by Alvin Yadav, based on code from Willi Kappler and Anton Köhler; the Mathieu-function library is Kuhlman's MIT-licensed implementation.

**Forward model** (`aem/at_simulation.py`) — steady-state reactive plumes from source geometries built of **circle, line and ellipse** elements. Coefficients of a **modified-Mathieu-function expansion** are fitted by least squares so each element boundary carries its prescribed concentration; the concentration field is then evaluated on a grid. Elements are grouped by coupling strength, so weakly interacting sources are solved separately and iteratively rather than as one dense system, and grid evaluation is parallelised across processes.

**Vertical orientation** enforces the water-table boundary condition by adding **mirror-image and zero-isoline elements** automatically.

**Solution validation** is built in — domain adequacy, vertical adequacy, concentration range and element-boundary checks — so a run can be rejected as physically meaningless instead of reporting a plausible-looking number.

**Source designer** (`aem_source_geometry.py`, `/aem/designer`) — a browser canvas where an arbitrary source polygon is drawn and automatically **packed with non-overlapping circular elements** (Shapely signed-distance packing, adjustable minimum and packing radius, multi-element selection). The packed geometry becomes the element configuration for a forward run.

**Inverse model** (`aem/at_inverse_model.py`) — recovers **one** of $\alpha_t$, $\alpha_l$, source radius $r$, $C_0$, $C_A$ or $\gamma$ from a **measured target plume length**, by bounded scanned search with per-parameter search bounds, step growth and tolerance. Non-estimated dispersivities are held at configured fixed values.

**Grid export** (`aem/at_grid_export.py`) — every solved field exports as long-form CSV (one `x, y, C` row per grid point) or as a lossless NPZ, written atomically. The last run per user is retained so the workbench can reopen it without a re-upload.

### 2.6 Data analysis workbench

Panel application `panel_data_analysis.py` on top of the pure-Python `data_analysis/` package (deliberately UI-free, so it is unit-testable). Data sources: the site database, an uploaded CSV, or the last AEM run.

| Tab | Contents |
|---|---|
| Univariate | Histograms; normal and lognormal distribution fits; kernel density estimation via KDEpy FFTKDE with ISJ / Silverman / Scott bandwidth selection and six kernels |
| Bivariate | Scatter with grouping and error bars; linear, polynomial, exponential and logarithmic fits reporting parameters and $R^{2}$, with 95 % confidence bands for the mean response by the delta method |
| Scientific | Gridded data: contour plots, profile extraction along either axis, $-\nabla C$ quiver fields — from AEM grids, numerical output, or any long-form CSV. MODFLOW 6 binaries (`.hds`, `.ucn`, `.cbc`) are converted to the same layout, so a simulated head field contours exactly like a measured concentration field |
| Statistics | Descriptive statistics including skew, kurtosis and missing counts |

Cross-cutting: four axis scales (linear, ln, log₁₀, inverse) applied by data transform so behaviour is identical on every plot; automatic conversion of raw column names into typeset LaTeX axis labels (`alpha_Tv` → $\alpha_{Tv}$, `plume_length_m` → "Plume length [m]"); a uniform two-decimal format that falls back to scientific notation outside $[0.01,\,10^{5}]$ so trace concentrations do not render as `0.00`; CSV and NPZ export of anything on screen.

### 2.7 Reporting

`pdf_report.py` (ReportLab) generates one branded report format shared by every model, from both the web pages and the dashboards: DFG and University of Tübingen logos, CAST/HYMCAT branding, model name, timestamp, paginated footer, metadata banner, full input-parameter table, output metric cards, result charts, optional simulated plume images, and a disclaimer.

### 2.8 Interface modes

Available for every model:

1. **Single simulation** — one parameter set, interactive result plot, live sliders for parameter sensitivity, PDF export.
2. **Multi-site comparison** — select several sites; the model runs once per site on that site's stored parameters, and the plot places modelled plume length against measured field plume length. One shared implementation (`panel_site_comparison.py`) serves all eight analytical and empirical models.
3. **Per-model About pages** (`/models/<slug>/about`) carrying the description and governing equation — public, no login.

Inputs are merged in a fixed order: model defaults → the selected site's database values → anything typed into the form. Database-sourced fields are marked as such in the interface.

---

## 3. Architecture

```text
Browser
  │
  ▼
Nginx :80  ── /static/*  → static assets
           ── /panel/*   → auth_request → Flask /auth/check → Panel :5007
           └── /*        → Gunicorn → Flask :5000
                                │
       ┌────────────────────────┼─────────────────────────┐
       ▼                        ▼                         ▼
  MySQL 8.4              Panel dashboards            Job queue (SQLite)
  users, sites           23 apps, Bokeh plots        subprocess workers
                                │                          │
                                ▼                          ▼
                    analytical / empirical /        MODFLOW 6 (mf6)
                    bioscreen / numerical /         AEM forward + inverse
                    AEM model modules
```

**Two-process design.** The page layer (Flask) and the interactive-computation layer (Panel) are separate services. Pages embed dashboards in same-origin iframes with model parameters passed in the URL. This keeps a long dashboard session from occupying a request worker, and lets dashboards be reached directly for scripted or power use.

**Identity is propagated, not asserted.** The reverse proxy validates the session against Flask and injects a trusted `X-Auth-Email` header into the dashboard request, overwriting anything the client sent. The dashboard service never trusts a query parameter for identity (a fallback exists for standalone local development and is off by default). This closes the obvious attack of editing `?email=` in an iframe URL to read another user's sites. Guests get a per-session id; every model works without an account, and an account is needed only to save sites.

**Asynchronous execution.** MODFLOW and AEM runs are submitted to a SQLite-backed queue, executed by separate worker processes, and polled by the browser. Runs can be cancelled, survive a page reload, and a crashed worker is reaped rather than leaving a job "running" forever. A multi-site numerical comparison is capped (default 12 runs) so one click cannot saturate the queue.

**Single source of truth for parameters.** `symbol_registry.py` holds canonical symbols, database columns, UI labels, units and per-model applicability; `param_meta.py` holds typeset notation and help text. Auto-fill, form rendering, dashboard tables and PDF reports all read from these, so a parameter is named and rendered identically everywhere.

**Per-model site filtering.** `model_site_validation.py` derives, from each model's own mathematical restrictions, which site records are admissible for it — Liedl divides by $C_A$, so sites with $C_A \le 0$ are hidden from its selector. Excluded sites are hidden *for that model only*, never deleted, and a missing value is not a violation (the page falls back to its manual default). Hydraulic conductivity is converted from the stored m s⁻¹ to the numerical model's m d⁻¹ at one explicit boundary (factor 86 400) with configurable plausibility bounds, and an audit script lists which sites are excluded and why.

### Technology stack

| Area | Technology |
|---|---|
| Web framework and routing | Flask 3, Jinja |
| Authentication | Flask-Login, Werkzeug password hashing |
| Interactive dashboards | Panel 1.4.5 |
| Plots | Bokeh 3.4.3 (interactive), Matplotlib (static and report) |
| Database | MySQL 8.4 via `mysql-connector-python` |
| Numerical simulation | FloPy + MODFLOW 6 (6.7.0), GWF/GWT |
| Analytic element method | NumPy/SciPy + modified Mathieu functions (Kuhlman) |
| Scientific computing | NumPy, SciPy, pandas, Shapely, KDEpy |
| Reports | ReportLab |
| Serving | Gunicorn, Nginx, Docker Compose |
| Runtime | Python 3.11 |

---

## 4. Security controls

CSRF tokens on all mutating forms · per-endpoint rate limits (login, registration, contact, site mutations) · login-timing equalisation against user enumeration · password policy with a length cap that bounds hashing work · request-size caps · HttpOnly/Secure/SameSite cookies · database errors redacted to a generic message while the detail is logged server-side · model-input errors translated to HTTP 400 rather than surfacing as 500 · non-spoofable identity propagation into the dashboard service.

---

## 5. Verification

- **~48 automated test modules** (`tests/`), run with pytest.
- **Numerical reference parity.** Both orientations are pinned against independently produced reference cases:

| Case | Reference $L_{max}$ | Application $L_{max}$ |
|---|---:|---:|
| Vertical | 42.0 m | 42.0 m |
| Horizontal | 36.1 m | 36.10288 m |

  These are checked-in fixtures, so any change that perturbs the numerical path fails the suite.
- **Equation regressions** for every analytical and empirical model.
- **Real solver smoke tests** — smallest-grid MODFLOW 6 runs actually execute, so a broken solver installation or FloPy API change is caught rather than mocked over.
- **Schema consistency test** comparing the Docker bootstrap SQL against the canonical runtime table definitions.
- **Security regressions**: malformed JSON bodies, forged cross-site POSTs, database-error redaction, rate-limit throttling, ownership filtering, login and logout flows.
- **Integration tests** for the Panel-behind-Nginx path including the websocket, and for rendered iframe URLs.
- **AEM tests** for the flow/solve path and the grid-export contract; **workbench tests** for fits, KDE, grids, statistics, notation, scales, formatting and MODFLOW ingestion.

---

## 6. Development history

| Period | Work |
|---|---|
| Nov–Dec 2025 | Repository initialised; Flask + Panel application skeleton |
| Dec 2025 – Feb 2026 | Responsive model page layouts, CSV/model integration, landing page; Docker-ready modelling stack |
| Mar–Apr 2026 | Numerical plume visualisation; analytical and numerical model updates; Panel-behind-Nginx proxy proven with a websocket integration test |
| Apr–May 2026 | MODFLOW 6 reference parity documented and matched; asynchronous numerical job execution; vertical site-selection validation |
| May–Jun 2026 | Security hardening; shared branded PDF reports; deferred numerical runs; pytest safety net; database schema single source of truth |
| Jun–Jul 2026 | Analysis workbench expanded; AEM package synced with upstream and wired end to end; `.npz` grid support; source designer with multi-element selection and adjustable packing radius |
| Jul–Aug 2026 | Reference database as default data source and accounts made optional; site database and visualisation work; numerical multi-scenario graphs; plume-comparison plot styling |

Branch names in the repository — `aem-upstream-sync`, `npz-workbench-support`, `designer-multiselect-minradius`, `numerical-plot-fixes`, `phase0-panel-frame-diagnostics`, `repo-hygiene` — map onto these workstreams if a finer-grained account is needed.

---

## 7. Limitations

State these rather than let a reviewer find them.

1. **Model selection toolbox is not implemented.** The Statistical-Threshold / AIC / AHP ranking approach remains a design, not code.
2. **Optimisation and Water Quality Index tiles are placeholders**, present on the landing page with no runtime module behind them.
3. **No in-place editing of site rows** (add, delete, clear, re-upload only) and **no migration system** — the runtime creates missing tables but does not alter existing ones.
4. **Invalid numeric text in a CSV becomes `NULL` rather than being rejected.** Convenient for sparse field data, but it can silently hide malformed values.
5. **Numerical grid cost is the user's responsibility.** There is a hard cell cap and an optional timeout, but fine grids are genuinely expensive. The tool is positioned for *preliminary* assessment, not detailed site modelling.
6. **The AEM inverse model estimates one parameter at a time** from a single target plume length. It is not a joint multi-parameter inversion and provides no formal uncertainty estimate.
7. **The hydraulic-conductivity unit assumption** (database m s⁻¹, numerical model m d⁻¹) and the default plausibility bounds are configuration, and should be reviewed per deployment.
8. **`README.md` currently lags the code** — it does not document the AEM toolbox, the data workbench, the asynchronous job queue, guest mode, the contact form or the About pages. Use this document and the code as the reference; the README will be brought forward.
9. **Encoding cleanup is outstanding** in several templates (mojibake from earlier text conversions). Cosmetic, but visible.
10. **No published DOI, versioned release tag or archived snapshot yet** — see §8.

---

## 8. Open decisions

1. **Application example** — which site, and who produces the runs. I can generate reproducible runs and exported figures for any site in the reference database or any supplied CSV.
2. **Version number and archived release.** A tagged release with a Zenodo (or equivalent) DOI needs deciding, and I need the go-ahead to cut the tag.
3. **Licence continuity.** The AEM package carries its own headers and the Mathieu library is MIT; the combined licence needs confirming before publication.
4. **Authorship and attribution.** The AEM code descends from work by Willi Kappler and Anton Köhler, extended by Alvin Yadav; the Mathieu implementation is Kuhlman's. Prof. Yadav should settle author order.
5. **Deployment target and public URL**, live by submission date.
6. **Funding lines.** Reports currently embed DFG (LI 727/29-1) and University of Tübingen branding — please confirm the current acknowledgements.

Available on request: a per-model parameter table (symbol, unit, source, default, admissible range) generated straight from `symbol_registry.py` and `param_meta.py` so notation matches the software exactly · screenshots or exported figures of any page or result · timing benchmarks across model classes · a reproducible example bundle (input CSV, exact parameters, output).

---

## 9. Where to look in the code

| Question | File |
|---|---|
| Analytical equations | `analytical_models.py` |
| Hbrid equations | `empirical_models.py` |
| BIOSCREEN-AT integration | `bioscreen_model.py` |
| MODFLOW 6 runners | `numerical_models.py` |
| AEM forward model | `aem/at_simulation.py`, `aem/at_element.py`, `aem/at_config.py` |
| AEM inverse model | `aem/at_inverse_model.py`, `aem/at_inverse_config.py`, `aem_jobs.py` |
| Source designer geometry | `aem_source_geometry.py` |
| Analysis workbench maths | `data_analysis/` (`fits`, `kde`, `stats`, `grids`, `scales`, `modflow`) |
| Parameter names, units, symbols | `symbol_registry.py`, `param_meta.py` |
| Per-model site admissibility | `model_site_validation.py`, `numerical_input_validation.py` |
| Job queue | `numerical_jobs.py` |
| Database schema | `data_queries.py` (canonical), `db_setup.sql` (mirror) |
| PDF reports | `pdf_report.py` |
| Public web routes | `app.py`, `site_routes.py`, `analytical_routes.py`, `empirical_routes.py`, `numerical_routes.py`, `aem_routes.py` |
| Dashboard registry | `panel_server.py` |
| Security controls | `security.py`, `panel_auth.py`, `route_guards.py` |
| Deployment | `Dockerfile`, `docker-compose.yml`, `nginx/default.conf`, `settings.py` |
| Implementation handbook | `README.md`  |
| User manual | <https://kamiz15.github.io/castbook-quarto/> |

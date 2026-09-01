# CAST Groundwater Contamination Assessment

CAST is a web application for groundwater-contamination assessment. It combines a Flask website, a MySQL site database, Panel dashboards, analytical and empirical plume-length equations, FloPy-based MODFLOW 6 simulations, an analytic-element-method (AEM) transport model with an inverse mode, a data-analysis workbench, Bokeh visualisations, and branded PDF reports.

This README documents the CAST application architecture, runtime flow, model implementations, configuration, routes, repository layout, and development procedures.

## Contents

1. [Implemented Features](#implemented-features)
2. [Architecture](#architecture)
3. [Application Flow](#application-flow)
4. [Model Catalogue](#model-catalogue)
5. [AEM Toolbox](#aem-toolbox)
6. [Data Analysis Workbench](#data-analysis-workbench)
7. [Asynchronous Job Queue](#asynchronous-job-queue)
8. [Database and Autofill](#database-and-autofill)
9. [Accounts, Guests, and Security](#accounts-guests-and-security)
10. [PDF Reports](#pdf-reports)
11. [Local Setup](#local-setup)
12. [Docker Setup](#docker-setup)
13. [Configuration](#configuration)
14. [Flask Routes](#flask-routes)
15. [Panel Routes](#panel-routes)
16. [Repository Layout](#repository-layout)
17. [File Guide](#file-guide)
18. [Known Limitations](#known-limitations)
19. [Change History](#change-history)
20. [Development Notes](#development-notes)

## Implemented Features

The application includes:

- A CAST landing page with animated background effects, toolbox navigation, documentation copy, and account links.
- Registration, Flask-Login authentication, logout, password hashing, and user-owned data access.
- Guest access: every model, dashboard, and simulation runs without an account. An account is required only to save sites to the user database. Guests are identified by a per-session id so one visitor's runs never reach another's.
- A bundled 112-site reference database used as the default data source for models and plots.
- A MySQL-backed site database with manual site entry, bulk CSV upload, filtering, and sorting.
- Database-to-model autofill for site-linked inputs, with database and manual fields shown separately.
- Analytical models:
  - Liedl et al. (2005), 2D.
  - Liedl 3D.
  - Chu et al.
  - Ham et al.
  - Cirpka et al. (2005).
  - BIOSCREEN-AT style concentration integration.
- Empirical models:
  - Maier and Grathwohl.
  - Birla et al.
- Numerical models:
  - Horizontal plan-view reactive transport in the `(x, y)` plane.
  - Vertical cross-section reactive transport in the `(x, z)` plane.
- An AEM (analytic element method) toolbox: forward transport model over circle/line/ellipse source elements, an interactive source designer with automatic element packing, and an inverse mode recovering one transport parameter from a target plume length.
- A data-analysis workbench: distribution fits, kernel density estimation, curve fits with confidence bands, gridded contour/profile/gradient plots, MODFLOW binary ingestion, and descriptive statistics.
- An asynchronous job queue for MODFLOW and AEM runs, with status polling, cancellation, and stale-job reaping.
- Interactive Bokeh result charts and editable Panel `Tabulator` scenario tables.
- Multi-site comparison pages that run any analytical or empirical model once per selected site and plot modelled against measured plume length.
- Public per-model About pages carrying the model description and governing equation.
- Branded PDF report generation with input tables, summary cards, charts, logos, and optional numerical plume images.
- A contact form with SMTP delivery, and imprint and privacy pages.
- A Docker Compose stack containing Nginx, Flask/Gunicorn, Panel, and MySQL services.

The earlier optimisation and Water Quality Index placeholder tiles are gone; the fifth landing tile (still carrying the id `model-optimization`) now opens the AEM toolbox. The model-selection toolbox described in the CAST documentation is not implemented.

## Architecture

### High-level Components

```text
Browser
  |
  | HTTP
  v
Flask application (app.py, default port 5000)
  |-- Jinja HTML pages
  |-- Flask-Login session (or per-session guest id)
  |-- site database forms and plots
  |-- model wrapper pages
  |-- AEM designer, forward, and inverse pages
  |-- GET PDF export routes
  |-- job submit / status / cancel / result endpoints
  |
  | iframe URL with query parameters
  v
Panel server (panel_server.py, default port 5007)
  |-- analytical dashboards
  |-- empirical dashboards
  |-- numerical dashboards
  |-- data analysis workbench
  |-- Bokeh plots
  |-- Panel FileDownload PDF exports
  |
  +---------------------> MySQL database
  |
  +---------------------> analytical_models.py
  +---------------------> empirical_models.py
  +---------------------> bioscreen_model.py
  +---------------------> numerical_models.py
  +---------------------> aem/ (at_simulation, at_inverse_model)
                              |
                              +----> FloPy
                              +----> MODFLOW 6 executable (MF6_EXE)

Job queue (numerical_jobs.py, SQLite under .numerical_jobs/)
  |-- submit / status / cancel / fetch_result
  +-- subprocess workers -> numerical_models.py or aem_jobs.py
```

The optional Docker deployment adds Nginx in front:

```text
Browser -> Nginx :80
              |-- /static/* -> mounted static directory
              |-- /panel/*  -> Panel service :5007
              +-- /*         -> Flask service :5000
```

See [Known Limitations](#known-limitations) before relying on the Docker stack for production deployment.

### Main Technology Stack

| Area | Technology |
| --- | --- |
| Website and HTTP routing | Flask 3 |
| Authentication helpers | Flask-Login and Werkzeug password hashing |
| Server-rendered UI | Jinja templates |
| Interactive model dashboards | Panel |
| Interactive charts | Bokeh |
| Database | MySQL 8 |
| Database client | `mysql-connector-python` |
| Numerical groundwater simulation | FloPy and MODFLOW 6 GWF/GWT |
| Analytic element method | NumPy/SciPy with modified Mathieu functions (Kuhlman, MIT) |
| Source-geometry packing | Shapely |
| Kernel density estimation | KDEpy |
| Tabular data handling | pandas, openpyxl |
| Job queue | SQLite (stdlib `sqlite3`) plus subprocess workers |
| Scientific calculations | NumPy and SciPy |
| Static numerical charts | Matplotlib |
| PDF reports | ReportLab |
| Production Flask process | Gunicorn |
| Reverse proxy | Nginx |
| Container orchestration | Docker Compose |

## Application Flow

### Public Page Flow

1. A browser requests a Flask page such as `/liedl/single`.
2. Flask-Login requires an authenticated account and the route loads site rows for `current_user.email`.
3. If the request includes `site_id`, the route maps database columns into model inputs.
4. The route combines:
   - model defaults,
   - selected-site values,
   - explicit URL query parameters.
5. Flask renders a Jinja template containing:
   - a conceptual-model image,
   - an optional site selector,
   - a split database/manual input form,
   - an iframe for the Panel output,
   - a PDF export link on supported single-run pages.
6. The iframe URL contains the model inputs plus `run=1` and `output_only=1`.
7. The Panel app reads those query values, computes the result, and renders output plots inside the iframe.

### Direct Panel Flow

Panel apps can also be opened directly on port `5007`, for example:

```text
http://localhost:5007/panel_liedl_single
http://localhost:5007/panel_numerical_vertical_single
```

Without `output_only=1`, most direct Panel pages show their own widgets, run buttons, editable multiple-scenario tables, and Panel-side PDF download buttons.

### Numerical Flow

Horizontal numerical pages:

1. Read the explicit domain and grid inputs: `Lx`, `Ly`, `nrow`, `ncol`, and `source`.
2. Run one MODFLOW 6 GWF flow model with the configured fixed-head, confined NPF, IMS, TDIS, and OC settings.
3. Feed the saved flow heads and budget into a separate GWT transport simulation through FMI.
4. Apply the horizontal CNC source with source rows centred in `y` at column `5`, donor value `gamma * Cd + 2 * Ca`, and acceptor `Ca` on the top and bottom rows.
5. Derive numerical plume length from the `C0 = 8` contour using the implemented contour-geometry method.
6. Render an interactive plan-view plot.
7. Offer profile and decreasing-concentration vector views as click-to-compute options; neither runs during the default simulation path.
8. Keep initial page load idle. MODFLOW runs only after the wrapper-level `Run Model` action is submitted.

Vertical numerical pages:

1. Read the explicit domain and grid inputs: `Lx`, `Lz`, `ncol`, and `nlay`.
2. Run one MODFLOW 6 GWF flow model with `nrow = 1`, `delc = 1`, top `0`, and the configured fixed-head, confined NPF, IMS, TDIS, and OC settings.
3. Feed the saved flow heads and budget into a separate GWT transport simulation through FMI.
4. Apply the vertical CNC source with donor cells `(k, 0, 5)` for `k in range(1, nlay)` with value `gamma * Cd + Ca`, and acceptor `Ca` across the top layer.
5. Derive numerical plume length from the `C0 = 8` mask/index method: `max(np.where(conc >= C0)[2]) * delr`, with no-cell cases returning `0`.
6. Render an interactive cross-section plot.
7. Offer profile and decreasing-concentration vector views as click-to-compute options; neither runs during the default simulation path.
8. Keep initial page load idle. MODFLOW runs only after the wrapper-level `Run Model` action is submitted.

Temporary numerical workspaces are created under `.numerical_runs/`.
Optional 3D numerical visualisation is not computed by the default numerical path.
Multiple-scenario numerical pages keep one Panel-side run button because their editable scenario table lives inside Panel. Their wrapper pages do not add a second run form.

The numerical path intentionally no longer sizes domains from analytical `Lmax`, no longer accepts `L_D_override`, and no longer derives grids from `delta_x`, `delta_y`, or `delta_z`. Those analytical sizing controls changed numerical results and were removed from the active numerical execution path.

## Model Catalogue

### Analytical and Screening Models

| Model | Primary implementation | Dashboard files | Main output |
| --- | --- | --- | --- |
| Liedl et al. (2005), 2D | `liedl_lmax()` in `analytical_models.py` | `panel_liedl_single.py`, `panel_liedl_multiple.py` | Maximum plume length |
| Liedl 3D | `liedl3d_lmax()` in `analytical_models.py` | `panel_liedl3d_single.py`, `panel_liedl3d_multiple.py` | Maximum plume length from an iterative solver |
| Chu et al. | `chu_lmax()` in `analytical_models.py` | `panel_chu.py` | Maximum plume length |
| Ham et al. | `ham_lmax()` in `analytical_models.py` | `panel_ham_single.py`, `panel_ham_multiple.py` | Maximum plume length |
| Cirpka et al. (2005) | `cirpka_lmax()` and `cirpka_domain_length()` in `analytical_models.py` | `panel_cirpka_single.py`, `panel_cirpka_multiple.py` | Maximum plume length and numerical domain length |
| BIOSCREEN-AT style screening | `bio()` and `bio_with_curve()` in `bioscreen_model.py` | `bioscreen_panel.py` | Plume length and concentration curve |

All standard analytical models provide single and multiple simulation pages. Single pages expose Flask-side PDF downloads. Most Panel dashboards also provide direct Panel-side PDF downloads after a run.

### Empirical Models

| Model | Primary implementation | Dashboard files | Main output |
| --- | --- | --- | --- |
| Maier and Grathwohl | `maier_lmax()` in `empirical_models.py` | `panel_maier_single.py`, `panel_maier_multiple.py` | Empirical maximum plume length |
| Birla et al. | `birla_lmax()` in `empirical_models.py` | `panel_birla_single.py`, `panel_birla_multiple.py` | Recharge-adjusted empirical maximum plume length |

### Numerical Models

| Model | Primary implementation | Dashboard files | Main output |
| --- | --- | --- | --- |
| Horizontal plan view `(x, y)` | `run_numerical_model_horizontal()` | `panel_numerical_horizontal_single.py`, `panel_numerical_horizontal_multiple.py` | Simulated plume contour and numerical `Lmax` |
| Vertical cross-section `(x, z)` | `run_numerical_model()` | `panel_numerical_vertical_single.py`, `panel_numerical_vertical_multiple.py` | Simulated concentration mask and numerical `Lmax` |

The numerical runner, Docker image, environment templates, UI labels, and PDF labels consistently use MODFLOW 6 GWF/GWT through FloPy.
The checked-in numerical reference fixtures pin the expected plume-length outputs:

| Fixture | Reference plume_length | App plume_length |
| --- | ---: | ---: |
| Vertical reference input | `42.0` | `42.0` |
| Horizontal reference input | `36.1` | `36.10288085194749` |

Earlier combined-orientation dashboards are retained under `archive/legacy_numerical/` for reference only.

### Multi-site Comparison

`panel_site_comparison.py` implements one shared multiple-simulation panel for every analytical and empirical model. The sidebar selects sites, the model runs once per selected site using that site's database parameters, and the plot places the modelled plume length beside the measured one. Only the per-model specification differs, so there is one panel body instead of eight near-copies. Parameters a site leaves `NULL` fall back to the values carried in the Panel URL.

Site admissibility is decided per model by `model_site_validation.py`, which encodes each model's own mathematical restrictions (for example, models that divide by `C_EA0` require `electron_acceptor_o2 > 0`). Violating sites are hidden from that model's selector only. They are never deleted and stay selectable for every model whose restrictions they satisfy. A `NULL` field is not a violation: the page falls back to its manual default. The vertical numerical model keeps its own stricter filter in `numerical_input_validation.py`, which does require the fields to be present.

## AEM Toolbox

Package `aem/`, routed by `aem_routes.py` under `/aem`. File headers record the provenance: written by Alvin Yadav, based on code from Willi Kappler and Anton Koehler; the Mathieu-function library is Kuhlman's MIT-licensed implementation.

### Forward Model

`aem/at_simulation.py` solves steady-state reactive plumes for source geometries built from circle, line, and ellipse elements:

1. Load a configuration of source elements (`aem/at_config.py`, `aem/at_element.py`).
2. For vertical orientation, add mirror-image and zero-isoline elements to enforce the water-table boundary condition.
3. Fit modified-Mathieu-function expansion coefficients by least squares so each element boundary carries its prescribed concentration.
4. Evaluate the concentration field on a grid. Elements are partitioned into coupling groups so weakly interacting sources are solved separately and iteratively rather than as one dense system; grid evaluation is parallelised with a multiprocessing pool.
5. Post-process: extract `L_max`, run the validation checks, and build plots.

Validation checks (`validate_solution`) cover domain adequacy, vertical adequacy, concentration range, and element boundary error, so a physically meaningless solution is rejected rather than reported.

### Source Designer

`aem_source_geometry.py` holds the framework-free packing algorithms. A polygon drawn on the designer canvas is packed with non-overlapping circles using Shapely signed-distance geometry, with a configurable minimum radius and packing radius, and multi-element selection. The packed configuration is saved per user and seeds a forward run.

### Inverse Model

`aem/at_inverse_model.py`, marshalled by `run_aem_inverse()` in `aem_jobs.py`, recovers one parameter from a target plume length. Supported parameters are `alpha_t`, `alpha_l`, `r`, `C0`, `ca`, and `gamma`. Search bounds, initial step factor, step growth, and `L` tolerance are configured per parameter in `aem/at_inverse_config.py`. The dispersivity not being estimated is held at a configured fixed value. The result carries the recovered value, the achieved `L_max`, the target, the fixed parameters, a convergence flag, and the matched field arrays.

### Grid Export

`aem/at_grid_export.py` writes a solved field either as long-form CSV (one `x, y, concentration` row per grid point) or as NPZ (1-D x axis, 1-D y axis, 2-D concentration), both atomically, under one shared column contract. The last run per user is retained in `AEM_EXPORT_DIR` so the workbench can reopen it without a re-upload.

Live `ATSimulation` objects hold `Mathieu` instances and a multiprocessing pool and are never pickled. `AEMForwardResult` and `AEMInverseResult` carry only plain arrays and scalars so they round-trip through the job queue.

## Data Analysis Workbench

Panel application `panel_data_analysis.py`, mounted at `/panel_data_analysis` and wrapped by `/data_analysis`. The maths lives in the `data_analysis/` package, which imports no Panel and is unit-tested directly.

Data sources: the site database, an uploaded CSV, or the last AEM run for the current user.

| Tab | Contents |
| --- | --- |
| Univariate | Histograms, normal and lognormal distribution fits, and KDE via KDEpy `FFTKDE` with ISJ, Silverman, or Scott bandwidth and six kernels (`data_analysis/kde.py`, `stats.py`) |
| Bivariate | Scatter with grouping and error bars; linear, polynomial, exponential, and logarithmic fits with parameters, R2, and 95% delta-method confidence bands for the mean response (`data_analysis/fits.py`) |
| Scientific | Gridded data: contour, profile extraction along either axis, and `-grad C` quiver fields, from AEM grids, numerical results, or long-form CSV (`data_analysis/grids.py`) |
| Statistics | `describe()` augmented with skew, kurtosis, and missing counts |

Supporting modules:

| File | Responsibility |
| --- | --- |
| `data_analysis/datasets.py` | CSV intake, encoding fallbacks, column typing; every failure raises a user-safe `ValueError` |
| `data_analysis/scales.py` | Linear, ln, log10, and inverse axis scales, applied by data transform rather than axis type so all four behave identically |
| `data_analysis/notation.py` | Raw column names to typeset LaTeX axis labels; requires `pn.extension("mathjax")` |
| `data_analysis/formatting.py` | Two-decimal display convention, falling back to scientific notation outside `[0.01, 100000]` |
| `data_analysis/modflow.py` | Converts MODFLOW 6 `.hds`, `.ucn`, and `.cbc` binaries into the same long-form layout the Scientific tab consumes; pass domain extents for real metres rather than cell indices |
| `data_analysis/plots.py` | Bokeh figure builders, no Panel imports |

Everything on screen exports: statistics CSV, data CSV, and grid NPZ.

## Asynchronous Job Queue

`numerical_jobs.py` is a generic queue keyed by `kind`, backed by SQLite under `.numerical_jobs/` (`NUMERICAL_JOB_ROOT`), with results pickled to `results/` and worker output to `logs/`.

- Statuses: `queued`, `running`, `done`, `failed`, `cancelled`.
- `submit_job(kind, params)` enqueues; `pump_queue()` starts workers up to `NUMERICAL_MAX_CONCURRENCY` (default 2); each job runs in its own subprocess.
- `cancel_job()` terminates a running worker; `_reap_stale_jobs()` fails jobs whose process is gone or which exceed `NUMERICAL_JOB_TIMEOUT_SECONDS` (default 900), so a crashed worker never leaves a job stuck in `running`.
- Worker failures are logged in full; the client sees a generic message. AEM workers may prefix a message that is safe to show verbatim, and only that first line is passed through.
- `NUMERICAL_MULTIPLE_MAX_RUNS` (default 12) caps how many runs one multi-site numerical comparison may queue.

Both the numerical routes (`/numerical/jobs/...`) and the AEM routes (`/aem/jobs/...`) use this queue. Job metadata records the submitting identity so one user cannot poll or download another user's result.

## Accounts, Guests, and Security

Model pages, dashboards, and simulations are public. An account is required only for saving sites, because `sites.user_email` is a foreign key onto `users`.

- Guests receive a per-session id (`guest-<random>@guest.invalid`, `security.current_email()`), so an anonymous visitor's runs and jobs stay separated from everyone else's without creating a database row.
- Identity reaches the Panel service only through the reverse-proxy-injected `X-Auth-Email` header, which Nginx sets from the `auth_request` to `/auth/check` and always overwrites. `panel_auth.authenticated_email()` never trusts `?email=` unless `PANEL_TRUST_QUERY_EMAIL` is explicitly enabled for standalone local development.
- `security.py` provides CSRF tokens for mutating forms, per-endpoint rate limits, a password policy with a maximum length that bounds hashing work, JSON and form body validation, and a generic database-error message.
- `app.py` equalises login response timing with a dummy hash comparison so a non-existent account cannot be identified by timing.
- Cookies are HttpOnly, SameSite=Lax, and Secure by default (`SESSION_COOKIE_SECURE`). `MAX_CONTENT_LENGTH` rejects oversized bodies.
- `route_guards.guard_model_errors` turns model-input exceptions (`ValueError`, `TypeError`, `ZeroDivisionError`, `OverflowError`) into HTTP 400 rather than 500.

## Database and Autofill

### Runtime Schema

`data_queries.py` is the active database access module. It creates these tables if needed:

```text
users
  id
  username
  email                 UNIQUE
  password_hash
  country
  organisation

sites
  id
  user_email            FOREIGN KEY -> users.email
  site_unit
  compound
  aquifer_thickness
  plume_length
  plume_width
  hydraulic_conductivity
  electron_donor
  electron_acceptor_o2
  electron_acceptor_no3
```

### Site Data Page

`GET /sites` renders the current site table.

`POST /sites` supports:

- `action=manual`: insert one site record.
- `action=upload_csv`: parse and insert multiple records.

The table view supports per-column substring filtering and ascending or descending sorting.

### CSV Columns

The canonical CSV headers are:

```text
site_unit
compound
aquifer_thickness
plume_length
plume_width
hydraulic_conductivity
electron_donor
electron_acceptor_o2
electron_acceptor_no3
```

The CSV importer also accepts several human-readable aliases, normalises case and punctuation, strips UTF-8 BOM markers, and converts numeric blanks or markers such as `N/A`, `null`, and `-` to SQL `NULL`.

### Model Autofill

`symbol_registry.py` provides canonical database-to-model mappings:

| Canonical symbol | Database column | Typical use |
| --- | --- | --- |
| `M` | `aquifer_thickness` | Aquifer or source thickness |
| `S_w` | `plume_width` | Source width |
| `K` | `hydraulic_conductivity` | Database conductivity in `m/s`; converted to numerical `hk` in `m/d` during numerical autofill |
| `C_D` | `electron_donor` | Electron donor concentration |
| `C_A` | `electron_acceptor_o2` | Electron acceptor concentration |

Inputs such as dispersivities, porosity, heads, grid spacing, source buffers, simulation time, threshold concentration, stoichiometric ratio, retardation, and decay coefficients are not stored in the current database and must be entered manually.

The analytical and numerical Flask routes use `symbol_registry.py`. The empirical routes currently use a smaller local mapping for `M`, `Ca`, and `Cd`.

## PDF Reports

`pdf_report.py` defines `CASTReport`, a ReportLab-based PDF generator shared by Flask routes and Panel apps.

Generated reports can include:

- HYMCAT / CAST branding.
- DFG and University of Tuebingen logos.
- Model name, timestamp, and page number with total page count.
- A metadata banner.
- An input-parameter table.
- Output metric cards.
- A disclaimer.
- Matplotlib comparison charts.
- Optional numerical plume images.

Every single-model wrapper uses the same report-download card partial at `templates/report_download_card.html`. Analytical, empirical, BIOSCREEN, and numerical PDF exports all use the shared branded `CASTReport` engine.

Single-run Flask pages expose report URLs such as `/liedl/single/export`. Panel dashboards use `pn.widgets.FileDownload` for reports generated from their current interactive state.

## Local Setup

### Prerequisites

- Python 3.11 is recommended because the Docker image uses Python 3.11.
- MySQL 8 or a compatible MySQL server.
- A MODFLOW 6 executable for numerical pages.
- Two terminals: one for Flask and one for Panel.

### Install Python Dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Configure Environment Variables

Create `.env` from `.env.example`, then adjust it for local execution:

```powershell
Copy-Item .env.example .env
```

For a typical local Windows setup, review at least:

```dotenv
DB_HOST=localhost
DB_PORT=3306
PANEL_PUBLIC_BASE=http://localhost:5007
PANEL_ALLOW_ORIGINS=localhost:5007,127.0.0.1:5007,localhost:5000,127.0.0.1:5000
MF6_EXE=C:\absolute\path\to\mf6.exe
```

For local development, `numerical_models.py` searches `.modflow_bin/` automatically if `MF6_EXE` is not set. Keep platform-specific solver binaries outside version control.

### Prepare MySQL

Create the `cast_project` database and configure a MySQL user with access to it. The application creates missing tables on its first connection, but the database itself must already exist.

The application does not create a demo login or hard-code account credentials. Register an account through `/register` after startup. If a deployment needs a demonstration account, create it explicitly through the registration flow or a deployment-specific seed process with credentials supplied outside version control.

`data_queries.py` owns the canonical table definitions. `db_setup.sql` mirrors those definitions for Compose bootstrap and can also initialise an existing database manually:

```powershell
mysql -u root -p cast_project < db_setup.sql
```

### Start Panel

```powershell
python panel_server.py
```

Panel listens on:

```text
http://localhost:5007
```

### Start Flask

In a second activated terminal:

```powershell
python app.py
```

Flask listens on:

```text
http://localhost:5000
```

### View the Current Workspace

For local two-process development, open:

```text
http://localhost:5000
```

Panel dashboards are served separately at:

```text
http://localhost:5007
```

For the Docker Compose deployment, open the Nginx entrypoint instead:

```text
http://localhost
```

### Suggested Manual Check

1. Register an account.
2. Log in.
3. Open `/sites`.
4. Add a site manually or upload a CSV.
5. Open an analytical single-run page and load the site.
6. Confirm database-backed inputs are marked `DB`.
7. Run a numerical page only after `MF6_EXE` is available.
8. Download a PDF report.

## Docker Setup

The repository contains a four-service Compose stack:

| Service | Purpose | Internal port |
| --- | --- | --- |
| `nginx` | Public reverse proxy and static-file server | `80` |
| `flask` | Gunicorn serving `app:app` | `5000` |
| `panel` | Panel dashboards from `panel_server.py` | `5007` |
| `db` | MySQL 8.4 with persistent `mysql_data` volume | `3306` |

Build and start:

```powershell
docker compose up --build
```

The intended public URL is:

```text
http://localhost
```

The Docker image downloads the official MODFLOW 6 `6.7.0` Linux release archive, installs `mf6` and its companion `libmf6.so`, and configures `MF6_EXE=/usr/local/bin/mf6`. It also serves Panel through Nginx at the same-origin `/panel/` prefix and checks the Flask-Login session before proxying Panel requests. Flask-rendered Bokeh pages can request Panel browser extensions from `/static/extensions/panel/`; Nginx rewrites only that Panel-owned subtree to `/panel/static/extensions/panel/` on the Panel service so it does not collide with Flask's remaining `/static/` files.

## Configuration

`settings.py` loads `.env` when `python-dotenv` is available.

| Variable | Default or example purpose |
| --- | --- |
| `SECRET_KEY` | Required Flask session signing key. Set it in the environment; there is no code default. |
| `FLASK_DEBUG` | Enables Flask debug mode. |
| `FLASK_HOST` | Flask bind host, default `0.0.0.0`. |
| `FLASK_PORT` | Flask port, default `5000`. |
| `DB_HOST` | MySQL hostname. Use `localhost` locally and `db` in Compose. |
| `DB_PORT` | MySQL port, default `3306`. |
| `DB_USER` | Required MySQL application user. Set it in the environment; there is no code default. |
| `DB_PASSWORD` | Required MySQL application password. Set it in the environment; there is no code default. |
| `DB_NAME` | MySQL database, default `cast_project`. |
| `MYSQL_ROOT_PASSWORD` | Required by the Compose MySQL service. Set it in the environment; it is not consumed by Flask. |
| `PANEL_PUBLIC_BASE` | Browser-facing Panel base. Use `http://localhost:5007` for local two-process development and `/panel` behind the Compose Nginx proxy. Its path also drives the Panel server prefix. |
| `PANEL_HOST` | Panel bind host, default `0.0.0.0`. |
| `PANEL_PORT` | Panel port, default `5007`. |
| `PANEL_ALLOW_ORIGINS` | Comma-separated websocket origins accepted by Panel. |
| `MF6_EXE` | MODFLOW 6 executable used by numerical code. The Docker image installs it at `/usr/local/bin/mf6`. |
| `SESSION_COOKIE_SECURE` | Send session and remember cookies over HTTPS only. Default on; set false for plain-HTTP local development. |
| `TRUST_PROXY_HEADERS` | Trust the reverse proxy's `X-Real-IP` for rate-limit identity. Default on; disable only if Flask is exposed without the bundled proxy. |
| `PANEL_TRUST_QUERY_EMAIL` | Let the Panel service fall back to `?email=` when no proxy injects `X-Auth-Email`. Default off; local development only. |
| `CONTACT_EMAIL`, `CONTACT_FROM_EMAIL`, `CONTACT_MAX_MESSAGE_LENGTH` | Contact-form destination, sender, and message-length cap. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS` | Contact-form mail delivery. Without `SMTP_HOST` the form logs and acknowledges instead of sending. |
| `MAX_SITE_UPLOAD_ROWS` | Cap on site rows accepted in one CSV upload, default `10000`. |
| `MAX_REQUEST_BYTES` | Hard request-body cap, default 50 MB. Match this to the nginx `client_max_body_size`. |
| `AEM_EXPORT_DIR` | Where an AEM forward run drops its concentration grid, one file per user, default `.aem_exports`. |
| `NUMERICAL_JOB_ROOT` | Job-queue root holding the SQLite database, pickled results, and worker logs, default `.numerical_jobs`. |
| `NUMERICAL_MAX_CONCURRENCY` | Simultaneous job workers, default `2`. |
| `NUMERICAL_JOB_TIMEOUT_SECONDS` | Age after which a running job is reaped as stale, default `900`. |
| `NUMERICAL_MULTIPLE_MAX_RUNS` | Cap on runs queued by one multi-site numerical comparison, default `12`. |
| `NUMERICAL_MAX_CELLS` | Hard pre-run cap on `n_cols * n_rows`, default `40000`. Increase grid spacing before raising this limit. |
| `NUMERICAL_SOLVER_TIMEOUT_S` | Per-process timeout for each MF6 flow or transport run, default `0` for disabled. Set a positive value only when a deployment needs an explicit ceiling. |
| `NUMERICAL_HK_MIN_M_PER_DAY` | Lower plausibility bound for site-linked conductivity after conversion to numerical `hk` in `m/d`, default `0.000001`. |
| `NUMERICAL_HK_MAX_M_PER_DAY` | Upper plausibility bound for site-linked conductivity after conversion to numerical `hk` in `m/d`, default `1000`. |
| `VERTICAL_NUMERICAL_NCOL_MIN` | Minimum accepted vertical-model column count for site-linked runs, default `6`. |
| `VERTICAL_NUMERICAL_NLAY_MIN` | Minimum accepted vertical-model layer count for site-linked runs, default `2`. |

Keep `.env` private. Copy placeholder names from the tracked `.env.example`, then provide real values only through your local environment or ignored `.env`. The tracked `.env.docker` file contains non-secret Docker settings only.

## Flask Routes

### Core and Authentication Routes

| Method | Route | Handler | Purpose |
| --- | --- | --- | --- |
| `GET` | `/` | `home()` | Landing page. |
| `GET` | `/health` | `health()` | Liveness plus database reachability, for container health checks. Returns 503 on a database outage. |
| `GET` | `/me` | `me()` | JSON authentication state for frontend `fetch()` callers; 401 rather than a redirect when signed out. |
| `GET` | `/models/<slug>/about` | `model_about()` | Public per-model description and governing equation page. |
| `POST` | `/contact` | `contact()` | Rate-limited, CSRF-protected contact form; sends via SMTP when configured, otherwise logs and acknowledges. |
| `GET` | `/login` | `login_page()` | Login form. |
| `POST` | `/login` | `authenticate()` | JSON login request; authenticates a loader-backed Flask-Login user. |
| `GET` | `/auth/check` | `auth_check()` | Internal Nginx subrequest endpoint for the Flask-Login session protecting `/panel/`. |
| `GET` | `/register` | `register_page()` | Registration form. |
| `POST` | `/register` | `register_user()` | JSON registration request with `username`, `email`, `password`, and `confirmPassword`; hashes the password and inserts the user. |
| `GET` | `/logout` | `logout()` | Logs out the Flask-Login user and returns home. |

### Site Database and Plot Routes

| Method | Route | Handler | Purpose |
| --- | --- | --- | --- |
| `GET`, `POST` | `/sites` | `site_database()` | Site table, manual insert, CSV upload, filters, and sorting. Guests may browse but not save. |
| `POST` | `/sites/<int:site_id>/delete` | `delete_site()` | Delete one owned site row. |
| `POST` | `/sites/clear` | `clear_sites()` | Delete every site owned by the caller. |
| `GET` | `/sites/user.<file_format>` | `user_database_export()` | Filtered user-database export as `csv`, `xlsx`, or `pdf`. |
| `GET` | `/sites/reference.<file_format>` | `reference_database_export()` | Reference-database export as `csv`, `xlsx`, or `pdf`. |
| `GET` | `/dispersivity-data` | `dispersivity_data()` | Legacy dispersivity dataset page with histogram, box, and scatter assets. |
| `GET` | `/data_analysis` | `data_analysis()` | Wrapper page embedding the data-analysis workbench. |
| `POST` | `/report/export` | `report_export()` | PDF export of the current analysis view. |
| `GET` | `/plot_bar` | `plot_bar()` | User/reference plume-length bar chart page. |
| `GET` | `/plot_hist` | `plot_hist()` | Default plume-length histogram page. |
| `GET` | `/plot_box` | `plot_box()` | Default plume-length box-plot page. |
| `POST` | `/plots/histogram` | `histogram_json()` | JSON or form endpoint returning Bokeh histogram components. |
| `POST` | `/plots/boxplot` | `boxplot_json()` | JSON or form endpoint returning Bokeh box-plot components. |

### Analytical Routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/analytical` | Analytical model landing page. |
| `GET` | `/liedl/single` | Liedl single-run wrapper page. |
| `GET` | `/liedl/single/export` | Liedl single-run PDF. |
| `GET` | `/liedl/multiple` | Liedl multiple-run wrapper page. |
| `GET` | `/chu/single` | Chu single-run wrapper page. |
| `GET` | `/chu/single/export` | Chu single-run PDF. |
| `GET` | `/chu/multiple` | Chu multiple-run wrapper page. |
| `GET` | `/ham/single` | Ham single-run wrapper page. |
| `GET` | `/ham/single/export` | Ham single-run PDF. |
| `GET` | `/ham/multiple` | Ham multiple-run wrapper page. |
| `GET` | `/bioscreen/single` | BIOSCREEN-AT single-run wrapper page. |
| `GET` | `/bioscreen/single/export` | BIOSCREEN-AT single-run PDF. |
| `GET` | `/bioscreen/multiple` | BIOSCREEN-AT multiple-run wrapper page. |
| `GET` | `/liedl3d/single` | Liedl 3D single-run wrapper page. |
| `GET` | `/liedl3d/single/export` | Liedl 3D single-run PDF. |
| `GET` | `/liedl3d/multiple` | Liedl 3D multiple-run wrapper page. |
| `GET` | `/cirpka/single` | Cirpka single-run page with specialised Flask-side result preparation. |
| `GET` | `/cirpka/single/export` | Cirpka single-run PDF. |
| `GET` | `/cirpka/multiple` | Cirpka multiple-run wrapper page. |

### Empirical Routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/empirical` | Empirical model landing page. |
| `GET` | `/empirical/maier/single` | Maier and Grathwohl single-run page. |
| `GET` | `/empirical/maier/single/export` | Maier and Grathwohl single-run PDF. |
| `GET` | `/empirical/maier/multiple` | Maier and Grathwohl multiple-run page. |
| `GET` | `/empirical/birla/single` | Birla single-run page. |
| `GET` | `/empirical/birla/single/export` | Birla single-run PDF. |
| `GET` | `/empirical/birla/multiple` | Birla multiple-run page. |

### Numerical Routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/numerical` | Numerical model landing page. |
| `GET` | `/numerical/single` | Compatibility redirect to `/numerical/vertical/single`. |
| `GET` | `/numerical/multiple` | Compatibility redirect to `/numerical/vertical/multiple`. |
| `GET` | `/numerical/horizontal/single` | Horizontal numerical single-run page. |
| `GET` | `/numerical/horizontal/single/export` | Runs a horizontal numerical simulation and returns a PDF. |
| `GET` | `/numerical/horizontal/multiple` | Horizontal numerical multiple-run page. |
| `GET` | `/numerical/vertical/single` | Vertical numerical single-run page. |
| `GET` | `/numerical/vertical/single/export` | Runs a vertical numerical simulation and returns a PDF. |
| `GET` | `/numerical/vertical/multiple` | Vertical numerical multiple-run page. |

### Numerical Job Routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/numerical/jobs` | Submit a numerical run to the queue and return its job id. |
| `GET` | `/numerical/jobs/<job_id>` | Poll job status and result metadata. |
| `POST` | `/numerical/jobs/<job_id>/cancel` | Cancel a queued or running job. |
| `GET` | `/numerical/jobs/<job_id>/report` | PDF report built from a completed job. |
| `GET` | `/numerical/jobs/<job_id>/download/<kind>` | Download a run artifact, including the MODFLOW `.hds` and `.ucn` binaries. |

### AEM Routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/aem` | AEM toolbox landing page. |
| `GET` | `/aem/designer` | Interactive source-geometry designer. |
| `GET` | `/aem/forward` | Forward-simulation page. |
| `GET` | `/aem/inverse` | Inverse parameter-estimation page. |
| `POST` | `/aem/api/pack` | Pack a drawn polygon with non-overlapping circular elements. |
| `POST` | `/aem/api/repack` | Re-pack an existing design at a new radius. |
| `POST` | `/aem/api/design` | Save the current designer configuration for the caller. |
| `POST` | `/aem/api/forward` | Submit a forward AEM run to the job queue. |
| `POST` | `/aem/api/inverse` | Submit an inverse AEM run to the job queue. |
| `GET` | `/aem/jobs/<job_id>` | Poll AEM job status. |
| `POST` | `/aem/jobs/<job_id>/cancel` | Cancel an AEM job. |
| `GET` | `/aem/jobs/<job_id>/result` | JSON result payload for a completed AEM job. |
| `GET` | `/aem/jobs/<job_id>/result.csv` | Long-form `x, y, concentration` grid export. |
| `GET` | `/aem/jobs/<job_id>/result.npz` | Native grid export for the workbench. |

## Panel Routes

`panel_server.py` mounts these Panel applications:

| Panel route | App function | Purpose |
| --- | --- | --- |
| `/` | `liedl_single_app` | Convenience root; opens Liedl single simulation. |
| `/panel_liedl_single` | `liedl_single_app` | Liedl single simulation. |
| `/panel_liedl_multiple` | `liedl_multiple_app` | Liedl scenario table. |
| `/panel_liedl3d_single` | `liedl3d_single_app` | Liedl 3D single simulation. |
| `/panel_liedl3d_multiple` | `liedl3d_multiple_app` | Liedl 3D scenario table. |
| `/panel_chu_single` | `chu_single_app` | Chu single simulation. |
| `/panel_chu_multiple` | `chu_multiple_app` | Chu scenario table. |
| `/panel_ham_single` | `ham_single_app` | Ham single simulation. |
| `/panel_ham_multiple` | `ham_multiple_app` | Ham scenario table. |
| `/panel_bioscreen_single` | `bioscreen_single_app` | BIOSCREEN-AT single simulation. |
| `/panel_bioscreen_multiple` | `bioscreen_multiple_app` | BIOSCREEN-AT time sweep. |
| `/panel_maier_single` | `maier_single_app` | Maier and Grathwohl single simulation. |
| `/panel_maier_multiple` | `maier_multiple_app` | Maier and Grathwohl scenario table. |
| `/panel_birla_single` | `birla_single_app` | Birla single simulation. |
| `/panel_birla_multiple` | `birla_multiple_app` | Birla scenario table. |
| `/panel_cirpka_single` | `cirpka_single_app` | Cirpka single output. |
| `/panel_cirpka_single_output` | `cirpka_single_app` | Alias used by Cirpka single wrapper page. |
| `/panel_cirpka_multiple` | `cirpka_multiple_app` | Cirpka scenario table. |
| `/panel_data_analysis` | `data_analysis_app` | Data-analysis workbench. |
| `/panel_numerical_horizontal_single` | `numerical_horizontal_single_app` | Horizontal numerical single simulation. |
| `/panel_numerical_horizontal_multiple` | `numerical_horizontal_multiple_app` | Horizontal numerical scenario table. |
| `/panel_numerical_vertical_single` | `numerical_vertical_single_app` | Vertical numerical single simulation. |
| `/panel_numerical_vertical_multiple` | `numerical_vertical_multiple_app` | Vertical numerical scenario table. |

Panel is configured with one-hour session-token expiration, a server prefix derived from `PANEL_PUBLIC_BASE`, and websocket origins from `PANEL_ALLOW_ORIGINS`.

## Repository Layout

```text
cast_landing_demo/
|-- app.py                         Flask entrypoint and account routes
|-- settings.py                    Environment-backed configuration
|-- data_queries.py                Active MySQL schema and data access
|-- site_routes.py                 Site database and plot endpoints
|-- analytical_routes.py           Analytical wrapper and export routes
|-- empirical_routes.py            Empirical wrapper and export routes
|-- numerical_routes.py            Numerical wrapper, job, and export routes
|-- aem_routes.py                  AEM pages, designer API, and job endpoints
|-- analytical_models.py           Analytical equations
|-- empirical_models.py            Empirical equations
|-- bioscreen_model.py             BIOSCREEN integration
|-- numerical_models.py            FloPy MODFLOW 6 runners
|-- numerical_jobs.py              Generic SQLite-backed async job queue
|-- aem/                           AEM package: elements, simulation, inverse, export
|-- aem_jobs.py                    AEM job marshalling and pickle-able results
|-- aem_source_geometry.py         Source-polygon element packing
|-- data_analysis/                 Workbench maths, free of Panel imports
|-- model_site_validation.py       Per-model site admissibility rules
|-- numerical_input_validation.py  Vertical numerical site validation and unit conversion
|-- param_meta.py                  Per-input notation symbol and help text
|-- security.py                    CSRF, rate limits, identity, request validation
|-- route_guards.py                Model-input errors to HTTP 400
|-- symbol_registry.py             Canonical database-to-model aliases
|-- plot_functions.py              Bokeh and Matplotlib plot helpers
|-- pdf_report.py                  ReportLab PDF engine
|-- panel_server.py                Panel route registry
|-- panel_*.py                     Panel dashboards and shared helpers
|-- panel_theme.py                 Central Panel theme matching the site design
|-- panel_auth.py                  Trusted-header identity for Panel sessions
|-- panel_site_comparison.py       Shared multi-site comparison panel
|-- panel_data_analysis.py         Data-analysis workbench dashboard
|-- bioscreen_panel.py             BIOSCREEN dashboards
|-- templates/                     Jinja HTML pages
|-- static/                        CSS, browser JavaScript, images, report assets
|-- scripts/                       Maintenance and repinning utilities
|-- tests/                         Pytest suite and fixtures
|-- archive/                       Non-runtime reference artifacts and retired drafts
|-- nginx/default.conf             Docker reverse proxy
|-- solvers/                       Optional solver-binary directory
|-- db_setup.sql                   Compose MySQL bootstrap schema
|-- docker-compose.yml             Multi-service container stack
|-- Dockerfile                     Python image and MODFLOW 6 installation
|-- requirements.txt               Python dependencies
|-- requirements-dev.txt           Test dependencies
|-- .env.example                   Environment-variable example
|-- .env.docker                    Compose application environment
|-- .gitignore                     Local artifact exclusions
|-- .dockerignore                  Docker-context exclusions
|-- .modflow_bin/                  Ignored local solver executables
|-- .numerical_runs/               Ignored numerical scratch directories
|-- .numerical_jobs/               Ignored job-queue database, results, and logs
|-- .aem_exports/                  Ignored per-user AEM grid exports
`-- README.md                      This handbook
```

## File Guide

### Core Flask Files

| File | Responsibility |
| --- | --- |
| `app.py` | Creates Flask app, configures Flask-Login loader, registers blueprints, renders home/login/register pages, authenticates accounts, hashes passwords, inserts accounts, and logs users out. |
| `settings.py` | Loads `.env`, parses boolean and CSV values, and defines Flask, MySQL, and Panel configuration. |
| `data_queries.py` | Active MySQL layer. Ensures runtime tables, opens connections, lists site rows, normalises numeric input, and inserts one or many sites. |
| `site_routes.py` | Site database UI, CSV alias mapping, CSV validation, table filtering and sorting, reference-database rows and exports, site deletion and clearing, full-page plot handlers, and JSON Bokeh plot endpoints. |
| `security.py` | CSRF tokens, per-endpoint rate limiting, guest-session identity, email and password validation, JSON and form body guards, and the generic database-error message. |
| `route_guards.py` | Translates model-input exceptions raised inside a view into HTTP 400. |
| `param_meta.py` | One source of truth for each input's notation symbol and help text, shared by the analytical, empirical, and numerical routes. |

### Domain Model Files

| File | Responsibility |
| --- | --- |
| `analytical_models.py` | Liedl, Chu, Ham, Liedl 3D, and Cirpka equations plus multiple-run helpers. |
| `empirical_models.py` | Maier and Grathwohl and Birla plume-length equations. |
| `bioscreen_model.py` | BIOSCREEN-style numerical concentration integration using Gauss-Legendre quadrature; returns plume length and optional concentration curve. |
| `numerical_models.py` | FloPy MODFLOW 6 flow/transport execution, executable discovery, temporary workspace handling, reference-aligned source setup, orientation-specific plume-length extraction, and PNG generation. |
| `numerical_input_validation.py` | Shared vertical numerical site-input validation, configurable plausibility ranges, database `K` to `hk` conversion, and valid-site filtering. |
| `model_site_validation.py` | Per-model site admissibility derived from each model's own mathematical restrictions; filters site drop-downs without deleting rows. |
| `symbol_registry.py` | Central canonical symbols, database columns, UI labels, units, and model-specific applicability. |
| `aem/at_config.py`, `aem/at_element.py` | AEM configuration and circle/line/ellipse element definitions. |
| `aem/at_simulation.py` | AEM solve: coupling groups, least-squares Mathieu coefficients, parallel grid evaluation, `L_max` extraction, and solution validation. |
| `aem/at_inverse_model.py`, `aem/at_inverse_config.py` | Inverse parameter estimation and its per-parameter search bounds. |
| `aem/at_grid_export.py` | Long-form CSV and native NPZ grid export under one column contract, written atomically. |
| `aem/mathieu_functions_OG.py` | Modified Mathieu functions of complex parameter (Kuhlman, MIT licence). |
| `aem_jobs.py` | Builds an `ATConfiguration` from posted parameters and returns pickle-able forward and inverse results to the job queue. |
| `aem_source_geometry.py` | Framework-free Shapely packing algorithms behind the source designer. |
| `numerical_jobs.py` | Generic job queue: SQLite state, subprocess workers, concurrency cap, cancellation, and stale-job reaping. |
| `data_analysis/` | Workbench maths: CSV intake, curve fits, KDE, statistics, grids, axis scales, LaTeX notation, number formatting, MODFLOW binary ingestion, and Bokeh builders. |

### Flask Model Route Files

| File | Responsibility |
| --- | --- |
| `analytical_routes.py` | Analytical landing page, site selection, alias expansion, external input fields, Panel iframe URLs, analytical single-run PDFs, and specialised Cirpka preparation. |
| `empirical_routes.py` | Empirical landing page, site selection, basic autofill, Panel iframe URLs, and empirical single-run PDFs. |
| `numerical_routes.py` | Numerical landing page, compatibility redirects, orientation-specific field specifications, vertical site validation/filtering, site autofill, Panel iframe URLs, job submission and polling, artifact downloads, and simulation-backed horizontal/vertical PDF routes. |
| `aem_routes.py` | AEM landing, designer, forward, and inverse pages; polygon packing and design-save APIs; forward and inverse job submission; job status, cancellation, and JSON/CSV/NPZ result endpoints with ownership checks. |

### Utility Scripts

| File | Responsibility |
| --- | --- |
| `scripts/audit_vertical_sites.py` | Scans the site database with the same vertical validation function used by dropdown filtering and reports excluded site ids, names, fields, values, and reasons. |

### Panel Server and Shared Helpers

| File | Responsibility |
| --- | --- |
| `panel_server.py` | Registers all Panel URL paths and starts `pn.serve()`. |
| `panel_analytical_common.py` | Query-parameter aliases, Panel request readers, result cards, error cards, database comparison points, and shared Bokeh comparison chart. Reused beyond strictly analytical dashboards. |
| `panel_empirical_common.py` | Similar shared helpers for empirical dashboards. |
| `panel_numerical_comparison.py` | Small Bokeh helpers for analytical-versus-numerical single and multiple comparisons. |
| `panel_numerical_optional_views.py` | Lazy profile and decreasing-concentration vector controls that post-process retained numerical results only after a click. |
| `panel_site_comparison.py` | One shared multiple-simulation panel for all eight analytical and empirical models: site selection, per-site runs, and modelled-versus-measured comparison. |
| `panel_data_analysis.py` | Data-analysis workbench: source selection, the four tabs, and the CSV/NPZ export buttons. |
| `panel_theme.py` | Central Panel theme applied once at startup, mirroring the design tokens in `static/styles.css`. |
| `panel_auth.py` | Resolves the caller's identity from the trusted reverse-proxy header, never from a client-supplied query parameter. |

### Analytical and Empirical Panel Apps

| File | Responsibility |
| --- | --- |
| `panel_liedl_single.py` | Liedl single dashboard and PDF download. |
| `panel_liedl_multiple.py` | Editable Liedl scenario table, summary plot, and PDF download. |
| `panel_liedl3d_single.py` | Liedl 3D single dashboard and PDF download. |
| `panel_liedl3d_multiple.py` | Editable Liedl 3D scenario table and PDF download. |
| `panel_chu.py` | Chu single and multiple dashboards. |
| `panel_ham_single.py` | Ham single dashboard and PDF download. |
| `panel_ham_multiple.py` | Editable Ham scenario table and PDF download. |
| `bioscreen_panel.py` | BIOSCREEN single dashboard and multiple-time sweep dashboard. |
| `panel_cirpka_single.py` | Lightweight query-driven Cirpka result and comparison dashboard. |
| `panel_cirpka_multiple.py` | Editable Cirpka scenario table, summary, comparison plot, and PDF download. |
| `panel_maier_single.py` | Maier and Grathwohl single dashboard and PDF download. |
| `panel_maier_multiple.py` | Editable Maier and Grathwohl scenario table and PDF download. |
| `panel_birla_single.py` | Birla single dashboard and PDF download. |
| `panel_birla_multiple.py` | Editable Birla scenario table and PDF download. |

### Numerical Panel Apps

| File | Responsibility |
| --- | --- |
| `panel_numerical_horizontal_single.py` | Horizontal single dashboard with explicit grid/domain inputs, FloPy execution, interactive plume chart, and PDF export. |
| `panel_numerical_horizontal_multiple.py` | Horizontal scenario table and multiple-run dashboard using explicit grid/domain inputs. |
| `panel_numerical_vertical_single.py` | Vertical single dashboard with explicit grid/domain inputs, FloPy execution, interactive plume chart, and PDF export. |
| `panel_numerical_vertical_multiple.py` | Vertical scenario table and multiple-run dashboard using explicit grid/domain inputs. |
| `archive/legacy_numerical/` | Retired combined numerical dashboards retained for reference only. |

### Plotting and Reporting

| File | Responsibility |
| --- | --- |
| `plot_functions.py` | Loads optional reference CSV data, cleans numeric arrays, renders Bokeh plume plots, renders model comparisons, and creates site-database bar, box, histogram, and Liedl plots. |
| `pdf_report.py` | Shared branded ReportLab PDF engine. |
| `archive/drafts/pdf_styles.json` | Retired PDF-style metadata draft. `pdf_report.py` owns the active report styles. |
| `static/report_assets/Logo_Universitaet_Tuebingen.svg` | University logo embedded in PDF headers. |
| `static/report_assets/dfg-logo-foerderung/dfg_logo_schriftzug_blau_foerderung_de.png` | DFG logo embedded in PDF headers. |

### Templates

| File | Responsibility |
| --- | --- |
| `templates/base.html` | Main shell: header navigation, sidebar, footer, contact placeholder, static CSS, and browser script. |
| `templates/index.html` | Landing page, toolbox tiles, animated hero, external toolbox copy, and documentation section. |
| `templates/login.html` | Standalone login form. |
| `templates/register.html` | Standalone registration form plus an inline submit handler. |
| `templates/site_database.html` | CSV upload, manual insert, filter controls, sort controls, and site table. |
| `templates/analytical_landing.html` | Analytical model tile page. |
| `templates/empirical_landing.html` | Empirical model tile page. |
| `templates/numerical_landing.html` | Horizontal and vertical numerical tile page. |
| `templates/model_page_base.html` | Shared model-wrapper layout used by current numerical single templates. |
| `templates/model_input_form.html` | Shared split database/manual input form. |
| `templates/liedl_single.html` | Liedl single wrapper. |
| `templates/ham_single.html` | Ham single wrapper. |
| `templates/panel_liedl_multiple.html` | Liedl multiple wrapper. |
| `templates/panel_liedl3d_single.html` | Liedl 3D single wrapper. |
| `templates/panel_liedl3d_multiple.html` | Liedl 3D multiple wrapper. |
| `templates/panel_chu_single.html` | Chu single wrapper. |
| `templates/panel_chu_multiple.html` | Chu multiple wrapper. |
| `templates/panel_ham_multiple.html` | Ham multiple wrapper. |
| `templates/panel_bioscreen_single.html` | BIOSCREEN single wrapper. |
| `templates/panel_bioscreen_multiple.html` | BIOSCREEN multiple wrapper. |
| `templates/panel_cirpka_single.html` | Cirpka single wrapper. |
| `templates/panel_cirpka_multiple.html` | Cirpka multiple wrapper. |
| `templates/panel_maier_single.html` | Maier single wrapper. |
| `templates/panel_maier_multiple.html` | Maier multiple wrapper. |
| `templates/panel_birla_single.html` | Birla single wrapper. |
| `templates/panel_birla_multiple.html` | Birla multiple wrapper. |
| `templates/panel_numerical_horizontal_single.html` | Horizontal numerical single wrapper extending `model_page_base.html`. |
| `templates/panel_numerical_horizontal_multiple.html` | Horizontal numerical multiple wrapper. |
| `templates/panel_numerical_vertical_single.html` | Vertical numerical single wrapper extending `model_page_base.html`. |
| `templates/panel_numerical_vertical_multiple.html` | Vertical numerical multiple wrapper. |
| `templates/plot_bar.html` | Bokeh bar-chart page. |
| `templates/plot_box.html` | Box-plot page; currently contains duplicated legacy and Jinja markup. |
| `templates/plot_hist.html` | Histogram page; currently contains duplicated legacy and Jinja markup. |
| `archive/drafts/liedl_description.html` | Retired Liedl description draft. Active Liedl pages use the current wrappers. |

### Static Frontend Files

| File or directory | Responsibility |
| --- | --- |
| `static/styles.css` | Global CAST layout, navigation, cards, forms, model pages, responsive rules, and visual styling. |
| `static/script.js` | Sidebar and dropdown behaviour, account-form requests, active-navigation highlights, CSV filename display, iframe sizing, title animation, and landing-page canvas animation. |
| `static/images/conceptual_liedl_2d.png` | Liedl 2D conceptual diagram. |
| `static/images/conceptual_liedl_3d.png` | Liedl 3D conceptual diagram. |
| `static/images/conceptual_chu.png` | Chu conceptual diagram. |
| `static/images/conceptual_ham.png` | Ham conceptual diagram. |
| `static/images/conceptual_bioscreen.png` | BIOSCREEN conceptual diagram. |
| `static/images/conceptual_cirpka.png` | Cirpka conceptual diagram. |
| `static/images/conceptual_numerical.png` | Earlier generic numerical conceptual diagram. |
| `static/images/conceptual_numerical_horizontal.png` | Current horizontal numerical diagram. |
| `static/images/conceptual_numerical_vertical.png` | Current vertical numerical diagram. |

### Database, Deployment, and Metadata Files

| File | Responsibility |
| --- | --- |
| `db_setup.sql` | MySQL bootstrap schema mounted into the Compose database container. It mirrors the canonical `data_queries.py` table definitions. |
| `requirements.txt` | Python dependencies. |
| `Dockerfile` | Python 3.11 image, official MODFLOW 6 release installation, Python packages, and app copy. |
| `docker-compose.yml` | Nginx, Flask, Panel, MySQL services, health checks, and MySQL volume. |
| `nginx/default.conf` | Flask `/static/`, Panel-owned `/static/extensions/panel/`, authenticated `/panel/`, websocket, and Flask reverse-proxy rules. |
| `solvers/.gitkeep` | Keeps the optional solver directory in Git. |
| `.env.example` | Example environment settings. |
| `.env.docker` | Docker application environment template. |
| `.gitignore` | Excludes local secrets, logs, virtualenvs, solver binaries, and run artifacts. |
| `.dockerignore` | Docker context exclusions. |

### Documentation, Reference, and Local Artifact Files

| File | Status and purpose |
| --- | --- |
| `CAST_Brief.md` | User-focused capability briefing, written for the manuscript author. |
| `CAST_Toolkit_Technical_Brief.md` | Technical reference: governing equations as implemented, architecture, verification, and a file map. |
| `archive/reference_artifacts/` | Standalone Cirpka reference script, expert-provided CSV inputs, and numerical screenshots. Not loaded by the application. |
| `archive/generated_artifacts/test_svg.pdf` | Generated PDF test artifact retained outside runtime paths. |
| `archive/placeholders/` | Empty `Horizontal_sim_final.py` and one-byte `feedback` placeholders retained instead of deleted. |
| `archive/drafts/` | Retired PDF-style metadata and Liedl description drafts. |
| `archive/legacy_numerical/` | Retired combined numerical Panel dashboards and wrappers. |
| `flask*.log`, `panel*.log` | Local server logs. Ignored by Git. |
| `.modflow_bin/` | Ignored local solver binaries including `mf6.exe`. |
| `.numerical_runs/` | Ignored FloPy workspaces. Normally temporary; interrupted runs can leave directories behind. |
| `.numerical_jobs/` | Ignored job-queue SQLite database, pickled results, worker logs, and saved AEM designs. |
| `.aem_exports/` | Ignored per-user AEM concentration grids, one file per user, replaced on each run. |
| `__pycache__/` | Ignored Python bytecode cache. |
| `tmp*` | Ignored local temporary artifacts. |

## Known Limitations

### Not Implemented

The model-selection toolbox described in the CAST documentation (Statistical Threshold, AIC, and AHP ranking) is a design, not code. The AEM inverse model estimates one parameter at a time from a single target plume length; it is not a joint multi-parameter inversion and reports no uncertainty bounds.

### Site Database Operations

The current UI supports listing, searching, page-size selection, manual and CSV insertion, row deletion, clearing the user database, duplicate-row prevention, and Copy/CSV/XLSX/PDF/Print exports. It does not provide in-place row editing.

Numeric parsing intentionally converts invalid numeric text to `NULL` rather than rejecting the row. This is convenient for sparse data but can hide malformed values.

### Hydraulic Conductivity Conversion and Bounds

The implementation assumes that database hydraulic conductivity `K` is stored in `m/s` and numerical models consume `hk` in `m/d`. Numerical site autofill applies one explicit conversion in `numerical_input_validation.py` using `DB_K_M_PER_S_TO_NUMERICAL_HK_M_PER_D = 86400`. Converted values outside the configurable `NUMERICAL_HK_MIN_M_PER_DAY` and `NUMERICAL_HK_MAX_M_PER_DAY` range are rejected for vertical site-linked modelling.

The default plausibility bounds are configurable and should be reviewed as part of model calibration and deployment configuration. Run `python scripts/audit_vertical_sites.py` to list sites excluded from the vertical numerical dropdown, including the failed field, converted value, and validation reason.

### Runtime Schema Is Not a Migration System

`data_queries.py` is the single source of truth for the active database structure. Compose bootstrap SQL in `db_setup.sql` mirrors its tables, columns, keys, named foreign-key constraint, and `ON DELETE CASCADE` behaviour. The unused SQLAlchemy draft was removed so it cannot be mistaken for an active setup path.

The runtime `ensure_schema()` approach creates missing tables for development, but it does not alter existing tables or replace a migration system.

### Plot Visualisation v2 Scope

The Analysis Visualisation menu intentionally exposes only the working site-database pages: bar graph, box plot, and histogram. The unfinished all-plots, scatterplot, and statistical-analysis placeholders were removed for v2.

`static/original.csv` contains the bundled 112-site CAST reference database, with native search, sorting, page-size selection, and pagination. Copy, filtered CSV/XLSX/PDF downloads, and Print apply to the user-uploaded database; `static/sample_db.csv` is the downloadable upload example. `plot_functions.py` uses the reference file for reference-data plots. The `/dispersivity-data` page uses the legacy `static/fig1_plots.csv` dataset and its histogram, box plot, and scatter plot assets with the current responsive table controls.

### Numerical Work Is User-sized

Numerical and AEM runs go through the asynchronous queue described above, with cancellation, a concurrency cap, and stale-job reaping. Grid cost is still the user's responsibility: `NUMERICAL_MAX_CELLS` bounds the grid and `NUMERICAL_SOLVER_TIMEOUT_S` can bound the solver, but fine grids consume substantial CPU and memory. Job results are pickled to disk and are not pruned automatically, so `NUMERICAL_JOB_ROOT` grows until it is cleaned.

BIOSCREEN also uses a loop with a high safety cap of `100000` distance steps.

### Security Follow-up

Before production deployment:

- Replace query-string Panel email context with signed claims if ownership-sensitive Panel features expand.
- Review the login and registration rate limits against the deployment's expected traffic.
- Decide whether external Google Fonts are acceptable in the deployment environment.

### Encoding Cleanup Is Still Needed

Several templates and source strings contain mojibake from earlier text-encoding conversions. Examples include malformed punctuation, symbols, and icon text. The application should be normalised to UTF-8 consistently.

### Automated Pytest Safety Net

Install development dependencies and run the complete local safety net with:

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

The suite covers analytical and empirical equation regressions, canonical symbol mappings, CSV alias and SQL `NULL` normalization, authentication flows and security failure paths, authenticated wrapper rendering, PDF generation, schema consistency, numerical conductivity autofill, MODFLOW 6 executable discovery, smallest-grid MODFLOW 6 smoke simulations, and reference-output checks for the horizontal and vertical numerical fixtures.

## Change History

Keep this section updated whenever implementation, configuration, reporting, or documentation behaviour changes. Add new entries above older entries before committing.

### 12 August 2026 - README Brought Forward

- Documented the AEM toolbox, the data-analysis workbench, the asynchronous job queue, guest access, and the security model, none of which this handbook previously covered.
- Added the AEM, numerical job, site export/delete, contact, health, `/me`, and About routes to the route tables.
- Added the newer configuration variables: cookie and proxy trust settings, contact/SMTP delivery, upload and request caps, job-queue roots, concurrency, timeouts, and the AEM export directory.
- Removed stale entries: the deleted `plot_routes.py` and `CAST_Implementation_Specification.md`, the forced-`output_only` limitation, the missing-conceptual-image limitation, and the synchronous-numerical-work limitation.
- Added `CAST_Brief.md` (user-focused capability briefing) and `CAST_Toolkit_Technical_Brief.md` (technical reference) for the manuscript work.

### 6 August 2026 - Plot and Interaction Polish

- Recoloured the plume comparison plot and set the `Lmax` label with a subscript.
- Added parameter sliders to single-run dashboards for live sensitivity exploration.

### 4 August 2026 - Reference Database by Default

- Made the bundled 112-site reference database the default data source and accounts optional.
- Added per-session guest identity so anonymous visitors can run every model without their runs mixing.

### July 2026 - AEM Toolbox End to End

- Synced the AEM package with upstream and wired its grid export through to the data-analysis workbench.
- Added multi-element selection and an adjustable packing radius to the source designer.
- Added `.npz` grid support so a run round-trips into the workbench losslessly.
- Fixed the designer canvas resize loop and versioned the designer and inverse script tags for cache busting.

### June 2026 - Analysis Workbench and Model UI

- Expanded the analysis workbench: distribution fits, KDE, curve fits with confidence bands, gridded contour/profile/quiver views, and MODFLOW binary ingestion.
- Added source-geometry headbar links and rendered numerical multiple-scenario graphs.
- Made the numerical domain length a parameter rather than a literal, and reported one plume length per run.

### June 2026 - Asynchronous Numerical Jobs

- Moved MODFLOW runs off the request path into a SQLite-backed queue with subprocess workers.
- Added status polling, cancellation, stale-job reaping, a concurrency cap, and a per-comparison run cap.
- Added validation of vertical numerical site selection before a run is queued.

### 9 June 2026 - MODFLOW 6 Numerical Reference Alignment

- Added numerical reference scripts and inputs for horizontal and vertical regression tests.
- Reworked horizontal and vertical numerical runners to match the explicit MODFLOW 6 domain, grid, time stepping, flow, transport, CNC source, and plume-length methods used by the reference cases.
- Removed analytical `Lmax` domain sizing, `L_D_override`, and grid-spacing-derived numerical domains from the active numerical execution path.
- Updated numerical Flask and Panel inputs to surface the required numerical parameters directly: `Lx`, `Lz`/`Ly`, `ncol`, `nlay`/`nrow`, `source`, `prsity`, `al`, `at`, `atv`, `gamma`, `C_D`, `C_A`, `C0`, `h1`, `h2`, `hk`, and `perlen`.
- Added regression tests pinning app output to captured reference plume lengths: vertical `42.0` and horizontal `36.1`.

### 1 June 2026 - Deferred Numerical Runs and Shared Reports

- Stopped numerical single-run wrappers from launching MODFLOW during initial page load.
- Replaced the ambiguous `Update Output` action with one final `Run Model` button and removed duplicate wrapper run forms from numerical scenario pages.
- Fixed vertical single-run `alpha_Tv` forwarding and derived balanced source-buffer defaults for database-loaded aquifer thicknesses.
- Standardised single-model report cards through `templates/report_download_card.html`; all model PDFs continue to use the shared branded `CASTReport` engine.

### 1 June 2026 - Non-Runtime Artifact Archive

- Archived unused scratch references, generated PDF output, and placeholders instead of deleting them.
- Retired the unwired PDF-style metadata and stale Liedl description drafts under `archive/drafts/`.
- Kept the orientation-specific numerical dashboards active and moved the older combined dashboards under `archive/legacy_numerical/`.
- Added `archive/README.md` so retained files remain clearly separated from active application code.

### 1 June 2026 - Lazy Numerical Optional Views

- Added profile and decreasing-concentration vector buttons to numerical dashboards.
- Kept both post-processing views lazy: they are derived from the retained solver result only after a user click.
- Documented 3D numerical visualisation as outside the default numerical execution path.

### 1 June 2026 - Analytical Domain Sizing Overrides

- Centralised the `LD = 1.5 * Lmax` numerical-domain rule for Cirpka-driven horizontal and Liedl-driven vertical simulations.
- Kept automatic sizing as the default path and added optional advanced domain-length overrides for power users.
- Added regression coverage confirming automatic sizing matches the previous explicit extent within tolerance.

### 1 June 2026 - Pytest Safety Net

- Added pytest configuration and a development dependency file.
- Added equation, symbol-registry, CSV import, stateful authentication, wrapper-rendering, PDF, solver-discovery, and real smallest-grid MODFLOW 6 smoke coverage.
- Kept the existing unittest-style regression modules collected by pytest.

### 31 May 2026 - Database Schema Source of Truth

- Kept `data_queries.py` `ensure_schema()` as the canonical schema definition.
- Aligned `db_setup.sql` with the runtime tables, columns, keys, named foreign-key constraint, and cascading site deletion.
- Removed the unused SQLAlchemy draft setup file so there is one active database setup path.
- Added a regression test that compares bootstrap SQL directly with the canonical runtime statements.

### 31 May 2026 - Visualisation Menu v2 Cleanup

- Removed dead Analysis Visualisation dropdown entries and the placeholder `/plots/*` blueprint.
- Kept the working `/plot_bar`, `/plot_box`, and `/plot_hist` site-database pages.
- Loaded matching Bokeh browser resources from the base template.
- Deduplicated the box-plot and histogram templates and standardised their component variable names.
- Added regression coverage for menu links, rendered empty-state Bokeh pages, missing `static/original.csv`, and removed placeholder routes.

### 31 May 2026 - Editable Multiple-run Embeds

- Removed forced `output_only=1` from analytical, empirical, and numerical multiple-run wrapper iframes.
- Kept compact `output_only=1` embeds for single-run wrapper outputs.
- Prevented wrapper query strings from restoring output-only mode on multiple-run pages.
- Added route-level regression coverage for rendered iframe URLs.

### 31 May 2026 - Numerical Conductivity Autofill Boundary

- Assumed database conductivity `K` is stored in `m/s` and numerical `hk` is consumed in `m/d`.
- Added one explicit `m/s` to `m/d` conversion with a named `86400` factor at the numerical autofill boundary.
- Added configurable post-conversion plausibility bounds.
- Added units to editable conductivity fields across site entry, numerical wrappers, and Panel scenario tables.
- Added regression tests for the exact conversion and the bounds guard.

### 31 May 2026 - Web Security Hardening

- Required `SECRET_KEY`, `DB_USER`, and `DB_PASSWORD` from the environment with no application defaults.
- Removed checked-in Compose credential values and documented placeholder-only environment setup.
- Added session-backed CSRF protection to login, registration, and site mutation forms.
- Added login and registration rate limits.
- Validated JSON and form request bodies before field access.
- Replaced raw database exception responses with generic user messages while retaining server-side logs.
- Added regression tests for malformed JSON, forged POST rejection, database-error redaction, and throttling.

### 31 May 2026 - Registration Submit Cleanup

- Consolidated account registration into one shared submit handler in `static/script.js`.
- Standardised the registration request body on `username`, `email`, `password`, and `confirmPassword`.
- Disabled the submit button while a request is in flight and restored it when registration fails.

### 31 May 2026 - Flask-Login Authentication Alignment

- Standardised account access on Flask-Login and removed raw auth-session keys.
- Protected site, model wrapper, plot, and PDF export routes with `@login_required`.
- Added an Nginx `auth_request` check so direct `/panel/` requests require the same Flask-Login session.
- Removed silent `demo@example.com` fallbacks and made `current_user.email` authoritative for site ownership filtering.
- Added authentication regression tests for protected access, login, logout, ownership filtering, and Panel iframe email propagation.

### 31 May 2026 - Same-origin Panel Proxy Alignment

- Added `PANEL_PUBLIC_BASE` as the single browser-facing Panel URL setting.
- Derived Panel's served prefix from that public base so local development stays on `localhost:5007` while Compose serves Panel below `/panel`.
- Preserved `/panel` through Nginx and aligned websocket proxy headers, allowed origins, and the Panel container health check.

### 31 May 2026 - MODFLOW 6 Canonical Solver Alignment

- Confirmed MODFLOW 6 GWF/GWT as the canonical numerical engine.
- Replaced the legacy Docker solver build with the official MODFLOW 6 `6.7.0` Linux release.
- Standardised Docker, environment templates, settings, UI text, PDF labels, and documentation on `MF6_EXE`.

### 1 June 2026 - Numerical Solver Diagnostics and Runtime Bounds

- Added timestamped logs for MF6 executable resolution, derived grids, input writes, external flow and transport runs, UCN reads, plume extraction, and contour builds.
- Captured MF6 stdout and stderr in the application log and reported the resolved absolute solver path at the start of each numerical run.
- Added a process-level timeout that terminates stalled MF6 runs and returns a readable error.
- Added the `NUMERICAL_MAX_CELLS` pre-run cap and `NUMERICAL_SOLVER_TIMEOUT_S` timeout setting.
- Logged full Panel callback tracebacks while retaining readable result-pane errors and restoring disabled run buttons in `finally`.

### 31 May 2026 - README Consolidation

- Consolidated the project notes and running implementation record into this single `README.md`.
- Documented the architecture, model catalogue, routes, file responsibilities, local setup, Docker caveats, and known limitations.
- Added this change-history section so future updates can be tracked without maintaining a separate documentation file.

### 31 May 2026 - Reporting PDF Updates

- Replaced reconstructed report-header marks with the full official DFG funding logo and the official University of Tuebingen SVG artwork.
- Kept HYMCAT as text because no HYMCAT logo asset is included in the repository.
- Added project, institution, and funding metadata to generated reports.
- Included Matplotlib result charts in analytical and empirical report exports.
- Updated numerical report exports to run the requested simulation and include plume-concentration images plus analytical-versus-numerical comparison charts.

### 31 May 2026 - Model Input and Output UI Updates

- Split model inputs into `Database Inputs` and `Manual Model Inputs` columns across single-run and multiple-run Flask wrapper pages.
- Reused the shared input-form template for the specialised Cirpka single-run page.
- Updated number inputs to accept valid decimal values without browser step-validation conflicts.
- Updated embedded Panel URLs to include model parameters, `run=1`, and `output_only=1`.
- Changed iframe loading to eager mode and aligned iframe hostnames with the Flask request host.

### 31 May 2026 - Reviewed Numerical Model Integration

- Connected the reviewed horizontal and vertical numerical scripts through FloPy MODFLOW 6 wrappers.
- Added orientation-specific Flask routes, templates, Panel apps, and landing-page links.
- Added explicit horizontal and vertical hydraulic-conductivity handling for the vertical model.
- Added simulation-backed plume-length extraction, static PNG generation, and interactive Bokeh plume visualisations.
- Kept local solver binaries and temporary FloPy workspaces outside version control.

## Development Notes

### Source of Truth

Use these files as the primary implementation references:

- `data_queries.py` for active database behaviour.
- `analytical_models.py`, `empirical_models.py`, `bioscreen_model.py`, `numerical_models.py`, and `aem/at_simulation.py` for calculations.
- `analytical_routes.py`, `empirical_routes.py`, `numerical_routes.py`, `aem_routes.py`, and `site_routes.py` for public Flask behaviour.
- `panel_server.py` for mounted Panel apps.
- `symbol_registry.py` and `param_meta.py` for canonical database mappings and input notation.
- `model_site_validation.py` for which sites each model will accept.
- `numerical_jobs.py` for background execution semantics.
- `security.py` and `panel_auth.py` for identity and request-hardening behaviour.
- `pdf_report.py` for generated report layout.

### Adding a New Model

A new model usually needs:

1. A calculation function in a model module.
2. A single and/or multiple Panel app.
3. Registration in `panel_server.py`.
4. A Flask wrapper route and optional export route.
5. A wrapper template under `templates/`.
6. A conceptual image under `static/images/`.
7. Navigation links in `templates/base.html` and the relevant landing page.
8. Symbol aliases in `symbol_registry.py` when database autofill applies.
9. Tests for the equation, routing, and report export.

# PACS Handoff Guide

**Preliminary Assessment of Contaminated Sites — a guide for the research team taking the project over.**

Written 22 September 2026, against branch `final` (commit `06230c0` and later). Companion to
`README.md`, not a replacement for it:

| Document | What it is | Reach for it when |
| --- | --- | --- |
| `README.md` | The reference handbook: every route, every config variable, setup procedures, model catalogue, known limitations. | You need the exact name of a variable, a route, or a setup step. |
| `HANDOFF_GUIDE.md` (this file) | The map. Every file in the repository with its purpose, a "where do I change X" cookbook, the traps that cost real time, and a plan for experimenting safely. | You are new here, or you know *what* you want to change but not *where*. |

Nothing in this guide is aspirational. Every statement was checked against the code as it
stands, and where something is broken or half-finished it says so.

---

## 1. Read this page first

Five facts that explain most of the confusion newcomers have with this codebase.

1. **Every model page is two applications stitched together.** The page frame (header, input
   form, text, download card) is a Flask + Jinja template. The part that computes and draws is a
   **Panel** app running in a *separate process*, embedded in an `<iframe>`. If you change a
   label and nothing happens, you edited the wrong one of the two. Section 4 tells you which.

2. **The containers do not see your edits.** `docker-compose.yml` builds the code *into* the
   image (`build: .`) and bind-mounts only `nginx/default.conf` and `static/`. After editing any
   `.py` or `templates/*.html` you must `docker compose build flask panel && docker compose up -d
   flask panel`. Editing CSS/JS under `static/` only needs a browser refresh.

3. **Long simulations do not run in the web request.** Numerical and AEM runs are submitted to a
   SQLite-backed job queue (`numerical_jobs.py`), executed by a separate worker process
   (`numerical_job_worker.py`), and polled by the page. A traceback from a failed run is in the
   worker log, not in the browser.

4. **Parameter names are governed centrally.** `symbol_registry.py` is the single source of truth
   mapping database column ↔ canonical symbol ↔ UI label ↔ model function argument, and
   `param_meta.py` holds the notation symbol and help text per input. Renaming a parameter in
   one place only will break autofill, CSV import, or the PDF silently. Tests
   (`test_symbol_registry.py`, `test_var_sym_conventions.py`) exist to catch exactly that.

5. **The test suite is the safety net and it is large.** 244 tracked files, 49 test files, 486 test functions (about 750 cases once parametrised). Most run
   in about a minute; three files take ~4 minutes because they launch Panel apps and MODFLOW.
   Run them before and after every change — Section 7 shows the fast subsets.

---

## 2. The mental model

```
   Browser
      |
      | :80
      v
   nginx  (nginx/default.conf)
      |-- /static/                -> Flask static files
      |-- /static/extensions/panel/ -> Panel's own bundled assets  (order matters!)
      |-- /panel/...              -> auth_request /auth/check, then Panel :5007 (+ websocket)
      `-- everything else         -> Flask :5000
                                        |
   Flask (gunicorn, app.py)              |
      |-- renders the page shell from templates/
      |-- reads/writes MySQL through data_queries.py
      |-- submits jobs to the queue (numerical_jobs.py)
      `-- builds PDFs with pdf_report.py (PACSReport)
                                        |
   Panel server (panel_server.py, :5007)  |
      |-- one app per model page (panel_*.py)
      |-- identity comes from the proxy header only (panel_auth.py)
      |-- draws Bokeh figures from plot_functions.py
      `-- polls the job queue and renders the result
                                        |
   Worker process (numerical_job_worker.py)
      `-- numerical_models.py -> FloPy -> MODFLOW 6 (`mf6` binary)
          aem_jobs.py        -> aem/   -> analytic-element solve
```

**The report bridge.** A Panel app cannot hand a file to the outer page directly. Instead
`panel_theme.report_bridge_html()` posts a `pacs-report` message to the parent window; the
listener in `static/script.js` enables the *Download PDF Report* button, which POSTs the run's
parameters to `/report/export`. Three `postMessage` channels work this way and **both sides must
use the same type string**:

| Message type | Sent by | Received by |
| --- | --- | --- |
| `pacs-report` | `panel_theme.py` | `static/script.js` |
| `pacs-frame-height` | `panel_theme.py` | `static/script.js` |
| `pacs-input` | `panel_analytical_common.py` (explore sliders) | `static/script.js` |
| `pacs-scenario-open` / `pacs-scenario-row` | `panel_model_scenarios.py` ↔ `static/script.js` | both directions |

---

## 3. Getting it running

### Docker (what production uses, and the closest thing to it locally)

```bash
cd cast_landing_demo
cp .env.example .env            # then set SECRET_KEY, DB_USER, DB_PASSWORD
docker compose up -d --build    # nginx :80, flask, panel, MySQL
docker compose ps               # all four should report (healthy)
```
Open <http://localhost/>. Logs: `docker compose logs -f panel` (or `flask`).

### Without Docker (faster edit-reload loop, needs MySQL and `mf6` yourself)

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements-dev.txt
python panel_server.py                               # terminal 1, :5007
python app.py                                        # terminal 2, :5000
```
Set `DEMO_BYPASS_LOGIN=1` in `.env` to skip the login wall while developing, and `MF6_EXE` to
your MODFLOW 6 executable if you want the numerical models to run.

### Driving a Panel page directly (the best debugging trick in this repo)

Every Panel app reads its inputs from query parameters, so you can bypass the whole Flask shell:

```
http://localhost/panel/panel_numerical_vertical_single?Lz=10&grid_size=1&al=1&atv=0.1&gamma=3.5&C_D=5&C_A=8&prsity=0.3&hk=8.64&gradient=0.0125&output_only=1&run=1
```

`output_only=1` strips the input widgets (that is the mode the iframe uses) and `run=1` starts
the simulation immediately. Change a number in the URL, reload, and you have reproduced a user's
exact run with no clicking.

---

## 4. Cookbook: text and wording changes

The most common handover question is *"where does this sentence live?"* Grep is your friend
(`grep -rn "the exact sentence" templates/ static/ *.py`), but here is the map.

| What you see on screen | File to edit | Notes |
| --- | --- | --- |
| Site name in the header badge and its tagline | `templates/base.html` (`brand-badge`, `brand-sub`) | Also the mobile brand link further down the same file. |
| Browser tab titles | `{% block title %}` in each template; the default sits in `base.html` | Login and register have their own `<title>` because they do not extend `base.html`. |
| Top navigation, sidebar, footer, contact copy | `templates/base.html` | One file drives every page's chrome. |
| Landing page hero, tiles, documentation copy | `templates/index.html` | The animated headline is assembled in `static/script.js`. |
| Model page heading, kicker, the "Set the input parameters..." hint | Blocks `model_title`, `model_kicker`, `model_hint` in `templates/model_workbench_single.html` (or the `_multiple` variant), overridden per model in the small `templates/panel_<model>_<mode>.html` wrappers | Those wrappers are 8-11 lines each and contain nothing but block overrides. |
| Long "About this model" pages | `templates/about_<model>.html` (10 files) | All extend `model_about_base.html`; equations, assumptions, references and figure captions live here. |
| Input field **labels** on the Flask form | The field-spec tuples in `analytical_routes.py`, `empirical_routes.py`, `numerical_routes.py` (e.g. `NUMERICAL_INPUT_SPECS`) | Tuple shape is `(name, label, default, step, min)`. |
| Input field **symbols and help tooltips** | `param_meta.py` | `_SYMBOLS` holds HTML notation such as `&alpha;<sub>L</sub>`; the descriptions hold help text. Several descriptions are still placeholders - filling them in is a good first contribution. |
| Widget labels **inside** the plot frame | The `name=` argument of the Panel widget in the relevant `panel_*.py` | The same parameter often appears twice: once on the Flask form, once in the Panel app. |
| Result-card row labels such as "Maximum Plume Length" | The `_rows` list and `state["outputs"]` in the relevant `panel_*_single.py` | The same strings feed the PDF, so changing them changes the report too. |
| Error and status messages for numerical runs | `numerical_input_validation.py`, top of file | Every reader-facing message is a constant in one block by design; the rule is "the message is the instruction, nothing else". |
| PDF cover, footer, disclaimer, project mark | `pdf_report.py` (`_draw_project_mark`, class `PACSReport`) | Logos come from `static/report_assets/`. |
| Download-card wording | `templates/report_download_card.html`, `templates/report_bridge_card.html`, **and** the two matching strings in `static/script.js` | The JS rewrites that hint at runtime, so change both or the old wording reappears. |
| Imprint, privacy and other legal text | `templates/imprint.html`, `templates/privacy.html` | Institutional text - clear it with the PI before editing. |
| Axis labels, legends, the metadata line under a plot | `plot_functions.py`, plus the `footer_meta` string built in each `panel_*_single.py` | |
| Site-database column headings | `symbol_registry.py` (canonical labels) and `templates/site_database.html` | Do not edit a heading in the template alone: CSV import matches against the registry. |

> **Tip - the two-place rule.** Anything a user can see usually has a Flask-side definition
> (label, step, minimum) *and* a Panel-side widget. After a text change, check the page in the
> browser **and** the generated PDF, because the PDF takes its labels from the Panel side.

---

## 5. Cookbook: computational and scientific changes

| Change you want | Where | Watch out for |
| --- | --- | --- |
| A closed-form equation (Liedl 2005, Liedl 3D, Chu, Ham, Cirpka) | `analytical_models.py` | Pure functions with no web imports - test them from a REPL or via `tests/test_model_equations.py`. |
| An empirical / hybrid equation (Maier & Grathwohl, Birla) | `empirical_models.py` | 27 lines in total; both are one-liners. |
| The Koehler (2024) surrogate polynomials | `kohler_model.py` | Coefficients are documented against the published tables and `tests/test_kohler_model.py` pins them to Table 4 of the paper. If you change a coefficient, that test *should* fail. |
| BIOSCREEN-style concentration integration | `bioscreen_model.py` | Gauss-Legendre quadrature; returns plume length plus an optional concentration curve. |
| The MODFLOW 6 setup: grid, boundaries, source cells, time stepping, packages | `numerical_models.py` | The two runners mirror the reference scripts in `tests/fixtures/orlando_reference/`, and the regression tests compare against numbers captured from them. See the re-pinning tip below. |
| How plume length is extracted from a concentration field | `numerical_models.py` (`_plume_length`, `_horizontal_plume_length_from_source_extent`) | This one number drives every plot, card and PDF. |
| Grid defaults, steps, or the minimum spacing | `numerical_routes.py` (`NUMERICAL_INPUT_SPECS`, minimum currently `0.1` m) and the `FloatInput(start=..., step=...)` calls in `panel_numerical_*_single.py` | Change both, or the form and the widget disagree. |
| Validation rules and plausibility bounds for site data | `numerical_input_validation.py`, `model_site_validation.py`, and the `NUMERICAL_HK_*` environment variables | `python scripts/audit_vertical_sites.py` prints exactly which sites a rule change would exclude from the dropdown. |
| The hydraulic-conductivity unit conversion | `numerical_input_validation.py` (`DB_K_M_PER_S_TO_NUMERICAL_HK_M_PER_D = 86400`) | The database stores K in m/s; the numerical models want m/d. This is the only conversion point in the codebase. |
| The AEM solve: elements, coupling groups, Mathieu coefficients, grid evaluation | `aem/at_simulation.py` (2119 lines - the big one) | Vendored from an upstream tree. Keep edits surgical and commented so the vendor diff stays readable. |
| AEM inverse search behaviour or bounds | `aem/at_inverse_model.py`, `aem/at_inverse_config.py` | One parameter at a time by design, with no uncertainty bounds (see README, Known Limitations). |
| A new statistic, fit or distribution in the Data Workbench | `data_analysis/` (`stats.py`, `fits.py`, `kde.py`, `scales.py`), then surface it in `panel_data_analysis.py` | The `data_analysis` package deliberately contains **no Panel imports** so it stays unit-testable. Please keep it that way. |
| A new plot | `plot_functions.py` for site and model plots, `data_analysis/plots.py` for the workbench | Both return Bokeh figures; reuse the existing styling helpers. |
| A whole new model | See the checklist below | |

### Adding a new model, end to end

The eight closed-form models are assembled from the same parts, so copy the nearest neighbour:

1. **Equation** - add the function to `analytical_models.py` or `empirical_models.py`.
2. **Symbols** - register its parameters in `symbol_registry.py`, add notation and help text to `param_meta.py`.
3. **Single page** - copy `panel_liedl_single.py` (95 lines) and adapt the widgets and result card.
4. **Multiple page** - most models need only a thin wrapper: `panel_birla_multiple.py` is 7 lines and delegates to the shared engines `panel_site_comparison.py` and `panel_model_scenarios.py`.
5. **Register the Panel routes** - `panel_server.py`.
6. **Flask routes** - landing tile, single, multiple and `/export` routes in `analytical_routes.py` or `empirical_routes.py`.
7. **Templates** - an 8-line `panel_<model>_single.html` and `_multiple.html` wrapper, plus an `about_<model>.html`.
8. **Conceptual figure** - a PNG in `static/images/`, pointed at by the `conceptual_image` block.
9. **Tests** - the shared suites (`test_multiple_site_comparison.py`, `test_model_scenarios.py`, `test_route_smoke.py`) iterate over model lists, so adding yours there exercises it for free.

> **Tip - re-pinning the numerical regressions.** If you deliberately change the MODFLOW setup,
> the reference assertions in `tests/test_numerical_models.py` will fail. That is the safety net
> working, not a bug. Re-capture the new truth with
> `docker compose exec flask python scripts/repin_numerical.py`, sanity-check that the printed
> plume lengths are physically sensible, and paste them into the test. Never "fix" such a failure
> by loosening a tolerance before you understand why the number moved.

---

## 6. Complete file reference

Every tracked file in the repository (244 of them), grouped by what it does. Line counts are
there to tell you at a glance whether a file is a one-liner or a month of reading.

### 6.1 Entry points and configuration

| File | Lines | Purpose |
| --- | --- | --- |
| `app.py` | 461 | The Flask application: creates the app, wires Flask-Login, registers every blueprint, and owns the home page, `/health`, the model *about* pages, the contact form (SMTP optional), login, register, `/auth/check` (used by nginx to authorise Panel), `/me` and logout. Also the HTTP error handlers. |
| `settings.py` | 108 | All configuration in one place, read from the environment with `.env` support. Parses booleans and CSV lists, validates that required values exist, and fails loudly at import time on a nonsensical combination. If you add an environment variable, add it here, to `.env.example` **and** to the README's configuration table. |
| `panel_server.py` | 104 | The Panel process: maps every URL path to its app function and calls `pn.serve()`. A new Panel page is not reachable until it is registered here. |
| `numerical_job_worker.py` | 47 | The subprocess entry point the job queue spawns. Loads a pickled payload, runs it, writes the result back. Deliberately tiny so a crash in a run cannot take the web server with it. |
| `pytest.ini` | 4 | Points pytest at `tests/` and defines the `integration` marker for tests needing the Docker stack. |
| `requirements.txt` | 17 | Runtime dependencies, all version-pinned or bounded. Note the exact pins `bokeh==3.4.3` and `panel==1.4.5` - see trap 7 in Section 9. |
| `requirements-dev.txt` | 2 | The runtime set plus pytest. |
| `.env.example` | 46 | Documented template for local configuration. Copy to `.env`. |
| `.env.docker` | 28 | The environment the Compose services load. Secrets are *not* here - `SECRET_KEY`, `DB_USER` and `DB_PASSWORD` must come from the shell or a `.env` file, and Compose refuses to start without them. |
| `Dockerfile` | 49 | Python 3.11-slim, downloads and installs the official MODFLOW 6 release, installs requirements, copies the app, and runs as an unprivileged `pacs` user. |
| `docker-compose.yml` | 108 | Four services - nginx (:80), flask (gunicorn, 4 workers), panel, MySQL - with health checks, capped JSON logging, and a named volume `numerical_jobs` so queued jobs, results and AEM exports survive a redeploy. |
| `nginx/default.conf` | 112 | The reverse proxy and the only place that knows the URL layout: Flask static, then Panel's own bundled assets (that order matters), then `/panel/` behind an `auth_request` to `/auth/check` with websocket upgrade, then Flask for everything else. |
| `db_setup.sql` | 38 | Bootstrap schema mounted into the Compose MySQL container. Mirrors the tables `data_queries.ensure_schema()` creates. Keep the two in step. |
| `simulation_config.json` | 16 | Default AEM domain and dispersivity settings used as a starting point for a forward run. |
| `solvers/.gitkeep` | 1 | Keeps the optional local solver directory in Git; drop an `mf6` binary here when running outside Docker. |
| `.gitignore` / `.dockerignore` | 57 / 14 | Exclusions for local artefacts (run scratch directories, job database, logs, solver binaries) and for the Docker build context. |
| `README.md` | 1249 | The reference handbook. |
| `HANDOFF_GUIDE.md` | - | This guide. |

### 6.2 Flask route modules (the page shells and the JSON APIs)

| File | Lines | Purpose |
| --- | --- | --- |
| `site_routes.py` | 925 | The site database: upload, manual insert, filtering and sorting, the reference database, exports to CSV/XLSX/PDF, row and bulk deletion, the legacy full-page plot routes, the dispersivity-data page, and `POST /report/export`, which is what the *Download PDF Report* button on every model page hits. |
| `analytical_routes.py` | 779 | Landing page and the single/multiple/export routes for Liedl, Liedl 3D, Chu, Ham, Cirpka and BIOSCREEN. Builds the Panel iframe URLs (`_panel_src`, `_build_panel_query`) and the input field specs, and carries a special-cased Cirpka preparation path. |
| `numerical_routes.py` | 784 | Landing page, horizontal and vertical single/multiple pages, the per-orientation field specs (`NUMERICAL_INPUT_SPECS`), site autofill with vertical validation, job submit/status/cancel endpoints, artefact downloads (`.hds`, `.ucn`), and the simulation-backed PDF routes. |
| `empirical_routes.py` | 370 | The same pattern for Maier & Grathwohl, Birla and Koehler. |
| `aem_routes.py` | 548 | Native (non-Panel) AEM pages: landing, source designer, forward and inverse runs; the polygon-packing and design-save JSON APIs; job submission, status, cancellation; and result endpoints as JSON/CSV/NPZ with ownership checks. |
| `route_guards.py` | 68 | Turns the exceptions the model functions raise on impossible inputs into HTTP 400 instead of a 500. Wrap any new route that evaluates a model straight from query parameters. |
| `security.py` | 210 | CSRF tokens, per-endpoint rate limiting, guest-session identity, email and password policy, JSON and form body guards, and the single generic database-error message shown to users. |

### 6.3 Science and domain logic

| File | Lines | Purpose |
| --- | --- | --- |
| `analytical_models.py` | 229 | The closed-form plume-length equations (Liedl, Chu, Ham, Liedl 3D, Cirpka) plus helpers for multi-run pages. |
| `empirical_models.py` | 27 | Maier & Grathwohl and Birla plume-length equations. |
| `kohler_model.py` | 173 | Koehler et al. (2024): two second-order polynomial surrogates for BIOSCREEN-AT, one for maximum plume length, one for the time to reach it. The docstring warns that `gamma` here is *not* the stoichiometric ratio used elsewhere - read it before touching. |
| `bioscreen_model.py` | 115 | BIOSCREEN-style concentration integration by Gauss-Legendre quadrature. |
| `numerical_models.py` | 912 | The MODFLOW 6 engine: executable discovery, temporary workspaces, source-cell layout for both orientations (`horizontal_source_rows`, `vertical_source_layers`, `balanced_source_buffers`), the solver invocation with timeout and log capture, plume-length extraction, and PNG generation for the PDF. |
| `numerical_input_validation.py` | 321 | Every reader-facing message for numerical runs (as constants), the `UserMessageError` type that marks a message as safe to display, unit conversion from database K, per-field validation, site filtering, and the source-segment parsers. |
| `model_site_validation.py` | 123 | Per-model admissibility rules derived from each equation's own mathematical restrictions (a model that divides by `C_EA0` needs it non-zero). Used to filter site dropdowns rather than to delete data. |
| `symbol_registry.py` | 472 | The alias registry: canonical symbol, database column, UI label, unit and per-model applicability, in one table. The stated rule is *conceptual symbol == UI label == variable name (or mapped alias)*. |
| `param_meta.py` | 289 | Per-input HTML notation symbol and help text, shared by all three route modules. |
| `data_queries.py` | 490 | The MySQL layer: `ensure_schema()`, connections, numeric cleaning, ownership-scoped site reads, single and bulk insert with duplicate detection, deletion, and the reference-site fallback. Note it is *not* a migration system - see README. |
| `numerical_jobs.py` | 340 | The generic async queue: SQLite state, submit/status/fetch/cancel, a concurrency cap, worker spawning, and reaping of stale jobs whose process died. Generic over a `kind` string, so AEM reuses it. |
| `aem_jobs.py` | 515 | The AEM-specific half of the queue: builds an `ATConfiguration` from posted parameters (optionally seeded from a bundled designer export) and returns pickle-able forward and inverse results. |
| `aem_source_geometry.py` | 176 | Framework-free Shapely geometry behind the source designer: packing a polygon with circle/line elements. |

### 6.4 The `aem/` package (analytic element method)

Vendored from an upstream research tree; the only edit applied to vendored files was making the
imports relative. Treat it as third-party code you happen to own.

| File | Lines | Purpose |
| --- | --- | --- |
| `aem/__init__.py` | 64 | Makes the flat upstream module directory a real package and documents the vendoring rule. |
| `aem/at_simulation.py` | 2119 | The solver: loads a configuration of source elements, forms coupling groups, solves for Mathieu coefficients by least squares, evaluates the concentration field in parallel, extracts `L_max`, and validates the solution. |
| `aem/at_config.py` | 173 | `ATConfiguration`: domain, dispersivities, element list, output settings. |
| `aem/at_element.py` | 178 | `ATElement` and the element-type enum (circle, line, ellipse). |
| `aem/at_inverse_model.py` | 666 | Inverse parameter estimation: scans one parameter against a target plume length, with logging and statistics output. |
| `aem/at_inverse_config.py` | 180 | Per-parameter search bounds and inverse-run settings. |
| `aem/at_grid_export.py` | 212 | Exports a solved grid as tidy long-form CSV (one row per sample point) and as native NPZ, written atomically under one column contract. |
| `aem/mathieu_functions_OG.py` | 589 | Modified Mathieu functions of complex parameter. Third-party, MIT licence, Kristopher L. Kuhlman - keep the header. |
| `aem/designer_exports/source_config_horizontal.json` | 34 | Bundled designer export used to seed a horizontal AEM run. |
| `aem/designer_exports/source_config_vertical_61.json` | 504 | Bundled vertical source configuration (61 elements). |
| `aem/designer_exports/source_config_vertical_84.json` | 688 | Bundled vertical source configuration (84 elements). |

### 6.5 The `data_analysis/` package (Data Workbench maths)

Pure numpy/pandas/scipy. No Panel imports, by design, so every function is unit-testable.

| File | Lines | Purpose |
| --- | --- | --- |
| `data_analysis/__init__.py` | 16 | Package docstring and the rule about staying Panel-free. |
| `data_analysis/datasets.py` | 218 | CSV and NPZ intake, column typing, and validation. Every failure raises `ValueError` with a message safe to show a user. |
| `data_analysis/stats.py` | 132 | Descriptive statistics and preparation for distribution plots (normal and lognormal only, per the requirements). |
| `data_analysis/fits.py` | 202 | Curve fitting - linear, polynomial, exponential, logarithmic - each returning parameters, a vectorised `predict`, R², sample size and an optional 95% confidence band. |
| `data_analysis/kde.py` | 60 | Kernel density estimation through KDEpy's FFTKDE with ISJ bandwidth; imported lazily so the optional dependency can be absent. |
| `data_analysis/grids.py` | 185 | Long-form rows to a regular grid for contour and quiver plots (validating the lattice is rectangular), and the reverse for numerical results. |
| `data_analysis/scales.py` | 93 | Axis transforms: linear, ln, log10, inverse - implemented by transforming data and relabelling, so all four behave identically on every plot. |
| `data_analysis/formatting.py` | 87 | Two-decimal formatting everywhere (a supervisor requirement) while still rendering values that span orders of magnitude. |
| `data_analysis/notation.py` | 345 | Turns programmer column names (`plume_length_m`, `alpha_Tv`) into typeset LaTeX labels for Bokeh axes. |
| `data_analysis/modflow.py` | 218 | Reads MODFLOW 6 binary output (`.hds`, `.ucn`) and converts it to workbench-ready long-form CSV. |
| `data_analysis/plots.py` | 451 | The workbench's Bokeh figure builders, taking plain data and returning figures. |

### 6.6 Panel applications

**Shared infrastructure**

| File | Lines | Purpose |
| --- | --- | --- |
| `panel_theme.py` | 354 | The single theme for every Panel app: document-level CSS and class-level default stylesheets matching `static/styles.css`, plus the report and frame-height bridges. Call `apply_theme()` once at startup (`panel_server.py` does). |
| `panel_auth.py` | 59 | Resolves the caller's identity from the reverse-proxy header only, never from a client-supplied query parameter. The `PANEL_TRUST_QUERY_EMAIL` switch exists for local development and must stay off in production. |
| `panel_analytical_common.py` | 587 | The shared widget and layout kit, used well beyond the analytical pages: query readers, info/metric/summary/error cards, the explore sliders with their baseline chip, and the modelled-vs-measured comparison chart. |
| `panel_empirical_common.py` | 66 | The same helpers with the empirical pages' query-parameter aliases. |
| `panel_site_comparison.py` | 321 | One shared multiple-simulation engine for all eight closed-form models: pick sites, run once per site from that site's database parameters, plot modelled against measured. |
| `panel_model_scenarios.py` | 944 | The other multiple mode: an editable scenario table (typed rows or uploaded CSV), each row a parameter set, plotted against the measured lengths of ticked sites. Carries the Add-row dialog bridge and the upload handling. |
| `panel_numerical_multiple_common.py` | 444 | The scenario-table engine for the numerical multiple pages, so they behave like every other multiple page. |
| `panel_numerical_comparison.py` | 51 | Small Bokeh helpers for analytical-versus-numerical comparison, single and multiple. |
| `panel_numerical_optional_views.py` | 122 | The lazy extra views (concentration profile, gradient vectors) that post-process a retained result only after the user clicks, so a page load never pays for them. |

**One app per model page.** The `*_single.py` files own their widgets, result card, plot and PDF
state; the `*_multiple.py` files are usually thin wrappers over the shared engines above.

| File | Lines | Purpose |
| --- | --- | --- |
| `panel_liedl_single.py` | 95 | Liedl et al. (2005) single run. The best template to copy for a new model. |
| `panel_liedl_multiple.py` | 16 | Liedl scenario table. |
| `panel_liedl3d_single.py` | 97 | Liedl 3D (2011) single run. |
| `panel_liedl3d_multiple.py` | 7 | Liedl 3D multiple, one run per selected site. |
| `panel_chu.py` | 98 | Chu single **and** multiple in one module. |
| `panel_ham_single.py` | 86 | Ham et al. (2004) single run. |
| `panel_ham_multiple.py` | 7 | Ham multiple. |
| `panel_cirpka_single.py` | 69 | Cirpka et al. (2006) single run, query-driven. |
| `panel_cirpka_multiple.py` | 7 | Cirpka multiple. |
| `panel_maier_single.py` | 86 | Maier & Grathwohl (2006) single run. |
| `panel_maier_multiple.py` | 7 | Maier multiple. |
| `panel_birla_single.py` | 89 | Birla et al. (2020) single run. |
| `panel_birla_multiple.py` | 7 | Birla multiple. |
| `panel_kohler_single.py` | 144 | Koehler (2024) single run. The only page showing **two** numbers - `L_max` from Eq. (13) and the time to reach it from Eq. (14) - so its layout differs on purpose. |
| `panel_kohler_multiple.py` | 12 | Koehler multiple; its spec carries an `extra` callable that writes `T_Lmax` and a fitted-range verdict as two more table columns. |
| `bioscreen_panel.py` | 132 | BIOSCREEN single dashboard plus the multiple-time sweep. |
| `panel_numerical_horizontal_single.py` | 333 | Horizontal MODFLOW run: inputs, job submission and polling, the reactive plume figure, optional views, artefact downloads, PDF state. |
| `panel_numerical_horizontal_multiple.py` | 138 | Horizontal scenario table over the shared numerical multiple engine. |
| `panel_numerical_vertical_single.py` | 298 | The vertical equivalent, including the source direction/coverage controls. |
| `panel_numerical_vertical_multiple.py` | 191 | Vertical scenario table, with a pre-run feasibility check that reports unusable scenarios before any solve. |
| `panel_data_analysis.py` | 711 | The Data Workbench: choose a source (your database, an uploaded CSV/NPZ, or your last AEM run), then four tabs - univariate, bivariate, scientific/gridded, and export. |

### 6.7 Plotting and reporting

| File | Lines | Purpose |
| --- | --- | --- |
| `plot_functions.py` | 1268 | Every figure outside the workbench: the reactive plume plots for both orientations (`plot_reactive_plume_interactive` is the one the numerical pages use), contour and hover layers, concentration profiles and gradient vectors, model comparisons, and the site-database bar/box/histogram/scatter charts. Also loads the bundled reference CSV. |
| `pdf_report.py` | 999 | `PACSReport`: the one branded ReportLab engine behind every PDF - cover, project mark, parameter and output tables, embedded matplotlib or PNG figures, page footer, disclaimer. |
| `static/report_assets/` (2 files) | - | The university and DFG logos embedded in PDF headers; listed individually in 6.9. |

### 6.8 Templates

All 58 Jinja templates. The inheritance chain is
`base.html` -> `model_workbench_single|multiple.html` -> the per-model wrapper, or
`base.html` -> `model_about_base.html` -> `about_<model>.html`.

**Shell and shared layout**

| File | Lines | Purpose |
| --- | --- | --- |
| `base.html` | 169 | The site shell: head, brand badge and tagline, desktop navigation, mobile sidebar, footer, and the script/style includes. Every visible page except login and register extends it. |
| `model_workbench_single.html` | 75 | The standard single-model page: heading blocks, input form, report card, and the output iframe. |
| `model_workbench_multiple.html` | 86 | The same for multiple mode. |
| `model_page_base.html` | 64 | The older model-wrapper layout, still used by the numerical single templates. |
| `model_about_base.html` | 94 | The layout for every *About this model* page: category, title, chips, governing equation, body sections. |
| `model_input_form.html` | 255 | The shared split database/manual input form, driven by the field specs from the route modules. The file where the `[-]` dimensionless convention is documented. |
| `report_download_card.html` | 13 | The download card on single pages. |
| `report_bridge_card.html` | 10 | The card whose hint text the report bridge updates at runtime. |

**Landing and content pages**

| File | Lines | Purpose |
| --- | --- | --- |
| `index.html` | 122 | Landing page: hero, toolbox tiles, statistics, documentation copy. |
| `analytical_landing.html` | 69 | Analytical toolbox tiles. |
| `empirical_landing.html` | 42 | Hybrid/empirical toolbox tiles. |
| `numerical_landing.html` | 32 | Horizontal and vertical numerical tiles. |
| `aem_landing.html` | 17 | AEM toolbox entry. |
| `aem_designer.html` | 77 | The source designer (canvas UI driven by `static/aem.js`). |
| `aem_forward.html` | 23 | AEM forward-run page. |
| `aem_inverse.html` | 32 | AEM inverse-run page. |
| `site_database.html` | 245 | The site database page: upload, manual insert, filters, sorting, the responsive table and its export controls. |
| `panel_data_analysis.html` | 22 | Wrapper hosting the Data Workbench Panel app. |
| `dispersivity_data.html` | 88 | The legacy dispersivity dataset page with its histogram, box and scatter assets. |
| `login.html` | 47 | Standalone login form (does not extend `base.html`). |
| `register.html` | 61 | Standalone registration form with an inline submit handler. |
| `imprint.html` | 32 | Institutional imprint. |
| `privacy.html` | 59 | Privacy policy. |
| `plot_bar.html` / `plot_box.html` / `plot_hist.html` | 22 / 23 / 23 | The legacy full-page Bokeh plot pages. `plot_box` and `plot_hist` still contain duplicated legacy markup (README notes this). |

**About pages** - long-form model documentation, the natural home for text edits:
`about_liedl.html` (81), `about_liedl3d.html` (88), `about_chu.html` (71), `about_ham.html` (70),
`about_cirpka.html` (78), `about_bioscreen.html` (53), `about_maier.html` (68),
`about_birla.html` (73), `about_kohler.html` (108), `about_numerical.html` (89).

**Per-model page wrappers** - 8-11 lines each, nothing but block overrides (title, kicker, hint,
conceptual image, about link, Panel path):
`liedl_single.html`, `panel_liedl_multiple.html`, `panel_liedl3d_single.html`,
`panel_liedl3d_multiple.html`, `panel_chu_single.html`, `panel_chu_multiple.html`,
`ham_single.html`, `panel_ham_multiple.html`, `panel_cirpka_single.html`,
`panel_cirpka_multiple.html`, `panel_maier_single.html`, `panel_maier_multiple.html`,
`panel_birla_single.html`, `panel_birla_multiple.html`, `panel_kohler_single.html`,
`panel_kohler_multiple.html`, `panel_bioscreen_single.html`, `panel_bioscreen_multiple.html`,
`panel_numerical_horizontal_single.html` (40), `panel_numerical_horizontal_multiple.html`,
`panel_numerical_vertical_single.html` (40), `panel_numerical_vertical_multiple.html`.

### 6.9 Static assets

| File | Size | Purpose |
| --- | --- | --- |
| `static/styles.css` | 91 KB | The entire design system: layout, navigation, cards, forms, model pages, tables, responsive rules. The Panel theme in `panel_theme.py` mirrors its tokens, so a colour change belongs in both. |
| `static/script.js` | 33 KB | Browser behaviour: sidebar and dropdowns, account forms, active-nav highlighting, CSV filename display, iframe height sync, the animated headline, the landing canvas, and all three `postMessage` bridges. |
| `static/aem.js` | 75 KB | The AEM source designer front end (canvas drawing, element editing, calls to the packing API). |
| `static/site_database.js` | 9 KB | Site-database table behaviour: search, sort, page size, selection, exports. |
| `static/original.csv` | 14 KB | The bundled 112-site reference database, used when a user has uploaded nothing. |
| `static/sample_db.csv` | 318 B | The downloadable example upload. |
| `static/fig1_plots.csv` | 5 KB | Dataset behind the dispersivity-data page. |
| `static/fonts/InterVariable.woff2` | 343 KB | The one self-hosted font. |

**Images, one row each** (the *Used by* column is what breaks if you delete the file)

| File | Size | Used by |
| --- | --- | --- |
| `static/images/conceptual_liedl_2d.png` | 40 KB | `liedl_single.html`, `panel_liedl_multiple.html` |
| `static/images/conceptual_liedl_3d.png` | 123 KB | `panel_liedl3d_single.html`, `panel_liedl3d_multiple.html` |
| `static/images/conceptual_liedl_2005.png` | 69 KB | `about_liedl.html` |
| `static/images/conceptual_liedl_2011.png` | 243 KB | `about_liedl3d.html` |
| `static/images/conceptual_chu_2005.png` | 60 KB | `about_chu.html` |
| `static/images/conceptual_ham.png` | 79 KB | `ham_single.html`, `panel_ham_multiple.html`, `about_ham.html` |
| `static/images/conceptual_ham_2004.png` | 60 KB | `about_ham.html` |
| `static/images/conceptual_maier_2006.png` | 57 KB | `about_maier.html` |
| `static/images/conceptual_cirpka_horizontal.png` | 219 KB | `about_cirpka.html` |
| `static/images/conceptual_bioscreen.png` | 82 KB | `about_bioscreen.html`, both BIOSCREEN wrappers |
| `static/images/solution_bioscreen_at.png` | 20 KB | `about_bioscreen.html` |
| `static/images/conceptual_numerical_horizontal.png` | 388 KB | `about_numerical.html`, `panel_numerical_horizontal_single.html` |
| `static/images/conceptual_numerical_vertical.png` | 400 KB | `about_numerical.html`, `panel_numerical_vertical_single.html` |
| `static/images/fig_birla.png` | 202 KB | `about_birla.html` |
| `static/images/conceptual_chu.png` | 69 B | `panel_chu_single.html`, `panel_chu_multiple.html` - **1x1 placeholder**, trap 8 |
| `static/images/conceptual_cirpka.png` | 69 B | `panel_cirpka_single.html`, `panel_cirpka_multiple.html` - **1x1 placeholder**, trap 8 |
| `static/images/conceptual_numerical.png` | 69 B | nothing - **1x1 placeholder and now unreferenced**; safe to delete |
| `static/images/fig_chu.jpeg` | 19 KB | nothing - orphaned figure, kept in case an about page wants it back |
| `static/images/logos/university-tuebingen.svg` | 60 KB | `base.html` partner logos |
| `static/images/logos/iit-delhi.png` | 4 KB | `base.html` partner logos |
| `static/images/logos/university-waterloo.png` | 13 KB | `base.html` partner logos |
| `static/DispersivityPlots/box.png` | 20 KB | `dispersivity_data.html` |
| `static/DispersivityPlots/scatter.png` | 35 KB | `dispersivity_data.html` |
| `static/DispersivityPlots/ticks.png` | 24 KB | `dispersivity_data.html` |
| `static/report_assets/Logo_Universitaet_Tuebingen.svg` | 60 KB | PDF header (`pdf_report.py`) |
| `static/report_assets/dfg-logo-foerderung/dfg_logo_schriftzug_blau_foerderung_de.png` | 18 KB | PDF header (`pdf_report.py`) |

### 6.10 Tests

486 test functions across 49 files (about 750 cases once parametrised). Names are deliberately sentence-like, so `pytest -q -k
"plume"` is a good way to find the test that documents a behaviour you are about to change.

| File | Tests | What it protects |
| --- | --- | --- |
| `conftest.py` | - | Puts the repository root on `sys.path` so tests import the modules directly. |
| `test_route_smoke.py` | 24 | Every page renders, navigation contains the right entries, wrapper pages carry their iframe and report card. The broadest early-warning test. |
| `test_model_scenarios.py` | 55 | The scenario-table multiple mode: columns cover every model argument, a ticked site contributes only its measurement, rows run, uploads work, the bridges are wired. |
| `test_aem_flow.py` | 47 | AEM pages, job submission, ownership, result endpoints, and that AEM stays out of the Panel registry. |
| `test_aem_grid_export.py` | 28 | The CSV/NPZ grid export contract (row order, coordinates, headers) - vendored with the AEM code and fast, since it needs no solve. |
| `test_numerical_models.py` | 28 | Solver discovery, source-cell layout, plume-length extraction, and the pinned reference plume lengths. Needs `mf6` for the end-to-end cases. |
| `test_data_analysis_notation.py` | 18 | Column name to typeset label conversion. |
| `test_explore_sliders.py` | 15 | Slider bounds and the baseline chip, including that the frame holds still so the point can move. |
| `test_data_analysis_scales_format.py` | 14 | Axis transforms and two-decimal formatting. |
| `test_visualisation_routes.py` | 14 | The plot routes and JSON plot endpoints. |
| `test_auth.py` / `test_auth_pytest.py` / `test_auth_hardening.py` | 13 / 5 / 9 | Registration, login, logout, session handling; then the hardening pass - email validation, password length, user-enumeration resistance, rate-limit identity not trusting client headers. |
| `test_data_analysis_grids.py` | 13 | Gridding, lattice validation, and dataset intake. |
| `test_data_analysis_modflow.py` | 12 | MODFLOW binary reading, exercised against real flopy-written binaries rather than mocks. |
| `test_model_site_filtering.py` | 11 | Which sites each model may use, derived from its mathematical restrictions. |
| `test_multiple_site_comparison.py` | 11 | Every model runs once per selected site and every report row maps to a computed parameter. |
| `test_csv_import.py` | 9 | Delimiter detection, header aliasing, extra-field handling on upload. |
| `test_numerical_autofill.py` | 10 | Site autofill for the numerical pages: which database values reach which field, and what happens when one is missing. |
| `test_data_analysis_fits.py` | 9 | Fits recover known coefficients; R² and confidence bands behave. |
| `test_data_analysis_panel.py` | 9 | The workbench loads the user's database, refreshes, and exports. |
| `test_data_analysis_stats_kde.py` | 9 | Descriptive statistics and KDE. |
| `test_kohler_model.py` | 9 | The Koehler surrogates against the published numbers, including the turning point. |
| `test_numerical_multiple_graphs.py` | 8 | The vertical multiple page's feasibility checks and graph assembly. |
| `test_numerical_multiple_sites.py` | 7 | The numerical multiple page behaves like every other multiple page. |
| `test_pdf_report_site_table.py` | 7 | Multiple-run reports lay inputs out like the site table and split wide models instead of shrinking columns. |
| `test_site_delete.py` | 7 | Deletion is scoped to the owner; foreign or missing rows give 404. |
| `test_site_validation.py` | 7 | The data layer rejects bad numbers, over-long text and oversized uploads with clear messages. |
| `test_var_sym_conventions.py` | 7 | The symbol/label/variable convention holds across pages and scenario tables. |
| `test_multiple_wrappers.py` | 6 | Every multiple wrapper page is wired to its engine. |
| `test_error_handling.py` | 5 | Invalid model inputs give 400; non-finite parameters fall back to defaults. |
| `test_data_analysis_npz.py` | 5 | NPZ grid intake. |
| `test_model_equations.py` | 5 | Known equation outputs, including the Cirpka domain-length relation. |
| `test_proxy_config.py` | 5 | The nginx config orders Panel assets before Flask static and reports frame-height sync failures. |
| `test_lazy_numerical_views.py` | 4 | Optional views compute only after a click. |
| `test_reference_fallback.py` | 4 | The shipped reference database stands in for users with no uploads. |
| `test_site_database_layout.py` | 4 | The compact responsive table and its native controls. |
| `test_vertical_site_validation.py` | 4 | Vertical site validation and that the dropdown filter uses the shared function. |
| `test_pdf_report_numerical.py` | 4 | The numerical report accepts the current parameter/output shape and preserves image aspect ratio. |
| `test_contact_route.py` | 3 | The contact form works with and without SMTP configured, and rejects bad addresses. |
| `test_data_analysis_database.py` | 3 | The workbench frame shows visible numbers only and excludes internal fields. |
| `test_numerical_jobs.py` | 3 | Queueing does not cancel a running job and preserves queued/completed state. |
| `test_panel_proxy.py` | 3 | **Integration**: Panel through nginx on :80 - same-origin iframe, authenticated websocket upgrade (101), Panel's bundled assets. Skips automatically when :80 is unreachable. |
| `test_analytical_panel_layout.py` | 2 | Multiple pages carry both graph and editable table; embedded apps do not repeat the outer chrome. |
| `test_numerical_interactive_plots.py` | 2 | The reactive plume builder splits the Ca/Cd fields, adds hover, and puts depth downward for the vertical view. |
| `test_numerical_panel_autorun.py` | 2 | Autorun works with constant button names. |
| `test_report_plot_consistency.py` | 2 | The on-screen plot and the PDF plot use the same points; report rows use canonical symbols. |
| `test_schema_consistency.py` | 2 | `db_setup.sql` and `data_queries.ensure_schema()` agree. |
| `test_symbol_registry.py` | 2 | Canonical symbols map to the expected database columns and header matching covers new parameters. |
| `test_report_export_ui.py` | 1 | Report status labels stay plain ASCII. |

**Fixtures.** `tests/fixtures/orlando_reference/` holds the independently written reference
scripts (`horizontal_W-1.py`, `Horizontal_sim_final.py`, `vertical_model.py`) and their input
CSVs (`input_horizontal_W-1.csv`, `input_horizontal_W.csv`, `input_vertical.csv`,
`input_vertical_W.csv`, `input2.csv`). They are the scientific ground truth the numerical models are pinned against - read them
before changing `numerical_models.py`, and do not edit them to make a test pass.

### 6.11 Maintenance scripts

| File | Lines | Purpose |
| --- | --- | --- |
| `scripts/audit_vertical_sites.py` | 63 | Runs the vertical validation over the whole site database and reports every excluded site with the failing field, converted value and reason. Run it after changing any bound. |
| `scripts/repin_numerical.py` | 48 | Captures real MODFLOW plume lengths for the reference inputs, for pasting into the regression tests. Must run where `flopy` and `mf6` exist - i.e. inside the container. |

---

## 7. Running the tests

```bash
# everything (about 5 minutes; three files dominate)
python -m pytest tests -q

# the fast sweep you can run after every edit (about 1 minute)
python -m pytest tests -q --deselect tests/test_route_smoke.py \
    --deselect tests/test_numerical_models.py \
    --deselect tests/test_numerical_multiple_graphs.py

# find the test that documents a behaviour
python -m pytest tests -q -k "plume or grid"

# the integration test, which needs the Compose stack up on :80
docker compose up -d
python -m pytest tests/test_panel_proxy.py -q
```

What needs what:

| Suite | Requirement | If the requirement is missing |
| --- | --- | --- |
| Most unit tests | Nothing beyond `requirements-dev.txt` | - |
| `test_numerical_models.py` end-to-end cases | `mf6` on `PATH` or `MF6_EXE` set | Those cases fail or skip; run them in the container instead. |
| `test_panel_proxy.py` | The Docker stack healthy on `localhost:80` | Skips itself automatically, so CI without Docker is not blocked. |
| `test_data_analysis_modflow.py` | `flopy` (in `requirements.txt`) | Fails - it writes real MODFLOW binaries. |

There is **no CI configuration in this repository** (no `.github/workflows`). Tests run when
somebody remembers to run them. Section 9 recommends fixing that, because it is the cheapest
safety net a rotating research team can have.

---

## 8. Traps and tips

These are the things that cost real time here. Each one is a genuine property of this codebase,
not general advice.

1. **Rebuild after every Python or template change.**
   `docker compose build flask panel && docker compose up -d flask panel`. The code is baked into
   the image; only `static/` and `nginx/default.conf` are bind-mounted. A change that "had no
   effect" is almost always an unrebuilt image.

2. **Line endings are mixed across the repository.** Some files are stored with LF, others with
   CRLF. A find-and-replace script that rewrites a whole file in text mode will silently flip
   every line ending and produce a diff of thousands of lines with two real changes hidden in it.
   Read and write bytes, or check `git diff --stat` before committing - if a one-line edit shows
   1200 changed lines, that is what happened.

3. **Do not push Bokeh figures rapidly from a Panel callback.** Assigning `pane.object = <new
   figure>` many times in quick succession is not safe: Panel writes a patch immediately when the
   websocket is free and schedules it for the next loop iteration otherwise, so a later patch can
   overtake an earlier one and the document keeps whichever arrived last. This is exactly how the
   old plume "growth animation" ended up freezing one frame short of the final plume and showing a
   plume length 5 % below the result card. Measured against the container, patch arrival order was
   `... 436.55, 487.91, 462.23, 513.59` - every third frame overtaken. If you want animation,
   update a `ColumnDataSource` in place instead of replacing the figure.

4. **The three `postMessage` bridges must match on both sides.** Change the type string in
   `panel_theme.py` (or `panel_analytical_common.py`, `panel_model_scenarios.py`) and you must
   change it in `static/script.js` in the same commit, or the download button, the iframe height
   sync, or the Add-row dialog stops working with no error anywhere.

5. **Three test files are slow (~4 minutes total)** because they launch Panel apps and MODFLOW:
   `test_route_smoke.py`, `test_numerical_models.py`, `test_numerical_multiple_graphs.py`. Use the
   deselect line in Section 7 while iterating, then run the full suite before committing.

6. **`mf6` is a separate binary, not a Python package.** The Dockerfile downloads the official
   MODFLOW 6 release into the image. Outside Docker, put the executable on `PATH`, in `solvers/`,
   or point `MF6_EXE` at it - otherwise every numerical run fails with "the simulation engine is
   unavailable".

7. **Your local virtual environment probably does not match production.**
   `requirements.txt` pins `panel==1.4.5` and `bokeh==3.4.3`, which is what the container runs. A
   freshly created local venv can easily end up on a much newer Panel (1.8.x) with different
   rendering and different websocket behaviour. Before concluding "it works locally", check
   `python -c "import panel; print(panel.__version__)"` against
   `docker compose exec panel python -c "import panel; print(panel.__version__)"`. Upgrading those
   pins is a deliberate project, not a side effect of `pip install -U`.

8. **Three conceptual images are 1x1 transparent placeholders.**
   `static/images/conceptual_chu.png`, `conceptual_cirpka.png` and `conceptual_numerical.png` are
   69-byte 1x1 PNGs, and the Chu and Cirpka wrapper pages still point at them, so those pages show
   an empty figure slot. Real alternatives already exist in the same directory
   (`conceptual_chu_2005.png`, `conceptual_cirpka_horizontal.png`) - repointing the
   `conceptual_image` block is a five-minute fix and a good first pull request.

9. **`ensure_schema()` is not a migration system.** It creates tables if they are absent; it does
   not alter existing ones. Adding a column means writing the `ALTER TABLE` yourself and keeping
   `db_setup.sql` in step. `tests/test_schema_consistency.py` checks the two agree.

10. **Invalid numbers in an uploaded CSV become `NULL`, not an error.** Convenient for sparse
    field data, but it means a typo in a column silently drops a value rather than rejecting the
    row. If you tighten this, `tests/test_site_validation.py` and `test_csv_import.py` are where
    the current behaviour is written down.

11. **`PANEL_TRUST_QUERY_EMAIL` must stay off outside development.** With it on, a Panel app will
    believe an identity passed in the URL. Production identity comes only from the header nginx
    injects after `/auth/check` (`panel_auth.py`).

12. **Job artefacts are never pruned.** `NUMERICAL_JOB_ROOT` accumulates the queue database,
    pickled results, worker logs and AEM exports. On a long-lived deployment, clean it on a
    schedule or it grows without bound.

13. **`DEMO_BYPASS_LOGIN=1` makes local work much faster** by skipping the login wall. Never set
    it on a public deployment.

14. **Keep the repository clean.** `.env`, server logs, `Results/`, `outputs/` and solver binaries
    are git-ignored on purpose. The two briefing documents (`PACS_Brief.md`,
    `PACS_Toolkit_Technical_Brief.md`) are deliberately *untracked* local files - if the team wants
    them versioned, that is a decision to make explicitly, not by accident.

15. **Grep for the sentence, not for the file.** With the page split across a Jinja template and a
    Panel app, `grep -rn "some words" templates/ static/ *.py` finds the owner faster than
    guessing. The codebase is verbose on purpose: many modules carry long docstrings explaining
    *why* a decision was made, and comments marked `ponytail:` flag deliberate simplifications
    with their upgrade path.

---

## 9. Experimenting without breaking the live site

The team's question was how to try changes - text, equations, layout - without risking the running
service. Short answer: **yes, this is completely standard practice, and there are three levels of
it.** Pick by how much setup you are willing to do once.

### What professional teams actually do

Branching for isolation is the baseline. Research-software engineering guidance recommends a
simple feature-branch model for small university teams - and specifically recommends tying
branches to the publication process so a paper's results stay reproducible
([RSE Sheffield](https://rse.shef.ac.uk/blog/2019-best-practice/),
[A Research Software Engineering Workflow for Computational Science and Engineering](https://arxiv.org/pdf/2208.07460)).
The same literature flags exactly this project's situation as the classic risk: when
non-permanent research staff leave, the *reasoning* behind the code leaves with them unless
standard practices are followed ([Sustainable Research Software Hand-Over](https://arxiv.org/pdf/1909.09469)).
That is what this guide, the docstrings and the test suite are for.

On top of branching, industry practice has moved from one shared **staging** server towards
**preview (ephemeral) environments** - a temporary deployment created per branch or pull request
and destroyed when it merges. This has been standard at companies like Vercel, Netlify and GitHub
for years, and the 2026 guidance is that previews win when your problem is *reviewing and trying
out branches*, while a persistent staging environment wins when your problem is *release safety*
([preview vs staging](https://getautonoma.com/blog/preview-environments-vs-staging-environments),
[Shipyard's guide](https://shipyard.build/preview-environments/),
[setup guide](https://alloy.app/library/staging-vs-preview-environments-guide)).
For a small research team the honest translation is: a branch plus a second local stack covers
almost everything, and one shared staging URL is worth it only if non-developers (a supervisor, a
reviewer) need to click around before changes go live.

Running a second isolated copy of a Compose stack on one machine is itself a well-trodden
pattern: give it a different project name and different ports and Docker keeps the containers,
networks and volumes separate
([Docker forums](https://forums.docker.com/t/multiple-instances-of-docker-compose-on-a-single-server-that-listen-on-different-ports/137757),
[worked example](https://essamamdani.com/blog/running-multiple-instances-of-a-single-docker-compose-application)).

### Level 1 - branch + local stack (recommended starting point)

Costs nothing, works today, no server access needed.

```bash
git switch -c experiment/new-source-term      # never work on `final` directly
# ... edit ...
python -m pytest tests -q                     # fast sweep from Section 7
docker compose up -d --build                  # your own machine, your own database
git push -u origin experiment/new-source-term # a colleague can review or pull it
```

Conventions worth adopting: branch names like `text/about-liedl-wording`,
`model/vertical-source-term`, `fix/grid-minimum`; one topic per branch; `final` only ever
receives reviewed work. Merge through a GitHub pull request even if you are the only reviewer -
the PR page is where the "why" of a change survives after people leave.

### Level 2 - a sandbox stack beside production on the same server

When someone needs a clickable URL, run a second, isolated stack from the same repository. The
pieces are already in place: the only fixed port is nginx's `80:80`, and Compose isolates
everything else per project name.

```bash
# one-time: a checkout for the sandbox, on the branch being tried
git clone <repo> pacs-sandbox && cd pacs-sandbox
git switch experiment/new-source-term
cp .env.docker .env.sandbox        # point DB_NAME at a separate database
```

Then run it under its own project name and port:

```bash
COMPOSE_PROJECT_NAME=pacs-sandbox docker compose -f docker-compose.yml \
  -f docker-compose.sandbox.yml up -d --build
```

where `docker-compose.sandbox.yml` is a small override file (it does not exist yet - this is the
one piece of work Level 2 needs):

```yaml
services:
  nginx:
    ports:
      - "8080:80"        # production keeps :80, sandbox answers on :8080
  flask:
    env_file: [.env.sandbox]
  panel:
    env_file: [.env.sandbox]
```

Because the project name differs, the sandbox gets its own containers, network and
`numerical_jobs` volume, so a wrecked sandbox database cannot touch production data. Point a
subdomain at `:8080`, put HTTP auth in front of it, and mark the page visibly (a banner, or the
`brand-sub` tagline) so nobody mistakes it for the live site.

### Level 3 - per-branch ephemeral previews

The industry default, and overkill for three people, but worth knowing: a GitHub Actions workflow
builds the stack for every pull request, deploys it under a generated name, comments the URL on
the PR and destroys it on merge. Only worth building if branches start outliving the patience of
whoever is reviewing them.

### What to do first, concretely

1. **Protect `final` on GitHub.** Settings -> Branches -> require a pull request before merging.
   One click; it makes accidental direct pushes impossible.
2. **Add CI.** A workflow that runs `python -m pytest tests -q` (minus the Docker-only test) on
   every pull request. This repository has ~750 test cases and no automation to run them - that is the
   single highest-value improvement available.
3. **Write `docker-compose.sandbox.yml`** as above, commit it, and document the two commands in
   the README.
4. **Adopt the branch-name convention** and require that every merged branch names its topic.
5. **Keep a `CHANGELOG` habit** in the PR description: what changed scientifically, and which
   pinned test numbers moved and why. This is the part that saves the *next* handover.

---

## 10. Where things stand

**Recently changed (September 2026), so recent commits are worth reading:**

- `CAST` was renamed to `PACS - Preliminary Assessment of Contaminated Sites` across pages,
  headers, PDF branding, message bridges, container user, docs and tests.
- The pre-run grid cell-count cap was removed, along with its computed
  "increase the grid size to at least X m" message; the grid-spacing minimum is now a flat 0.1 m
  in the forms and widgets. `NUMERICAL_MAX_CELLS` no longer exists.
- The plume growth animation was removed (trap 3), so numerical single pages now render the final
  plume once.

**Known open items, honestly stated** (README's *Known Limitations* has the full list):

- The model-selection toolbox (statistical threshold, AIC, AHP ranking) is a design, not code.
- The AEM inverse model estimates one parameter at a time and reports no uncertainty bounds.
- No in-place editing of site-database rows.
- `plot_box.html` and `plot_hist.html` still contain duplicated legacy markup.
- Several help texts in `param_meta.py` are placeholders.
- Three conceptual images are placeholders (trap 8).
- No CI, and no branch protection on `final`.

**When something breaks, look here in this order:** the browser console (bridge and iframe
problems) -> `docker compose logs -f panel` (Panel app tracebacks) -> `docker compose logs -f
flask` (routes, PDF, database) -> the worker logs under `NUMERICAL_JOB_ROOT` (failed simulations)
-> `docker compose logs -f nginx` (routing and websocket upgrades).

Good luck, and thank you for keeping it running.

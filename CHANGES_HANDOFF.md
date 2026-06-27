# CAST Change Log and Handoff

Last updated: 2026-06-23

## Scope

This handoff records the completed AEM native-web migration and the related
input/conceptual-model layout change. The repository had many unrelated local
changes before this work; they were not reverted or included as part of this
scope.

## Completed Changes

### Shared model input layout

- Inputs render on the left and the conceptual model renders on the right.
- Both cards use equal grid tracks and stretched heights on desktop.
- The layout collapses to a usable single column on narrow screens.
- The change is implemented through `templates/model_page_base.html` and the
  scoped model-input rules in `static/styles.css`.

### One AEM entry

- The public navigation contains one `AEM Model` link to `/aem`.
- The old public Forward/Designer/Inverse menu split is gone.
- `/aem` and `/aem/designer` open the native source designer.
- Forward and inverse remain authenticated workflow pages, but are not
  separate public navigation entries.

### AEM no longer uses Panel

- AEM pages are native Flask templates with browser JavaScript and HTML canvas.
- AEM has no iframe, Bokeh document, Panel websocket, or `/panel/` dependency.
- The AEM applications and imports were removed from `panel_server.py`.
- The former `panel_aem_designer.py`, `panel_aem_forward.py`,
  `panel_aem_inverse.py`, and `templates/panel_aem_*.html` files were removed.
- Non-AEM analytical, empirical, and numerical Panel applications remain
  registered and unchanged by this migration.

### Source-faithful geometry

- `aem_source_geometry.py` contains the source designer's Shapely/Numpy
  geometry methods, including largest-gap-first `greedy_circle_pack()` and the
  iterative `repack_after_resize()` algorithm.
- Resizing keeps the changed circle fixed, iteratively resolves overlaps,
  corrects polygon-boundary violations, shrinks constrained neighbors, and
  regrows/nudges neighbors into available space as in the supplied source.
- The browser re-finds the selected circle after repacking, matching the source
  behavior when returned indices change.
- Drawn vertices use the source grid rules: 0.05 m snapping with Python-style
  half-even rounding, x clamped to `[0, 0.5]`, and nonnegative y.
- Vertical designs use the source coordinate shift and geometry-derived domain
  bounds before solver submission. Horizontal designs use the corresponding
  source-derived bounds.
- `Shapely>=2.0,<3.0` was added to `requirements.txt`.

### Native designer

- `templates/aem_designer.html` and `static/aem.js` provide polygon drawing,
  server-side packing, circle selection/movement, radius and concentration
  editing, circle/polygon deletion, repacking, clearing, and source/domain view.
- The canvas uses one physical units-per-pixel scale so circles and geometry are
  not distorted.
- Wheel zoom and pan are supported.
- JSON import/export round-trips the canonical AEM configuration schema.
- Malformed, self-intersecting, zero-area, oversized, or non-finite input is
  rejected before packing or job submission.

### Design-to-result flow

- Submitting a design stores it under a random, owner-scoped, 256-bit token and
  redirects to the distinct native forward page.
- Design tokens expire after 24 hours and cannot be read by another user.
- Large circle designs are stored server-side instead of being embedded in the
  query string, avoiding nginx request-line limits.
- `aem_jobs.py` continues to use the existing async numerical-job storage and
  unchanged `aem_forward` / `aem_inverse` worker kinds.
- Solver mathematics under `aem/` was not modified.
- Result responses expose only bounded, owner-checked summaries and plot data;
  internal pickle files and raw exceptions are not returned.
- Native result rendering uses the solver x/y extents, lower-origin rows, axis
  labels, and a concentration color legend.

### Security and validation

- All AEM pages require the existing Flask authentication.
- All state-changing AEM endpoints use the project's CSRF protection, and
  `static/aem.js` sends the CSRF header.
- Token and job reads, cancellation, and results enforce authenticated owner
  matching and return 404 for foreign resources.
- JSON requests are capped at 1 MiB, with additional polygon, element,
  candidate, numeric, and grid-work limits.
- Numeric values must be finite and satisfy the model's positive/bounds rules.

## Native AEM Routes

- `GET /aem` and `GET /aem/designer`: designer page
- `GET /aem/forward?design=<token>`: forward/run page
- `GET /aem/inverse`: inverse page
- `POST /aem/api/pack`: validate and pack a polygon
- `POST /aem/api/repack`: run the source resize/repack algorithm
- `POST /aem/api/design`: validate and store an owner-scoped design
- `POST /aem/api/forward`: enqueue an AEM forward job
- `POST /aem/api/inverse`: enqueue an AEM inverse job
- `GET /aem/jobs/<job_id>`: owner-checked job status
- `POST /aem/jobs/<job_id>/cancel`: owner-checked cancellation
- `GET /aem/jobs/<job_id>/result`: bounded owner-checked result data

## Files Added

- `aem_source_geometry.py`
- `static/aem.js`
- `templates/aem_designer.html`
- `templates/aem_forward.html`
- `templates/aem_inverse.html`
- `tests/test_aem_flow.py`

## Files Updated

- `aem_routes.py`
- `aem_jobs.py`
- `panel_server.py`
- `requirements.txt`
- `docker-compose.yml`
- `static/styles.css`
- `templates/base.html`
- `templates/model_page_base.html`

## Files Removed

- `panel_aem_designer.py`
- `panel_aem_forward.py`
- `panel_aem_inverse.py`
- `templates/panel_aem_designer.html`
- `templates/panel_aem_forward.html`
- `templates/panel_aem_inverse.html`
- `tests/test_aem_panel_regressions.py`

Some of these paths were already untracked in the dirty worktree, so their
addition/removal may not appear as a conventional tracked Git deletion.

## Verification

Final independent review approved acceptance criteria A-H with no known
critical, high, or medium issues.

- Full test suite: `210 passed`, plus `22 subtests passed`
- Focused AEM tests: `33 passed`
- Final AEM + route/auth review set: `96 passed`
- Python compilation: passed
- `node --check static/aem.js`: passed
- Node geometry/helper assertions: passed
- `docker compose config --quiet`: passed
- Scoped `git diff --check`: passed
- No AEM Panel files, registrations, iframe URLs, or Panel asset references
  remain; non-AEM Panel registrations remain.

## Remaining Verification Limitations

- Automated checks did not drive a real browser DOM/canvas or capture responsive
  visual screenshots. The canvas interactions were checked through JavaScript
  helpers/contracts and Flask tests.
- A live nginx + Flask + worker multi-container heavy solver run was not executed
  during the final pass. Queue integration, ownership, worker kinds, Compose
  configuration, and the full Python suite were verified.
- JavaScript normalizes snapped decimal coordinates (for example,
  `0.15000000000000002` becomes `0.15`). This preserves the exact grid point and
  has no practical UI or solver effect, but is not bit-for-bit Python float
  representation parity.

## Run Locally

Because `requirements.txt` changed, rebuild the services:

```powershell
cd C:\Users\User\Desktop\cast_landing_demo
docker compose up -d --build flask panel worker nginx
```

Then open `http://localhost/aem`. The Panel service is still required by other
models, but AEM itself no longer connects to it.

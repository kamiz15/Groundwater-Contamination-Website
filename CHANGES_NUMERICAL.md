# Numerical Model — Change Summary

A record of the changes made to the numerical (MODFLOW 6 / FloPy) horizontal & vertical
models, their plots, input forms, reporting, job system, and supporting code. Source of
truth for the new behaviour: Orlando's `horizontal_W.py` / `vertical_W (1).py` and the two
conceptual schemas, plus the Anton/Prof meeting decisions.

Status legend: ✅ done & verified · ⚠️ needs a real MODFLOW run to re-confirm · ⬜ pending.

---

## 1. Core model rewrite (`numerical_models.py`)

✅ `run_numerical_model_horizontal` and `run_numerical_model` were rewritten to match
Orlando's new scripts.

- **Seven modifiable inputs** (the rest are derived/standard):
  - Horizontal: `source_thickness (Sw), grid_size, al, at, gamma, Cd, Ca`
  - Vertical: `Lz, grid_size, al, atv, gamma, Cd, Ca`
- **Analytical domain sizing** (`L_D = 1.5 × L_max`), not user input:
  - Horizontal (Cirpka): `L_D = 1.5 · Sw² / (16·αt·erfinv(Ca/(γCd+Ca))²)`; domain width `= 10·Sw`
  - Vertical (Liedl): `L_D = 1.5 · (4Lz²)/(π²·αtv) · ln((4γCd+Ca)/(πCa))`
- **Grid** from `grid_size` (Δx=Δy / Δx=Δz); columns/layers derived.
- **Heads removed as inputs** — derived from a fixed hydraulic gradient.
- **Standards** (editable defaults): porosity `0.3`, K `8.64 m/d`, gradient `0.0125`.
- **No right-hand boundary** (Orlando's choice; confirms the long-open O8 question).
- **Save only the final concentration step** (`CONCENTRATION LAST`) — less memory.
- Result objects now expose `domain_length`, `domain_width`/`aquifer_thickness`,
  `peclet`, `courant`, `perlen`, `k_warning`, `head_file`, `concentration_file`.
- Legacy `numerical_model()` wrapper removed (unused).

**Validated end-to-end in Docker with real MODFLOW 6.7.0:** horizontal `plume_length ≈ 117.99 m`
(`L_D 143.66`), vertical `≈ 514.21 m` (`L_D 688.50`). The vertical 514 m matches the "≈515"
Orlando quoted in the meeting.

---

## 2. Analytical model fix — the real root cause (`analytical_models.py`)

✅ **`cirpka_2005` used `erfcinv` where Orlando's model uses `erfinv`.** This single mix-up was
the cause of the platform-vs-Orlando discrepancy discussed across several meetings:

- Old (`erfcinv`): `L_max ≈ 15.4 m` → this is the "~15 m" the platform showed.
- New (`erfinv`): `L_max ≈ 95.8 m`, `L_D ≈ 143.66 m` → matches Orlando's numerical `L_D` exactly.

The pinned analytical regression test was updated accordingly (`123.16 → 766.17` for the
`cirpka_lmax` reference case). Orphaned `erfcinv` import removed.

---

## 3. Plots (`numerical_models.py`, `plot_functions.py`)

- ✅ **Real backward transformation** (replaces an earlier placeholder split): with `C0 = Ca`,
  `Ca = C0 − conc` (Blues, 0..Ca) and `Cd = (conc − C0)/γ` (Reds, 0..Cd), black plume contour at `C0`.
- ✅ **Schema annotations**: source `CD` marker, `CA` label, `L^n_max` callout, and a caption below
  each figure with `L_D`, Δx/Δy(z), porosity, K, gradient, **Péclet**, Courant.
- ✅ **Uppercase `CA`/`CD`** labels and colorbars (Prof's request), subscripts removed.
- ✅ **Colorbars** standardised to vertical, right-side on both models.
- ✅ Removed the redundant dashed `L_max`/`LD` marker lines earlier; the `L^n_max` callout is now a
  clean **dashed vertical line** with a white-boxed label, and the `CD` label is a white-boxed tag at
  the source (no overlap with the colormap or axis title).
- ✅ **Smoother, more detailed rendering** — display-only `bilinear` interpolation plus an upsample
  (`_display_field`) so coarse grids no longer show blocky "staircase" gaps between the Ca/Cd fields.
  **Display only**: `plume_length` and the returned `concentration` are computed from the raw arrays.

---

## 4. Input form — 3 columns (`numerical_routes.py`, `templates/model_input_form.html`)

✅ The numerical input page now renders **three columns** instead of the old DB/Manual split:

- **Input** — the 7 user/DB fields (source/Lz, grid size, αL, αT/αTv, γ, Cd, Ca).
- **Analytical** — read-only, server-computed `L_D` and width/thickness (from the analytical model).
- **Standard** — editable defaults (porosity, K, gradient).

Implemented via a per-field `column` tag + a server-side `_numerical_analytical_fields()` helper;
all other models keep their existing DB/Manual two-column form. (The Panel app form was also grouped
into Input / Analytical / Standard.)

---

## 5. Reporting (`pdf_report.py`, `numerical_routes.py`)

- ✅ **Two-decimal formatting everywhere** in report output (`CASTReport._fmt_value`).
- ✅ **Péclet & Courant** added as report fields; the report's domain-length row now reads the model's
  real `result.domain_length`.
- ⬜ *Open:* a visual pass on the "Download PDF Report" button to confirm the full prior format — see
  `AGENT_PROMPTS_REMAINING.md`, Task #2.

---

## 6. Downloads (`numerical_models.py`, `numerical_routes.py`, panels)

✅ The model captures the MODFLOW head (`.hds`) and concentration (`.ucn`) bytes on the result; an
ownership-checked route `GET /numerical/jobs/<id>/download/<head|concentration>` serves them; both
single panels show **Download head / Download concentration** buttons after a run.

---

## 7. Hydraulic-conductivity policy (`numerical_models.py`, panels)

✅ **Accept + warn** (O9): any K is accepted, but a warning is logged and returned
(`result.k_warning`) when K is outside the typical sand-aquifer range (1–100 m/d, env-configurable
`NUMERICAL_HK_MIN/MAX_M_PER_DAY`). Surfaced as a "⚠ K warning" row in the single panels.

---

## 8. Jobs: no more self-cancelling + queueing (`numerical_jobs.py`, panels)

✅ **`submit_job` no longer cancels other jobs.** Previously every new submission force-cancelled all
queued/running jobs (this is why simulations showed "cancelled" on their own). Now a submission only
**enqueues**; the existing queue runs up to `NUMERICAL_MAX_CONCURRENCY` (default 2) and the rest wait
**queued** until a slot frees. Manual cancellation still works via the cancel button (`cancel_job`).
The two job tests that asserted the old auto-cancel were rewritten to the new queue contract
(`tests/test_numerical_jobs.py` → 3 passed).

✅ The displayed **job ID is shortened** to its first 8 characters in the panels.

---

## 9. Performance — the 4-minute run (`numerical_models.py`)

✅ Root cause: `perlen = Lx/v + 1000` days combined with the Courant timestep made the number of
timesteps **scale with K**. A high-K site (K≈518 m/d) produced ~4346 timesteps → ~4 minutes.

Fix: scale the simulation time by **pore-volume flushes** instead of a fixed 1000-day buffer:
`perlen = N · (Lx/v)` with `N = NUMERICAL_PORE_VOLUMES` (default 6). This makes the timestep count
**grid-bounded (~6·ncol/5 ≈ 173), independent of K** — the K≈518 case drops `4346 → 173` steps
(~25× faster, seconds not minutes).

**Not a physics change.** The grid, boundary conditions, dispersivities, transport scheme, analytical
sizing and the per-step timestep (Courant ≈ 5) are unchanged — only the total run duration changes,
and only to stop once steady state is reached. The steady-state plume length is the same; for the
validated low-K case the new time is actually *longer* than Orlando's, so the result is identical.
⚠️ Re-confirm once in Docker (`scripts/repin_numerical.py`); bump `NUMERICAL_PORE_VOLUMES` to 8–10 if
any case needs more flushes to stabilise.

---

## 10. UI / config

- ✅ **Demo Mode** label and the two non-functional "Demo only" buttons removed from `templates/base.html`
  (the demo *login* bypass itself was left intact).
- ✅ **`FLASK_DEBUG=false`** in `.env` — the Werkzeug auto-reloader was restarting the dev server on
  library file changes and killing in-flight jobs. With it off, jobs survive. (Reminder: run jobs via
  the real Flask/Docker server, not by repeatedly killing the dev process.)

---

## 11. Testing

- `tests/test_numerical_models.py` — migrated to the new 7-input signatures; reference plume lengths
  **re-pinned from real MODFLOW runs** (117.99 / 514.21); `mf6`/`flopy`-gated skip so solver tests skip
  cleanly when the binary is absent.
- `tests/test_model_equations.py` — Cirpka expectation re-pinned to the `erfinv` value.
- `tests/test_numerical_jobs.py` — rewritten to the queue (no auto-cancel) contract.
- Suites green where runnable: `19 passed, 4 skipped` (numerical), `12 passed` (equations),
  `3 passed` (jobs).

---

## 12. Remaining work

- ⬜ **#1 Interactive graphs + load animation** — switch the result display from a static PNG to an
  interactive (Bokeh) figure with hover/zoom/pan; keep `plot_png` for the PDF.
- ⬜ **#2 PDF report button** — visual verification/fix in the prior format.
- ⬜ Re-validate the faster runs and the new pages end-to-end in Docker.
- ⬜ Monday conceptual question: centred vertical source vs full-thickness (currently full-thickness).

Ready-to-run agent prompts for #1 and #2 (plan → build → test → debug) are in
`AGENT_PROMPTS_REMAINING.md`. Full task-by-task status is in `NUMERICAL_MODEL_TASKS.md`.

---

## Deploy / verify

1. `docker compose up -d --build` (the image **COPYs** code at build — a rebuild is required to pick up
   these changes; the running container otherwise serves the old code).
2. Open `/numerical/horizontal/single` or `/numerical/vertical/single` — new 3-column form, schema plot
   with `CA`/`CD`, download buttons.
3. `docker compose exec flask python scripts/repin_numerical.py` — confirms the model runs and prints the
   real plume lengths / faster timing.

# Numerical Model — Task Tracker

Living checklist for the numerical-model rework. Updated as tasks complete.
Source of truth for new behaviour: Orlando's `horizontal_W.py`, `vertical_W (1).py`,
`input_horizontal_W.csv`, `input_vertical_W.csv`, plus the two conceptual schemas.

Legend: ✅ done · 🔄 in progress · ⬜ to do · ⛔ blocked / needs decision

---

## A. Already done (earlier sessions)

- ✅ **O4** Horizontal dual Ca/Cd colorbar plot (placeholder threshold split) — *to be replaced by the real backward transform, see N3*
- ✅ Remove dashed `Lmax` vertical marker line from all numerical plots
- ✅ Remove grey dotted `LD` domain line; clean unused `Span` import
- ✅ Vertical dual Ca/Cd colorbar plot (right-side colorbars, Depth-down)
- ✅ **O5** Save only final concentration step (`CONCENTRATION LAST`)
- ✅ **O7** Draw plume boundary at true threshold `C0` (threaded from panels)
- ✅ **O1** Auto sim-time helper `_steady_state_perlen` (opt-in, +1000 d)

## B. Resolved by Orlando's new files

- ✅ **O3** Analytical-vs-numerical gap → analytical formulas now defined in code (Cirpka/Liedl); source term uses full `Sw²`
- ✅ **O8** Right-side boundary → Orlando commented it out → **dropped**

---

## C. New work (this effort)

### Core model rewrite (stay true to Orlando's new code)
- ✅ **N1** `run_numerical_model_horizontal` rewritten to `horizontal_W.py` (Cirpka `L_D`,
  `D_W=10·Sw`, grid-size grid, auto `perlen`, derived heads, Courant 5, Péclet). Agent-verified.
  New signature: `(source_thickness, grid_size, al, at, gamma, cd, ca, prsity=0.3, hk=8.64, gradient=0.0125, h_left=20)`.
- ✅ **N2** `run_numerical_model` (vertical) rewritten to `vertical_W (1).py` (Liedl `L_D`,
  `nlay=Lz/grid_size`, source full thickness, no right boundary, depth-down). Agent-verified.
  New signature: `(Lz, grid_size, al, atv, gamma, cd, ca, prsity=0.3, hk=8.64, gradient=0.0125, h_left=20)`.
  Result dataclasses now expose domain_length / peclet / courant / perlen. Legacy `numerical_model()` removed.

  **✅ Callers updated (N6 — RESOLVED, no TypeError; verified by grep + compile + tests):**
  - ✅ `panel_numerical_horizontal_single.py`, `panel_numerical_vertical_single.py`
  - ✅ `panel_numerical_horizontal_multiple.py`, `panel_numerical_vertical_multiple.py`
  - ✅ `numerical_routes.py` (field specs + `_horizontal_pdf` / `_vertical_pdf` + DB autofill `source_thickness` key + report route reads `result.domain_length`/peclet/courant; dead `report_meta["Lx"]` removed)
  - ✅ `tests/test_numerical_models.py` (4 sites on new kwargs). **Re-pinned with real MODFLOW 6.7.0
    runs (in Docker):** horizontal plume_length ≈ 117.99 m (L_D 143.66), vertical ≈ 514.21 m (L_D 688.50).
    Model validated end-to-end against the live solver. ✅ **N6 fully done.**
  No old-signature keys reach the model anywhere. Confirmed: `grep` for `Lx/A_W/ncol/nrow/alpha_Th/av/ath/h1/h2/perlen/plume_threshold` in caller dicts → none.
- ✅ **N3** Real backward transform in plots: `Ca = C0−conc` (Blues, 0..Ca),
  `Cd = (conc−C0)/γ` (Reds, 0..Cd), `C0 = Ca`, black contour at `C0`. Done via `imshow`
  in both numerical_models.py plot blocks (horizontal = bottom bars, vertical = right bars).
  *Note: plume_length extraction still uses the separate `c0` threshold — align to `Ca` in N1/N2.*
- ✅ **N4** Schema-annotated graphs: source `C_D` bar, `C_A` labels, `L^n_max` callout,
  and a standards/Péclet/Courant caption below each figure. Verified by render.
  *Remaining nice-to-have: explicit `R_W^a/R_W^b` buffer labels and a Δx/Δy grid-cell glyph.*

### Analytical model
- ✅ **N5** Cirpka analytical aligned to Orlando's numerical model. **Root cause found:**
  `cirpka_2005` used `erfcinv` instead of `erfinv`. Fixed → `Lmax=95.77 m`, `L_D=143.66 m`
  (matches Orlando's numerical L_D exactly). The old `erfcinv` gave `15.40 m` — *this is the
  "~15 m" the platform showed in the meeting*. Resolves the long-standing analytical-vs-numerical
  discrepancy (O3). Orphaned `erfcinv` import removed. Verified numerically.

### Input form (panels)
- 🔄 **N6** Wire callers to the new model (3-column form). Pattern in Section F.
  All 5 CODE callers migrated (compile + grep + signature-match verified; Panel/mf6 not
  runnable in sandbox). New 7-input + standards form, new params dict, Bokeh→PNG via HTML img.
  - ✅ `panel_numerical_horizontal_single.py` (reference impl) + rebuilt PDF parameters (L_D/width/Péclet/time).
  - ✅ `panel_numerical_vertical_single.py`
  - ✅ `panel_numerical_horizontal_multiple.py` (7-input scenario table)
  - ✅ `panel_numerical_vertical_multiple.py` (7-input scenario table)
  - ✅ `numerical_routes.py` — field specs + `_horizontal_pdf` / `_vertical_pdf` param dicts.
  - ✅ `tests/test_numerical_models.py` — migrated to new kwargs; mf6/flopy-gated skip added;
    added an analytical `L_D` test (no solver) asserting Cirpka = 143.66 m; Orlando's new input
    CSVs copied to `tests/fixtures/orlando_reference/`. **Suite green: 19 passed, 4 skipped.**
    Numerical plume-length pins (`# TODO`) await a real mf6 run.
  - ✅ Regression fixed: `test_model_equations.py` `cirpka_lmax` expectation re-pinned to the
    erfinv value (766.17, was 123.16 from erfcinv).
  - ✅ Follow-up done: report route (`numerical_job_report`) now reads `result.domain_length`
    for the domain-length row (plus Péclet + Courant). The `report_meta["Lx"]=0.0` key is now
    inert/unused.

**N6 COMPLETE** (all code callers + tests on the new scheme; only the report-route `domain_length` polish + real-mf6 plume-length re-pin remain).

### Reporting
- 🔄 **N7** PDF report per Prof's instructions:
  - ✅ 2-decimal formatting everywhere in output (`CASTReport._fmt_value`, applied to the
    input table + results grid; chart caption already used `:.2f`). Verified inline.
  - ✅ Péclet & Courant as report fields — added to the PDF report outputs (report route reads
    `result.peclet` / `result.courant`). **N7 COMPLETE.**
  - ✅ schema-style figures flow into the report automatically once the model passes the
    N4 `plot_png` (no report change needed).

### Decided but not yet implemented
- ✅ **O9** Hydraulic-conductivity *Accept + warn*: `_k_range_warning(hk)` accepts any K, logs +
  returns a warning when outside 1–100 m/d (env-configurable `NUMERICAL_HK_MIN/MAX_M_PER_DAY`);
  exposed as `result.k_warning` and shown as a "⚠ K warning" row in both single panels. Verified.

### Still open / external
- ⬜ **O2** Background job execution (partly built in `numerical_jobs.py`).

---

### New (from 2nd Orlando meeting)
- ✅ **N8** Download outputs: model now captures the MODFLOW head (`.hds`) and concentration
  (`.ucn`) bytes on the result; ownership-checked route `GET /numerical/jobs/<id>/download/<head|concentration>`;
  "Download head/concentration" buttons in both single panels (shown after a run). Compile/structure
  verified (run-test needs mf6).
- ✅ **N9** Annotation style → **uppercase CA/CD** (your choice): colorbar labels + source bar +
  acceptor labels in both plots now use `CA`/`CD` (subscript removed). Verified.

### Agent prompt tasks completed (June 22, 2026)
- ✅ **Task #1 - Interactive graphs + load animation**: single horizontal/vertical panels now render
  a Bokeh Ca/Cd interactive plume figure from raw `result.concentration` with pan/zoom/save tools,
  hover readouts, source/CA/CD/L^n max annotations, and a queued/running pulse animation. The
  matplotlib `result.plot_png` path remains unchanged for PDF output.
- ✅ **Task #2 - Download PDF Report button**: panel and Flask report paths keep using
  `CASTReport.generate(...)` with the new numerical parameters, L_D + width/thickness, Peclet,
  Courant, numerical Lmax, and schema `plot_png`; numeric report values are formatted to two decimals.
  Evidence generated in `outputs/`: interactive HTML, sample PDF, and rendered PDF page PNGs.

## D. Decisions resolved (2nd Orlando meeting)
- ✅ **Plot architecture** → matplotlib (stay true to Orlando's `imshow` code).
- ✅ **7 inputs** (top): grid_size, αL, αT, γ, Ca, Cd, + source_thickness (horiz) / Lz (vert).
- ✅ **Standard** (info shown *below the graph*, modifiable): porosity 0.3, K 8.64 m/d, gradient 0.0125.
- ✅ **Analytical** (computed, not asked): L_D = 1.5·Lmax, domain width/thickness.
- ✅ Heads removed (derived from gradient). Right boundary dropped. Courant target = 5.
- ✅ **Colorbar placement**: standardised to vertical right-side bars on BOTH models.
- ⬜ Vertical source = whole thickness for now (centred-source conceptual model deferred — ask Monday).

---

## G. Deployment & testing (answers to live questions)

- **Changes are in the real repo.** `git status` shows `numerical_models.py`, `numerical_routes.py`,
  `analytical_models.py`, all four `panel_numerical_*`, `pdf_report.py`, `plot_functions.py`,
  `tests/*`, and this tracker as modified/added. (Other modified files in the tree are pre-existing
  uncommitted work, not from this effort.)
- **Why the site looks unchanged in Docker:** the image **COPYs the code at build** (`Dockerfile: COPY . /app`);
  the compose services mount only `static/`, data, and the DB init — **not the `.py` code**. The running
  container has the old code. Rebuild to pick up changes:
  `docker compose up -d --build`  (or `docker compose build flask panel && docker compose up -d`).
  Then the changes show on the **numerical horizontal/vertical pages** specifically.
- **Running MODFLOW for tests:** the container already has `mf6` (installed in the Dockerfile). To run the
  suite inside Docker:  `docker compose exec flask python -m pytest tests/test_numerical_models.py -q`.
  The 4 solver tests un-skip when `flopy`+`mf6` are present. To re-pin: capture `result.plume_length` from
  `run_numerical_model_horizontal(**input_horizontal_W.csv)` and `run_numerical_model(**input_vertical_W.csv)`
  and replace the `# TODO` asserts.
- **Sandbox note:** I installed flopy 3.10 + MODFLOW 6.7.0 here and confirmed the flow model runs in 0.02 s;
  full reference runs exceed the sandbox's 45 s shell cap, so the numerical re-pin is left for your Docker.

## E. Workflow note
Builds done inline (full Orlando-code + repo context); each task gets a verification
(test/debug) agent. Changes left in place for review; this file updated as tasks reach ✅.

---

## F. N6 turnkey spec (execute next — panels/routes/tests)

New model takes **7 inputs + 3 standard defaults**. Apply to each caller.

- New params (horizontal): `{source_thickness, grid_size, al, at, gamma, cd, ca, prsity, hk, gradient}`
- New params (vertical):   `{Lz, grid_size, al, atv, gamma, cd, ca, prsity, hk, gradient}`
- Drop everywhere: `Lx/Ly/A_W, ncol, nrow, alpha_Th/av/ath, h1, h2, perlen, plume_threshold/c0, source_col_index, vk, source_bottom_buffer`.

Per file:
1. `panel_numerical_horizontal_single.py` / `panel_numerical_vertical_single.py`
   - Widgets in 3 groups: **Input** (source_thickness/Lz, grid_size, al, at/atv, gamma, cd, ca);
     **Standard (modifiable)** (prsity=0.3, hk=8.64, gradient=0.0125);
     **Analytical (read-only, post-run)** show `result.domain_length`, width/thickness, `result.peclet`, `result.perlen`.
   - Delete widgets: lx, ly, nrow, ncol, h1, h2, c0, perlen. Fix validation + PDF parameters list.
   - Build the new params dict; `submit_job` unchanged.
   - Display: replace Bokeh `graph_pane` + `plot_*_plume_interactive(...)` with `pn.pane.PNG(result.plot_png)`
     (model now renders the full schema figure). Drop `comparison_pane`.
2. `panel_numerical_horizontal_multiple.py` / `..._vertical_multiple.py` — same param-dict swap per scenario row.
3. `numerical_routes.py` `_horizontal_pdf` (282-298) / `_vertical_pdf` (319-336) — same swap.
4. `tests/test_numerical_models.py` (4 sites) — new kwargs; **re-pin** expected plume lengths from a real `mf6` run.
5. After wiring: **N8** downloads (persist `.hds`/`.ucn`) and **N7** Péclet/Courant report fields drop in cleanly.

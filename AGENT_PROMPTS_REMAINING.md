# Agent prompts — remaining numerical-model tasks

Loop for each task: **Planning → Build → Test → (Debug if Test fails) → repeat until approved.**
Repo (sandbox path): `/sessions/<session>/mnt/cast_landing_demo` (= `C:\Users\User\Desktop\cast_landing_demo`).
Hard rules for every agent: make edits via the real files (bash/python, not only sandbox scratch);
never change the solver grid / physics / `plume_length`; keep `result.plot_png` (matplotlib) for the PDF;
the MODFLOW binary is at `/sessions/<session>/mf6bin/mf6` (set `MF6_EXE`) but full runs are slow — prefer
synthetic data for plot tests.

Context both tasks share:
- Numerical run returns a dataclass (`numerical_models.py`): `HorizontalModelResult` / `NumericalModelResult`
  with `concentration` (raw 2-D array), `x_grid`, `y_grid`/`z_grid`, `plume_length`, `domain_length`,
  `domain_width`/`aquifer_thickness`, `peclet`, `courant`, `perlen`, `plot_png`, `head_file`, `concentration_file`.
- Ca/Cd backward transform used in the static plot: `C0 = ca`; `Ca_field = C0 - conc` (mask conc>=C0, Blues 0..Ca);
  `Cd_field = (conc - C0)/gamma` (mask conc<=C0, Reds 0..Cd); black contour at `C0`. Horizontal origin lower;
  vertical depth-down (origin upper).
- Single panels (`panel_numerical_horizontal_single.py`, `panel_numerical_vertical_single.py`) render the result
  in `_render_completed_result` by setting `graph_pane.object` to an HTML `<img>` of `result.plot_png`
  (`graph_pane = pn.pane.HTML(...)`).

---

## TASK #1 — Interactive graphs + load animation

### 1a. Planning agent
> Read-only. Repo: `…/cast_landing_demo`. Plan how to make the numerical result plots **interactive**
> (zoom, pan, hover-readout of concentration) and add a subtle **load animation**, replacing the current
> static matplotlib PNG shown via `pn.pane.HTML(<img>)` in `panel_numerical_horizontal_single.py` /
> `panel_numerical_vertical_single.py` (`_render_completed_result`). The data available on the result is
> `concentration` (raw 2-D), `x_grid`, `y_grid`/`z_grid`, `plume_length`, `domain_length`, `domain_width`/
> `aquifer_thickness`, `ca`/`cd`/`gamma` (panel widgets). Recommend Bokeh (already a dependency, Panel-native via
> `pn.pane.Bokeh`) vs Plotly. The interactive figure must reproduce the dual Ca/Cd field (backward transform
> above), the black `C0` plume contour, the `CA`/`CD` labels, the source marker, and an `L^n_max` line, with a
> HoverTool showing distance/width(depth)/Ca/Cd. Specify: which library, a new builder function (where to add it —
> e.g. `plot_functions.py`), the exact panel wiring change, how to keep `result.plot_png` for the PDF, and how to
> add a CSS/JS fade/pulse load animation while the job runs. Output a numbered plan with file:line and the exact
> code to add. Flag anything ambiguous (e.g. animate plume growth over time would require saving all timesteps —
> currently only LAST is saved; note this).

### 1b. Build agent
> Implement the approved plan. Add an interactive figure builder (Bokeh recommended) that takes the raw
> `concentration` + grids + `ca,cd,gamma` and returns a `bokeh` figure: two image layers (Ca Blues, Cd Reds via the
> backward transform), the `C0` contour line, `CA`/`CD`/source/`L^n_max` annotations, pan/box-zoom/wheel-zoom/reset/
> save tools, and a HoverTool. Wire `graph_pane` in both single panels to `pn.pane.Bokeh(fig)` instead of the HTML
> `<img>`; keep building `result.plot_png` (matplotlib) so the PDF is unchanged. Add a lightweight load animation
> (e.g. a CSS `@keyframes` pulse on the result card while status is queued/running). Do NOT touch the solver,
> grid, or `plume_length`. Edit the real files via bash/python. Compile-check every file.

### 1c. Test agent
> Verify (no full MODFLOW run needed): all touched files `py_compile`; the new builder produces a valid Bokeh
> figure on a synthetic `concentration` array (assert it has image renderers, a contour/line, and a HoverTool);
> the Ca/Cd split matches the backward transform (Ca nonzero where conc<C0, Cd where conc>C0); orientation correct
> (vertical depth-down); `result.plot_png` is still produced and the PDF path still uses it; `plume_length` and the
> returned raw `concentration` are unchanged. Run `pytest tests/test_numerical_models.py tests/test_model_equations.py
> tests/test_numerical_jobs.py -q` with `MF6_EXE=/nonexistent` so solver tests skip; expect the prior green result.
> Report PASS/FAIL with evidence.

### 1d. Debug agent (only if Test fails)
> Fix the specific failure the Test agent reported (e.g. Bokeh image dw/dh/extent wrong, flipped axis, missing
> HoverTool, panel pane type mismatch). Re-run the failing check until green. Touch only what's needed.

---

## TASK #2 — Fix the "Download PDF Report" button

### 2a. Planning agent
> Read-only. Trace the PDF report path and find what (if anything) broke after the 7-input migration.
> Two paths exist: (1) the panel `export_btn` (`pn.widgets.FileDownload`, callback `_pdf_callback`) which calls
> `CASTReport("…").generate(state["parameters"], state["outputs"], plot_data=…, plot_images=…)` where
> `state["parameters"]/["outputs"]/["plot_images"]` are built in `_render_completed_result`; and (2) the Flask route
> `numerical_job_report` in `numerical_routes.py` which builds a PDF from saved job meta + `result`. Check:
> does `CASTReport.generate` (`pdf_report.py`) accept the current `parameters`/`outputs` shapes; does the schema
> figure (`result.plot_png`) embed; is the 2-decimal `_fmt_value` applied; do the new analytical/Péclet/Courant rows
> render; is "the format it had before" preserved. Generate a sample PDF in `outputs/` and report whether it is valid
> and what looks wrong. Output a numbered plan with exact file:line fixes.

### 2b. Build agent
> Apply the approved fixes so the "Download PDF Report" button reliably produces a valid PDF in the prior format,
> using the new 7-input parameters plus the analytical `L_D`/width, `Péclet`, `Courant`, the numerical `Lmax`, and
> the schema `plot_png` figure, with 2-decimal formatting. Fix both the panel `_pdf_callback` path and the
> `numerical_job_report` route if needed. Edit real files via bash/python; compile-check.

### 2c. Test agent
> Generate a PDF via `CASTReport(...).generate(...)` with representative new-scheme `parameters`/`outputs`/
> `plot_images` (build a tiny synthetic `plot_png`); assert the returned bytes are a non-empty valid PDF
> (`%PDF` header, opens with pypdf/pdfplumber if available); render page 1 to a PNG and confirm it shows the
> parameter table, the results, and the figure. Confirm `_fmt_value` gives 2 decimals. Run the existing pdf/report
> tests if present. Report PASS/FAIL + the rendered page-1 image path.

### 2d. Debug agent (only if Test fails)
> Fix the specific PDF failure (e.g. a parameter dict key the report expects, an image-size/ReportLab flowable
> error, a None passed where a list is expected). Re-generate and re-render until the PDF is valid and complete.

---

## After both tasks
- Update `NUMERICAL_MODEL_TASKS.md` (mark #1/#2 done).
- Present rendered evidence (interactive figure screenshot/HTML, PDF page-1 image) for approval.
- Validate end-to-end in Docker (real Flask, not the dev reloader) — run a job, confirm interactivity + working PDF.

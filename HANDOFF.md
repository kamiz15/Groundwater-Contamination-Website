# Handoff — AEM/model UI upgrade + src2 port

Branch: `fix/horizontal-multiple-plume-graph`. Working tree has uncommitted changes (nothing committed by this session yet). Ponytail mode active throughout.

## Context
Task: bring the app up to date with the reference research code at `C:\Users\User\Desktop\src 2\src`, plus 3 personal UI additions, plus 4 follow-up fixes from a screenshot review.

Key finding: the app is already a near-complete port of src2. Only genuinely new deltas were ported (see below); desktop-only matplotlib/CLI tooling was intentionally NOT re-vendored (the browser designer already replaces it).

---

## DONE & verified (first wave — 4 Fable-5 agents, all green)

1. **Param notation (italic/lowercase/greek)** — numerical/analytical/empirical inputs.
   - New `param_meta.py` (`PARAM_META` name→{symbol,description}, `attach_meta()`), imported by `analytical_routes.py`, `empirical_routes.py`, `numerical_routes.py`.
   - `templates/model_input_form.html` macro `render_model_input` renders `field.symbol|safe` + the `?` tooltip.
   - Spec labels stripped of embedded plain symbols (78 labels) so notation shows once.
   - AEM templates hand-edited: `templates/aem_designer.html`, `templates/aem_inverse.html` (forward has no manual inputs).
2. **"?" hover tooltips** — CSS `.param-help` / `.param-help__tip` in `static/styles.css`; markup in the macro + AEM templates.
3. **AEM failure detail** — root cause was `aem_job_status` masking ALL worker errors. Now surfaces specific violated conditions. Changed: `aem_routes.py` (`_validated_config` collects all violations; `USER_FACING_ERROR` passthrough), `aem_jobs.py` (concrete reason + inputs), `static/aem.js` (pre-submit + α-ratio warning).
4. **src2 model-layer port** — `aem/at_config.py` (`from_dict` + `elem.index`), `aem/at_element.py` (`index`), NEW `aem/at_inverse_config.py` (`InverseConfiguration` + `DEFAULT_PARAM_SEARCH`), `aem/at_inverse_model.py` (additive inv_cfg entry point; public API `estimate_parameter_scanned`/`compute_lmax` UNCHANGED). `at_simulation.py` / `mathieu_functions_OG.py` untouched (byte-identical to reference — keep it that way).

Tests at that point: `tests/test_aem_flow.py` 45 passed; `test_route_smoke.py` + `test_numerical_multiple_graphs.py` 71 passed.

---

## DONE & verified (second wave — 2 Sonnet-5 agents, all green)

**Agent A** (`static/aem.js`, `templates/aem_designer.html`, `aem_routes.py`):
- Fix 1 ✅ **L_max line** in `renderField()` — now matches the reference exactly: **full-height** navy dashed `axvline` at `xPix(result.L_max)` + an upper-right legend box. (An earlier attempt to shorten it to the plume's donor extent looked disconnected and was reverted.) NOTE: the reference computes `L_max = nose_grid_index × dom_inc` (measured from the domain's left edge `dom_xmin`, not from x=0), so the line sits ~|dom_xmin| to the right of the visible nose — this offset exists in the reference too. If it ever looks too far right, compare our `dom_xmin` (client `referenceConfig`: `min(xs) − maxHW − 2`) vs the reference designer's.
- Fix 2 ✅ **View button removed** — markup + `"v"` keybind + `toggleView` (now dead) + click listener + Clear-all `viewBtn` reset all removed. `fullView`/its `draw()` usages left intact (still live). Zero `aem-view` refs remain.
- Fix 4 ✅ **honest water-table message + dashed y=−0.1 clearance guide** (vertical only), client (aem.js) + server (aem_routes.py) messages match; `−0.1` rule NOT relaxed.

**Agent B** (`templates/base.html`, `static/styles.css`):
- Fix 3 ✅ cache-bust bumped `?v=20260625a` → `?v=20260706a`. ALSO fixed a real clipping bug: `.param-help__tip` was `left:50%; translateX(-50%)`, which overflowed the `overflow-x:hidden` sidebar and was clipped even when revealed → changed to `left:0`. Verified live via preview tools (`visibility:hidden` at rest; no clipping either column).

Final verification (this session): `node --check static/aem.js` clean; `py_compile` clean on all touched py; `pytest tests/test_aem_flow.py -q` → **45 passed**.

---

## REMAINING TODO (not started)

1. **Fill tooltip descriptions** — the **AEM designer** tooltips are now REAL text (copied verbatim from `source_designer.py` MODEL_FIELDS/COMP_FIELDS). Still placeholders `[TODO: describe <name>]`: the numerical/analytical/empirical forms (`param_meta.py`) and `aem_inverse.html`. User to provide real text for those. See memory `param-notation-tooltips.md`.

### Numerical inputs: analytical column → derivation box, then 4 semantic groups (done)
- Removed the read-only **Analytical** column (Domain Length/Width) from `model_input_form.html`.
- Added an **"Domain from the analytical model"** box under the Conceptual Model (`model_page_base.html`, shown when `analytical_fields` is defined): lists the auto-computed values + a per-model `{% block analytical_explanation %}` (Cirpka 2005 for horizontal, Liedl-type vertical formula). Text in `panel_numerical_horizontal_single.html` / `panel_numerical_vertical_single.html`. CSS `.analytical-derivation`. `_numerical_analytical_fields` still computes values (unchanged).
- **Notation fixes (numerical params only)** in `param_meta.py` + `numerical_routes.py`: `hk` *k*→**K**; `grid_size` d*x*=d*y*→**Δ*x*=Δ*y*** (Grid Size→Grid Spacing); `source_thickness` *w*_s→**W_s** (Source Thickness→**Source Width** — it's the source width Sw); `at` α_T→**α_Th** (→Horizontal Transverse Dispersivity); `Lz` *l*_z→**M** (matches vertical Liedl formula). All are numerical-exclusive keys — analytical/empirical untouched. Those models still use the earlier all-lowercase symbols (e.g. aquifer thickness `M`→*m*); a full app-wide correct-notation pass is NOT done — offer it if the user wants consistency across analytical/empirical too.
- Then grouped the editable inputs into **4 semantic groups** via `NUMERICAL_FIELD_COLUMN` (numerical_routes.py): `chemical` (γ,c_D,c_A), `physical` (source thickness/Lz, α_L, α_T/α_Tv), `standard` (porosity, K, gradient = flow/hydraulic), `numerical` (grid spacing). The user's "analytical" group was really **numerical/discretisation** (grid spacing isn't chemical/physical/flow). Rendered as 4 cards in 2 stacked columns via `render_input_group` macro + `.model-input-groups-2col`/`.model-input-col` CSS. Any unmapped field defaults to `physical` (was `input`).

### Designer-parity pass (done this session, matches reference `source_designer.py`)
- Settings split into **Model parameters** (αL, αT, cA, γ, Ws) + **Computational parameters** (Δ, Control points, Expansion terms, Plot aspect), Ws back in the model group; descriptive labels ("Long. dispersivity αL" etc.).
- Help badge is now a **filled blue "i"** (`.param-help` in styles.css, `--brand-500`) app-wide; glyph switched `?`→`i` in the macro + `aem_inverse.html` too for consistency.
- **Index # (i)** toggle button + `i` shortcut → `drawIndices()` numbers each element (allElementDicts order; ponytail: not the reference's spatial reindex).
- Numeric per-element edit fields were added then **removed** at user request (rendered full-width/broken under the canvas). Selection editing stays keyboard/drag only. If re-added, put them compact IN the sidebar, not `.aem-designer-panel`.
- Removed the dashed y=−0.1 clearance line (kept the honest water-table message + the −0.1 rule).
- **Sidebar width fix:** the descriptive labels overflowed the 2-col grid → clipped right column + scrollbar. Designer field grid is now **single column, label stacked above input** (`.aem-designer-form .aem-field-grid`, styles.css ~L1744).
- CSS cache token now `?v=20260706c`.
2. **Confirm the "full port of everything new" scope** — user chose full port. I ported all functional deltas but SKIPPED desktop-only files (`source_designer.py` matplotlib UI, `designer_solver.py` multiprocessing/zip, `main.py`, `generate_configs.py`, `run_tests.py`) as inapplicable to Flask. If the user actually wants those vendored, that's outstanding.
3. **Lowercase-symbol judgment call** — I lowercased conventionally-uppercase symbols (M→*m*, K→*k*, D→*d*) per the user's "all lowercase" instruction. Some hydrogeology texts keep these capital. Per-symbol revert is a one-line edit each in `param_meta.py` if the user disagrees.
4. **Manual visual QA** — tooltip hover behavior verified live by Agent B. Still unrendered end-to-end: the notation on a numerical/analytical form, and the **L_max line on a real forward run**. Recommend one analytical page + the AEM designer + a forward-sim graph. NOTE: browser must hard-refresh (or the new `?v=20260706a` handles it) to drop the stale cached CSS that caused the always-on-tooltip bug.
5. **Verify L_max line placement physics** — L_max is plume length from the source (≈x=0). Confirm on a real forward run the dashed line lands at the visible plume tip; if L_max is measured from a source offset, adjust the x anchor in `renderField()`.
6. **Commit** — nothing committed this session; user hasn't asked to commit. Group logically when they do.

## Landmines / do-not-touch
- `aem/at_simulation.py`, `aem/mathieu_functions_OG.py`: keep byte-identical to src2 (only vendoring import diffs).
- `aem_jobs.py` imports `inv.estimate_parameter_scanned`, `compute_lmax` — keep those signatures.
- `numerical_routes.py` ~L305-307 derives display name/unit from `field["label"]` via `.split(" [")` — label edits must keep the `[unit]` bracket.
- The −0.1 water-table threshold is a real solver requirement (reference `designer_model.validate_for_export`), not a bug.
- Import-path convention in `aem/`: package-relative (`from .at_x import`), NOT the bare imports the standalone src2 uses.

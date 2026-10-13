"""AEM (Analytic Element Method) transport simulation package.

Vendored from the upstream src/ tree for use inside the PACS Flask/Panel app.
The upstream tree is a flat module directory; here it is a real package, so the
only edit applied to a vendored file is turning its intra-package imports
relative (``from .at_element import ...``).

Provenance
----------
Synced from AEM_Transport_AK @ db41cc3 (2026-10-05), taken from the upstream
``aem_update_db41cc3`` drop, whose files already carry the relative-import edit.
Verified at that sync: the five changed files are byte-identical to the drop's
``aem/`` copies (``at_grid_export`` and ``at_inverse_config`` were already
identical), so there are NO local edits to the vendored files. When the next
drop lands, diff against that baseline first — any difference is either a new
upstream change or an undocumented local edit, and both need a decision rather
than a merge.

Consequence of taking the drop as-is: ``conc_array`` builds its axes with
``arange(dom_min, dom_max + inc, inc)``, so a vertical grid's top row stops
short of z = 0 when ``dom_ymin`` is not a multiple of ``dom_inc`` (the designer
snaps its bounds, so only imported/custom bounds and the bundled samples hit
this). ``static/aem.js`` pins the plotted z-axis to 0 for vertical runs. A
local fix that anchored the axes at multiples of ``inc`` was dropped here; it is
in git history (``56ad9ac``) if it should come back.

Only 7 of upstream's 17 modules are vendored. Deliberately absent, because the
web layer replaces them: ``source_designer`` / ``designer_model`` /
``designer_solver`` (superseded by the native designer, ``aem_routes.py`` and
``aem_source_geometry.py``), ``main`` (Flask is the entrypoint),
``generate_configs`` / ``run_tests`` / ``train_xmax_from_runs`` (batch research
harness), ``xmax_features`` / ``xmax_predictor`` (needs scikit-learn + joblib,
and upstream ships no trained model — only a dataset to fit from), and
``at_element_OG`` (dead upstream too).

One consequence worth knowing: ``ATConfiguration.use_xmax_predictor`` is parsed
but **inert here**. Upstream's only reader is ``main.py``, which is not
vendored. The field is kept so at_config stays a clean copy of upstream; setting
it does nothing until ``xmax_predictor`` is vendored too. It is a latency
optimisation only — the domain-extension loop in ``ATSimulation.run()``, not the
predictor, is what guarantees the plume is never truncated.

Modules and the public surface the app uses:

- ``aem.at_config`` — ``ATConfiguration`` (adds the grid-export knobs
  ``concentration_output`` / ``export_step`` / ``export_path`` /
  ``export_npz_float32``, plus ``show_plots``, ``dynamic_domain``,
  ``use_xmax_predictor``, ``allow_decoupling``, ``probe_points``)
- ``aem.at_element`` — ``ATElement``, ``ATElementType``
- ``aem.at_grid_export`` — ``GRID_COLUMNS`` and the free functions
  ``grid_csv_bytes`` / ``grid_npz_bytes`` / ``write_grid_csv`` /
  ``write_grid_npz``; use these when only the arrays are at hand (e.g. past the
  job-queue pickle boundary, where no live ATSimulation survives)
- ``aem.at_simulation`` — ``ATSimulation`` (``run``, ``grid_csv_bytes``,
  ``grid_npz_bytes``, ``probe_concentration``, ``generate_run_label``),
  ``create_mirrored_element``. In vertical orientation each source is paired
  with its mirror image and nothing else: upstream deleted
  ``create_zero_isoline`` (it was commented out before). Bringing it back
  changes solved concentrations — measured at an earlier sync, a single source
  moved L_max 58 -> 55 m. Pinned by
  ``tests/test_aem_flow.py::test_vertical_assembly_adds_mirror_images_and_no_zero_isoline``.
  ``sim.L_max`` is an x position (``dom_xmin`` + the contour's grid offset;
  it used to be a distance from the grid's left edge) truncated to a whole meter
  by ``int()``. That is upstream's definition and is left alone, but the app
  reports the exact tip instead (``aem_jobs.plume_tip_x``), because the
  truncation puts the plot's L_max marker up to 1 m short of the contour.
  An element whose Mathieu ``q``
  exceeds 200 makes ``run()`` raise ``ValueError``; ``aem_jobs`` rewrites that
  for the user (``SOURCE_TOO_LARGE_ERROR``).
- ``aem.at_inverse_config`` — ``InverseConfiguration``, ``DEFAULT_PARAM_SEARCH``
  (the solver constants that used to live in ``at_inverse_model``)
- ``aem.at_inverse_model`` — ``estimate_parameter_scanned``,
  ``compute_lmax_general``, ``process_input_file_with_logging``
- ``aem.mathieu_functions_OG`` — ``Mathieu`` special functions

Heavy work (multiprocessing Pool, matplotlib rendering) only runs when
ATSimulation.run() is called, never at import time.
"""

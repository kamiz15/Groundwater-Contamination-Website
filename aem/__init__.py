"""AEM (Analytic Element Method) transport simulation package.

Vendored from the upstream src/ tree for use inside the CAST Flask/Panel app.
The upstream tree is a flat module directory; here it is a real package, so the
only edit applied to a vendored file is turning its intra-package imports
relative (``from .at_element import ...``).

Provenance
----------
Synced from AEM_Transport_AK-main (Köhler et al. 2026 drop, reviewed 2026-08-06).
Verified at that sync: every vendored file below is identical to its upstream
``src/`` counterpart except for the relative-import lines. Nothing else. When
the next drop lands, diff against that baseline first — a difference that is not
an import line is either a new upstream change or an undocumented local edit,
and both need a decision rather than a merge.

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
  with its mirror image and nothing else: ``create_zero_isoline`` is still
  defined but its call sites are commented out, matching upstream. (The
  ``zero_``-prefixed branches further down the module are consequently dead;
  they are kept because upstream keeps them.) Re-enabling it changes solved
  concentrations — measured at this sync, a single source moved L_max 58 -> 55 m
  — and the upstream append also sat outside the loop, so it only ever added an
  isoline for the *last* source. Pinned by
  ``tests/test_aem_flow.py::test_vertical_assembly_adds_mirror_images_and_no_zero_isoline``.
- ``aem.at_inverse_config`` — ``InverseConfiguration``, ``DEFAULT_PARAM_SEARCH``
  (the solver constants that used to live in ``at_inverse_model``)
- ``aem.at_inverse_model`` — ``estimate_parameter_scanned``,
  ``compute_lmax_general``, ``process_input_file_with_logging``
- ``aem.mathieu_functions_OG`` — ``Mathieu`` special functions

Heavy work (multiprocessing Pool, matplotlib rendering) only runs when
ATSimulation.run() is called, never at import time.
"""

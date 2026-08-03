"""AEM (Analytic Element Method) transport simulation package.

Vendored from the upstream src/ tree for use inside the CAST Flask/Panel app.
The upstream tree is a flat module directory; here it is a real package, so the
only edit applied to a vendored file is turning its intra-package imports
relative (``from .at_element import ...``).

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
  ``create_mirrored_element``
- ``aem.at_inverse_config`` — ``InverseConfiguration``, ``DEFAULT_PARAM_SEARCH``
  (the solver constants that used to live in ``at_inverse_model``)
- ``aem.at_inverse_model`` — ``estimate_parameter_scanned``,
  ``compute_lmax_general``, ``process_input_file_with_logging``
- ``aem.mathieu_functions_OG`` — ``Mathieu`` special functions

Heavy work (multiprocessing Pool, matplotlib rendering) only runs when
ATSimulation.run() is called, never at import time.
"""

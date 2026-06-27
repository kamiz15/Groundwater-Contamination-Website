"""AEM (Analytic Element Method) transport simulation package.

Vendored from the upstream src/ tree for use inside the CAST Flask/Panel app.
Public entry points used by the app:
- ATConfiguration (aem.at_config)
- ATElement, ATElementType (aem.at_element)
- ATSimulation, create_mirrored_element (aem.at_simulation)
- process_input_file_with_logging (aem.at_inverse_model)

Heavy work (multiprocessing Pool, matplotlib rendering) only runs when
ATSimulation.run() is called, never at import time.
"""

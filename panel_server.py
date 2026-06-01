# panel_server.py
import logging
import os

import panel as pn

from settings import PANEL_ALLOW_ORIGINS, PANEL_HOST, PANEL_PORT, PANEL_SERVE_PREFIX

from panel_liedl_single import liedl_single_app
from panel_liedl_multiple import liedl_multiple_app
from panel_liedl3d_single import liedl3d_single_app
from panel_liedl3d_multiple import liedl3d_multiple_app

from panel_chu import chu_single_app, chu_multiple_app

from panel_ham_single import ham_single_app
from panel_ham_multiple import ham_multiple_app

from bioscreen_panel import bioscreen_single_app, bioscreen_multiple_app

from panel_maier_single import maier_single_app
from panel_maier_multiple import maier_multiple_app
from panel_birla_single import birla_single_app
from panel_birla_multiple import birla_multiple_app
from panel_numerical_horizontal_single import numerical_horizontal_single_app
from panel_numerical_horizontal_multiple import numerical_horizontal_multiple_app
from panel_numerical_vertical_single import numerical_vertical_single_app
from panel_numerical_vertical_multiple import numerical_vertical_multiple_app
from panel_cirpka_single import cirpka_single_app
from panel_cirpka_multiple import cirpka_multiple_app
from panel_source_geometry import source_geometry_app
from panel_source_inversion import source_inversion_app


pn.extension("tabulator")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

# IMPORTANT:
# "" maps to "/" (root). This avoids Panel trying to render its index template.
apps = {
    "": liedl_single_app,  # <-- visiting http://localhost:5007/ opens Liedl single

    "panel_liedl_single": liedl_single_app,
    "panel_liedl_multiple": liedl_multiple_app,
    "panel_liedl3d_single": liedl3d_single_app,
    "panel_liedl3d_multiple": liedl3d_multiple_app,

    "panel_chu_single": chu_single_app,
    "panel_chu_multiple": chu_multiple_app,

    "panel_ham_single": ham_single_app,
    "panel_ham_multiple": ham_multiple_app,


    "panel_bioscreen_single": bioscreen_single_app,
    "panel_bioscreen_multiple": bioscreen_multiple_app,

    "panel_maier_single": maier_single_app,
    "panel_maier_multiple": maier_multiple_app,
    "panel_birla_single": birla_single_app,
    "panel_birla_multiple": birla_multiple_app,
    "panel_numerical_horizontal_single": numerical_horizontal_single_app,
    "panel_numerical_horizontal_multiple": numerical_horizontal_multiple_app,
    "panel_numerical_vertical_single": numerical_vertical_single_app,
    "panel_numerical_vertical_multiple": numerical_vertical_multiple_app,
    "panel_cirpka_single": cirpka_single_app,
    "panel_cirpka_single_output": cirpka_single_app,
    "panel_cirpka_multiple": cirpka_multiple_app,
    "panel_source_geometry": source_geometry_app,
    "panel_source_inversion": source_inversion_app,
}

if __name__ == "__main__":
    pn.serve(
        apps,
        port=PANEL_PORT,
        address=PANEL_HOST,
        show=False,

        # Allow websocket origins for either local development or the public proxy.
        websocket_origin=PANEL_ALLOW_ORIGINS,

        # Keep Bokeh resources and websocket endpoints under the public proxy path.
        prefix=PANEL_SERVE_PREFIX,
        root_path=PANEL_SERVE_PREFIX or None,

        # reduce token expiry annoyance
        session_token_expiration=60 * 60,  # 1 hour
    )

    print(f"Panel running at http://{PANEL_HOST}:{PANEL_PORT}{PANEL_SERVE_PREFIX}/")
    print("Apps:")
    print("  /  (Liedl single)")
    for k in apps:
        if k != "":
            print(f"  /{k}")

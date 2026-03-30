# panel_server.py
import panel as pn

from settings import PANEL_ALLOW_ORIGINS, PANEL_HOST, PANEL_PORT

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
from panel_numerical_single import numerical_single_app
from panel_numerical_multiple import numerical_multiple_app


pn.extension("tabulator")

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
    "panel_numerical_single": numerical_single_app,
    "panel_numerical_multiple": numerical_multiple_app,

}

if __name__ == "__main__":
    pn.serve(
        apps,
        port=PANEL_PORT,
        address=PANEL_HOST,
        show=False,

        # allow websockets from both Panel and Flask ports
        allow_websocket_origin=PANEL_ALLOW_ORIGINS,

        # reduce token expiry annoyance
        session_token_expiration=60 * 60,  # 1 hour
    )

    print(f"Panel running at http://{PANEL_HOST}:{PANEL_PORT}/")
    print("Apps:")
    print("  /  (Liedl single)")
    for k in apps:
        if k != "":
            print(f"  /{k}")

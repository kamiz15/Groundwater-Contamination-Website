# panel_server.py
import panel as pn

from panel_liedl_single import liedl_single_app
from panel_liedl_multiple import liedl_multiple_app

from panel_chu import chu_single_app, chu_multiple_app

from panel_ham_single import ham_single_app
from panel_ham_multiple import ham_multiple_app

from bioscreen_panel import bioscreen_single_app, bioscreen_multiple_app

from panel_maier_single import maier_single_app
from panel_maier_multiple import maier_multiple_app
from panel_birla_single import birla_single_app
from panel_birla_multiple import birla_multiple_app


pn.extension("tabulator")

# IMPORTANT:
# "" maps to "/" (root). This avoids Panel trying to render its index template.
apps = {
    "": liedl_single_app,  # <-- visiting http://localhost:5007/ opens Liedl single

    "panel_liedl_single": liedl_single_app,
    "panel_liedl_multiple": liedl_multiple_app,

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

}

if __name__ == "__main__":
    pn.serve(
        apps,
        port=5007,
        address="localhost",
        show=False,

        # allow websockets from both Panel and Flask ports
        allow_websocket_origin=[
            "localhost:5007",
            "127.0.0.1:5007",
            "localhost:5000",
            "127.0.0.1:5000",
        ],

        # reduce token expiry annoyance
        session_token_expiration=60 * 60,  # 1 hour
    )

    print("Panel running at http://localhost:5007/")
    print("Apps:")
    print("  /  (Liedl single)")
    for k in apps:
        if k != "":
            print(f"  /{k}")

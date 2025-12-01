# panel_server.py
import panel as pn
from bokeh.server.server import Server

# --- IMPORT PANEL PYTHON APPS ---
from panel_liedl_single import liedl_single_app
from panel_liedl_multiple import liedl_multiple_app
from panel_chu import chu_single_app, chu_multiple_app   # <-- CORRECT
from panel_ham_single import ham_single_app
from panel_ham_multiple import ham_multiple_app

pn.extension()


# ---- REQUIRED WRAPPER FUNCTIONS (func(doc)) ----
def make_liedl_single(doc):
    pn.panel(liedl_single_app()).server_doc(doc)

def make_liedl_multiple(doc):
    pn.panel(liedl_multiple_app()).server_doc(doc)

def make_chu_single(doc):
    pn.panel(chu_single_app()).server_doc(doc)

def make_chu_multiple(doc):
    pn.panel(chu_multiple_app()).server_doc(doc)

def make_ham_single(doc):
    pn.panel(ham_single_app()).server_doc(doc)

def make_ham_multiple(doc):
    pn.panel(ham_multiple_app()).server_doc(doc)


# ---- START SERVER ----
def main():
    server = Server(
        {
            "/panel_liedl_single": make_liedl_single,
            "/panel_liedl_multiple": make_liedl_multiple,
            "/panel_chu_single": make_chu_single,
            "/panel_chu_multiple": make_chu_multiple,
            "/panel_ham_single": make_ham_single,
            "/panel_ham_multiple": make_ham_multiple,
        },
        port=5007,
        allow_websocket_origin=[
            "localhost:5000",
            "127.0.0.1:5000",
            "localhost:5007",
            "127.0.0.1:5007",
        ],
        num_procs=1,
    )

    server.start()
    print("Panel apps running at http://localhost:5007")
    server.io_loop.start()


if __name__ == "__main__":
    main()

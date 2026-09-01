from __future__ import annotations

import html
import re
import unittest
from contextlib import ExitStack
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import analytical_routes
import app as app_module
import empirical_routes
import numerical_routes


MULTIPLE_WRAPPERS = [
    "/liedl/multiple",
    "/chu/multiple",
    "/ham/multiple",
    "/bioscreen/multiple",
    "/liedl3d/multiple",
    "/cirpka/multiple",
    "/empirical/maier/multiple",
    "/empirical/birla/multiple",
    "/numerical/horizontal/multiple",
    "/numerical/vertical/multiple",
]

SINGLE_WRAPPERS = [
    "/liedl/single",
    "/empirical/maier/single",
    "/numerical/horizontal/single",
]


def _iframe_src(response) -> str:
    page = response.get_data(as_text=True)
    return html.unescape(re.search(r'<iframe\b[^>]*\bsrc="([^"]+)"', page).group(1))


class MultipleWrapperTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True, LOGIN_DISABLED=True)
        self.client = app_module.app.test_client()
        self.patches = ExitStack()
        for module in (analytical_routes, empirical_routes, numerical_routes):
            self.patches.enter_context(patch.object(module, "_current_email", return_value="user@example.com"))
            self.patches.enter_context(patch.object(module, "get_user_sites_rows", return_value=[]))

    def tearDown(self):
        self.patches.close()
        app_module.app.config["LOGIN_DISABLED"] = False

    def test_multiple_wrapper_iframes_do_not_force_output_only(self):
        for path in MULTIPLE_WRAPPERS:
            with self.subTest(path=path):
                response = self.client.get(f"{path}?output_only=1")
                iframe_src = _iframe_src(response)
                iframe_query = parse_qs(urlparse(iframe_src).query)

                self.assertEqual(response.status_code, 200)
                self.assertNotIn("output_only", iframe_query)

    def test_single_wrapper_iframes_keep_output_only(self):
        for path in SINGLE_WRAPPERS:
            with self.subTest(path=path):
                response = self.client.get(path)
                iframe_src = _iframe_src(response)
                iframe_query = parse_qs(urlparse(iframe_src).query)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(iframe_query["output_only"], ["1"])


class StageLayoutTests(unittest.TestCase):
    """Analytical / empirical multiples: the single-simulation shell - a sidebar
    carrying the site picker, and the Panel frame carrying graph and table."""

    SITE = {
        "id": 1, "display_id": 1, "site_unit": "Borden", "compound": "Benzene",
        "aquifer_thickness": 2.0, "plume_length": 120.0, "electron_donor": 5.0,
        "electron_acceptor_o2": 8.0, "alpha_tv": 0.001, "gamma": 3.5, "extra_data": {},
    }

    def setUp(self):
        app_module.app.config.update(TESTING=True, LOGIN_DISABLED=True)
        self.client = app_module.app.test_client()
        self.patches = ExitStack()
        for module in (analytical_routes, empirical_routes, numerical_routes):
            self.patches.enter_context(patch.object(module, "_current_email", return_value="user@example.com"))
            self.patches.enter_context(patch.object(module, "get_user_sites_rows", return_value=[self.SITE]))

    def tearDown(self):
        self.patches.close()
        app_module.app.config["LOGIN_DISABLED"] = False

    ANALYTICAL = [p for p in MULTIPLE_WRAPPERS if not p.startswith("/numerical/")]

    def test_every_multiple_page_is_one_full_width_frame(self):
        """No sidebar on any of them: the picker, the graph, the toolbar and the
        scenario table are all in the Panel document, so the page is one frame
        with the report card under it."""
        for path in MULTIPLE_WRAPPERS:
            with self.subTest(path=path):
                page = self.client.get(path).get_data(as_text=True)

                self.assertIn("model-workbench-layout--full", page)
                self.assertNotIn("model-workbench-sidebar", page)
                self.assertNotIn('id="compare_sites"', page)   # it is in the frame
                self.assertNotIn("model-input-form", page)      # replaced by the picker
                self.assertIn('data-min-height="800"', page)
                self.assertIn("clipboard-write", page)          # Copy needs it

    def test_every_multiple_page_carries_the_add_row_dialog(self):
        """The dialog belongs to the page: one built inside the Panel frame could
        only ever cover the frame. Its fields come from the model's own spec."""
        for path in self.ANALYTICAL:
            with self.subTest(path=path):
                page = self.client.get(path).get_data(as_text=True)

                self.assertIn('id="scenarioDialog"', page)
                self.assertIn('id="scenarioForm"', page)
                self.assertIn('id="scenario_measured"', page)
                self.assertIn("scenario-dialog-field", page)    # at least one parameter

    def test_the_report_card_sits_under_the_frame(self):
        """With no sidebar it has nowhere else to go, and it belongs under the
        run it exports anyway."""
        page = self.client.get("/chu/multiple").get_data(as_text=True)

        self.assertIn("report", page.lower())
        self.assertLess(page.index("<iframe"), page.lower().index("report export"))

    def test_numerical_multiples_get_the_same_page(self):
        """One layout across all ten - the numerical pair included."""
        page = self.client.get("/numerical/vertical/multiple").get_data(as_text=True)

        self.assertIn("model-workbench-layout--full", page)
        self.assertNotIn("model-workbench-sidebar", page)
        self.assertIn('id="scenarioDialog"', page)      # its Add-row dialog too


if __name__ == "__main__":
    unittest.main()

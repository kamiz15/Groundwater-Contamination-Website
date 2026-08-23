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
    """Analytical / empirical multiples: no sidebar - graph, then the Panel card."""

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

    def test_no_sidebar_survives_on_the_multiple_pages(self):
        """Every input lives on the Panel card under the graph now."""
        for path in self.ANALYTICAL:
            with self.subTest(path=path):
                page = self.client.get(path).get_data(as_text=True)

                self.assertNotIn("model-workbench-sidebar", page)
                self.assertNotIn('name="compare_sites"', page)   # picker moved into the Panel
                self.assertNotIn("Update Graph", page)
                self.assertNotIn("runScenariosBtn", page)        # the button moved too
                self.assertNotIn("model-input-form", page)
                self.assertIn("model-workbench-layout--full", page)

    def test_the_report_card_follows_the_graph(self):
        """It was in the sidebar; without one it belongs under the run it exports."""
        page = self.client.get("/chu/multiple").get_data(as_text=True)

        self.assertIn("report", page.lower())
        self.assertLess(page.index("Simulation Panel"), page.lower().index("report export"))

    def test_numerical_multiples_keep_their_sidebar(self):
        """Their run trigger is the sidebar picker's submit, so it stays."""
        page = self.client.get("/numerical/vertical/multiple").get_data(as_text=True)

        self.assertIn("model-workbench-sidebar", page)
        self.assertIn('name="compare_sites"', page)
        self.assertNotIn("model-workbench-layout--full", page)


if __name__ == "__main__":
    unittest.main()

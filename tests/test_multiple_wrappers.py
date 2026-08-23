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


class MultipleStageLayoutTests(MultipleWrapperTests):
    """Graph on top of the stage, the manual input form directly under it."""

    ANALYTICAL = [p for p in MULTIPLE_WRAPPERS if not p.startswith("/numerical/")]

    def test_input_form_sits_under_the_graph_in_the_stage(self):
        for path in self.ANALYTICAL:
            with self.subTest(path=path):
                page = self.client.get(path).get_data(as_text=True)

                self.assertIn('id="model-input-form"', page)
                self.assertIn("model-workbench-stage--multiple", page)
                # Graph first, form under it - the stage order in the diagram.
                self.assertLess(page.index("Simulation Panel"), page.index('id="model-input-form"'))

    def test_numerical_multiples_keep_their_own_stage(self):
        """They pass no input_fields, so the form must not appear there."""
        for path in ["/numerical/horizontal/multiple", "/numerical/vertical/multiple"]:
            with self.subTest(path=path):
                page = self.client.get(path).get_data(as_text=True)
                self.assertNotIn("model-input-form", page)

    def test_running_the_model_keeps_the_picked_sites(self):
        """Both forms carry each other's state, or one submit wipes the other."""
        sites = [{"id": 1, "site_unit": "Borden", "compound": "BTEX", "display_id": 1},
                 {"id": 2, "site_unit": "Vejen", "compound": "BTEX", "display_id": 2}]
        with patch.object(analytical_routes, "get_user_sites_rows", return_value=sites), \
             patch.object(analytical_routes, "filter_valid_sites_for_model",
                          side_effect=lambda rows, _model: (rows, {})):
            page = self.client.get("/liedl/multiple?compare_sites=2").get_data(as_text=True)

        form = page[page.index('id="model-input-form"'):]
        self.assertIn('name="compare_sites" value="2"', form)
        # ...and the sidebar's picker carries the model's parameters back.
        sidebar = page[:page.index('id="model-input-form"')]
        self.assertIn('name="alpha_Tv"', sidebar)


if __name__ == "__main__":
    unittest.main()

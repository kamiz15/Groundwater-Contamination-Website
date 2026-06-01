from __future__ import annotations

import re
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import app as app_module
import plot_functions
import site_routes


VISUALISATION_ROUTES = ["/plot_bar", "/plot_box", "/plot_hist"]
REMOVED_PLACEHOLDER_ROUTES = [
    "/plots/",
    "/plots/bar",
    "/plots/box",
    "/plots/hist",
    "/plots/scatter",
    "/plots/stats",
]


class VisualisationRouteTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True, LOGIN_DISABLED=True)
        self.client = app_module.app.test_client()
        self.patches = ExitStack()
        self.patches.enter_context(patch.object(site_routes, "_current_email", return_value="user@example.com"))
        self.patches.enter_context(patch.object(site_routes, "get_user_sites", return_value=[]))
        plot_functions._REF_DF = None

    def tearDown(self):
        self.patches.close()
        app_module.app.config["LOGIN_DISABLED"] = False
        plot_functions._REF_DF = None

    def test_visualisation_menu_contains_only_working_routes(self):
        response = self.client.get("/plot_bar")
        page = response.get_data(as_text=True)
        menu = re.search(
            r"Analysis Visualisation.*?<ul class=\"dropdown\">(.*?)</ul>",
            page,
            flags=re.DOTALL,
        ).group(1)
        hrefs = re.findall(r'href="([^"]+)"', menu)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(hrefs, VISUALISATION_ROUTES)
        self.assertNotIn("#", hrefs)

    def test_remaining_routes_render_bokeh_without_reference_csv(self):
        with patch.object(plot_functions.Path, "exists", return_value=False):
            for path in VISUALISATION_ROUTES:
                with self.subTest(path=path):
                    response = self.client.get(path)
                    page = response.get_data(as_text=True)

                    self.assertEqual(response.status_code, 200)
                    self.assertIn('src="/static/extensions/panel/', page)
                    self.assertIn("cdn.bokeh.org/bokeh/release/bokeh-", page)
                    self.assertIn("Bokeh.embed.embed_items", page)
                    self.assertIn("No data available", page)
                    self.assertIn('class="card-like analysis-plot-shell bokeh-output"', page)
                    self.assertIn('"sizing_mode":"stretch_width"', page)

    def test_placeholder_plot_blueprint_routes_are_removed(self):
        for path in REMOVED_PLACEHOLDER_ROUTES:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)


if __name__ == "__main__":
    unittest.main()

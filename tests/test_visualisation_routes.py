from __future__ import annotations

import re
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import app as app_module
import plot_functions
import site_routes


LEGACY_PLOT_ROUTES = ["/plot_bar", "/plot_box", "/plot_hist"]
DATABASE_VISUALISATION_ROUTES = ["/data_analysis"]
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
        self.get_rows = self.patches.enter_context(patch.object(site_routes, "get_user_sites_rows", return_value=[]))
        plot_functions._REF_DF = None

    def tearDown(self):
        self.patches.close()
        app_module.app.config["LOGIN_DISABLED"] = False
        plot_functions._REF_DF = None

    def test_database_page_links_to_visualisation_routes(self):
        response = self.client.get("/sites")
        page = response.get_data(as_text=True)
        actions = re.search(
            r"<h3>Visual Analysis</h3>.*?<div class=\"model-actions\">(.*?)</div>",
            page,
            flags=re.DOTALL,
        ).group(1)
        hrefs = re.findall(r'href="([^"]+)"', actions)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(hrefs, DATABASE_VISUALISATION_ROUTES)
        self.assertIn('class="primary-btn" href="/data_analysis"', actions)
        self.assertNotIn("#", hrefs)

    def test_database_page_hides_legacy_filter_and_sort_tools(self):
        self.get_rows.return_value = [{"id": 1, "site_unit": "A", "compound": "B", "extra_data": {}}]
        response = self.client.get("/sites")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Clear Database", page)
        self.assertNotIn("Filter Columns", page)
        self.assertNotIn("Sort Rows", page)
        self.assertNotIn("Apply Filters", page)

    def test_remaining_routes_render_bokeh_without_reference_csv(self):
        with patch.object(plot_functions.Path, "exists", return_value=False):
            for path in LEGACY_PLOT_ROUTES:
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

    def test_data_analysis_wrapper_renders_panel_iframe(self):
        response = self.client.get("/data_analysis")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("/panel_data_analysis", page)
        self.assertIn('class="panel-frame output-panel-frame data-analysis-frame"', page)

    def test_data_analysis_wrapper_passes_an_owned_completed_aem_job(self):
        meta = {"email": "user@example.com", "kind": "aem_forward"}
        with (
            patch.object(site_routes, "load_job_meta", return_value=meta),
            patch.object(site_routes, "job_status", return_value={"status": "done"}),
        ):
            response = self.client.get("/data_analysis?aem_job=job-1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("/panel_data_analysis?aem_job=job-1", response.get_data(as_text=True))

    def test_data_analysis_wrapper_rejects_another_users_aem_job(self):
        meta = {"email": "other@example.com", "kind": "aem_forward"}
        with patch.object(site_routes, "load_job_meta", return_value=meta):
            response = self.client.get("/data_analysis?aem_job=job-1")

        self.assertEqual(response.status_code, 404)

    def test_placeholder_plot_blueprint_routes_are_removed(self):
        for path in REMOVED_PLACEHOLDER_ROUTES:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)


if __name__ == "__main__":
    unittest.main()

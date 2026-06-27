from __future__ import annotations

import html
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
    return html.unescape(page.split('iframe src="', 1)[1].split('"', 1)[0])


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


if __name__ == "__main__":
    unittest.main()

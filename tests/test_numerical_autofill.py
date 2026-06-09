from __future__ import annotations

import unittest
from unittest.mock import patch

import numerical_routes
from symbol_registry import db_hydraulic_conductivity_to_numerical_hk


class NumericalAutofillTests(unittest.TestCase):
    def test_db_k_m_per_s_maps_to_numerical_hk_m_per_day(self):
        site = {"id": 42, "hydraulic_conductivity": 0.001}

        with patch.object(numerical_routes, "_current_email", return_value="user@example.com"):
            query = numerical_routes._build_panel_query(site, orientation="horizontal")

        self.assertEqual(query["hk"], 86.4)

    def test_converted_db_k_outside_configured_bounds_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "hk 86400 m/d exceeds max"):
            db_hydraulic_conductivity_to_numerical_hk(1.0)


if __name__ == "__main__":
    unittest.main()

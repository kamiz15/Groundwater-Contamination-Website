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

    def test_extra_data_gamma_autofills_numerical_query(self):
        # 'gamma' is a numerical model field with no fixed DB column; it must be
        # picked up from extra_data and surfaced in the panel query.
        site = {"id": 7, "extra_data": {"gamma": "4.2"}}

        with patch.object(numerical_routes, "_current_email", return_value="user@example.com"):
            query = numerical_routes._build_panel_query(site, orientation="horizontal")

        self.assertEqual(query["gamma"], 4.2)

    def test_fixed_columns_still_autofill_without_extra_data(self):
        # Backward compatibility: a site carrying only fixed columns (no
        # extra_data) produces the same canonical keys as before.
        site = {
            "id": 42,
            "aquifer_thickness": 10.0,
            "hydraulic_conductivity": 0.001,
            "electron_donor": 5.0,
            "electron_acceptor_o2": 8.0,
        }

        with patch.object(numerical_routes, "_current_email", return_value="user@example.com"):
            query = numerical_routes._build_panel_query(site, orientation="horizontal")

        self.assertEqual(query["hk"], 86.4)
        self.assertEqual(query["M"], 10.0)
        self.assertEqual(query["C_D"], 5.0)
        self.assertEqual(query["C_A"], 8.0)
        # No extra_data means no spurious gamma autofill.
        self.assertNotIn("gamma", query)


if __name__ == "__main__":
    unittest.main()

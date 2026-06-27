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

    def test_vertical_autofill_is_resilient_to_missing_fields(self):
        # A site missing aquifer_thickness / hydraulic_conductivity must still
        # autofill the values it does carry (no all-or-nothing raise).
        site = {
            "id": 7,
            "electron_donor": 5.0,
            "electron_acceptor_o2": 8.0,
            "gamma": 3.5,
            "alpha_tv": 0.1,
        }
        with patch.object(numerical_routes, "_current_email", return_value="user@example.com"):
            query = numerical_routes._build_panel_query(site, orientation="vertical")
        self.assertEqual(query["C_D"], 5.0)
        self.assertEqual(query["C_A"], 8.0)
        self.assertEqual(query["gamma"], 3.5)
        self.assertEqual(query["atv"], 0.1)  # vertical transverse dispersivity field
        self.assertNotIn("Lz", query)  # missing thickness -> field keeps its default
        self.assertNotIn("hk", query)

    def test_transverse_dispersivity_maps_to_numerical_field_names(self):
        site = {"id": 8, "alpha_th": 0.2, "alpha_tv": 0.1}
        with patch.object(numerical_routes, "_current_email", return_value="user@example.com"):
            query = numerical_routes._build_panel_query(site, orientation="horizontal")
        self.assertEqual(query["at"], 0.2)   # horizontal transverse dispersivity field
        self.assertEqual(query["atv"], 0.1)  # vertical transverse dispersivity field

    def test_hk_out_of_band_skips_only_hk(self):
        # 1.0 m/s -> 86400 m/d exceeds the band; hk is skipped but other site
        # values still autofill.
        site = {
            "id": 9,
            "aquifer_thickness": 10.0,
            "hydraulic_conductivity": 1.0,
            "electron_donor": 5.0,
        }
        with patch.object(numerical_routes, "_current_email", return_value="user@example.com"):
            query = numerical_routes._build_panel_query(site, orientation="vertical")
        self.assertNotIn("hk", query)
        self.assertEqual(query["Lz"], 10.0)
        self.assertEqual(query["C_D"], 5.0)

    def test_vertical_solver_style_extra_data_autofills_numerical_fields(self):
        site = {
            "id": 10,
            "extra_data": {"Lz": "12", "grid_size": "0.5", "al": "2.0"},
        }

        with patch.object(numerical_routes, "_current_email", return_value="user@example.com"):
            query = numerical_routes._build_panel_query(site, orientation="vertical")

        self.assertEqual(query["Lz"], 12.0)
        self.assertEqual(query["grid_size"], 0.5)
        self.assertEqual(query["al"], 2.0)

    def test_horizontal_solver_style_extra_data_autofills_numerical_fields(self):
        site = {
            "id": 11,
            "extra_data": {"grid_size": "0.75", "al": "2.5", "at": "0.25"},
        }

        with patch.object(numerical_routes, "_current_email", return_value="user@example.com"):
            query = numerical_routes._build_panel_query(site, orientation="horizontal")

        self.assertEqual(query["grid_size"], 0.75)
        self.assertEqual(query["al"], 2.5)
        self.assertEqual(query["at"], 0.25)

    def test_typed_database_value_wins_over_solver_extra_data_alias(self):
        site = {
            "id": 12,
            "aquifer_thickness": 10.0,
            "extra_data": {"Lz": "99"},
        }

        with patch.object(numerical_routes, "_current_email", return_value="user@example.com"):
            query = numerical_routes._build_panel_query(site, orientation="vertical")

        self.assertEqual(query["Lz"], 10.0)

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

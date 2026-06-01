from panel_source_inversion import source_inversion_app


def test_inversion_dashboard_keeps_input_and_output_sections_in_vertical_flow():
    dashboard = source_inversion_app()
    input_section = dashboard.objects[1]
    output_section = dashboard.objects[2]

    assert dashboard.sizing_mode == "stretch_width"
    assert input_section.sizing_mode == "stretch_width"
    assert input_section.styles["min-height"] == "280px"
    assert input_section.styles["align-items"] == "flex-start"
    assert output_section.sizing_mode == "stretch_width"

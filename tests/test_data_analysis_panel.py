import panel as pn
import pandas as pd
import pytest

import panel_data_analysis as workbench


def _site(site_id, display_id, name, plume_length):
    return {
        "id": site_id,
        "display_id": display_id,
        "user_email": "user@example.com",
        "site_unit": name,
        "compound": "BTEX",
        "plume_length": plume_length,
        "extra_data": {},
    }


def _named_widget(app, widget_type, name):
    return next(widget for widget in app.select(widget_type) if widget.name == name)


def test_workbench_loads_authenticated_users_database_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(workbench, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(
        workbench,
        "get_user_sites_rows",
        lambda email: calls.append(email) or [_site(1580, 1, "Current Site", 25.0)],
    )

    app = workbench.data_analysis_app()
    preview = _named_widget(app, pn.widgets.Tabulator, "Data preview")
    uni_col = _named_widget(app, pn.widgets.Select, "Column")
    biv_x = _named_widget(app, pn.widgets.Select, "X column")

    assert calls == ["user@example.com"]
    assert list(preview.value["Site Number"]) == [1]
    assert list(preview.value["Site unit"]) == ["Current Site"]
    assert uni_col.value == "Plume Length L_p [m]"
    assert biv_x.value == "Site Number"
    assert preview.layout == "fit_columns"
    status_cards = app.objects[0].select(pn.pane.HTML)
    assert len(status_cards) == 1
    assert "Data source:</b> Site database" in str(status_cards[0].object)
    assert "1 rows" in str(status_cards[0].object)
    assert "CSV notation:" not in str(status_cards[0].object)
    assert not any(
        "Data Analysis Workbench" in str(pane.object)
        for pane in app.select(pn.pane.Markdown)
    )


def test_workbench_database_refresh_replaces_the_current_dataset(monkeypatch):
    rows = [_site(1580, 1, "First Site", 25.0)]
    monkeypatch.setattr(workbench, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(workbench, "get_user_sites_rows", lambda _email: list(rows))

    app = workbench.data_analysis_app()
    preview = _named_widget(app, pn.widgets.Tabulator, "Data preview")
    refresh = _named_widget(app, pn.widgets.Button, "Refresh site database")

    rows.append(_site(1581, 2, "Second Site", 30.0))
    refresh.clicks += 1

    assert list(preview.value["Site Number"]) == [1, 2]
    assert list(preview.value["Site unit"]) == ["First Site", "Second Site"]


def test_temporary_csv_does_not_replace_the_saved_database(monkeypatch):
    rows = [_site(1580, 1, "Saved Site", 25.0)]
    monkeypatch.setattr(workbench, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(workbench, "get_user_sites_rows", lambda _email: list(rows))

    app = workbench.data_analysis_app()
    preview = _named_widget(app, pn.widgets.Tabulator, "Data preview")
    file_input = _named_widget(app, pn.widgets.FileInput, "Upload another CSV or NPZ")
    refresh = _named_widget(app, pn.widgets.Button, "Refresh site database")

    file_input.param.update(
        filename="temporary.csv",
        value=b"Plume length[m],Temporary value,Group\n25,99,A\n",
    )
    assert list(preview.value["Plume Length L_p [m]"]) == [25]
    assert list(preview.value["Temporary value"]) == [99]

    refresh.clicks += 1
    assert "Temporary value" not in preview.value.columns
    assert list(preview.value["Site unit"]) == ["Saved Site"]


def test_workbench_keeps_upload_prompt_when_site_database_is_empty(monkeypatch):
    monkeypatch.setattr(workbench, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(workbench, "get_user_sites_rows", lambda _email: [])

    app = workbench.data_analysis_app()
    preview = _named_widget(app, pn.widgets.Tabulator, "Data preview")
    status_cards = app.objects[0].select(pn.pane.HTML)
    html = " ".join(str(pane.object) for pane in status_cards)

    assert preview.value.empty
    assert len(status_cards) == 1
    assert "No uploaded site data is available" in html
    assert "Upload a CSV file" in html
    assert "CSV notation:" in html


def test_workbench_opens_an_aem_grid_on_the_scientific_tab(monkeypatch):
    frame = pd.DataFrame({
        "x [m]": [0.0, 1.0, 0.0, 1.0],
        "z [m]": [-1.0, -1.0, 0.0, 0.0],
        "concentration [mg/L]": [1.0, 2.0, 3.0, 4.0],
    })
    monkeypatch.setattr(workbench, "_request_argument", lambda _name: "job-1")
    monkeypatch.setattr(workbench, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(
        workbench, "_load_aem_job_frame",
        lambda job_id, email: (frame, "AEM forward result"),
    )
    monkeypatch.setattr(
        workbench, "get_user_sites_rows",
        lambda _email: pytest.fail("site database should not load for an AEM handoff"),
    )

    app = workbench.data_analysis_app()

    preview = _named_widget(app, pn.widgets.Tabulator, "Data preview")
    tabs = next(widget for widget in app.select(pn.Tabs))
    assert list(preview.value.columns) == list(frame.columns)
    assert tabs.active == 2
    assert _named_widget(app, pn.widgets.Select, "Grid X column").value == "x [m]"
    assert _named_widget(app, pn.widgets.Select, "Grid Y column").value == "z [m]"
    assert _named_widget(app, pn.widgets.Select, "Grid value column").value == "concentration [mg/L]"
    assert any("Grid ready: 2" in str(pane.object) for pane in app.select(pn.pane.HTML))


def test_panel_aem_loader_rejects_another_users_job(monkeypatch):
    monkeypatch.setattr(
        workbench, "load_job_meta",
        lambda _job_id: {"email": "other@example.com", "kind": "aem_forward"},
    )
    monkeypatch.setattr(workbench, "job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(
        workbench, "fetch_result",
        lambda _job_id: pytest.fail("another user's result must not be read"),
    )

    with pytest.raises(ValueError, match="unavailable"):
        workbench._load_aem_job_frame("job-1", "user@example.com")

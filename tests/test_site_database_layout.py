from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_site_database_uses_compact_responsive_table_layout():
    template = (ROOT / "templates" / "site_database.html").read_text(encoding="utf-8")
    styles = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")

    assert "site-table-wrapper" in template
    assert "site-data-table" in template
    assert 'data-label="{{ label }}"' in template
    assert ".site-data-table" in styles
    assert "table-layout: fixed" in styles
    assert ".site-table-wrapper" in styles
    assert "overflow-x: visible" in styles
    assert "upload-notation-list" not in template
    assert ".upload-notation-list" not in styles
    assert "Download Sample File" in template
    assert "sample_db.csv" in template
    upload_form = template.split('class="site-form csv-form"', 1)[1].split("</form>", 1)[0]
    assert "Upload CSV" in upload_form
    assert "Download Sample File" in upload_form
    assert upload_form.index("Upload CSV") < upload_form.index("Download Sample File")
    assert "Download Reference Database" in template
    assert "Dispersivity Data" in template
    assert 'class="section-head database-page-head"' in template
    assert '<span class="kicker">Data Management</span>' in template
    assert "database-upload-card" in template
    assert "database-manual-card" in template
    assert ".database-page-head" in styles
    assert ".data-themed-page .data-table th" in styles


def test_database_tables_have_native_controls_without_internal_scrollbars():
    template = (ROOT / "templates" / "site_database.html").read_text(encoding="utf-8")
    styles = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    script = (ROOT / "static" / "site_database.js").read_text(encoding="utf-8")

    assert template.count("data-database-browser") == 2
    assert template.count("data-database-size") == 2
    assert template.count("data-database-search") == 2
    assert template.count("data-database-pagination") == 2
    assert "data-database-sort" in template
    assert ".reference-table-wrapper" in styles
    assert "overflow: visible" in styles
    assert "scrollX" not in script
    assert "scrollY" not in script
    for action in ("copy", "csv", "excel", "pdf", "print"):
        assert f'data-database-export="{action}"' in template
    assert "data-reference-export" not in template
    assert "navigator.clipboard" in script
    assert 'exportUrl("xlsx")' in script
    assert "printWindow.print()" in script
    assert ".reference-export-toolbar" in styles


def test_dispersivity_page_uses_current_responsive_ui_without_scrollbars():
    template = (ROOT / "templates" / "dispersivity_data.html").read_text(encoding="utf-8")
    styles = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'class="section-spaced dispersivity-data-page data-themed-page"' in template
    assert 'class="section-head database-page-head"' in template
    assert 'class="card-like data-page-card dispersivity-table-card"' in template
    assert "data-database-browser" in template
    assert "data-database-size" in template
    assert "data-database-search" in template
    assert "data-database-sort" in template
    assert "data-database-pagination" in template
    assert "Download Dispersivity Data" in template
    for image in ("ticks.png", "box.png", "scatter.png"):
        assert image in template
    assert ".dispersivity-plot-grid" in styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in styles
    assert "width: calc((100% - 1rem) / 2)" in styles
    assert "justify-self: center" in styles
    assert "overflow" not in template

def test_data_workbench_uses_shared_data_page_theme_without_changing_iframe():
    template = (ROOT / "templates" / "panel_data_analysis.html").read_text(encoding="utf-8")
    styles = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'class="section-spaced model-page data-workbench-page data-themed-page"' in template
    assert 'class="section-head database-page-head"' in template
    assert '<span class="kicker">Interactive Analysis</span>' in template
    assert "card-like model-output-card data-page-card data-workbench-card" in template
    assert 'class="panel-frame output-panel-frame data-analysis-frame"' in template
    assert ".content.data-page-content" in styles
    assert ".data-workbench-card .output-panel-shell" in styles

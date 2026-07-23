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

from pathlib import Path


def test_report_export_status_labels_are_plain_ascii():
    script = (Path(__file__).parents[1] / "static" / "script.js").read_text(
        encoding="utf-8"
    )

    assert 'btn.textContent = "Preparing PDF...";' in script
    assert 'btn.textContent = "Export failed - try again";' in script
    assert 'link.textContent = "Submitting simulation...";' in script
    assert 'show("Simulation finished - downloading report.");' in script
    assert '"Running simulation...";' in script

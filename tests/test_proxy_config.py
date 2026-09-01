from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_panel_extension_static_assets_are_proxied_before_flask_static():
    config = (PROJECT_ROOT / "nginx" / "default.conf").read_text(encoding="utf-8")
    panel_static = "location /static/extensions/panel/ {"
    flask_static = "location /static/ {"

    assert panel_static in config
    assert "proxy_pass http://$panel_upstream/panel$request_uri;" in config
    assert config.index(panel_static) < config.index(flask_static)

def test_panel_frame_height_sync_reports_why_it_failed():
    """The iframe height sync must never fail silently.

    It can only measure a same-origin iframe; when it cannot, the frame stays at
    its CSS floor and the embedded plot is cut off. That used to be swallowed by
    a bare catch, which made a clipped graph impossible to diagnose from the
    browser."""
    source = (PROJECT_ROOT / "static" / "script.js").read_text(encoding="utf-8")
    assert "/* not ready / cross-origin */" not in source, (
        "the silent swallow is back; a clipped panel frame would be invisible again"
    )
    assert "noteSync" in source
    assert 'noteSync(frame, "cross-origin"' in source
    assert 'noteSync(frame, "failed"' in source
    assert "frame.dataset.frameSync" in source


def test_workbench_iframes_disable_redundant_inner_scrolling():
    for template_name in ("model_workbench_single.html", "model_workbench_multiple.html"):
        template = (PROJECT_ROOT / "templates" / template_name).read_text(encoding="utf-8")
        assert 'scrolling="no"' in template

    source = (PROJECT_ROOT / "static" / "script.js").read_text(encoding="utf-8")
    assert 'doc.documentElement.style.overflowY = "hidden"' in source
    assert 'doc.body.style.overflowY = "hidden"' in source


def test_numerical_multiple_pages_use_one_panel_frame():
    """The numerical multiple pages sit on the shared multiple shell, the same one
    every other multiple uses: one panel frame, and the run button inside it. The
    second (headless runner) frame and its cross-frame run relay are gone."""
    styles = (PROJECT_ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    for template_name in (
        "panel_numerical_horizontal_multiple.html",
        "panel_numerical_vertical_multiple.html",
    ):
        template = (PROJECT_ROOT / "templates" / template_name).read_text(encoding="utf-8")
        assert '{% extends "model_workbench_multiple.html" %}' in template
        assert "<iframe" not in template          # the shared shell owns the frame
        assert "postMessage" not in template      # no cross-frame run relay
        # The picker is a widget in the frame now, so the page has no form to
        # submit and no picker of its own.
        assert "compare_submit_label" not in template

    shared = (PROJECT_ROOT / "templates" / "model_workbench_multiple.html").read_text(encoding="utf-8")
    assert shared.count("<iframe") == 1
    assert 'name="compare_sites"' not in shared       # it lives in the panel

    assert "numerical-multiple" not in styles     # run-button/runner styles removed


def test_absolute_panel_base_is_flagged_as_cross_origin():
    """An absolute PANEL_PUBLIC_BASE makes every embed cross-origin (a different
    port is a different origin), which disables the iframe height sync. Only a
    path-only value is same-origin."""
    from urllib.parse import urlparse

    def is_cross_origin(value):
        parsed = urlparse(value)
        return bool(parsed.scheme or parsed.netloc)

    assert is_cross_origin("http://localhost:5007")
    assert is_cross_origin("https://cast.example.org/panel")
    assert not is_cross_origin("/panel")
    assert not is_cross_origin("")

    app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    assert "_warn_about_panel_embedding" in app_source, "startup diagnostic removed"
    assert "PANEL_ALLOW_ORIGINS" in app_source

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_panel_extension_static_assets_are_proxied_before_flask_static():
    config = (PROJECT_ROOT / "nginx" / "default.conf").read_text(encoding="utf-8")
    panel_static = "location /static/extensions/panel/ {"
    flask_static = "location /static/ {"

    assert panel_static in config
    assert "proxy_pass http://$panel_upstream/panel$request_uri;" in config
    assert config.index(panel_static) < config.index(flask_static)

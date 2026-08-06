"""Central CAST theme for all Panel apps.

Call apply_theme() once (in panel_server.py) before serving. It injects
document-level CSS and sets class-level default stylesheets so every
Button, input, Tabulator etc. in every app matches the site redesign,
without editing the individual panel_*.py files.

Design tokens mirror static/styles.css:
  bg #f5f7fa | panel #eef1f5 | border #e3e8ef | text #16212e
  muted #5b6b7f | accent #1f72cd / #155da9 / #114b88 | navy #0b2c4f
"""

import html as _html
import json as _json

import panel as pn

FONT_FAMILY = "Inter, 'Source Sans 3', system-ui, 'Segoe UI', Roboto, Arial, sans-serif"

# Document-level (light DOM): fonts + page base
GLOBAL_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body {
  font-family: Inter, 'Source Sans 3', system-ui, 'Segoe UI', Roboto, Arial, sans-serif;
  background: #f5f7fa;
  color: #16212e;
}
"""

# Buttons (Button + FileDownload render .bk-btn inside their shadow root)
BUTTON_CSS = """
:host { font-family: %(font)s; }
.bk-btn {
  border-radius: 8px;
  font-family: %(font)s;
  font-weight: 600;
  font-size: 14px;
  padding: 9px 16px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
  transition: background .15s ease, border-color .15s ease, color .15s ease;
}
.bk-btn-primary {
  background: #155da9;
  border: 1px solid #155da9;
  color: #fff;
}
.bk-btn-primary:hover {
  background: #114b88;
  border-color: #114b88;
}
.bk-btn-default {
  background: #eef1f5;
  border: 1px solid #e3e8ef;
  color: #16212e;
}
.bk-btn-default:hover {
  border-color: #5598e3;
  color: #114b88;
}
""" % {"font": FONT_FAMILY}

# Text/number inputs, selects, sliders
INPUT_CSS = """
:host { font-family: %(font)s; }
label {
  font-family: %(font)s;
  font-weight: 600;
  font-size: 13px;
  color: #5b6b7f;
}
.bk-input {
  font-family: %(font)s;
  background: #f8fafc;
  color: #16212e;
  border: 1px solid #e3e8ef;
  border-radius: 8px;
  padding: 6px 10px;
  min-height: 34px;
  transition: border-color .15s ease, box-shadow .15s ease;
}
.bk-input:focus {
  border-color: #5598e3;
  box-shadow: 0 0 0 3px rgba(31, 114, 205, 0.12);
  outline: none;
}
""" % {"font": FONT_FAMILY}

# Sliders. Bokeh builds these on noUiSlider, so INPUT_CSS (.bk-input) never
# reaches them - they kept the stock grey bar. A 4px track with the CAST accent
# on the travelled portion reads as an instrument next to the plot rather than
# as one more form control.
SLIDER_CSS = """
:host { font-family: %(font)s; }
.bk-slider-title {
  font-family: %(font)s;
  font-weight: 600;
  font-size: 12.5px;
  color: #5b6b7f;
  margin-bottom: 2px;
  /* CAST parameter names are long ("Horizontal Transverse Dispersivity a_Th
     [m]"). Bokeh keeps the title on one line, so side-by-side sliders bleed
     into each other; wrap instead. */
  white-space: normal;
  line-height: 1.35;
}
.bk-slider-value, .bk-slider-title .bk-slider-value {
  font-weight: 700;
  color: #0b2c4f;
}
.noUi-target {
  background: #dfe5ee;
  border: 0;
  border-radius: 999px;
  box-shadow: none;
  height: 4px;
  margin: 10px 8px 14px;
}
.noUi-connect { background: #1f72cd; }
.noUi-handle {
  width: 16px;
  height: 16px;
  right: -8px;
  top: -6px;
  border: 2px solid #fff;
  border-radius: 50%%;
  background: #155da9;
  box-shadow: 0 1px 3px rgba(11, 44, 79, 0.35);
  cursor: grab;
  transition: background .15s ease, box-shadow .15s ease;
}
.noUi-handle:hover { background: #114b88; }
.noUi-handle:active { cursor: grabbing; }
.noUi-handle::before, .noUi-handle::after { display: none; }
.noUi-handle:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(31, 114, 205, 0.28);
}
@media (prefers-reduced-motion: reduce) {
  .noUi-handle { transition: none; }
}
""" % {"font": FONT_FAMILY}

# Tabulator scenario tables
TABULATOR_CSS = """
:host { font-family: %(font)s; }
.tabulator {
  font-family: %(font)s;
  border: 1px solid #e3e8ef;
  border-radius: 8px;
  background: #eef1f5;
}
.tabulator .tabulator-header {
  background: #e7ebf1;
  border-bottom: 1px solid #e3e8ef;
}
.tabulator .tabulator-header .tabulator-col {
  background: #e7ebf1;
  border-right: 1px solid #e3e8ef;
}
.tabulator .tabulator-header .tabulator-col-title {
  font-weight: 600;
  font-size: 12.5px;
  color: #5b6b7f;
}
.tabulator-row {
  border-bottom: 1px solid #eef1f5;
  color: #16212e;
}
.tabulator-row.tabulator-row-even { background: #e9edf3; }
.tabulator-row:hover { background: #e1ebfa; }
.tabulator .tabulator-cell { border-right: 1px solid #f1f4f8; }
""" % {"font": FONT_FAMILY}

# Markdown headings ("## Model name", "### Manual scenario inputs")
MARKDOWN_CSS = """
:host { font-family: %(font)s; color: #16212e; }
h1, h2, h3, h4 { font-family: %(font)s; letter-spacing: -0.01em; }
h2 {
  font-size: 1.25rem;
  font-weight: 700;
  color: #16212e;
  margin: 0 0 4px;
  padding-bottom: 8px;
  border-bottom: 2px solid #1f72cd;
  display: inline-block;
}
h3 {
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #5b6b7f;
  margin: 10px 0 4px;
}
""" % {"font": FONT_FAMILY}


# One sheet for every component, not one per class.
#
# `stylesheets` is a single param.Parameter owned by panel.viewable.Layoutable
# and shared down the whole hierarchy, so `SomeWidget.param.stylesheets.default
# = [...]` does not scope to that widget - it reassigns the default for every
# Layoutable. Setting it per class therefore just let each assignment overwrite
# the previous one, and only the last (Markdown) survived. The blocks above are
# already scoped by component-internal selectors (.bk-btn, .bk-input, .noUi-*,
# .tabulator), so concatenating them is safe: a component matches its own rules
# and ignores the rest.
COMPONENT_CSS = "\n".join([BUTTON_CSS, INPUT_CSS, SLIDER_CSS, TABULATOR_CSS, MARKDOWN_CSS])


def apply_theme() -> None:
    """Inject CAST styling into every Panel app served by this process."""
    if GLOBAL_CSS not in pn.config.raw_css:
        pn.config.raw_css.append(GLOBAL_CSS)

    pn.viewable.Layoutable.param.stylesheets.default = [COMPONENT_CSS]


def report_bridge_html(title="", subtitle="", filename="", parameters=None,
                       outputs=None, plot_data=None, plot_images_b64=None,
                       clear=False) -> str:
    """HTML snippet that posts the latest run results to the parent page.

    Set it as the .object of a hidden pn.pane.HTML after each run. The parent
    page (script.js) listens for the message and enables the styled
    "Report Export" card outside the iframe. Use clear=True after a failed
    run so the stale report is hidden.
    """
    if clear:
        payload = {"type": "cast-report", "clear": True}
    else:
        payload = {
            "type": "cast-report",
            "title": title,
            "subtitle": subtitle,
            "filename": filename,
            "state": {
                "parameters": parameters or [],
                "outputs": outputs or [],
                "plot_data": plot_data,
                "plot_images": plot_images_b64 or [],
            },
        }
    encoded = _html.escape(_json.dumps(payload), quote=True)
    # data: URI fails to decode as an image -> onerror fires on insertion,
    # with no network request. Re-setting the pane creates a fresh <img>,
    # so the message is re-posted on every run.
    return (
        '<img src="data:," style="display:none" alt="" '
        f'data-payload="{encoded}" '
        "onerror='window.parent.postMessage(JSON.parse(this.dataset.payload), \"*\")'>"
    )

import numpy as np
from bokeh.models import ColorBar, HoverTool
from bokeh.palettes import Blues256, Reds256

from plot_functions import plot_reactive_plume_interactive


def _image_renderers(fig):
    return [r for r in fig.renderers if r.glyph.__class__.__name__ == "Image"]


def _hover_rect_data(fig):
    """The hover overlay rect carries the RAW (non-upsampled) Ca/Cd fields, so
    Ca/Cd correctness is asserted here rather than on the displayed image (which
    is bilinearly upsampled for a smooth render)."""
    for r in fig.renderers:
        if r.glyph.__class__.__name__ == "Rect":
            return r.data_source.data
    raise AssertionError("no hover rect renderer found")


def test_reactive_plume_builder_splits_ca_cd_and_adds_hover():
    concentration = np.array([
        [6.0, 8.0, 10.0],
        [4.0, 9.0, 12.0],
    ])
    fig = plot_reactive_plume_interactive(
        concentration,
        np.array([0.0, 5.0, 10.0]),
        np.array([0.0, 2.0]),
        ca=8.0,
        cd=5.0,
        gamma=2.0,
        plume_length=5.0,
        domain_length=10.0,
        cross_extent=2.0,
        orientation="horizontal",
        source_extent=1.0,
    )

    # Two image layers (Ca, Cd); displayed image is upsampled, so verify the
    # Ca/Cd split via the raw hover data instead of the image arrays.
    assert len(_image_renderers(fig)) == 2
    assert fig.x_range.start == 0.0
    assert fig.x_range.end == 10.0
    assert fig.y_range.start == 0.0
    assert fig.y_range.end == 2.0
    hover = _hover_rect_data(fig)
    np.testing.assert_allclose(np.asarray(hover["ca"]), [2.0, 0.0, 0.0, 4.0, 0.0, 0.0])
    np.testing.assert_allclose(np.asarray(hover["cd"]), [0.0, 0.0, 1.0, 0.0, 0.5, 2.0])
    assert any(renderer.glyph.__class__.__name__ == "MultiLine" for renderer in fig.renderers)
    assert any(isinstance(tool, HoverTool) for tool in fig.tools)
    assert {item.label.value for item in fig.legend[0].items} == {"Plume length = 5.0 m"}
    colorbars = [layout for layout in fig.right if isinstance(layout, ColorBar)]
    assert [bar.title for bar in colorbars] == ["C_a [mg/L]", "C_d [mg/L]"]
    images = _image_renderers(fig)
    assert images[0].glyph.global_alpha == 1.0
    assert images[1].glyph.global_alpha == 1.0
    assert images[0].glyph.color_mapper.palette == list(reversed(Blues256))
    assert images[1].glyph.color_mapper.palette == list(reversed(Reds256))


def test_reactive_plume_builder_uses_depth_down_for_vertical():
    concentration = np.array([
        [6.0, 8.0, 10.0],
        [4.0, 9.0, 12.0],
    ])
    fig = plot_reactive_plume_interactive(
        concentration,
        np.array([0.0, 5.0, 10.0]),
        np.array([0.0, 2.0]),
        ca=8.0,
        cd=5.0,
        gamma=2.0,
        plume_length=5.0,
        domain_length=10.0,
        cross_extent=2.0,
        orientation="vertical",
        footer_meta="L_D = 10.00 m | K = 8.64 m/d",
    )

    assert fig.y_range.start == 2.0
    assert fig.y_range.end == 0.0
    assert fig.height == 350
    assert fig.sizing_mode == "stretch_width"
    assert fig.title is None
    assert fig.background_fill_color == "#eef1f5"
    assert fig.outline_line_color == "#cbd5e1"
    assert fig.grid[0].grid_line_alpha == 0.0
    assert fig.legend[0].click_policy == "hide"
    # Two legend entries now: the plume length and the CD source band.
    legend_labels = {item.label.value for item in fig.legend[0].items}
    assert legend_labels == {"Plume length = 5.0 m", "CD source"}
    assert any(isinstance(tool, HoverTool) for tool in fig.tools)
    tool_names = {tool.__class__.__name__ for tool in fig.tools}
    assert {"PanTool", "WheelZoomTool", "BoxZoomTool", "ResetTool", "SaveTool"} <= tool_names

    images = _image_renderers(fig)
    assert len(images) == 2
    # Depth is inverted via y_range (cross_extent -> 0) only; rows are passed
    # un-flipped so row 0 (shallow) renders at the TOP. The displayed image is
    # bilinearly upsampled, so Ca/Cd correctness is checked via the raw hover data.
    hover = _hover_rect_data(fig)
    np.testing.assert_allclose(np.asarray(hover["ca"]), [2.0, 0.0, 0.0, 4.0, 0.0, 0.0])
    np.testing.assert_allclose(np.asarray(hover["cd"]), [0.0, 0.0, 1.0, 0.0, 0.5, 2.0])
    assert images[0].glyph.color_mapper.palette == list(reversed(Blues256))
    assert images[0].glyph.color_mapper.palette[0] == Blues256[-1]
    assert images[1].glyph.color_mapper.palette == list(reversed(Reds256))
    assert images[1].glyph.color_mapper.palette[0] == Reds256[-1]

    contour = next(renderer for renderer in fig.renderers
                   if renderer.glyph.__class__.__name__ == "MultiLine")
    assert contour.glyph.line_color == "black"
    plume_line = next(renderer for renderer in fig.renderers
                      if renderer.glyph.__class__.__name__ == "Line")
    assert plume_line.data_source.data["x"] == [5.0, 5.0]
    assert plume_line.glyph.line_dash == [6]
    # Vertical now carries reference-style annotations (source bar label, CA, rotated Lmax).
    assert any(renderer.glyph.__class__.__name__ == "Text" for renderer in fig.renderers)

    colorbars = [layout for layout in fig.right if isinstance(layout, ColorBar)]
    assert [bar.title for bar in colorbars] == ["Ca [mg/L]", "Cd [mg/L]"]

    # The metadata footer is added as a bottom Title.
    from bokeh.models import Title
    assert any(isinstance(t, Title) and "L_D" in (t.text or "") for t in fig.below)

from bokeh.models import ColumnDataSource, HoverTool
from bokeh.plotting import figure


def single_comparison_plot(title, analytical_label, numerical_label, analytical_value, numerical_value):
    labels = [analytical_label, numerical_label]
    values = [float(analytical_value), float(numerical_value)]
    colors = ["#0d9887", "#163c66"]
    source = ColumnDataSource({"label": labels, "value": values, "color": colors})

    p = figure(
        title=title,
        x_range=labels,
        y_axis_label="Plume Length Lmax [m]",
        height=340,
        sizing_mode="stretch_width",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        toolbar_location="above",
    )
    p.vbar(x="label", top="value", width=0.55, color="color", source=source)
    p.add_tools(HoverTool(tooltips=[("Model", "@label"), ("Lmax", "@value{0.00} m")]))
    p.y_range.start = 0
    p.xgrid.grid_line_color = None
    return p


def multiple_comparison_plot(title, analytical_label, numerical_label, analytical_values, numerical_values):
    analytical_values = [float(v) for v in analytical_values]
    numerical_values = [float(v) for v in numerical_values]
    count = min(len(analytical_values), len(numerical_values))
    scenarios = [str(i + 1) for i in range(count)]

    p = figure(
        title=title,
        x_range=scenarios,
        y_axis_label="Plume Length Lmax [m]",
        x_axis_label="Scenario",
        height=360,
        sizing_mode="stretch_width",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        toolbar_location="above",
    )
    p.line(scenarios, analytical_values[:count], color="#0d9887", line_width=2.5, legend_label=analytical_label)
    p.scatter(scenarios, analytical_values[:count], color="#0d9887", size=9)
    p.line(scenarios, numerical_values[:count], color="#163c66", line_width=2.5, legend_label=numerical_label)
    p.scatter(scenarios, numerical_values[:count], color="#163c66", size=9)
    p.y_range.start = 0
    p.legend.location = "top_left"
    p.legend.click_policy = "hide"
    return p

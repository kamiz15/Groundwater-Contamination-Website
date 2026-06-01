from __future__ import annotations

from time import perf_counter
from typing import Callable

import panel as pn

from plot_functions import (
    plot_concentration_gradient_vectors_interactive,
    plot_concentration_profile_interactive,
)


class LazyNumericalViews:
    """Render optional numerical post-processing views only after a user click."""

    def __init__(
        self,
        payload_getter: Callable[[], dict | None],
        *,
        profile_plotter: Callable = plot_concentration_profile_interactive,
        vector_plotter: Callable = plot_concentration_gradient_vectors_interactive,
    ):
        self._payload_getter = payload_getter
        self._profile_plotter = profile_plotter
        self._vector_plotter = vector_plotter
        self.computation_counts = {"profile": 0, "vector": 0}

        self.profile_button = pn.widgets.Button(name="Show Profile View", button_type="default")
        self.vector_button = pn.widgets.Button(name="Show Vector View", button_type="default")
        self.status_pane = pn.pane.HTML("", sizing_mode="stretch_width")
        self.profile_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=340)
        self.vector_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=430)
        self.view_container = pn.Column(sizing_mode="stretch_width", styles={"gap": "10px"})

        self.profile_button.on_click(self.toggle_profile)
        self.vector_button.on_click(self.toggle_vector)
        self.panel = pn.Column(
            "### Optional Visualisations",
            pn.Row(self.profile_button, self.vector_button, sizing_mode="stretch_width"),
            pn.pane.HTML(
                '<p style="margin:0;color:#6b7280;font-size:0.86rem;">'
                "<strong>3D visualisation:</strong> TODO - planned as a long-term optional view."
                "</p>",
                sizing_mode="stretch_width",
            ),
            self.status_pane,
            self.view_container,
            sizing_mode="stretch_width",
            styles={"gap": "10px"},
        )

    def reset(self) -> None:
        """Drop post-processing views when a fresh solver result is requested."""
        self.profile_pane.object = None
        self.vector_pane.object = None
        self.view_container.objects = []
        self.profile_button.name = "Show Profile View"
        self.vector_button.name = "Show Vector View"
        self.status_pane.object = ""

    def _payload(self) -> dict:
        payload = self._payload_getter()
        if not payload:
            raise ValueError("Run the numerical simulation before requesting an optional view.")
        return payload

    def _compute(self, kind: str, plotter: Callable):
        payload = self._payload()
        started = perf_counter()
        plot = plotter(
            payload["concentration"],
            payload["x_grid"],
            payload["cross_grid"],
            cross_axis_label=payload["cross_axis_label"],
            title=payload["title"],
        )
        elapsed_ms = (perf_counter() - started) * 1000.0
        self.computation_counts[kind] += 1
        print(f"[optional-view] {kind} computed on click in {elapsed_ms:.2f} ms")
        self.status_pane.object = (
            f'<p style="margin:0;color:#3f6212;font-size:0.86rem;">'
            f"{kind.title()} view computed on click in {elapsed_ms:.2f} ms.</p>"
        )
        return plot

    def _shown(self, pane) -> bool:
        return pane in self.view_container.objects

    def _show(self, pane) -> None:
        if pane not in self.view_container.objects:
            self.view_container.append(pane)

    def _hide(self, pane) -> None:
        self.view_container.objects = [item for item in self.view_container.objects if item is not pane]

    def toggle_profile(self, _=None) -> None:
        if self._shown(self.profile_pane):
            self._hide(self.profile_pane)
            self.profile_button.name = "Show Profile View"
            return
        try:
            if self.profile_pane.object is None:
                self.profile_pane.object = self._compute("profile", self._profile_plotter)
            self._show(self.profile_pane)
            self.profile_button.name = "Hide Profile View"
        except Exception as exc:
            self.status_pane.object = f'<p style="margin:0;color:#991b1b;">{exc}</p>'

    def toggle_vector(self, _=None) -> None:
        if self._shown(self.vector_pane):
            self._hide(self.vector_pane)
            self.vector_button.name = "Show Vector View"
            return
        try:
            if self.vector_pane.object is None:
                self.vector_pane.object = self._compute("vector", self._vector_plotter)
            self._show(self.vector_pane)
            self.vector_button.name = "Hide Vector View"
        except Exception as exc:
            self.status_pane.object = f'<p style="margin:0;color:#991b1b;">{exc}</p>'

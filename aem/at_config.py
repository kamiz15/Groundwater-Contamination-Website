# Written by Willi Kappler, willi.kappler@uni-tuebingen.de
# Based on code from Anton Köhler

# Python std library:
import json
import logging
from typing import Any

# Local imports:
from .at_element import ATElement, ATElementType
import math

logger = logging.getLogger(__name__)


class ATConfiguration:
    def __init__(self):
        self.alpha_l: float = 2.0
        self.alpha_t: float = 0.2
        self.beta: float = 10 / (2.0 * self.alpha_l)
        self.ca: float = 8.0
        self.gamma: float = 3.5
        self.dom_xmin: float = 0.0
        self.dom_xmax: float = 600.0
        self.dom_ymin: float = -20.0
        self.dom_ymax: float = 40.0
        self.dom_inc: float = 0.5
        self.num_cp: int = 100  # Number of controll points
        self.num_terms: int = 7  # Number of terms
        self.elements: list = []
        self.orientation: str = "horizontal"
        self.plot_aspect: str = "scaled"

    @staticmethod
    def from_dict(data: dict) -> "ATConfiguration":
        """
        Build an ATConfiguration from an already-parsed config dict.

        Separating parsing from file I/O lets the designer pass a dict
        directly (avoiding a temp file) and keeps from_json as a thin wrapper.
        """
        config = ATConfiguration()
        config.alpha_l = data.get("alpha_l", config.alpha_l)
        config.alpha_t = data.get("alpha_t", config.alpha_t)
        config.beta = 1 / (2 * config.alpha_l)
        config.ca = data.get("ca", config.ca)
        config.gamma = data.get("gamma", config.gamma)
        config.dom_xmin = data.get("dom_xmin", config.dom_xmin)
        config.dom_xmax = data.get("dom_xmax", config.dom_xmax)
        config.dom_ymin = data.get("dom_ymin", config.dom_ymin)
        config.dom_ymax = data.get("dom_ymax", config.dom_ymax)
        config.dom_inc = data.get("dom_inc", config.dom_inc)
        config.num_cp = data.get("num_cp", config.num_cp)
        config.num_terms = data.get("num_terms", config.num_terms)
        config.orientation = data.get("orientation", config.orientation)
        config.plot_aspect = data.get("plot_aspect", config.plot_aspect)

        for i, elem_data in enumerate(data.get("elements", [])):
            kind = elem_data["kind"].lower()
            if kind == "circle":
                elem = ATElement(
                    kind=ATElementType.Circle,
                    x=elem_data["x"],
                    y=elem_data["y"],
                    c=elem_data["c"],
                    r=elem_data["r"]
                )
            elif kind == "line":
                theta_deg = elem_data.get("theta", 90)
                elem = ATElement(
                    kind=ATElementType.Line,
                    x=elem_data['x'],
                    y=elem_data['y'],
                    c=elem_data['c'],
                    r=elem_data['l']/2.0,  #radius
                    theta=math.radians(theta_deg)  # default vertical
                )
            elif kind == "ellipse":
                # Ellipse element expects semi-axes a (semi-major) and b (semi-minor), and optional theta in degrees.
                theta_deg = elem_data.get("theta", 0)
                a = elem_data.get("a", None)
                b = elem_data.get("b", None)
                if a is None or b is None:
                    raise ValueError("Ellipse requires 'a' and 'b' (semi-axes) in the config.")

                elem = ATElement(
                    kind=ATElementType.Ellipse,
                    x=float(elem_data['x']),
                    y=float(elem_data['y']),
                    c=float(elem_data['c']),
                    r=float(a),  # map 'a' → r (semi-major)
                    theta=math.radians(float(theta_deg)),  # degrees → radians
                    b=float(b)  # semi-minor
                )
            else:
                raise ValueError(f"Unknown element kind: {elem_data['kind']}")

            elem.label = elem_data.get("label", f"Element {i + 1}")
            elem.id = elem_data.get("id", f"source_{len(config.elements)}")
            elem.index = elem_data.get("index", None)   # designer metadata; solver ignores it
            config.elements.append(elem)
        return config

    @staticmethod
    def from_json(filename: str) -> Any:
        """
        Load the configuration (JSON format) from the given file name.

        :param file_name: File name of the configuration.
        :return: A valid configuration from the given JSON file.
        """
        logger.debug(f"Load configuration from file: {filename}.")
        with open(filename, "r") as f:
            data = json.load(f)
        return ATConfiguration.from_dict(data)

    def annotate_elements_on_plot(self, ax):
        for elem in self.elements:
            ax.text(elem.x, elem.y, elem.label, fontsize=14, ha="center", va="center", color="black",
                bbox=dict(facecolor="white", alpha=0.5))

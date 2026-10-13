# Written by Alvin Yadav
# Based on code from Willi Kappler and Anton Köhler

# Python std library:
import math
import cmath
import logging
from enum import Enum

# External library:
import numpy as np

# Local imports:
from .mathieu_functions_OG import Mathieu
#from mathieu_functions_pygsl import Mathieu

logger = logging.getLogger(__name__)

# Mathieu parameter limits, set from measured ODE-residual accuracy of the
# Mathieu routines: clean to q~60, degrading through q~150, unusable past q~200.
Q_WARN = 100.0
Q_MAX_USABLE = 200.0

class ATElementType(Enum):
    """
    This enum class defines the various element types.

    - Circle: x, y and radius
    - Line: x1, y1 and x2, y2
    - Ellipse: x, y and semi-axes (a=r, b)
    """
    Circle = 0
    Line = 1
    Ellipse = 2


class ATElement:
    def __init__(self, kind: ATElementType, x: float, y: float, c: float, r=1.0, theta: float = math.pi/2, b: float | None = None):
        self.kind = kind
        self.x: float = x
        self.y: float = y
        self.c: float = c
        self.r: float = r
        self.b: float | None = b
        self.theta: float = theta
        self.theta_eff: float | None = None # effective angle after anisotropy stretch
        self.d: float = 0.0
        self.q: float = 0.0
        self.m: Mathieu = Mathieu(0.0)
        self.outline: list = []
        # For a line only: the psi of each control point, i.e. which face of
        # the slit it belongs to. See set_outline.
        self.outline_psi = None
        self.label: str = ""
        self.id: str = ""
        self.index: int | None = None   # designer metadata; solver ignores it

    def calc_d_q(self, alpha_t: float, alpha_l: float, beta: float, num_terms: int = 12):
        a = float(self.r)
        s = math.sqrt(alpha_l / alpha_t)
        eps = 1e-15

        if self.kind == ATElementType.Circle:
            # circle -> ellipse (a, s a)
            s2 = s * s
            if s2 <= 1.0 + eps:
                self.d = max(a * math.sqrt(max(s2 - 1.0, eps)), eps)
            else:
                self.d = math.sqrt((s * a) ** 2 - a ** 2)
            self.theta_eff = None  # irrelevant for circles

        elif self.kind == ATElementType.Ellipse:
            # Ellipse: semi-axes a=r, b=self.b, rotated by theta.
            # Apply global stretch S=diag(1, s) with s = sqrt(alpha_l/alpha_t).
            a = float(self.r)
            b = float(self.b if self.b is not None else self.r)
            θ = float(self.theta)
            cθ, sθ = math.cos(θ), math.sin(θ)
            # Rotation and stretch
            R = np.array([[cθ, -sθ],
                          [sθ,  cθ]], dtype=float)
            S = np.array([[1.0, 0.0],
                          [0.0, s      ]], dtype=float)
            S_inv = np.array([[1.0, 0.0],
                              [0.0, 1.0/s]], dtype=float)
            # Quadratic form of ellipse in local coords: x^2/a^2 + y^2/b^2 = 1
            D = np.array([[1.0/(a*a), 0.0],
                          [0.0,       1.0/(b*b)]], dtype=float)
            # In stretched coords, ellipse equation becomes p_s^T M p_s = 1 with M = S^{-T} R D R^T S^{-1}
            M = S_inv.T @ R @ D @ R.T @ S_inv
            w, V = np.linalg.eigh(M)
            w = np.maximum(w, 1e-15)
            axes = 1.0 / np.sqrt(w)
            order = np.argsort(axes)[::-1]  # a_s >= b_s
            a_s, b_s = axes[order[0]], axes[order[1]]
            v_major = V[:, order[0]]
            # Effective major-axis angle in stretched frame and focal distance
            self.theta_eff = math.atan2(v_major[1], v_major[0])
            self.d = max(math.sqrt(max(a_s*a_s - b_s*b_s, 0.0)), 1e-15)

        elif self.kind == ATElementType.Line:
            # line deforms under global stretch: use stretched angle & half-length
            cθ, sθ = math.cos(self.theta), math.sin(self.theta)
            self.theta_eff = math.atan2(s * sθ, cθ)  # θ_s
            self.d = max(a * math.sqrt(cθ * cθ + (s * sθ) ** 2), eps)  # a_s

        else:
            raise ValueError(f"Unknown element type: {self.kind}")

        self.q = (self.d ** 2 * beta ** 2) / 4.0

        # The Mathieu routines lose accuracy as q grows: the angular functions
        # stop satisfying the Mathieu ODE (relative residual ~3e-4 at q=224,
        # ~1 at q=977) and enlarging M does not recover it, so a large element
        # would otherwise return a plausible-looking but meaningless field.
        abs_q = abs(self.q)
        if abs_q > Q_MAX_USABLE:
            raise ValueError(
                f"Element '{self.id or self.label or self.kind}' has Mathieu "
                f"q={abs_q:.1f}, beyond the range the Mathieu routines can "
                f"resolve (limit {Q_MAX_USABLE:g}); the solution would be "
                f"silently wrong. q grows with (element size x "
                f"sqrt(alpha_l/alpha_t) x beta)^2 - shrink the element, split "
                f"it into smaller ones, or raise alpha_t.")
        if abs_q > Q_WARN:
            logger.warning(
                "Element '%s' has Mathieu q=%.1f (>%g): basis-function "
                "accuracy is degraded and boundary values may be off.",
                self.id or self.label or self.kind, abs_q, Q_WARN)

        buffer_est = max(10, int(math.ceil(math.sqrt(abs_q))) + 10)
        M = max(20, num_terms + buffer_est)
        self.m = Mathieu(self.q, M=M)

    def set_outline(self, num_cp: int):
        self.outline_psi = None     # lines set it below; nothing else needs it
        if self.kind == ATElementType.Circle:
            phi = np.linspace(0, 2 * math.pi, num_cp, endpoint=False)
            self.outline = [
                (self.x + self.r * math.cos(p),
                 self.y + self.r * math.sin(p))
                for p in phi
            ]

        elif self.kind == ATElementType.Ellipse:
            a = float(self.r)
            b = float(self.b if self.b is not None else self.r)
            θ = float(self.theta)
            t_vals = np.linspace(0, 2 * math.pi, num_cp, endpoint=False)
            cθ, sθ = math.cos(θ), math.sin(θ)
            self.outline = [
                (self.x + a * math.cos(t) * cθ - b * math.sin(t) * sθ,
                 self.y + a * math.cos(t) * sθ + b * math.sin(t) * cθ)
                for t in t_vals
            ]

        elif self.kind == ATElementType.Line:
            # A line is a slit, so it has two faces. In elliptic coordinates a
            # point on it is (eta=0, psi), with psi in (0, pi) on one face and
            # in (pi, 2*pi) on the other; the two faces share the same physical
            # (x, y). Sampling psi uniformly therefore covers both faces and
            # records which one each control point belongs to.
            #
            # That record is the point of this parametrisation. At eta = 0 the
            # acosh branch in uv() has to pick the face from a quantity that is
            # zero in exact arithmetic, so it ends up decided by rounding noise
            # (~1e-17). Because ce is even in psi and se is odd, a face picked
            # at random flips the sign of every odd basis function, which is
            # what made line elements badly conditioned.
            #
            # In the element frame the slit is X = d*cos(psi), so the offset
            # along the line is t = r*cos(psi). The half-step offset keeps the
            # control points off the two tips, where the mapping is singular.
            psis = (np.arange(num_cp) + 0.5) * 2.0 * math.pi / num_cp
            c_th, s_th = math.cos(self.theta), math.sin(self.theta)
            self.outline = [
                (self.x + self.r * math.cos(p) * c_th,
                 self.y + self.r * math.cos(p) * s_th)
                for p in psis
            ]
            self.outline_psi = psis
        else:
            raise ValueError(f"Unknown element kind: {self.kind}")

    def uv(self, x: float, y: float, alpha_l: float, alpha_t: float) -> tuple[float, float]:
        """
        Map local offsets (dx, dy) -> (eta, psi), respecting anisotropy and element type.
        Sequence:
          (i) global stretch (x, s*y)
          (ii) rotate into element frame:
               - Circle: no rotation
               - Line: rotate by -θ_s (stretched angle)
          (iii) acosh with stable branch:
               - Circle: z = (Y + i*X)/d  (matches your OG circle mapping)
               - Line:   z = (X + i*Y)/d  (puts η=0 along the line)
        """
        s = math.sqrt(alpha_l / alpha_t)
        x_s, y_s = x, s * y

        if self.kind == ATElementType.Line:
            # rotate by effective stretched angle
            θ = self.theta_eff if self.theta_eff is not None else self.theta
            cθ, sθ = math.cos(θ), math.sin(θ)
            X = cθ * x_s + sθ * y_s
            Y = -sθ * x_s + cθ * y_s
            z = complex(X, Y) / (self.d if self.d != 0.0 else 1e-15)  # (X + i*Y)/d

        elif self.kind == ATElementType.Ellipse:
            # Stretch then rotate into principal axes (theta_eff), then confocal map z=(X+iY)/d
            θ = self.theta_eff if self.theta_eff is not None else self.theta
            cθ, sθ = math.cos(θ), math.sin(θ)
            X =  cθ * x_s + sθ * y_s
            Y = -sθ * x_s + cθ * y_s
            z = complex(X, Y) / (self.d if self.d != 0.0 else 1e-15)

        else:
            # circle: no rotation
            X, Y = x_s, y_s
            z = complex(Y, X) / (self.d if self.d != 0.0 else 1e-15)  # (Y + i*X)/d

        # acosh via stable branch; enforce η >= 0 for consistency
        w = cmath.log(z + cmath.sqrt((z - 1.0) * (z + 1.0)))
        if w.real < 0.0:
            w = -w

        eta = w.real
        psi = w.imag % (2.0 * math.pi)
        return (eta, psi)

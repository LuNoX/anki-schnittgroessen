"""Komposition der Kartenbilder: oben/links das System, unten/rechts das Skelett mit Verlauf.

Vorder- und Rückseite haben dasselbe Layout (gleiche Größe, gleiche Datengrenzen); auf der
Vorderseite bleibt das Skelett leer.
"""

from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .. import conventions as cv  # noqa: E402
from ..keypoints import KeyPoint  # noqa: E402
from ..model import SystemDef  # noqa: E402
from ..solver import Result  # noqa: E402
from .base import Canvas, Geo  # noqa: E402
from .diagram import draw_diagram, draw_skeleton  # noqa: E402
from .loads import draw_loads  # noqa: E402
from .structure import draw_dimensions, draw_fiber, draw_hinges, draw_members, draw_supports, draw_triads  # noqa: E402

matplotlib.rcParams.update({
    "mathtext.fontset": cv.MATH_FONTSET,
    "font.family": "serif",
    "font.serif": ["DejaVu Serif"],
    "font.size": cv.FONT_SIZE,
    "svg.hashsalt": "tm-anki",
    "svg.fonttype": "path",
})

TARGET_ASPECT = 1.7


def _draw_system(cv_: Canvas):
    draw_members(cv_)
    draw_fiber(cv_)
    draw_hinges(cv_)
    draw_supports(cv_)
    draw_loads(cv_)
    draw_triads(cv_)
    draw_dimensions(cv_)


def _figure(sysdef: SystemDef, result: Result, qty: str, kps: list[KeyPoint], show: bool):
    """Zwei Durchgänge: der erste ermittelt die Bildgröße, damit die Textgrößen-Schätzung
    (für Platzierung und Ränder) im zweiten zur festen Bildbreite passt."""
    geo = Geo(sysdef.structure)
    inch = cv.FIG_WIDTH_IN / (2.0 * geo.S)
    for _ in range(3):
        fig, W, H = _build(geo, result, qty, kps, show, inch)
        new_inch = min(cv.FIG_WIDTH_IN / W, cv.FIG_MAX_HEIGHT_IN / H)
        if abs(new_inch / inch - 1) < 0.05:
            break
        plt.close(fig)
        inch = new_inch
    fig.set_size_inches(W * new_inch, H * new_inch)
    return fig


def _build(geo: Geo, result: Result, qty: str, kps: list[KeyPoint], show: bool, inch: float):
    u = geo.u
    fig = plt.figure()
    ax1 = fig.add_axes((0, 0, 1, 1))
    ax2 = fig.add_axes((0, 0, 1, 1))
    for ax in (ax1, ax2):
        ax.set_axis_off()
    c1, c2 = Canvas(ax1, geo, inch), Canvas(ax2, geo, inch)
    _draw_system(c1)
    draw_skeleton(c2)
    draw_diagram(c2, result, qty, kps, visible=show)

    pad = 0.5 * u
    e1 = [c1.ext[0] - pad, c1.ext[1] - pad, c1.ext[2] + pad, c1.ext[3] + pad]
    e2 = [c2.ext[0] - pad, c2.ext[1] - pad, c2.ext[2] + pad, c2.ext[3] + pad]
    gap = 0.8 * u
    W1, H1 = e1[2] - e1[0], e1[3] - e1[1]
    W2, H2 = e2[2] - e2[0], e2[3] - e2[1]

    stacked = (max(e1[2], e2[2]) - min(e1[0], e2[0]), H1 + gap + H2)
    side = (W1 + gap + W2, max(e1[3], e2[3]) - min(e1[1], e2[1]))

    def badness(wh):
        return abs(math.log((wh[0] / wh[1]) / TARGET_ASPECT))

    use_stacked = geo.H < 1e-9 or badness(stacked) <= badness(side)
    if use_stacked:
        W, H = stacked
        x0 = min(e1[0], e2[0])
        ax1.set_position((0, (H2 + gap) / H, 1, H1 / H))
        ax2.set_position((0, 0, 1, H2 / H))
        ax1.set_xlim(x0, x0 + W)
        ax2.set_xlim(x0, x0 + W)
        ax1.set_ylim(e1[1], e1[3])
        ax2.set_ylim(e2[1], e2[3])
    else:
        W, H = side
        y0 = min(e1[1], e2[1])
        ax1.set_position((0, 0, W1 / W, 1))
        ax2.set_position(((W1 + gap) / W, 0, W2 / W, 1))
        ax1.set_xlim(e1[0], e1[2])
        ax2.set_xlim(e2[0], e2[2])
        ax1.set_ylim(y0, y0 + H)
        ax2.set_ylim(y0, y0 + H)
    return fig, W, H


def _save(fig, fmt: str) -> bytes:
    buf = io.BytesIO()
    if fmt == "svg":
        fig.savefig(buf, format="svg", transparent=True, metadata={"Date": None})
    else:
        fig.savefig(buf, format="png", transparent=True, dpi=220)
    plt.close(fig)
    return buf.getvalue()


def render_card(sysdef: SystemDef, result: Result, qty: str, kps: list[KeyPoint], fmt: str = "svg"):
    """(Vorderseite, Rückseite) als Bytes."""
    front = _save(_figure(sysdef, result, qty, kps, show=False), fmt)
    back = _save(_figure(sysdef, result, qty, kps, show=True), fmt)
    return front, back

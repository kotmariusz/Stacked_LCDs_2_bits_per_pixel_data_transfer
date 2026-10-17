"""
Four optical states from polarizers that can only turn by 90 degrees.

Three polarizers in series: the first and third turn between 0 and 90 degrees,
the middle one is fixed at 30. What that buys you, what it does not, and where
the fourth state in the real two-panel stack actually comes from.

Render (Manim Community v0.18+):

    manim -pql polarizer_states.py S1_TwoPolarizers
    manim -pql polarizer_states.py S2_MiddlePolarizer
    manim -pql polarizer_states.py S3_WhereTheFourthComesFrom
    manim -pql polarizer_states.py S4_MountTheThirdOffAxis
    manim -pql polarizer_states.py S5_WhyTheLCDMakesColour

    manim -pqh polarizer_states.py -a        # all five, high quality
    python polarizer_states.py               # just print the numbers

Set USE_LATEX = False below if you do not have a LaTeX install; labels fall
back to plain text automatically either way.
"""

from manim import *
import numpy as np
import itertools

USE_LATEX = True

# ---------------------------------------------------------------- parameters

MIDDLE = 30.0          # the fixed middle polarizer, degrees
TURN = 90.0            # how far the outer two can turn
OFFSET3 = 54.0         # scene 4: mount the third polarizer this far round

# Scene 3. A liquid crystal cell is a retarder, and its retardance depends on
# wavelength: a cell trimmed to turn 550 nm by 90 degrees turns red less and
# blue more. 90 * (550 / lambda) is the simplest model that shows the effect.
# The real dispersion curve is not a straight 1/lambda, but the qualitative
# result - and the colours it predicts - are the same.
BANDS = {"R": 650.0, "G": 550.0, "B": 450.0}
LAMBDA0 = 550.0

COL_POL = "#5b8def"     # polarizers that turn
COL_FIX = "#b07bd4"     # the fixed one
COL_BEAM = "#ffd166"    # light
COL_DIM = "#6b7280"
COL_WARN = "#ef476f"
COL_GOOD = "#06d6a0"

STATE_NAMES = ["00", "01", "10", "11"]
COMBOS = list(itertools.product((0.0, TURN), repeat=2))


# ---------------------------------------------------------------- utilities

_LATEX_OK = None


def lab(tex, plain, **kw):
    """MathTex when LaTeX is available, Text otherwise.

    The probe runs once. Without it every label pays for its own failed LaTeX
    run, and a scene with thirty labels takes minutes to fail through them.
    """
    global _LATEX_OK
    if USE_LATEX:
        if _LATEX_OK is None:
            try:
                MathTex("x")
                _LATEX_OK = True
            except Exception:
                _LATEX_OK = False
        if _LATEX_OK:
            try:
                return MathTex(tex, **kw)
            except Exception:
                pass
    size = kw.pop("font_size", 28)      # Text runs larger than MathTex
    return Text(plain, font_size=size * 0.84, **kw)


def hexcol(rgb):
    r, g, b = (int(np.clip(c, 0, 1) * 255) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def c2(deg):
    """Malus: the fraction of linearly polarized light a polarizer passes."""
    return float(np.cos(np.radians(deg)) ** 2)


def polarizer(angle_deg, radius=0.52, color=COL_POL, n=7):
    """A polarizer seen face on: an aperture hatched along its axis."""
    g = VGroup(Circle(radius=radius, color=color, stroke_width=3.5))
    for i in range(n):
        y = (-1 + 2 * (i + 0.5) / n) * radius
        half = float(np.sqrt(max(radius ** 2 - y ** 2, 0.0)))
        g.add(Line([-half, y, 0], [half, y, 0], stroke_width=2, color=color))
    g.rotate(np.radians(angle_deg))
    return g


def pol_disc(angle_deg, radius=0.3):
    """Polarization looking down the beam: the transverse plane, face on."""
    ring = Circle(radius=radius, color=COL_DIM, stroke_width=1.8)
    ring.set_stroke(opacity=0.6)
    arrow = DoubleArrow([-radius * 0.86, 0, 0], [radius * 0.86, 0, 0], buff=0,
                        color=COL_BEAM, stroke_width=3, tip_length=0.13)
    arrow.rotate(np.radians(angle_deg))
    return VGroup(ring, arrow)


def beam(a, b, intensity):
    i = float(np.clip(intensity, 0, 1))
    seg = Line(a, b, color=COL_BEAM)
    seg.set_stroke(width=1.5 + 9 * i, opacity=0.18 + 0.82 * i)
    return seg


def bar_chart(values, names, base_y=-3.05, height=2.05, width=0.74,
              gap=1.42, colors=None):
    n = len(values)
    xs = [(i - (n - 1) / 2) * gap for i in range(n)]
    top = max(max(values), 1e-9)
    bars = VGroup()
    for i, (x, v, nm) in enumerate(zip(xs, values, names)):
        col = colors[i] if colors else COL_BEAM
        h = max(height * v / top, 0.012)
        bar = Rectangle(width=width, height=h, fill_color=col,
                        fill_opacity=0.9, stroke_color=col, stroke_width=1.5)
        bar.move_to([x, base_y + h / 2, 0])
        name = lab(rf"\mathtt{{{nm}}}", nm, font_size=30, color=WHITE)
        name.move_to([x, base_y - 0.32, 0])
        val = lab(rf"{v:.3f}", f"{v:.3f}", font_size=26, color=COL_DIM)
        val.move_to([x, base_y + h + 0.26, 0])
        bars.add(VGroup(bar, name, val))
    axis = Line([xs[0] - 0.75, base_y, 0], [xs[-1] + 0.75, base_y, 0],
                stroke_width=2, color=COL_DIM)
    return VGroup(axis, bars)


# ---------------------------------------------------------------- bench

class Bench(Scene):
    """A row of polarizers, some of which turn between two positions.

    Subclasses give the element list; everything else - the beam, the
    intensities, the chart - follows from Malus's law applied down the row.
    """

    bench_y = 1.15
    offsets = (0.0, 0.0)      # where each turning polarizer is mounted
    title_text = ""
    title_plain = ""

    def elements(self):
        """[(kind, angle, name)] left to right; kind is 'turn' or 'fixed'."""
        raise NotImplementedError

    # -- physics -----------------------------------------------------------

    def axes(self, t1, t2):
        """The absolute axis angle of every element, for this setting."""
        turns, out, k = [t1, t2], [], 0
        for kind, ang, _ in self.elements():
            if kind == "turn":
                out.append(turns[k] + self.offsets[k])
                k += 1
            else:
                out.append(ang)
        return out

    def trace(self, t1, t2):
        """[(polarization angle, intensity)] after each element.

        Intensity 1.0 is the light leaving the FIRST polarizer, so the
        unpolarized-input factor of 0.5 is left out throughout - it scales
        every state equally and so says nothing about the states.
        """
        a = self.axes(t1, t2)
        out, inten = [], 1.0
        for i, ang in enumerate(a):
            if i:
                inten *= c2(ang - a[i - 1])
            out.append((ang, inten))
        return out

    def intensities(self):
        return [self.trace(t1, t2)[-1][1] for t1, t2 in COMBOS]

    # -- drawing -----------------------------------------------------------

    def build_bench(self):
        specs = self.elements()
        n = len(specs)
        span = min(8.6, 2.9 * n)
        self.xs = [-span / 2 + span * i / (n - 1) for i in range(n)]
        self.specs = specs

        start = self.axes(*COMBOS[0])
        self.glyphs, self.labels = VGroup(), VGroup()
        self.turners, self.turn_now = [], []
        for x, (kind, _, name), ang in zip(self.xs, specs, start):
            g = polarizer(ang, color=COL_POL if kind == "turn" else COL_FIX)
            g.move_to([x, self.bench_y, 0])
            self.glyphs.add(g)
            if kind == "turn":
                self.turners.append(g)
                self.turn_now.append(ang)
            t = lab(rf"\text{{{name}}}", name, font_size=21, color=COL_DIM)
            t.move_to([x, self.bench_y + 1.02, 0])
            self.labels.add(t)

        self.source = VGroup(
            Line([self.xs[0] - 1.35, self.bench_y, 0],
                 [self.xs[0] - 0.62, self.bench_y, 0],
                 color=COL_DIM, stroke_width=3),
            lab(r"\text{light in}", "light in", font_size=20, color=COL_DIM)
            .move_to([self.xs[0] - 1.0, self.bench_y + 0.5, 0]))
        return VGroup(self.source, self.glyphs, self.labels)

    def light_group(self, t1, t2):
        tr, xs = self.trace(t1, t2), self.xs
        g = VGroup()
        for i in range(len(xs) - 1):
            ang, inten = tr[i]
            g.add(beam([xs[i] + 0.62, self.bench_y, 0],
                       [xs[i + 1] - 0.62, self.bench_y, 0], inten))
            d = pol_disc(ang)
            d.move_to([(xs[i] + xs[i + 1]) / 2, self.bench_y + 1.74, 0])
            g.add(d)
        ang, inten = tr[-1]
        g.add(beam([xs[-1] + 0.62, self.bench_y, 0],
                   [xs[-1] + 1.9, self.bench_y, 0], inten))
        return g

    def badges(self, t1, t2):
        """The axis angle written under each polarizer."""
        g = VGroup()
        for x, (kind, _, _), ang in zip(self.xs, self.specs,
                                        self.axes(t1, t2)):
            col = COL_POL if kind == "turn" else COL_FIX
            txt = lab(rf"{int(round(ang))}^\circ", f"{int(round(ang))}°",
                      font_size=30, color=col)
            txt.move_to([x, self.bench_y - 1.08, 0])
            g.add(txt)
        return g

    def turn_to(self, t1, t2):
        """Animations that physically turn the rotatable polarizers."""
        want, anims, k = [], [], 0
        for kind, _, _ in self.elements():
            if kind == "turn":
                want.append([t1, t2][k] + self.offsets[k])
                k += 1
        for g, now, target in zip(self.turners, self.turn_now, want):
            if abs(target - now) > 1e-6:
                anims.append(Rotate(g, np.radians(target - now)))
        self.turn_now = want
        return anims

    # -- the shared walk through all four settings -------------------------

    def show_title(self):
        t = lab(self.title_text, self.title_plain, font_size=34)
        t.to_edge(UP, buff=0.42)
        self.play(FadeIn(t, shift=DOWN * 0.2))
        return t

    def clear_bench(self, chart, *extra):
        """Drop the bench and lift the chart, making room to conclude.

        There is no gap on a 16:9 frame that fits a bench, a chart and three
        lines of prose at once; without this the closing text lands on the bars.
        """
        self.play(FadeOut(VGroup(self.source, self.glyphs, self.labels,
                                 *extra)),
                  chart.animate.shift(UP * 1.0).scale(1.18), run_time=0.9)

    def walk(self, caption=False):
        """Step through the four settings, filling the chart as we go."""
        vals = self.intensities()
        light, badge = self.light_group(*COMBOS[0]), self.badges(*COMBOS[0])
        self.play(Create(light), FadeIn(badge), run_time=1.2)
        chart = bar_chart([0.0] * 4, STATE_NAMES)
        self.play(Create(chart[0]), FadeIn(chart[1]), run_time=0.8)

        shown = []
        for k, (t1, t2) in enumerate(COMBOS):
            if k:
                nl, nb = self.light_group(t1, t2), self.badges(t1, t2)
                self.play(*self.turn_to(t1, t2),
                          ReplacementTransform(light, nl),
                          ReplacementTransform(badge, nb), run_time=0.95)
                light, badge = nl, nb
            cap = None
            if caption:
                a = self.axes(t1, t2)
                f1, f2 = c2(a[1] - a[0]), c2(a[2] - a[1])
                cap = lab(rf"{f1:.3f} \times {f2:.3f} = {vals[k]:.3f}",
                          f"{f1:.3f} × {f2:.3f} = {vals[k]:.3f}",
                          font_size=28, color=COL_BEAM)
                cap.move_to([4.45, -1.5, 0])
                self.play(FadeIn(cap, shift=UP * 0.1), run_time=0.45)
            shown.append(vals[k])
            new = bar_chart(shown + [0.0] * (4 - len(shown)), STATE_NAMES)
            self.play(ReplacementTransform(chart, new), run_time=0.55)
            chart = new
            self.wait(0.4)
            if cap:
                self.play(FadeOut(cap), run_time=0.25)
        return chart, light, badge


# ---------------------------------------------------------------- scene 1

class S1_TwoPolarizers(Bench):
    """Two polarizers that only turn by 90 degrees: two outcomes, not four."""

    title_text = (r"\text{Two polarizers, each turning }0^\circ"
                  r"\text{ or }90^\circ")
    title_plain = "Two polarizers, each turning 0° or 90°"

    def elements(self):
        return [("turn", None, "polarizer 1"), ("turn", None, "polarizer 2")]

    def construct(self):
        self.show_title()
        self.build_bench()
        self.play(FadeIn(self.source), Create(self.glyphs),
                  FadeIn(self.labels), run_time=1.6)
        chart, light, badge = self.walk()

        self.clear_bench(chart, light, badge)
        note = VGroup(
            lab(r"\text{four settings}\ \longrightarrow\ "
                r"\text{two intensities}",
                "four settings  →  two intensities",
                font_size=32, color=COL_BEAM),
            lab(r"\text{only the difference between the two axes matters}",
                "only the difference between the two axes matters",
                font_size=26, color=WHITE),
            lab(r"0^\circ\text{ apart or }90^\circ"
                r"\text{ apart - that is one bit}",
                "0° apart or 90° apart — that is one bit",
                font_size=26, color=COL_DIM),
        ).arrange(DOWN, buff=0.22).move_to([0, 2.0, 0])
        self.play(FadeIn(note, shift=UP * 0.15), run_time=1.1)
        self.wait(2.4)


# ---------------------------------------------------------------- scene 2

class S2_MiddlePolarizer(Bench):
    """A third polarizer fixed at 30 degrees in the middle: three levels."""

    title_text = (r"\text{Add a third, fixed at }30^\circ"
                  r"\text{, in the middle}")
    title_plain = "Add a third, fixed at 30°, in the middle"

    def elements(self):
        return [("turn", None, "polarizer 1"),
                ("fixed", MIDDLE, f"fixed {int(MIDDLE)}°"),
                ("turn", None, "polarizer 3")]

    def construct(self):
        self.show_title()
        self.build_bench()
        self.play(FadeIn(self.source), Create(self.glyphs),
                  FadeIn(self.labels), run_time=1.6)
        chart, light, badge = self.walk(caption=True)

        self.clear_bench(chart, light, badge)
        box = SurroundingRectangle(VGroup(chart[1][1], chart[1][2]),
                                   color=COL_WARN, buff=0.14, stroke_width=3)
        self.play(Create(box), run_time=0.8)
        note = VGroup(
            lab(r"\texttt{01}\text{ and }\texttt{10}\text{ are equal}",
                "01 and 10 are equal", font_size=32, color=COL_WARN),
            lab(r"\cos^4\!\theta,\ \ \cos^2\!\theta\sin^2\!\theta,\ \ "
                r"\sin^2\!\theta\cos^2\!\theta,\ \ \sin^4\!\theta",
                "cos⁴θ,  cos²θ sin²θ,  sin²θ cos²θ,  sin⁴θ",
                font_size=28, color=WHITE),
            lab(r"\text{for any middle angle, while both ends switch }"
                r"0^\circ/90^\circ",
                "for any middle angle, while both ends switch 0°/90°",
                font_size=24, color=COL_DIM),
            lab(r"\text{three levels, not four}", "three levels, not four",
                font_size=30, color=COL_BEAM),
        ).arrange(DOWN, buff=0.2).move_to([0, 2.05, 0])
        self.play(FadeIn(note, shift=UP * 0.15), run_time=1.3)
        self.wait(2.8)


# ---------------------------------------------------------------- scene 3

def band_rotations():
    return {k: TURN * LAMBDA0 / lam for k, lam in BANDS.items()}


def colour_states(symmetric):
    """The four states in RGB once the 90 degrees is wavelength dependent.

    symmetric=True   both ends turn, mirrored about the middle polarizer
    symmetric=False  the cells turn, the final analyser stays put at 0
    """
    rot, out = band_rotations(), {}
    for s1, s3 in itertools.product((0, 1), repeat=2):
        rgb = []
        for k in ("R", "G", "B"):
            r = rot[k]
            if symmetric:
                rgb.append(c2(MIDDLE - s1 * r) * c2(s3 * r - MIDDLE))
            else:
                rgb.append(c2(MIDDLE - s1 * r) * c2(MIDDLE + s3 * r))
        out[f"{s1}{s3}"] = np.array(rgb)
    return out


class S3_WhereTheFourthComesFrom(Scene):
    """Colour only breaks the tie if the stack is not symmetric."""

    def construct(self):
        title = lab(r"\text{Where the fourth state comes from}",
                    "Where the fourth state comes from", font_size=36)
        title.to_edge(UP, buff=0.4)
        self.play(FadeIn(title, shift=DOWN * 0.2))

        rot = band_rotations()
        prem = VGroup(
            lab(r"\text{the }90^\circ\text{ is really }90^\circ"
                r"\times 550/\lambda\ \text{ - a cell is a retarder}",
                "the 90° is really 90° × 550/λ — a cell is a retarder",
                font_size=25),
            lab(rf"650\,\text{{nm}}:{rot['R']:.0f}^\circ\quad"
                rf"550\,\text{{nm}}:{rot['G']:.0f}^\circ\quad"
                rf"450\,\text{{nm}}:{rot['B']:.0f}^\circ",
                f"650 nm: {rot['R']:.0f}°    550 nm: {rot['G']:.0f}°    "
                f"450 nm: {rot['B']:.0f}°",
                font_size=25, color=COL_DIM),
        ).arrange(DOWN, buff=0.16).move_to([0, 2.45, 0])
        self.play(FadeIn(prem), run_time=1.1)

        peak = max(float(v.max()) for sym in (True, False)
                   for v in colour_states(sym).values())

        def row(symmetric, y, heading, hcol):
            cols = colour_states(symmetric)
            head = lab(rf"\text{{{heading}}}", heading,
                       font_size=24, color=hcol)
            head.move_to([-4.45, y + 0.1, 0])
            sw = VGroup()
            for nm in STATE_NAMES:
                disp = np.clip(cols[nm] / peak, 0, 1) ** (1 / 2.2)
                sq = Square(side_length=0.92, fill_opacity=1.0,
                            fill_color=hexcol(disp),
                            stroke_color=WHITE, stroke_width=1.4)
                tag = lab(rf"\mathtt{{{nm}}}", nm, font_size=24)
                sw.add(VGroup(sq, tag).arrange(DOWN, buff=0.09))
            sw.arrange(RIGHT, buff=0.3).move_to([1.55, y, 0])
            return VGroup(head, sw), sw

        g1, sw1 = row(True, 0.75, "both ends turn (symmetric)", COL_WARN)
        g2, sw2 = row(False, -1.55, "cells turn, analyser fixed", COL_GOOD)

        self.play(FadeIn(g1, shift=UP * 0.12), run_time=1.1)
        b1 = SurroundingRectangle(VGroup(sw1[1], sw1[2]), color=COL_WARN,
                                  buff=0.1, stroke_width=3)
        c1 = lab(r"\text{identical}", "identical", font_size=24,
                 color=COL_WARN).move_to([5.45, 0.75, 0])
        self.play(Create(b1), FadeIn(c1), run_time=0.9)
        self.wait(1.0)

        self.play(FadeIn(g2, shift=UP * 0.12), run_time=1.1)
        b2 = SurroundingRectangle(VGroup(sw2[1], sw2[2]), color=COL_GOOD,
                                  buff=0.1, stroke_width=3)
        c2_ = lab(r"\text{four colours}", "four colours", font_size=24,
                  color=COL_GOOD).move_to([5.45, -1.55, 0])
        self.play(Create(b2), FadeIn(c2_), run_time=0.9)

        cap = lab(r"\text{the stack reads orange, cyan, green, purple: "
                  r"RGB }\approx 100\%\text{, grey }\approx 57\%",
                  "the stack reads orange, cyan, green, purple: "
                  "RGB ≈ 100%, grey ≈ 57%",
                  font_size=25, color=WHITE).move_to([0, -3.2, 0])
        self.play(FadeIn(cap, shift=UP * 0.12), run_time=1.0)
        self.wait(3.0)


# ---------------------------------------------------------------- scene 4

class S4_MountTheThirdOffAxis(Bench):
    """Four intensities from three polarizers, with no colour needed."""

    offsets = (0.0, OFFSET3)
    title_text = (r"\text{...or mount the third polarizer turned by }"
                  r"54^\circ")
    title_plain = "...or mount the third polarizer turned by 54°"

    def elements(self):
        return [("turn", None, "polarizer 1"),
                ("fixed", MIDDLE, f"fixed {int(MIDDLE)}°"),
                ("turn", None, f"polarizer 3, +{int(OFFSET3)}°")]

    def construct(self):
        self.show_title()
        self.build_bench()
        self.play(FadeIn(self.source), Create(self.glyphs),
                  FadeIn(self.labels), run_time=1.6)
        chart, light, badge = self.walk(caption=True)

        self.clear_bench(chart, light, badge)
        vals = sorted(self.intensities())
        gap = min(vals[i + 1] - vals[i] for i in range(3))
        note = VGroup(
            lab(r"\text{four distinct intensities}",
                "four distinct intensities", font_size=32, color=COL_BEAM),
            lab(r"\text{it still turns by }90^\circ"
                r"\text{ - it is only mounted differently}",
                "it still turns by 90° — it is only mounted differently",
                font_size=26, color=WHITE),
            lab(rf"\text{{smallest gap }}{gap:.3f}"
                rf"\text{{, so colour still separates them better}}",
                f"smallest gap {gap:.3f}, so colour still separates them "
                f"better", font_size=24, color=COL_DIM),
        ).arrange(DOWN, buff=0.2).move_to([0, 2.05, 0])
        self.play(FadeIn(note, shift=UP * 0.15), run_time=1.2)
        self.wait(2.8)


# ---------------------------------------------------------------- scene 5

# Why the liquid crystal can make colour and a polarizer cannot.
#
# The layer in this scene is illustrative: birefringent, its axes at 45° to
# the incoming polarization, with a delay of 1.5 waves at 550 nm
# (dn*d = 0.825 um). One and a half waves turns 550 nm by exactly 90°, so it
# is one of the "90° switches" of the earlier scenes, and about 0.8 um is a
# typical retardation for STN glass. It shows the mechanism; it is not fitted
# to these particular panels - OPTICS.md explains why such a fit fails.

DND_DEMO = 0.825                                     # microns
DEMO = (("red", 650.0, "#ff5a5a"),
        ("green", 550.0, "#3fbf6a"),
        ("blue", 450.0, "#5b8def"))

# Measured on the real stack: raw camera RGB averaged over ~9,500 cells per
# state from a decoded recording (see OPTICS.md). Bit 0 drives panel 1.
MEASURED_STATES = (
    ("00", "both off",   (0.9862, 0.7728, 0.5063)),
    ("01", "panel 1 on", (0.8150, 0.7230, 0.7731)),
    ("10", "panel 2 on", (0.7739, 0.9360, 0.5474)),
    ("11", "both on",    (0.5854, 0.8672, 0.8240)),
)


def txt(s, size=24, **kw):
    """Plain text for labels that change every frame.

    MathTex would recompile LaTeX for every new value; Text is cached and
    fast, and needs no LaTeX install."""
    return Text(s, font_size=size * 0.84, **kw)


def delay_waves(dnd_um, lam_nm):
    """How far the slow component falls behind, in waves: dn*d / lambda."""
    return dnd_um * 1000.0 / lam_nm


def exit_field(waves):
    """Light polarized along x, through a layer with its axes at +-45°.

    Returns the complex field (Ex, Ey) after the slow component has fallen
    `waves` behind. No delay leaves the light as it was; half a wave - or 1.5,
    2.5 - turns it by exactly 90°; anything in between leaves it elliptical."""
    e = np.exp(-2j * np.pi * waves)
    return (e + 1) / 2, (e - 1) / 2


def passed(field, analyser_deg):
    """Fraction of that light a polarizer at analyser_deg lets through."""
    a = np.radians(analyser_deg)
    ex, ey = field
    return float(abs(ex * np.cos(a) + ey * np.sin(a)) ** 2)


def show_rgb(rgb):
    """Linear light to a display colour (gamma 2.2)."""
    return hexcol(np.clip(np.asarray(rgb, float), 0, 1) ** (1 / 2.2))


def lam_colour(lam):
    """A display colour for a wavelength between the three demo bands."""
    pts = [(450.0, DEMO[2][2]), (550.0, DEMO[1][2]), (650.0, DEMO[0][2])]
    lam = float(np.clip(lam, 450.0, 650.0))
    for (l0, c0), (l1, c1) in zip(pts, pts[1:]):
        if lam <= l1:
            return interpolate_color(ManimColor(c0), ManimColor(c1),
                                     (lam - l0) / (l1 - l0))
    return ManimColor(pts[-1][1])


def pol_ellipse(field, radius, colour, width=5):
    """The path the field traces, looking down the beam."""
    ex, ey = field

    def f(t):
        z = np.exp(1j * t)
        return np.array([radius * np.real(ex * z), radius * np.real(ey * z), 0.0])
    return ParametricFunction(f, t_range=[0, 2 * np.pi, 0.02],
                              color=colour, stroke_width=width)


def molecules(x0, x1, y0, y1, tilt=0.0, nx=5, ny=8, colour="#6f9fe0"):
    """Rod-shaped molecules, side on. The light travels left to right, so the
    panel's plane is vertical here: tilt 0 lies in the panel, tilt 1 stands
    along the beam."""
    g = VGroup()
    for x in np.linspace(x0 + 0.3, x1 - 0.3, nx):
        for y in np.linspace(y0 + 0.35, y1 - 0.35, ny):
            m = Ellipse(width=0.13, height=0.44, color=colour,
                        fill_opacity=0.85, stroke_width=0)
            m.rotate(-tilt * PI / 2).move_to([x, y, 0])
            g.add(m)
    return g


class S5_WhyTheLCDMakesColour(ThreeDScene):
    """A polarizer only ever sees an angle, so it scales every colour alike.
    A liquid crystal delays one polarization by a fixed distance, which is a
    different number of waves for every colour - and that is the colour."""

    def construct(self):
        self.polarizers_are_colour_blind()
        self.two_speeds()
        self.three_colours()
        self.driving_a_pixel()
        self.four_states()

    # -- helpers -----------------------------------------------------------

    def title(self, tex, plain):
        t = lab(tex, plain, font_size=34).to_edge(UP, buff=0.4)
        self.play(FadeIn(t, shift=DOWN * 0.2))
        return t

    def caption(self, lines, y=-3.0, colours=None, size=24):
        g = VGroup(*[txt(s, size, color=(colours[i] if colours else WHITE))
                     for i, s in enumerate(lines)])
        g.arrange(DOWN, buff=0.14).move_to([0, y, 0])
        return g

    def clear(self):
        self.play(*[FadeOut(m) for m in self.mobjects], run_time=0.8)

    # -- 1 -----------------------------------------------------------------

    def polarizers_are_colour_blind(self):
        self.title(r"\text{A polarizer cannot make colour}",
                   "A polarizer cannot make colour")
        th = ValueTracker(0.0)
        y, xp1, xp2 = 1.0, -4.3, -1.5

        src = txt("white light", 20, color=COL_DIM).move_to([-6.1, y + 0.5, 0])
        inbeam = Line([-6.9, y, 0], [xp1 - 0.6, y, 0], color=WHITE,
                      stroke_width=9)
        p1 = polarizer(0).move_to([xp1, y, 0])
        mid = Line([xp1 + 0.6, y, 0], [xp2 - 0.6, y, 0], color=WHITE,
                   stroke_width=7)
        p2 = always_redraw(lambda: polarizer(th.get_value())
                           .move_to([xp2, y, 0]))
        l1 = txt("0°", 26, color=COL_POL).move_to([xp1, y - 0.95, 0])
        l2 = always_redraw(lambda: txt(f"{th.get_value():.0f}°", 26,
                                       color=COL_POL)
                           .move_to([xp2, y - 0.95, 0]))
        out = always_redraw(lambda: Line(
            [xp2 + 0.6, y, 0], [0.6, y, 0], color=WHITE,
            stroke_width=2 + 6 * c2(th.get_value()),
            stroke_opacity=0.15 + 0.85 * c2(th.get_value())))

        bx, base, H = (1.6, 2.5, 3.4), -1.5, 2.6

        def bars():
            v = c2(th.get_value())          # the same fraction for every colour
            g = VGroup()
            for x, (_, _, col) in zip(bx, DEMO):
                h = max(H * v, 0.015)
                g.add(Rectangle(width=0.62, height=h, fill_color=col,
                                fill_opacity=0.9, stroke_width=0)
                      .move_to([x, base + h / 2, 0]))
            return g
        rgb_bars = always_redraw(bars)
        axis = Line([1.1, base, 0], [3.9, base, 0], color=COL_DIM)
        names = VGroup(*[txt(n, 22, color=c).move_to([x, base - 0.3, 0])
                         for x, n, c in zip(bx, ("R", "G", "B"),
                                            [d[2] for d in DEMO])])
        swatch = always_redraw(lambda: Square(
            side_length=1.7, fill_color=show_rgb([c2(th.get_value())] * 3),
            fill_opacity=1, stroke_color=WHITE, stroke_width=2)
            .move_to([5.6, -0.15, 0]))
        sw_lab = txt("what comes out", 20, color=COL_DIM).move_to([5.6, 1.15, 0])

        self.play(FadeIn(src), Create(inbeam), Create(p1), FadeIn(l1),
                  Create(mid), FadeIn(p2), FadeIn(l2), run_time=1.4)
        self.add(out)
        self.play(Create(axis), FadeIn(names), FadeIn(rgb_bars),
                  FadeIn(swatch), FadeIn(sw_lab), run_time=1.0)
        self.play(th.animate.set_value(90), run_time=3.2, rate_func=smooth)
        self.play(th.animate.set_value(35), run_time=2.0, rate_func=smooth)

        cap = self.caption(
            ["Each colour passes the same fraction, cos²θ.",
             "θ is an angle — no wavelength appears anywhere —",
             "so polarizers change brightness, never colour."],
            y=-3.05, colours=[WHITE, COL_DIM, COL_BEAM])
        self.play(FadeIn(cap, shift=UP * 0.15), run_time=1.0)
        self.wait(2.6)
        self.clear()

    # -- 2 -----------------------------------------------------------------

    def fixed(self, *mobs):
        """Pin text to the screen while the camera looks at the 3D part.

        Pinning also adds the mobject to the scene, so pin each one right
        before the animation that brings it in."""
        self.add_fixed_in_frame_mobjects(*mobs)
        return mobs[0] if len(mobs) == 1 else VGroup(*mobs)

    def two_speeds(self):
        """An ellipsometry-style view of light going through the layer.

        The beam runs along x and the molecules stand along z, so the part of
        the field along z is slowed and the part along y is not. Each wave gets
        its own lane: the light itself along the beam, its slow part as a
        shadow on a back wall above it, its fast part on a floor below it."""
        XA, XB = -2.6, 0.8                       # the layer, along the beam
        X0, X1 = -6.3, 4.6
        XIN, XOUT = -5.7, 3.9                    # the two end-on rings
        AMP = 0.75                               # each of the two parts
        YW, ZF = 3.7, -2.45                      # back wall, floor
        H = AMP + 0.25
        lam = ValueTracker(550.0)
        tt = ValueTracker(0.0)                   # time, as a phase
        C_SLOW, C_FAST = "#c792ff", "#7fd6e8"
        C_LAYER = "#3b6db3"

        def period(l):
            return 2.5 * l / 550.0

        def ph_fast(x, l, t):
            return 2 * np.pi * (x - X0) / period(l) - t

        def ph_slow(x, l, t):
            # the part along the molecules gathers extra phase in the layer:
            # its crests crowd together there and arrive late after it
            return ph_fast(x, l, t) + 2 * np.pi * delay_waves(DND_DEMO, l) * \
                np.clip((x - XA) / (XB - XA), 0, 1)

        def field(x, l, t):
            return np.array([x, AMP * np.cos(ph_fast(x, l, t)),
                             AMP * np.cos(ph_slow(x, l, t))])

        # -- scenery -----------------------------------------------------
        title = self.fixed(lab(r"\text{A liquid crystal has two speeds}",
                               "A liquid crystal has two speeds", font_size=34)
                           .to_edge(UP, buff=0.4))
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.8)

        axis = Arrow3D([X0 - 0.2, 0, 0], [X1 + 0.5, 0, 0], color=COL_DIM,
                       thickness=0.008, height=0.22, base_radius=0.06)
        slab = Prism(dimensions=[XB - XA, 2.2, 2.2]).move_to([(XA + XB) / 2, 0, 0])
        slab.set_fill(C_LAYER, opacity=0.10)
        slab.set_stroke("#6f9fe0", width=1, opacity=0.5)
        rods = VGroup(*[
            Line([x, y, -0.42], [x, y, 0.42], color="#6f9fe0",
                 stroke_width=6, stroke_opacity=0.8)
            for x in np.linspace(XA + 0.55, XB - 0.55, 3) for y in (-0.8, 0.8)])

        def wall(points, colour):
            return Polygon(*points, stroke_color=colour, stroke_width=1,
                           stroke_opacity=0.35, fill_color=colour,
                           fill_opacity=0.05)

        back = wall([[X0, YW, -H], [X1, YW, -H], [X1, YW, H], [X0, YW, H]],
                    C_SLOW)
        floor = wall([[X0, -H, ZF], [X1, -H, ZF], [X1, H, ZF], [X0, H, ZF]],
                     C_FAST)
        # where the layer is, marked on both walls
        bands = VGroup(
            Polygon([XA, YW - 0.01, -H], [XB, YW - 0.01, -H],
                    [XB, YW - 0.01, H], [XA, YW - 0.01, H],
                    stroke_width=0, fill_color=C_LAYER, fill_opacity=0.22),
            Polygon([XA, -H, ZF + 0.01], [XB, -H, ZF + 0.01],
                    [XB, H, ZF + 0.01], [XA, H, ZF + 0.01],
                    stroke_width=0, fill_color=C_LAYER, fill_opacity=0.22))

        def ring(xc):
            return Circle(radius=AMP * 1.45, color=COL_DIM, stroke_width=1.5) \
                .rotate(PI / 2, axis=UP).move_to([xc, 0, 0])

        rings = VGroup(ring(XIN), ring(XOUT))

        self.move_camera(phi=56 * DEGREES, theta=-80 * DEGREES, zoom=0.86,
                         added_anims=[FadeIn(axis), FadeIn(slab), FadeIn(rods),
                                      FadeIn(rings), FadeIn(back),
                                      FadeIn(floor), FadeIn(bands)],
                         run_time=2.2)

        # -- the light ---------------------------------------------------
        def comb():
            l, t = lam.get_value(), tt.get_value()
            return VGroup(*[Line([x, 0, 0], field(x, l, t), color=lam_colour(l),
                                 stroke_width=1.3, stroke_opacity=0.35)
                            for x in np.arange(X0 + 0.15, X1, 0.3)])

        def resultant():
            l, t = lam.get_value(), tt.get_value()
            return ParametricFunction(lambda x: field(x, l, t),
                                      t_range=[X0, X1, 0.02],
                                      color=lam_colour(l), stroke_width=4)

        def part_slow():
            l, t = lam.get_value(), tt.get_value()
            return ParametricFunction(
                lambda x: np.array([x, YW, AMP * np.cos(ph_slow(x, l, t))]),
                t_range=[X0, X1, 0.02], color=C_SLOW, stroke_width=3.5)

        def part_fast():
            l, t = lam.get_value(), tt.get_value()
            return ParametricFunction(
                lambda x: np.array([x, AMP * np.cos(ph_fast(x, l, t)), ZF]),
                t_range=[X0, X1, 0.02], color=C_FAST, stroke_width=3.5)

        def end_on(xc):
            # the path the field's tip traces at this point, over one cycle
            l = lam.get_value()
            cf, cs = ph_fast(xc, l, 0), ph_slow(xc, l, 0)
            return ParametricFunction(
                lambda s: np.array([xc, AMP * np.cos(cf - s),
                                    AMP * np.cos(cs - s)]),
                t_range=[0, 2 * np.pi, 0.03], color=lam_colour(l),
                stroke_width=3.5)

        def tip(xc):
            l, t = lam.get_value(), tt.get_value()
            p = field(xc, l, t)
            return VGroup(Line([xc, 0, 0], p, color=WHITE, stroke_width=2.5),
                          Dot3D(p, radius=0.06, color=WHITE))

        def inset(xc, centre):
            # the same point seen end-on, flat: across = right, along = up
            l, t = lam.get_value(), tt.get_value()
            cf, cs = ph_fast(xc, l, 0), ph_slow(xc, l, 0)
            r, c = 0.6, np.array(centre)
            path = ParametricFunction(
                lambda s: c + np.array([r * np.cos(cf - s),
                                        r * np.cos(cs - s), 0]),
                t_range=[0, 2 * np.pi, 0.03], color=lam_colour(l),
                stroke_width=4)
            dot = Dot(c + np.array([r * np.cos(cf - t), r * np.cos(cs - t), 0]),
                      radius=0.06, color=WHITE)
            return VGroup(Circle(radius=r * 1.25, color=COL_DIM,
                                 stroke_width=1.5).move_to(c), path, dot)

        IN_AT, OUT_AT = (6.0, 0.75, 0), (6.0, -1.75, 0)
        teeth = always_redraw(comb)
        light = always_redraw(resultant)
        slow = always_redraw(part_slow)
        fast = always_redraw(part_fast)
        path_in = always_redraw(lambda: end_on(XIN))
        path_out = always_redraw(lambda: end_on(XOUT))
        tip_in = always_redraw(lambda: tip(XIN))
        tip_out = always_redraw(lambda: tip(XOUT))
        flat_in = always_redraw(lambda: inset(XIN, IN_AT))
        flat_out = always_redraw(lambda: inset(XOUT, OUT_AT))
        lab_in = txt("going in", 20, color=COL_DIM).move_to([6.0, 1.7, 0])
        lab_out = txt("coming out", 20, color=COL_DIM).move_to([6.0, -0.8, 0])

        cap1 = self.caption(
            ["The light arrives polarized at 45° to the molecules:",
             "every arrow of its field lies in one tilted plane."],
            y=-3.35, size=22)
        self.fixed(flat_in, lab_in, cap1)
        self.play(FadeIn(teeth), FadeIn(light), FadeIn(path_in),
                  FadeIn(tip_in), FadeIn(flat_in), FadeIn(lab_in),
                  FadeIn(cap1), run_time=1.2)
        self.play(tt.animate.increment_value(2 * np.pi), run_time=2.6,
                  rate_func=linear)

        # each shadow gets a label in its own lane
        lab_slow = txt("its part along the molecules: slower", 20,
                       color=C_SLOW).move_to([-3.2, 2.62, 0])
        lab_fast = txt("its part across them: faster", 20,
                       color=C_FAST).move_to([-3.6, -2.62, 0])
        cap2 = self.caption(
            ["That is two equal parts, one along the molecules and one across.",
             "Along them the light is slower, so that part falls behind."],
            y=-3.35, size=22)
        self.fixed(lab_slow, lab_fast, cap2)
        self.play(FadeOut(cap1), FadeIn(slow), FadeIn(fast), FadeIn(lab_slow),
                  FadeIn(lab_fast), FadeIn(cap2), run_time=1.2)
        self.play(tt.animate.increment_value(3 * np.pi), run_time=3.4,
                  rate_func=linear)

        readout = always_redraw(lambda: VGroup(
            txt(f"{lam.get_value():.0f} nm", 26,
                color=lam_colour(lam.get_value())),
            txt(f"falls {delay_waves(DND_DEMO, lam.get_value()):.2f} waves "
                f"behind", 22))
            .arrange(DOWN, buff=0.08).move_to([5.3, 2.75, 0]))
        cap3 = self.caption(
            ["1.5 waves behind: the two parts leave exactly out of step,",
             "so green comes out turned by 90°."],
            y=-3.35, size=22)
        self.fixed(readout, flat_out, lab_out, cap3)
        self.play(FadeOut(cap2), FadeIn(readout), FadeIn(path_out),
                  FadeIn(tip_out), FadeIn(flat_out), FadeIn(lab_out),
                  FadeIn(cap3), run_time=1.0)
        self.play(tt.animate.increment_value(3 * np.pi), run_time=3.0,
                  rate_func=linear)

        cap4 = self.caption(
            ["The same layer puts red 1.27 waves behind and blue 1.83,",
             "so every colour leaves with a different polarization."],
            y=-3.35, size=22)
        self.fixed(cap4)
        self.play(FadeOut(cap3), FadeIn(cap4), run_time=0.6)
        for target, secs in ((650, 2.8), (450, 3.8), (550, 2.2)):
            self.play(lam.animate(rate_func=smooth).set_value(target),
                      tt.animate(rate_func=linear).increment_value(secs * 2.2),
                      run_time=secs)
            self.wait(0.3)
        self.play(tt.animate.increment_value(2 * np.pi), run_time=2.0,
                  rate_func=linear)

        self.clear()
        self.set_camera_orientation(phi=0, theta=-90 * DEGREES, zoom=1.0)

    # -- 3 -----------------------------------------------------------------

    def three_colours(self):
        self.title(r"\text{Different delays, different polarizations}",
                   "Different delays, different polarizations")
        cols, cy, R = (-4.5, 0.0, 4.5), 0.35, 0.9
        what = ("nearly circular", "turned exactly 90°", "barely turned")
        an = ValueTracker(90.0)
        fields = [exit_field(delay_waves(DND_DEMO, l)) for _, l, _ in DEMO]

        heads, rings, ells, notes = VGroup(), VGroup(), VGroup(), VGroup()
        for x, (name, l, col), f, w in zip(cols, DEMO, fields, what):
            heads.add(VGroup(
                txt(f"{name}, {l:.0f} nm", 24, color=col),
                txt(f"{delay_waves(DND_DEMO, l):.2f} waves behind", 20,
                    color=COL_DIM)).arrange(DOWN, buff=0.08)
                .move_to([x, 2.15, 0]))
            ring = VGroup(
                Circle(radius=R, color=COL_DIM, stroke_width=2),
                DashedLine([-R, 0, 0], [R, 0, 0], color=COL_DIM,
                           stroke_width=2)).move_to([x, cy, 0])
            rings.add(ring)
            ells.add(pol_ellipse(f, R * 0.9, col).shift([x, cy, 0]))
            notes.add(txt(w, 20, color=WHITE).move_to([x, cy - R - 0.3, 0]))

        intro = txt("looking down the beam - dashed: how the light went in",
                    20, color=COL_DIM).move_to([0, 1.38, 0])
        self.play(FadeIn(heads), FadeIn(rings), FadeIn(intro), run_time=1.0)
        self.play(*[Create(e) for e in ells], run_time=2.2)
        self.play(FadeIn(notes), run_time=0.7)
        self.wait(1.6)

        def analyser_marks():
            # the axis as two notches outside the ring plus a faint line
            # through it, so it never hides the polarization it is reading
            g = VGroup()
            a = np.radians(an.get_value())
            u = np.array([np.cos(a), np.sin(a), 0.0])
            for x in cols:
                c = np.array([x, cy, 0.0])
                g.add(Line(c - u * R, c + u * R, color=COL_POL,
                           stroke_width=1.5, stroke_opacity=0.45))
                for sgn in (1, -1):
                    g.add(Line(c + sgn * u * R * 1.06, c + sgn * u * R * 1.34,
                               color=COL_POL, stroke_width=7))
            return g
        analysers = always_redraw(analyser_marks)
        alab = always_redraw(lambda: txt(
            f"then a polarizer at {an.get_value():.0f}°", 22,
            color=COL_POL).move_to([0, -1.25, 0]))
        for e in ells:
            e.set_z_index(3)
        # the intro line sits where the middle ring's top notch will land
        self.play(FadeOut(notes), FadeOut(intro), run_time=0.5)
        self.play(FadeIn(analysers), FadeIn(alab), run_time=0.8)

        def fractions():
            return [passed(f, an.get_value()) for f in fields]

        def bars():
            g = VGroup()
            for x, v, (_, _, col) in zip(cols, fractions(), DEMO):
                w = max(2.0 * v, 0.02)
                g.add(Rectangle(width=w, height=0.3, fill_color=col,
                                fill_opacity=0.9, stroke_width=0)
                      .move_to([x - 1.0 + w / 2, -1.85, 0]))
                g.add(txt(f"passes {100 * v:.0f}%", 20, color=WHITE)
                      .move_to([x, -2.25, 0]))
            return g
        rows = always_redraw(bars)
        frames = VGroup(*[Rectangle(width=2.0, height=0.3, color=COL_DIM,
                                    stroke_width=1).move_to([x, -1.85, 0])
                          for x in cols])
        self.play(FadeIn(frames), FadeIn(rows), run_time=0.9)
        self.wait(1.2)

        swatch = always_redraw(lambda: VGroup(
            Square(side_length=0.9, fill_color=show_rgb(fractions()),
                   fill_opacity=1, stroke_color=WHITE, stroke_width=2),
            txt("together", 22, color=WHITE))
            .arrange(RIGHT, buff=0.3).move_to([0, -3.15, 0]))
        self.play(FadeIn(swatch), run_time=0.8)
        self.wait(1.6)

        cap = txt("Turn the last polarizer by 90° and every fraction flips: "
                  "the complementary colour.", 22, color=COL_BEAM)
        cap.move_to([0, -3.75, 0])
        self.play(an.animate.set_value(0), run_time=2.6, rate_func=smooth)
        self.play(FadeIn(cap), run_time=0.8)
        self.wait(2.4)
        self.clear()

    # -- 4 -----------------------------------------------------------------

    def driving_a_pixel(self):
        self.title(r"\text{Driving a pixel changes the delay}",
                   "Driving a pixel changes the delay")
        t = ValueTracker(0.0)    # 0: molecules lie in the panel, 1: upright

        slab = RoundedRectangle(width=2.6, height=3.6, corner_radius=0.12,
                                fill_color="#1f3b63", fill_opacity=0.55,
                                stroke_color="#3b6db3", stroke_width=2)
        slab.move_to([-4.3, 0.0, 0])
        mol = always_redraw(lambda: molecules(-5.6, -3.0, -1.8, 1.8,
                                              tilt=t.get_value(), nx=4, ny=7))
        arrow = Arrow([-6.9, 0, 0], [-1.7, 0, 0], buff=0, color=WHITE,
                      stroke_width=3, max_tip_length_to_length_ratio=0.06)
        alab = txt("light", 20, color=COL_DIM).move_to([-6.4, 0.35, 0])
        volts = always_redraw(lambda: txt(
            f"drive: {100 * t.get_value():.0f}%", 22, color=COL_BEAM)
            .move_to([-4.3, -2.2, 0]))

        def waves_now(l):
            # the light sees less of the difference as the rods stand up
            return delay_waves(DND_DEMO * np.cos(t.get_value() * PI / 2) ** 2, l)

        def rgb_now():
            return [passed(exit_field(waves_now(l)), 90.0) for _, l, _ in DEMO]

        readout = always_redraw(lambda: txt(
            f"green falls {waves_now(550):.2f} waves behind", 24,
            color=WHITE).move_to([0.9, 1.6, 0]))
        swatch = always_redraw(lambda: Square(
            side_length=1.9, fill_color=show_rgb(rgb_now()), fill_opacity=1,
            stroke_color=WHITE, stroke_width=2).move_to([1.0, -0.35, 0]))
        sw_lab = txt("between crossed polarizers", 20,
                     color=COL_DIM).move_to([1.0, -1.65, 0])

        bx, base, H = (4.0, 4.8, 5.6), -1.3, 2.4

        def bars():
            g = VGroup()
            for x, v, (_, _, col) in zip(bx, rgb_now(), DEMO):
                h = max(H * v, 0.015)
                g.add(Rectangle(width=0.55, height=h, fill_color=col,
                                fill_opacity=0.9, stroke_width=0)
                      .move_to([x, base + h / 2, 0]))
            return g
        rgb_bars = always_redraw(bars)
        axis = Line([3.55, base, 0], [6.05, base, 0], color=COL_DIM)
        names = VGroup(*[txt(n, 20, color=c).move_to([x, base - 0.28, 0])
                         for x, n, c in zip(bx, ("R", "G", "B"),
                                            [d[2] for d in DEMO])])

        self.play(FadeIn(slab), FadeIn(mol), GrowArrow(arrow), FadeIn(alab),
                  FadeIn(volts), run_time=1.2)
        self.play(FadeIn(readout), FadeIn(swatch), FadeIn(sw_lab),
                  Create(axis), FadeIn(names), FadeIn(rgb_bars), run_time=1.0)
        self.wait(1.0)

        cap = self.caption(
            ["Voltage stands the molecules up along the beam, so the light",
             "sees less of the difference between them: the delay shrinks,",
             "and the colour runs through a whole sequence."],
            y=-3.05, size=22)
        self.play(FadeIn(cap, shift=UP * 0.15), run_time=0.9)
        self.play(t.animate.set_value(1.0), run_time=7.0, rate_func=linear)
        self.wait(0.8)

        cap2 = self.caption(
            ["Fully upright: no delay, so no colour — black between crossed "
             "polarizers.",
             "A real STN pixel never stands fully upright, so its driven state",
             "keeps some colour too — the same reason bare STN displays look tinted."],
            y=-3.05, colours=[WHITE, COL_DIM, COL_BEAM], size=22)
        self.play(FadeOut(cap), FadeIn(cap2, shift=UP * 0.15), run_time=0.9)
        self.play(t.animate.set_value(0.55), run_time=2.0, rate_func=smooth)
        self.wait(2.6)
        self.clear()

    # -- 5 -----------------------------------------------------------------

    def four_states(self):
        self.title(r"\text{Two panels, four colours}",
                   "Two panels, four colours")
        y, xs = 2.05, (-5.0, -2.5, 0.0, 2.5, 5.0)
        beam_line = Line([-6.8, y, 0], [6.8, y, 0], color=WHITE,
                         stroke_width=3, stroke_opacity=0.5)
        stack = VGroup(beam_line)
        for i, x in enumerate(xs):
            if i in (1, 3):
                cell = RoundedRectangle(width=0.7, height=1.15,
                                        corner_radius=0.08,
                                        fill_color="#1f3b63", fill_opacity=0.9,
                                        stroke_color="#3b6db3", stroke_width=2)
                cell.move_to([x, y, 0])
                cell.add(molecules(x - 0.35, x + 0.35, y - 0.58, y + 0.58,
                                   nx=2, ny=3))
                stack.add(cell, txt(f"panel {1 if i == 1 else 2}", 20,
                                    color="#7aa7e0").move_to([x, y - 0.85, 0]))
            else:
                col = COL_FIX if i == 2 else COL_POL
                stack.add(polarizer(30 if i == 2 else 0, radius=0.45,
                                    color=col).move_to([x, y, 0]))
        stack.add(txt("30°", 20, color=COL_FIX).move_to([0, y - 0.85, 0]))
        self.play(FadeIn(stack), run_time=1.2)

        sw = VGroup()
        for i, (code, desc, rgb) in enumerate(MEASURED_STATES):
            x = -4.65 + 3.1 * i
            lum = float(np.mean(rgb))
            sw.add(VGroup(
                Square(side_length=1.25, fill_color=hexcol(rgb),
                       fill_opacity=1, stroke_color=WHITE, stroke_width=2),
                txt(code, 26, color=WHITE),
                txt(desc, 20, color=COL_DIM),
                txt(f"brightness {lum:.3f}", 18, color=COL_DIM))
                .arrange(DOWN, buff=0.1).move_to([x, -0.8, 0]))
        head = txt("measured on this stack", 22, color=COL_DIM)
        head.move_to([0, 0.5, 0])
        self.play(FadeIn(head), LaggedStart(*[FadeIn(s, shift=UP * 0.15)
                                              for s in sw], lag_ratio=0.2),
                  run_time=2.0)
        self.wait(1.0)

        cap = self.caption(
            ["Each panel switches its layer between two delays, so the four",
             "combinations have four different spectra — at the same "
             "brightness.",
             "Polarizers decide how much light gets through.",
             "Only the liquid crystal decides how much of each colour."],
            y=-2.95, colours=[WHITE, WHITE, COL_BEAM, COL_BEAM], size=22)
        self.play(FadeIn(cap, shift=UP * 0.15), run_time=1.2)
        self.wait(4.0)


# ---------------------------------------------------------------- check

if __name__ == "__main__":
    def table(scene):
        s = scene()
        for t1, t2 in COMBOS:
            a = s.axes(t1, t2)
            print("   axes " + " ".join(f"{x:6.1f}" for x in a)
                  + f"   ->  {s.trace(t1, t2)[-1][1]:.3f}")

    print("S1  two polarizers, 0/90 each")
    table(S1_TwoPolarizers)
    print(f"\nS2  with a fixed {int(MIDDLE)} in the middle")
    table(S2_MiddlePolarizer)
    print("\nS3  per-band intensities (R, G, B)")
    for sym, name in ((True, "both ends turn (symmetric)"),
                      (False, "cells turn, analyser fixed")):
        print(f"   {name}")
        for nm, v in colour_states(sym).items():
            print(f"     {nm}  R={v[0]:.3f} G={v[1]:.3f} B={v[2]:.3f}")
    print(f"\nS4  third polarizer mounted +{int(OFFSET3)}")
    table(S4_MountTheThirdOffAxis)
    print(f"\nS5  one layer, dn*d = {DND_DEMO} um, axes at 45 degrees")
    for name, l, _ in DEMO:
        w = delay_waves(DND_DEMO, l)
        f = exit_field(w)
        print(f"   {name:5s} {l:.0f} nm   {w:.2f} waves behind   "
              f"crossed {passed(f, 90):.3f}   parallel {passed(f, 0):.3f}")

"""
Reproduce the optical analysis in OPTICS.md.

    python fit_optics.py              everything
    python fit_optics.py malus        the ideal-polarizer results only
    python fit_optics.py measure      what the measured colours imply
    python fit_optics.py jones        the Jones model, its check and its fit

Needs numpy and scipy. The measured state colours are embedded below; they come
out of the decoder, which labels every cell of every frame it decodes, so a
successful decode is also a colour measurement. See MEASURED for how they were
obtained.
"""

import sys
import itertools
import numpy as np

# ---------------------------------------------------------------- measured

# Raw camera RGB, averaged over 75 decoded frames of one recording,
# ~9,500 cells per state, no flat-field correction applied.
# Rows are states; the firmware drives panel 1 from bit 0 and panel 2 from bit 1
# (`if (value & 0x01) fill_cell(&lcd1 ...)`), so row s is (panel1=s&1,
# panel2=(s>>1)&1).
MEASURED = np.array([
    [0.9862, 0.7728, 0.5063],      # 00  both off      orange
    [0.8150, 0.7230, 0.7731],      # 01  panel 1 on    purple
    [0.7739, 0.9360, 0.5474],      # 10  panel 2 on    green
    [0.5854, 0.8672, 0.8240],      # 11  both on       cyan
])
NOISE = 0.034                      # per-cell sd in each channel
NAMES = ["00", "01", "10", "11"]

MIDDLE = 30.0


def c2(deg):
    return float(np.cos(np.radians(deg)) ** 2)


# ---------------------------------------------------------------- 1. Malus

def malus():
    print("TWO POLARIZERS, each 0 or 90")
    for a1, a3 in itertools.product((0, 90), repeat=2):
        print(f"   {a1:>2}/{a3:<2}   {c2(a3-a1):.4f}")

    print(f"\nTHREE POLARIZERS, middle fixed at {MIDDLE:.0f}")
    for a1, a3 in itertools.product((0, 90), repeat=2):
        f1, f2 = c2(MIDDLE-a1), c2(a3-MIDDLE)
        print(f"   {a1:>2}/{a3:<2}   {f1:.3f} x {f2:.3f} = {f1*f2:.4f}")

    print("\nthe two mixed paths, step by step")
    for a in ([0, 30, 90], [90, 30, 0]):
        inten, out = 1.0, []
        for i in range(1, len(a)):
            f = c2(a[i]-a[i-1])
            inten *= f
            out.append(f"turn {abs(a[i]-a[i-1]):2.0f} x{f:.3f} = {inten:.4f}")
        print(f"   {' -> '.join(map(str, a)):>16} :  " + "   ".join(out))
    print("   same two factors, opposite order -> same product")

    print("\nDEGENERACY.  x = cos^2(angle from polarizer 1 to the middle)")
    print("              y = cos^2(angle from the middle to polarizer 3)")
    print("  states are xy, x(1-y), (1-x)y, (1-x)(1-y)")
    print("  -> degenerate exactly when x == y or x + y == 1")
    x, y = c2(MIDDLE), c2(90-MIDDLE)
    print(f"  this stack: x={x:.3f} y={y:.3f} x+y={x+y:.3f}  <- on the line")

    def levels(x, y):
        return sorted([x*y, x*(1-y), (1-x)*y, (1-x)*(1-y)])

    def gap(x, y):
        L = levels(x, y)
        return min(L[i+1]-L[i] for i in range(3))

    g = np.linspace(0.001, 0.999, 999)
    best = max((gap(a, b), a, b) for a in g for b in g)
    print(f"\n  best four-level spread anywhere: smallest gap {best[0]:.4f}")
    print(f"    at theta={np.degrees(np.arccos(np.sqrt(best[1]))):.0f} deg, "
          f"phi={np.degrees(np.arccos(np.sqrt(best[2]))):.0f} deg")
    print("    levels " + " ".join(f"{v:.3f}" for v in levels(best[1], best[2])))
    x4, y4 = c2(30), c2(24)          # polarizer 3 mounted +54
    print(f"  mounting polarizer 3 at +54 deg: smallest gap {gap(x4, y4):.4f}")
    print("    levels " + " ".join(f"{v:.3f}" for v in levels(x4, y4)))


# ---------------------------------------------------------------- 2. measured

def measure():
    grey = MEASURED.mean(1)
    print("measured state colours (raw camera RGB)")
    for i, nm in enumerate(NAMES):
        print(f"   {nm}   R={MEASURED[i,0]:.3f} G={MEASURED[i,1]:.3f} "
              f"B={MEASURED[i,2]:.3f}   luminance {grey[i]:.4f}")
    spread = grey.max()-grey.min()
    print(f"\nluminance spread {spread:.4f}  "
          f"({100*spread/grey.mean():.1f}% of the mean, "
          f"{spread/NOISE:.2f}x the per-cell noise)")

    pairs = list(itertools.combinations(range(4), 2))
    rgb = min(float(np.linalg.norm(MEASURED[i]-MEASURED[j])) for i, j in pairs)
    gry = min(abs(grey[i]-grey[j]) for i, j in pairs)
    # a greyscale reading averages three channels, so its noise is sd/sqrt(3)
    gnoise = NOISE/np.sqrt(3)
    print(f"\nworst-case separation   RGB {rgb:.4f}   greyscale {gry:.4f}")
    print(f"relative to noise       RGB {rgb/NOISE:.1f}x        "
          f"greyscale {gry/gnoise:.2f}x")

    from math import erfc, sqrt
    pe = lambda d, s: 0.5*erfc(d/(2*s*sqrt(2)))
    print(f"\npredicted per-cell error, nearest centroid")
    print(f"   RGB        {100*pe(rgb, NOISE):.4f}%")
    print(f"   greyscale  {100*pe(gry, gnoise):.1f}%")
    print("   (the decoder measures about 100% and 57% accuracy)")


# ---------------------------------------------------------------- 3. Jones

LAM = np.arange(0.400, 0.701, 0.005)           # microns


def _channels():
    """Crude but broad camera responses. Real ones differ; see OPTICS.md."""
    c = {"R": (0.600, 0.040), "G": (0.540, 0.040), "B": (0.460, 0.040)}
    out = []
    for k in ("R", "G", "B"):
        w = np.exp(-0.5*((LAM-c[k][0])/c[k][1])**2)
        out.append(w/w.sum())
    return np.array(out)


CH = _channels()
N = len(LAM)


def _rot(t):
    c, s = np.cos(t), np.sin(t)
    return np.array([[c, -s], [s, c]])


def polarizer(deg):
    t = np.radians(deg)
    c, s = np.cos(t), np.sin(t)
    return np.array([[c*c, c*s], [c*s, s*s]], complex)


def tn(dnd, entry_deg, twist_deg=90.0, lam=None):
    """Twisted-nematic cell, Gooch-Tarry / Jones form, for every wavelength."""
    lam = LAM if lam is None else np.atleast_1d(lam)
    phi = np.radians(twist_deg)
    D = 2*np.pi*dnd/lam
    X = np.sqrt(phi**2 + (D/2)**2)
    sc = np.sin(X)/X
    M = np.empty((len(lam), 2, 2), complex)
    M[:, 0, 0] = np.cos(X) + 1j*(D/2)*sc
    M[:, 0, 1] = phi*sc
    M[:, 1, 0] = -phi*sc
    M[:, 1, 1] = np.cos(X) - 1j*(D/2)*sc
    e = np.radians(entry_deg)
    return _rot(e+phi) @ M @ _rot(-e)


def gooch_tarry_check():
    """A 90 deg TN between PARALLEL polarizers is dark at dn*d/lam =
    sqrt(3)/2, sqrt(15)/2, sqrt(35)/2. If this does not print zeros, the
    cell model is wrong and nothing below it means anything."""
    print("Gooch-Tarry check (expect 0.000000 at each)")
    for u in (np.sqrt(3)/2, np.sqrt(15)/2, np.sqrt(35)/2):
        M = tn(u*0.55, 0.0, lam=0.55)[0]
        E = polarizer(0) @ M @ np.array([1, 0], complex)
        print(f"   dn*d/lam = {u:.4f}   transmission "
              f"{float(np.vdot(E, E).real):.6f}")


def model(p, flip):
    """p = [middle, exit, dn*d_1, dn*d_2, gainR, gainG, gainB] -> (4,3)."""
    mid, out, d1, d2, gR, gG, gB = p
    P1 = np.broadcast_to(polarizer(mid), (N, 2, 2))
    P2 = np.broadcast_to(polarizer(out), (N, 2, 2))
    A, B = tn(d1, 0.0), tn(d2, mid)
    eye = np.broadcast_to(np.eye(2, dtype=complex), (N, 2, 2))
    E0 = np.zeros((N, 2), complex)
    E0[:, 0] = 1
    pred = np.zeros((4, 3))
    for s in range(4):
        b1, b2 = s & 1, (s >> 1) & 1
        if flip:
            b1, b2 = 1-b1, 1-b2
        M1 = eye if b1 else A
        M2 = eye if b2 else B
        E = np.einsum('nij,nj->ni', P1, np.einsum('nij,nj->ni', M1, E0))
        E = np.einsum('nij,nj->ni', P2, np.einsum('nij,nj->ni', M2, E))
        spec = np.real(np.sum(E*np.conj(E), axis=1))
        pred[s] = (CH @ spec) * np.array([gR, gG, gB])
    return pred


def jones():
    from scipy.optimize import least_squares

    print("ideal polarizers: Jones vs Malus")
    worst = 0.0
    for a1, a3 in itertools.product((0, 90), repeat=2):
        v = np.array([np.cos(np.radians(a1)), np.sin(np.radians(a1))], complex)
        E = polarizer(a3) @ polarizer(MIDDLE) @ polarizer(a1) @ v
        worst = max(worst, abs(float(np.vdot(E, E).real)
                               - c2(MIDDLE-a1)*c2(a3-MIDDLE)))
    print(f"   largest difference {worst:.2e}  -> identical\n")

    gooch_tarry_check()

    def fit(fix_mid=None, share=False, nstart=60):
        rng = np.random.default_rng(1)
        out = []
        for flip in (False, True):
            for _ in range(nstart):
                m0 = fix_mid if fix_mid is not None else rng.uniform(5, 85)
                p0 = np.array([m0, rng.uniform(-80, 170), rng.uniform(.1, 1.5),
                               rng.uniform(.1, 1.5), 3., 3., 3.])
                lo = np.array([0, -90, .05, .05, .01, .01, .01], float)
                hi = np.array([90, 180, 3., 3., 20, 20, 20], float)
                if fix_mid is not None:
                    lo[0], hi[0] = fix_mid-1e-6, fix_mid+1e-6
                if share:
                    p0[3] = p0[2]

                def resid(p):
                    q = p.copy()
                    if share:
                        q[3] = q[2]
                    return (model(q, flip)-MEASURED).ravel()

                try:
                    r = least_squares(resid, p0, bounds=(lo, hi), max_nfev=600)
                except Exception:
                    continue
                q = r.x.copy()
                if share:
                    q[3] = q[2]
                out.append((float(np.sqrt(np.mean(r.fun**2))), q, flip))
        out.sort(key=lambda t: t[0])
        return out

    print(f"\nfitting the model to the measured colours "
          f"(noise is {NOISE:.3f})")
    for name, kw in (("all free                 ", {}),
                     ("shared dn*d              ", {"share": True}),
                     ("middle fixed at 30       ", {"fix_mid": 30.0}),
                     ("middle 30 and shared dn*d", {"fix_mid": 30.0,
                                                    "share": True})):
        rms, p, flip = fit(**kw)[0]
        print(f"   {name}  rms {rms:.4f}   mid {p[0]:5.1f}  exit {p[1]:6.1f}  "
              f"dn*d {p[2]:.3f}/{p[3]:.3f}")

    print("\nis it identifiable? spread among fits within 10% of the best:")
    o = fit()
    good = [t for t in o if t[0] <= o[0][0]*1.10]
    P = np.array([t[1] for t in good])
    print(f"   {len(good)} of {len(o)} starts land there")
    for i, nm in enumerate(["middle", "exit", "dn*d 1", "dn*d 2"]):
        print(f"   {nm:8s} {P[:, i].min():7.2f} .. {P[:, i].max():7.2f}")
    print("\n   the exit angle is unconstrained and the retardances are loose;")
    print("   twelve numbers cannot pin seven parameters. See OPTICS.md.")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "malus"):
        print("="*68, "\nIDEAL POLARIZERS\n" + "="*68)
        malus()
    if what in ("all", "measure"):
        print("\n" + "="*68, "\nMEASURED\n" + "="*68)
        measure()
    if what in ("all", "jones"):
        print("\n" + "="*68, "\nJONES MODEL\n" + "="*68)
        jones()

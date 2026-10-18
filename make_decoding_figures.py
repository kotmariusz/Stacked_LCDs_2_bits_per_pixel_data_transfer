#!/usr/bin/env python3
"""Draw the figures in DECODING.md from the real examples, with the notebook's own decoder.

    python make_decoding_figures.py          every figure (a few minutes)
    python make_decoding_figures.py text     only the ones from the photograph
    python make_decoding_figures.py video    only the ones from the recording

Nothing about decoding is reimplemented here. The Setup cell of
colab/lcd_codec_colab.ipynb is loaded and run as it is, and the figures call the
same functions the Decode cell calls, so they show what the notebook does and
change when it does. The recording figures replay decode_video() one step at a
time, with its own functions and thresholds, so that each step can be drawn.

Needs numpy, pillow and matplotlib, plus OpenCV or the ffmpeg command for the
recording.
"""
import contextlib
import io
import json
import os
import sys
import types

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Polygon, Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
NOTEBOOK = os.path.join(HERE, "colab", "lcd_codec_colab.ipynb")
PHOTO = os.path.join(HERE, "examples", "text", "text_frame.jpg")
VIDEO = os.path.join(HERE, "examples", "video", "picture_26_frames.mp4")
OUT = os.path.join(HERE, "docs", "decoding")
GW, GH, CELL_PX = 32, 16, 4           # both examples were sent at CELL_PX 4
STEP = 0.25                           # the Decode cell's VIDEO_STEP
DPI = 200

# chart chrome, dark, so the figures sit with the photographs and animations
BG, INK, INK2, MUTED = "#1a1a19", "#f0efec", "#c3c2b7", "#898781"
LINE, AXIS = "#2c2c2a", "#383835"
BLUE, ORANGE, AQUA = "#3987e5", "#d95926", "#199e70"

# the four states as the camera sees them - raw RGB, averaged over about 9,500
# cells each in decoded frames of the recording (README, "The optics")
STATE_RGB = np.array([(0.9862, 0.7728, 0.5063), (0.8150, 0.7230, 0.7731),
                      (0.7739, 0.9360, 0.5474), (0.5854, 0.8672, 0.8240)])
STATE_NAME = ["both panels off", "panel 1 on", "panel 2 on", "both on"]

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
    "text.color": INK, "axes.labelcolor": INK2, "axes.edgecolor": AXIS,
    "xtick.color": MUTED, "ytick.color": MUTED, "font.family": "DejaVu Sans",
    "font.size": 9, "axes.titlesize": 10, "axes.titlecolor": INK,
    "axes.titlelocation": "left", "axes.titlepad": 8,
})


def load_decoder():
    """The notebook's Setup cell, run as it is."""
    nb = json.load(open(NOTEBOOK, encoding="utf-8"))
    setup = next(c for c in nb["cells"] if c["cell_type"] == "code")
    ns = {"__name__": "lcd_decoder"}
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile("".join(setup["source"]), NOTEBOOK + " (Setup cell)",
                     "exec"), ns)
    return types.SimpleNamespace(**ns)


D = load_decoder()


def read_any(data):
    """What the Decode cell accepts: a picture chunk first, then text."""
    r = D.check_picture_chunk(data)
    if r is not None:
        return ("picture", r)
    t = D.check_frame(data)
    return ("text", t) if t is not None else None


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print("  wrote", os.path.relpath(path, HERE))


def bare(ax):
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def draw_cells(ax, colours, outline=None, gap=0.06, lw=1.8):
    """A grid of coloured cells, row 0 at the top. colours: (rows, cols, 3)."""
    rows, cols = colours.shape[:2]
    for r in range(rows):
        for c in range(cols):
            ax.add_patch(Rectangle((c + gap/2, rows - 1 - r + gap/2),
                                   1 - gap, 1 - gap, color=colours[r, c],
                                   lw=0))
    for (r, c) in (outline or []):
        ax.add_patch(Rectangle((c + 0.02, rows - 1 - r + 0.02), 0.96, 0.96,
                               fill=False, ec=INK, lw=lw))
    ax.set_xlim(0, cols); ax.set_ylim(0, rows); ax.set_aspect("equal")
    bare(ax)


def grid_lines(ax, cols, rows, colour=BG, lw=0.5, alpha=0.6):
    for x in range(cols + 1):
        ax.plot([x, x], [0, rows], color=colour, lw=lw, alpha=alpha)
    for y in range(rows + 1):
        ax.plot([0, cols], [y, y], color=colour, lw=lw, alpha=alpha)


def swatch(fig, x, y, colour, size=0.02):
    fig.add_artist(Rectangle((x, y), size, size * fig.get_figwidth()
                             / fig.get_figheight(), color=colour,
                             transform=fig.transFigure))


def state_legend(fig, y, x0=0.06, w=0.88):
    for s in range(4):
        x = x0 + s * w / 4
        swatch(fig, x, y, STATE_RGB[s], 0.022)
        fig.text(x + 0.03, y + 0.004, f"{s:02b}  {STATE_NAME[s]}", color=INK2,
                 fontsize=8.5)


def straighten(im, corners, a, b, px=24):
    """The panel cut out of the photograph and squared up, px pixels a cell."""
    UL, UR, LR, LL = corners
    q = (UL[0], UL[1], LL[0], LL[1], LR[0], LR[1], UR[0], UR[1])
    return np.asarray(im.transform((a * px, b * px), Image.QUAD, q,
                                   Image.BICUBIC), np.float32) / 255.


# =========================================================================
#  the photograph
# =========================================================================

def read_photo(path, turned=False):
    """One photograph, read the way the Decode cell reads it. turned: the same
    photograph rotated 180 degrees, as if the phone had been held upside down."""
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if turned:
        im = im.transpose(Image.Transpose.ROTATE_180)
    r, note, lock, cc = D.pic_decode(im, GW, GH, read_any, relocate=True)
    if r is None:
        raise SystemExit(f"{path} did not decode")
    a, b = lock["aspect"]
    cells = D.sample(im, cc, a, b)
    src = D.flatten_light(cells) if lock["flat"] else cells
    cen, lab = D.kmeans(src.reshape(-1, 3))
    states = D.classify_nearest(src, lock["centres"])        # sampled coords
    frame = D.orient(states, lock["orient"])                  # frame coords
    # each cluster's colour as the camera saw it (the clustering itself may
    # have run on illumination-flattened values, which are not colours)
    seen = np.array([cells.reshape(-1, 3)[lab == k].mean(0) for k in range(4)])
    label = "the same, turned 180°" if turned else os.path.basename(path)
    return dict(path=path, label=label, im=im, result=r, note=note, lock=lock,
                corners=cc,
                found=D.find_panel(np.asarray(im, np.float32) / 255.),
                cells=cells, src=src, cluster_rgb=seen,
                labels=lab.reshape(b, a), states=states, frame=frame,
                data=D.unpack(frame, GW, GH, True))


def fig_anatomy():
    """What a frame is made of - generated, at the big cell size."""
    gw, gh, nbytes = D.grid_size(8, True)                 # 16 x 8 at CELL_PX 8
    msg = b"Hi :)"
    frame = D.build_frame(msg, nbytes)
    grid = D.frame_to_cells(frame, gw, gh, True)
    marks = D.markers(gw, gh)

    fig = plt.figure(figsize=(8.8, 6.6))
    ax = fig.add_axes([0.06, 0.40, 0.88, 0.50])
    draw_cells(ax, STATE_RGB[grid], outline=list(marks))
    ax.set_anchor("W")
    for (r, c), s in marks.items():
        ax.text(c + 0.5, gh - 1 - r + 0.5, f"{s:02b}", ha="center",
                va="center", color=BG, fontsize=8.5, fontweight="bold")
    fig.text(0.06, 0.94, "A frame, as the encoder makes it", fontsize=11)
    fig.text(0.06, 0.915, f"\"{msg.decode()}\" at CELL_PX 8: {gw} x {gh} cells, "
             f"2 bits each. Outlined: the four marker cells, which always "
             f"show 00, 01, 10 and 11.", color=INK2, fontsize=8.5)

    # the same frame, unrolled into reading order
    pos = D.payload_cells(gw, gh, True)
    shown = 3 + len(msg)                        # the header and the message
    sx = fig.add_axes([0.06, 0.20, 0.88, 0.10])
    strip = np.array([[grid[p] for p in pos[:shown * 4]]])
    draw_cells(sx, STATE_RGB[strip], gap=0.1)
    for i, s in enumerate(strip[0]):
        sx.text(i + 0.5, 0.5, f"{s:02b}", ha="center", va="center",
                color=BG, fontsize=7)
    names = ["magic", "length", "CRC-8"] + [f"'{chr(x)}'" for x in msg]
    for k in range(shown):
        x0, x1 = k * 4 + 0.15, k * 4 + 3.85
        sx.plot([x0, x0, x1, x1], [-0.12, -0.32, -0.32, -0.12], color=MUTED,
                lw=0.9, clip_on=False)
        sx.text(k * 4 + 2, -0.6, f"{frame[k]:02X}  {names[k]}", ha="center",
                va="top", color=INK2, fontsize=8)
    fig.text(0.06, 0.335, "The same cells in reading order – row by row, "
             "skipping the markers, four cells to a byte:",
             color=INK2, fontsize=8.5)
    fig.text(0.06, 0.09, f"… then zeros, state 00, to the end: "
             f"{nbytes} bytes in all. The CRC-8 covers the message, so one "
             f"misread cell anywhere in it fails the frame.",
             color=MUTED, fontsize=8)
    state_legend(fig, 0.025)
    save(fig, "frame_anatomy.png")


def fig_sent_vs_seen(p):
    payload = p["data"][3:3 + p["data"][1]]
    _, _, nbytes = D.grid_size(CELL_PX, True)
    sent = D.frame_to_cells(D.build_frame(payload, nbytes), GW, GH, True)
    a, b = p["lock"]["aspect"]
    seen = D.orient(straighten(p["im"], p["corners"], a, b), p["lock"]["orient"])
    same = int((p["frame"] == sent).sum())
    marks = list(D.markers(GW, GH))

    fig = plt.figure(figsize=(8.8, 3.05))
    ax1 = fig.add_axes([0.02, 0.19, 0.47, 0.62])
    draw_cells(ax1, STATE_RGB[sent], outline=marks, gap=0.08, lw=1.4)
    ax2 = fig.add_axes([0.51, 0.19, 0.47, 0.62])
    ax2.imshow(seen, extent=(0, GW, 0, GH), interpolation="lanczos")
    grid_lines(ax2, GW, GH, alpha=0.45)
    for (r, c) in marks:
        ax2.add_patch(Rectangle((c + 0.02, GH - 1 - r + 0.02), 0.96, 0.96,
                                fill=False, ec=INK, lw=1.4))
    ax2.set_xlim(0, GW); ax2.set_ylim(0, GH); bare(ax2)
    fig.text(0.02, 0.88, "Sent: the encoder's frame for the message",
             fontsize=10)
    fig.text(0.51, 0.88, "Seen: the photograph, squared up and turned the "
             "same way", fontsize=10)
    fig.text(0.02, 0.025, f"{same} of {GW * GH} cells read back as sent. The "
             "camera's colours drift across the panel, which is why the\nreader "
             "sorts the cells into four groups instead of matching them to "
             "fixed colours.", color=MUTED, fontsize=8, linespacing=1.5)
    save(fig, "sent_vs_seen.png")


def fig_steps(p):
    im, lock = p["im"], p["lock"]
    a, b = lock["aspect"]
    arr = np.asarray(im)
    pts = np.array(p["corners"])
    x0, y0 = pts.min(0); x1, y1 = pts.max(0)
    m = 0.10 * (x1 - x0)
    box = (int(max(0, x0 - m)), int(max(0, y0 - m)),
           int(min(arr.shape[1], x1 + m)), int(min(arr.shape[0], y1 + m)))

    fig = plt.figure(figsize=(8.8, 5.1))
    slots = [fig.add_axes([0.02 + k * 0.245, 0.03, 0.225, 0.78])
             for k in range(4)]
    ax = slots[0]
    ax.imshow(arr[box[1]:box[3], box[0]:box[2]])
    for corners, style, col in ((p["found"], (0, (3, 2)), INK2),
                                (p["corners"], "-", AQUA)):
        q = np.array(corners) - np.array(box[:2])
        ax.add_patch(Polygon(q, closed=True, fill=False, ec=col, lw=1.3,
                             ls=style))
    bare(ax)

    ax = slots[1]
    st = straighten(im, p["corners"], a, b, px=16)
    ax.imshow(st, extent=(0, a, 0, b), interpolation="lanczos")
    grid_lines(ax, a, b)
    ax.set_xlim(0, a); ax.set_ylim(0, b); bare(ax)

    draw_cells(slots[2], p["cells"].clip(0, 1), gap=0.0)
    draw_cells(slots[3], STATE_RGB[p["states"]], gap=0.12)

    titles = ["1  Find the panel", "2  Square it up", "3  One colour a cell",
              "4  Four states"]
    notes = ["dashed: the lit area\nsolid: after fitting the grid",
             f"{a} x {b} cells; each is\naveraged over its middle half",
             "what the camera saw,\ncell by cell",
             "each cell given the nearest\nof the four colour groups"]
    for k, (ax, t, n) in enumerate(zip(slots, titles, notes)):
        ax.set_anchor("N")
        x = 0.02 + k * 0.245
        fig.text(x, 0.935, t, fontsize=9.5)
        fig.text(x, 0.855, n, fontsize=7.5, color=MUTED)
    save(fig, "photo_steps.png")


def fig_colours(p):
    v = p["cells"].reshape(-1, 3)
    st = p["states"].ravel()
    s = v.sum(1)
    r, g = v[:, 0] / s, v[:, 1] / s
    lum = v @ np.array([0.2126, 0.7152, 0.0722])

    def accuracy(x):
        c = np.array([x[st == k].mean(0) for k in range(4)])
        return (np.argmin(((x[:, None, :] - c[None])**2).sum(2), 1) == st).mean()
    acc_l, acc_c = accuracy(lum[:, None]), accuracy(np.stack([r, g], 1))

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.8, 4.2),
                                 gridspec_kw=dict(width_ratios=[1.1, 1]))
    fig.subplots_adjust(left=0.08, right=0.97, top=0.76, bottom=0.14,
                        wspace=0.28)
    a1.scatter(r, g, s=14, c=v.clip(0, 1), edgecolors=BG, linewidths=0.4)
    for k in range(4):
        sel = st == k
        a1.annotate(f"{k:02b}", (r[sel].mean(), g[sel].mean()),
                    xytext=(-6, 22), textcoords="offset points", color=INK,
                    fontsize=9, fontweight="bold")
    a1.set_xlabel("red share  R / (R+G+B)")
    a1.set_ylabel("green share  G / (R+G+B)")
    a1.set_title("Colour: four separate groups", fontsize=10)

    bins = np.linspace(lum.min() - 0.02, lum.max() + 0.02, 40)
    for k in range(4):
        a2.hist(lum[st == k], bins=bins, histtype="step", lw=1.8,
                color=STATE_RGB[k], label=f"{k:02b}")
    a2.set_xlabel("brightness  0.21 R + 0.72 G + 0.07 B")
    a2.set_ylabel("cells")
    a2.set_title("Brightness: 00 and 11 on top of each other", fontsize=10)
    a2.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="upper right")
    for ax in (a1, a2):
        ax.grid(color=LINE, lw=0.6)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    fig.text(0.08, 0.925, f"The {GW * GH} cells of one photograph, coloured as "
             "the camera saw them", fontsize=11)
    fig.text(0.08, 0.875, f"Sorted by colour alone, {acc_c:.0%} of cells land "
             f"in the right group; by brightness alone, {acc_l:.0%} \u2013 and a "
             f"frame needs every one.", color=INK2, fontsize=8.5)
    save(fig, "colour_clusters.png")
    return acc_c, acc_l


def marker_check(p):
    """The orientations that fit a 32 x 16 frame, and what the markers say."""
    labels = p["labels"]
    allowed = dict(D.marker_readings(labels, GW, GH))
    rows = []
    for o in range(8):
        g = D.orient(labels, o)
        if g.shape != (GH, GW):
            continue
        perm = allowed.get(o)
        ok = None
        if perm is not None:
            ok = read_any(D.unpack(np.array(perm)[g], GW, GH, True))
        rows.append((o, g, perm, ok))
    return rows


def fig_orientation(pa, pb):
    fig = plt.figure(figsize=(8.8, 6.0))
    fig.text(0.02, 0.958, "Which way up? Ask the four marker cells",
             fontsize=11)
    fig.text(0.02, 0.905, f"Only four of the eight turns and flips give a "
             f"{GW} x {GH} grid. In the right one the four markers show four "
             "different colours,\nand those colours name the states: whatever "
             "sits on the 00 marker is state 00, and so on.",
             color=INK2, fontsize=8.5, linespacing=1.5)
    marks = sorted(D.markers(GW, GH).items(), key=lambda kv: kv[1])
    for row, p in enumerate((pa, pb)):
        y = 0.52 - row * 0.44
        th = fig.add_axes([0.02, y, 0.11, 0.31])
        th.imshow(np.asarray(p["im"])[::4, ::4]); bare(th)
        fig.text(0.02, y + 0.325, p["label"], fontsize=8, color=INK2)
        cen = p["cluster_rgb"].clip(0, 1)
        for k, (o, g, perm, ok) in enumerate(marker_check(p)):
            x = 0.16 + k * 0.21
            ax = fig.add_axes([x, y + 0.13, 0.19, 0.19 * 8.8 / 6.0 / 2])
            draw_cells(ax, cen[g], outline=[q for q, _ in marks], gap=0.0,
                       lw=1.2)
            ax.set_title(D.ORIENTS[o].replace("+", " + "), fontsize=8,
                         color=INK2, pad=4)
            if perm is None:
                fig.text(x, y + 0.085, "markers: one colour twice",
                         fontsize=8, color=MUTED)
                continue
            fig.text(x, y + 0.085, "markers: four colours", fontsize=8,
                     color=INK2)
            for s, (q, _) in enumerate(marks):          # what each one names
                sx = x + s * 0.046
                swatch(fig, sx, y + 0.035, cen[g[q]], 0.016)
                fig.text(sx + 0.019, y + 0.037, f"{s:02b}", fontsize=7.5,
                         color=INK2)
            fig.text(x, y - 0.01, "checksum passes" if ok else
                     "checksum fails", fontsize=8,
                     color=AQUA if ok else MUTED)
    fig.text(0.02, 0.02, "Row 2 is the same photograph turned 180° in software, "
             "as if the phone were held upside down: another orientation, the "
             "same text.", color=MUTED, fontsize=8)
    save(fig, "orientation.png")


def text_figures():
    print("photograph:")
    pa, pb = read_photo(PHOTO), read_photo(PHOTO, turned=True)
    if pb["result"] != pa["result"]:
        raise SystemExit("turned round, the photograph reads differently")
    for p in (pa, pb):
        print(f"  {p['label']}: {p['note']}")
        print(f"    -> {p['result'][1]!r}")
    fig_anatomy()
    fig_sent_vs_seen(pa)
    fig_steps(pa)
    acc = fig_colours(pa)
    fig_orientation(pa, pb)
    d = pa["data"]
    n = d[1]
    print(f"  frame: magic {d[0]:02X}, length {n}, CRC-8 {d[2]:02X} "
          f"(computed {D.crc8(d[3:3 + n]):02X}); colour alone {acc[0]:.0%}, "
          f"brightness alone {acc[1]:.0%}")
    print("  first bytes:", " ".join(f"{x:02X}" for x in d[:12]), "...")


# =========================================================================
#  the recording
# =========================================================================

def replay_video():
    """decode_video(), a step at a time, keeping what each step saw."""
    print("recording:")
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        got, total, lock = D.decode_video(VIDEO, GW, GH, D.check_picture_chunk,
                                          CELL_PX, True, step_s=STEP)
    print("  decode_video says:\n    "
          + log.getvalue().strip().replace("\n", "\n    "))
    if not lock or not total:
        raise SystemExit("the recording did not decode")

    samples, _, _ = D.video_samples(VIDEO, step_s=STEP, max_samples=1200)
    cells_at, grids = [], []
    for _, im in samples:                       # step 2: classify every sample
        try:
            c = D.sample(im, D.panel_corners(im, lock, True), *lock["aspect"])
            src = D.flatten_light(c) if lock["flat"] else c
            cells_at.append(c)
            grids.append(D.classify_nearest(src, lock["centres"]))
        except Exception:
            cells_at.append(None); grids.append(None)

    change, prev = np.full(len(grids), np.nan), None
    runs, cur = [], []                          # step 3: split into held frames
    for i, g in enumerate(grids):
        if g is None:
            continue
        if prev is not None:
            change[i] = float((g != grids[prev]).mean())
        prev = i
        if cur and float((g != grids[cur[-1]]).mean()) > D.GRID_CHANGE:
            runs.append(cur); cur = []
        cur.append(i)
    if cur:
        runs.append(cur)

    def read(states):
        gr = D.orient(states, lock["orient"])
        return (None if gr.shape != (GH, GW) else
                D.check_picture_chunk(D.unpack(gr, GW, GH, True)))

    held = []
    for run in runs:                            # the vote
        cons = D._consensus(grids, run)
        h = read(cons)
        how = "vote" if h else None
        if not h:
            h = next((x for x in (read(grids[i]) for i in run) if x), None)
            how = "one sample" if h else None
        held.append(dict(run=run, cons=cons, blank=bool(D.is_blank(cons)),
                         hit=h, how=how,
                         alone=[read(grids[i]) is not None for i in run]))

    for _ in range(3):                          # step 4: the reference pass
        have = {h["hit"][0] for h in held if h["hit"]}
        if len(have) >= total:
            break
        ref = D.Reference(lock["aspect"][::-1])
        for h in held:
            if h["hit"]:
                idx, tot, chunk = h["hit"]
                ts = D.true_states_sampled(idx, tot, chunk, GW, GH, CELL_PX,
                                           True, lock["orient"])
                for i in h["run"]:
                    if cells_at[i] is not None:
                        ref.add(cells_at[i], ts)
        tab, new = ref.table(), 0
        for h in held:
            if h["hit"]:
                continue
            st = np.stack([D.classify_nearest_ref(cells_at[i], tab)
                           for i in h["run"] if cells_at[i] is not None])
            cons = np.stack([(st == s).sum(0) for s in range(4)]
                            ).argmax(0).astype(np.uint8)
            r = read(cons) or next((x for x in (read(x) for x in st) if x), None)
            if r:
                h["hit"], h["how"], new = r, "reference", new + 1
        if not new:
            break

    found = {h["hit"][0] for h in held if h["hit"]}
    print(f"  replayed: {len(runs)} held frames, {len(found)}/{total} chunks "
          f"({sum(h['how'] == 'vote' for h in held)} by vote, "
          f"{sum(h['how'] == 'one sample' for h in held)} by a single sample, "
          f"{sum(h['how'] == 'reference' for h in held)} by the reference pass)")
    within = [change[i] for h in held for i in h["run"][1:]
              if np.isfinite(change[i])]
    across = [change[h["run"][0]] for h in held[1:]
              if np.isfinite(change[h["run"][0]])]
    seen_twice = len([h for h in held if h["hit"]]) - len(found)
    print(f"  cells changed since the previous sample: median "
          f"{100 * np.median(within):.1f}% inside a held frame, "
          f"{100 * np.median(across):.0f}% where a new run starts")
    print(f"  the {len(runs)} runs: {len(found)} chunks, {seen_twice} of them "
          f"seen a second time, {sum(h['blank'] for h in held)} blank, "
          f"{sum(1 for h in held if not h['hit'] and not h['blank'])} unread "
          f"(lengths {[len(h['run']) for h in held if not h['hit'] and not h['blank']]})")
    return dict(samples=samples, times=np.array([t for t, _ in samples]),
                grids=grids, change=change, held=held, lock=lock, got=got,
                total=total, read=read)


def fig_timeline(v):
    t, change, held = v["times"], v["change"], v["held"]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8.8, 4.9), sharex=True,
                                 gridspec_kw=dict(height_ratios=[1.6, 1]))
    fig.subplots_adjust(left=0.09, right=0.98, top=0.83, bottom=0.18,
                        hspace=0.12)
    ok = np.isfinite(change)
    a1.plot(t[ok], 100 * change[ok], color=BLUE, lw=1.6, marker="o", ms=2.8)
    a1.axhline(100 * D.GRID_CHANGE, color=MUTED, lw=1, ls=(0, (4, 3)))
    a1.set_ylabel("cells changed\nsince last sample, %")
    a1.set_ylim(0, 100)

    colour = {"vote": BLUE, "reference": ORANGE, "one sample": AQUA}
    for h in held:
        t0 = t[h["run"][0]] - STEP / 2 + 0.05      # a gap between neighbours
        t1 = t[h["run"][-1]] + STEP / 2 - 0.05
        if h["blank"]:
            a2.broken_barh([(t0, t1 - t0)], (0.15, 0.7), color=MUTED)
            a2.text((t0 + t1) / 2, 1.05, "blank", ha="center", fontsize=7,
                    color=INK2)
        elif h["hit"]:
            a2.broken_barh([(t0, t1 - t0)], (0.15, 0.7), color=colour[h["how"]])
            a2.text((t0 + t1) / 2, 0.5, f"{h['hit'][0] + 1}", ha="center",
                    va="center", fontsize=7, color=BG)
        else:
            a2.broken_barh([(t0, t1 - t0)], (0.15, 0.7), facecolor="none",
                           edgecolor=AXIS, lw=1)
    a2.set_ylim(0, 1.35); a2.set_yticks([])
    a2.set_xlabel("time in the recording, s")
    a2.set_ylabel("held\nframes")
    for ax in (a1, a2):
        ax.grid(axis="x", color=LINE, lw=0.6); ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    a1.grid(axis="y", color=LINE, lw=0.6)
    n = len(held)
    fig.text(0.09, 0.935, "Where one frame ends and the next begins",
             fontsize=11)
    fig.text(0.09, 0.885, f"{len(t)} samples, {STEP} s apart, each classified "
             f"with the locked colours. A held frame is a run with almost no "
             f"change: {n} of them here.", color=INK2, fontsize=8.5)
    for k, (lab, col) in enumerate((("read by the vote", BLUE),
                                    ("by a single sample", AQUA),
                                    ("by the reference pass", ORANGE),
                                    ("blank marker", MUTED))):
        x = 0.09 + k * 0.205
        swatch(fig, x, 0.025, col, 0.016)
        fig.text(x + 0.022, 0.027, lab, fontsize=8, color=INK2)
    fig.text(0.09, 0.075, f"Dashed: {D.GRID_CHANGE:.0%} of cells - a new run "
             "starts above it. Outlined runs: single samples caught mid-change.",
             fontsize=8, color=MUTED)
    save(fig, "video_timeline.png")


def fig_vote(v):
    """One held frame: its samples, and the per-cell vote across them."""
    held, grids = v["held"], v["grids"]

    def score(h):
        # best example: the vote reads it, as many single samples as possible
        # do not, and the samples disagree on as many cells as possible
        if h["how"] != "vote" or len(h["run"]) < 3:
            return (-1, 0)
        wrong = sum((grids[i] != h["cons"]).sum() for i in h["run"])
        return (h["alone"].count(False), wrong)
    h = max(held, key=score)
    run = h["run"][:6]
    n = len(run) + 1
    fh = 4.0
    fig = plt.figure(figsize=(8.8, fh))
    w = 0.94 / n
    gh_ = w * 0.86 * 8.8 / fh * 2              # height of a 16 x 32 grid
    top = 0.17 + gh_
    for k, i in enumerate(run + [None]):
        ax = fig.add_axes([0.03 + k * w, 0.17, w * 0.86, gh_])
        g = h["cons"] if i is None else grids[i]
        draw_cells(ax, STATE_RGB[g], gap=0.0)
        if i is not None:
            bad = np.argwhere(g != h["cons"])
            for r, c in bad:
                ax.add_patch(Rectangle((c, g.shape[0] - 1 - r), 1, 1,
                                       fill=False, ec=INK, lw=1.4))
            alone = v["read"](g) is not None
            fig.text(0.03 + k * w, top + 0.03, f"t = {v['times'][i]:.2f} s",
                     fontsize=8, color=INK2)
            fig.text(0.03 + k * w, 0.105, f"{len(bad)} cell"
                     f"{'' if len(bad) == 1 else 's'} off", fontsize=8,
                     color=INK2)
            fig.text(0.03 + k * w, 0.055, "reads alone" if alone else
                     "fails alone", fontsize=8, color=AQUA if alone else MUTED)
        else:
            fig.text(0.03 + k * w, top + 0.03, "the vote", fontsize=8.5,
                     color=INK)
            fig.text(0.03 + k * w, 0.105, f"chunk {h['hit'][0] + 1} of "
                     f"{h['hit'][1]}", fontsize=8, color=INK2)
            fig.text(0.03 + k * w, 0.055, "checksum passes", fontsize=8,
                     color=AQUA)
    fig.text(0.03, 0.93, "One held frame, sampled several times, and the vote "
             "across them", fontsize=11)
    fig.text(0.03, 0.88, "Outlined: cells where a sample disagrees with the "
             "majority. Each cell takes its most common state.", color=INK2,
             fontsize=8.5)
    save(fig, "video_vote.png")


def fig_picture(v):
    """The picture, with the band each chunk carried."""
    got, total = v["got"], v["total"]
    room = D.chunk_bytes(CELL_PX, True)
    q, w, h, bpp, missing, lost, verified = D.reassemble(got, total=total,
                                                         size=room)
    img = np.asarray(D.levels_to_image(q, bpp), np.float32) / 255.
    how = {}
    for hf in v["held"]:
        if hf["hit"]:
            how.setdefault(hf["hit"][0], hf["how"])
    per_px = 8 // bpp
    fig = plt.figure(figsize=(8.8, 6.2))
    ax = fig.add_axes([0.20, 0.08, 0.76, 0.76])
    ax.imshow(img, cmap="gray", vmin=0, vmax=1, interpolation="nearest",
              extent=(0, w, h, 0))
    bare(ax)
    bar = fig.add_axes([0.165, 0.08, 0.03, 0.76], sharey=ax)
    colour = {"vote": BLUE, "reference": ORANGE, "one sample": AQUA}
    for k in range(total):
        p0 = max(0, (k * room - D.IMG_HDR) * per_px) / w      # in rows
        p1 = min(h, ((k + 1) * room - D.IMG_HDR) * per_px / w)
        bar.add_patch(Rectangle((0, p0), 1, p1 - p0 - 0.25,
                                color=colour.get(how.get(k), AXIS), lw=0))
        if k % 2 == 0:
            bar.text(-0.4, (p0 + p1) / 2, f"{k + 1}", ha="right", va="center",
                     fontsize=7, color=INK2)
    bar.set_xlim(0, 1); bar.set_ylim(h, 0); bare(bar)
    fig.text(0.04, 0.935, f"The picture: {w} x {h}, {1 << bpp} grey levels, "
             f"{len(got)} of {total} chunks", fontsize=11)
    fig.text(0.04, 0.895, "Each chunk carries about four rows. The bar says "
             "how it was read: the vote (blue), a single sample (green) or the "
             "reference pass (orange).", color=INK2, fontsize=8.5)
    if verified:
        fig.text(0.04, 0.862, "The CRC-16 over the whole picture checks out.",
                 color=INK2, fontsize=8.5)
    save(fig, "video_picture.png")
    return verified


def gif_recording(v, start=None, seconds=8.0, fps=8, height=360):
    """The camera view beside what the decoder reads from it, frame by frame."""
    lock = v["lock"]
    if start is None:                       # a window with a few changes in it
        changes = [h["run"][0] for h in v["held"][1:]]
        start = max(0.0, v["times"][changes[min(4, len(changes) - 1)]] - 1.0)
    frames, _, _ = D.video_samples(VIDEO, step_s=1.0 / fps, start_s=start,
                                   end_s=start + seconds, max_samples=1000)
    font = ImageFont.truetype(font_manager.findfont("DejaVu Sans"), 18)
    small = ImageFont.truetype(font_manager.findfont("DejaVu Sans"), 15)
    a, b = lock["aspect"]
    cell = height // b
    out = []
    box = None
    for t, im in frames:
        try:
            cc = D.panel_corners(im, lock, True)
            c = D.sample(im, cc, a, b)
            src = D.flatten_light(c) if lock["flat"] else c
            states = D.classify_nearest(src, lock["centres"])
        except Exception:
            continue
        if box is None:
            pts = np.array(cc)
            x0, y0 = pts.min(0); x1, y1 = pts.max(0)
            m = 0.08 * (y1 - y0)
            box = (int(x0 - m), int(y0 - m), int(x1 + m), int(y1 + m))
        cam = im.crop(box)
        cam = cam.resize((int(cam.width * height / cam.height), height),
                         Image.BILINEAR)
        grid = Image.fromarray((STATE_RGB[states] * 255).astype(np.uint8))
        grid = grid.resize((a * cell, b * cell), Image.NEAREST)
        r = v["read"](states)
        W = cam.width + grid.width + 60
        canvas = Image.new("RGB", (W, height + 100), BG)
        canvas.paste(cam, (20, 50)); canvas.paste(grid, (cam.width + 40, 50))
        d = ImageDraw.Draw(canvas)
        d.text((20, 14), "what the camera recorded", font=small, fill=INK2)
        d.text((cam.width + 40, 14), "what the decoder reads", font=small,
               fill=INK2)
        msg = (f"t = {t:.1f} s    chunk {r[0] + 1} of {r[1]}, checksum passes"
               if r else f"t = {t:.1f} s    does not read on its own")
        d.text((20, height + 66), msg, font=font, fill=INK if r else MUTED)
        out.append(canvas)
    path = os.path.join(OUT, "recording.gif")
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in out]
    pal[0].save(path, save_all=True, append_images=pal[1:], loop=0,
                duration=int(1000 / fps), optimize=True, disposal=1)
    print("  wrote", os.path.relpath(path, HERE),
          f"({len(out)} frames, {os.path.getsize(path) / 1e6:.1f} MB)")


def video_figures():
    v = replay_video()
    fig_timeline(v)
    fig_vote(v)
    verified = fig_picture(v)
    print(f"  picture checksum verified: {verified}")
    gif_recording(v)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which not in ("all", "text", "video"):
        raise SystemExit("use: all, text or video")
    if which in ("all", "text"):
        text_figures()
    if which in ("all", "video"):
        video_figures()

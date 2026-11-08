# The optics of the two-panel stack

Why two stacked LCD panels can carry two bits per cell, where the four states
actually come from, and how far a model of them can be pushed before the
measurement stops supporting it.

Everything below is reproducible: `fit_optics.py` repeats the calculations, and
the measured numbers come out of the decoder itself.

---

## 1. The arrangement

Three polarizers in series. The outer two switch between 0° and 90° — that is
all a liquid-crystal cell does, electrically — and the middle one is fixed at
30°. Each panel contributes one bit, so a cell of the stack has four states.

```
light ──▶ [polarizer 1] ──▶ [fixed 30°] ──▶ [polarizer 3] ──▶ camera
            0° or 90°                         0° or 90°
```

---

## 2. Two polarizers are not enough

Without the middle one, four switch settings give only **two** intensities,
because only the difference between the two axes matters:

| polarizer 1 | polarizer 3 | apart | transmitted |
|---|---|---|---|
| 0° | 0° | 0° | 1.00 |
| 0° | 90° | 90° | 0.00 |
| 90° | 0° | 90° | 0.00 |
| 90° | 90° | 0° | 1.00 |

Four settings, one bit.

## 3. Three polarizers give three levels, not four

Adding the fixed 30° polarizer splits the chain into two independent Malus
factors, because the middle polarizer resets the polarization to its own axis:

| polarizer 1 | polarizer 3 | | transmitted |
|---|---|---|---|
| 0° | 0° | cos²30 · cos²30 | **0.5625** |
| 0° | 90° | cos²30 · sin²30 | **0.1875** |
| 90° | 0° | sin²30 · cos²30 | **0.1875** |
| 90° | 90° | sin²30 · sin²30 | **0.0625** |

(1.00 is the light leaving the first polarizer; unpolarized input halves all
four equally.)

The two mixed settings tie. They are genuinely different *inside* the stack:

```
 0° → 30° → 90°   turn 30°, ×0.750 = 0.750   then turn 60°, ×0.250 = 0.1875
90° → 30° →  0°   turn 60°, ×0.250 = 0.250   then turn 30°, ×0.750 = 0.1875
```

Between the panels, one path carries **three times** the light of the other — a
real difference, measurable with a probe in the gap. It does not survive to the
exit, because the output is the product of the same two factors in the opposite
order, and multiplication does not care about order. The camera sits at the
exit, so the decoder cannot use it.

### The general condition

Let θ be the angle between polarizer 1 and the middle, φ the angle between the
middle and polarizer 3, and set x = cos²θ, y = cos²φ. Each outer polarizer
swings 90°, so its factor is x or 1−x, y or 1−y, and the four states are:

```
xy        x(1-y)        (1-x)y        (1-x)(1-y)
```

These are four distinct numbers **unless x = y or x + y = 1**.

When both outer polarizers switch within the same 0°/90° frame, φ = 90° − θ, so
y = 1 − x *for every middle angle*. This arrangement sits exactly on the
degenerate line, and no choice of middle angle moves it off. With the middle at
30°: θ = 30°, φ = 60°, x = 0.75, y = 0.25, x + y = 1.000.

### What escapes it

Mount polarizer 3 turned by 54°, so it switches 54°/144° instead of 0°/90°. It
still turns by 90°, it is only mounted differently. Now φ = 24°, x + y = 1.59,
and the four levels separate: 0.626 / 0.209 / 0.124 / 0.041. Sweeping both
mounting angles, the best this geometry ever does is a smallest gap of 0.086, at
θ = 57° and φ = 63°, giving 0.561 / 0.232 / 0.146 / 0.061.

So four states by brightness alone are possible — but always crowded. This
project does not use them.

---

## 4. What the panels actually do — measured

The decoder yields the four state colours for free. Every frame that decodes
reveals the true state of each of its cells, so a successful decode is also a
colour measurement. Averaged over 75 frames of a decoded recording, roughly
9,500 cells per state, raw camera RGB with no flat-field correction:

| state | panel 1 | panel 2 | R | G | B | luminance | |
|---|---|---|---|---|---|---|---|
| `00` | off | off | 0.986 | 0.773 | 0.506 | 0.755 | orange |
| `01` | **on** | off | 0.815 | 0.723 | 0.773 | 0.770 | purple |
| `10` | off | **on** | 0.774 | 0.936 | 0.547 | 0.752 | green |
| `11` | **on** | **on** | 0.585 | 0.867 | 0.824 | 0.759 | cyan |

Per-cell standard deviation is about 0.034 in each channel.

**The four states are equal in brightness to within 2.4%.** The luminance spread
across all four is 0.018, which is half the per-cell noise. Essentially the
entire signal is chromatic.

### Why RGB works and greyscale does not

| | worst-case separation | relative to noise |
|---|---|---|
| RGB | 0.271 | **8.0×** |
| greyscale | 0.0027 | **0.14×** |

Nearest-centroid classification under that noise predicts a per-cell error rate
of **0.003% in RGB and 47.3% in greyscale**. The decoder measures roughly 100%
and 57% accuracy respectively — a 43% observed greyscale error against 47.3%
predicted.

This is the single most important fact about the decoder, and it is not a tuning
detail: a greyscale classifier is not a worse classifier here, it is reading a
channel that carries almost no information.

---

## 5. A Jones model, and how far it gets

Malus's law cannot explain colour, and it cannot explain equal brightness
either. It also is not the right tool: the cells are **retarders**, not
polarizers. A polarizer projects and discards; a retarder is unitary — it keeps
the light and reshapes the polarization, in general into an ellipse. Malus has
no way to represent an ellipse.

For three *ideal polarizers*, Jones calculus [1] and Malus agree to 8×10⁻¹⁷, which
is machine precision — each projector leaves the light in a definite linear
state with no phase to carry, so the amplitudes are just products of cosines.
The extra machinery only earns its keep once a retarder is in the chain.

The cells are modelled as 90° twisted-nematic layers in the Gooch–Tarry form [2],
with retardance Δ = 2πΔnd/λ and

    X = √(φ² + (Δ/2)²)

The implementation is checked against the known transmission minima of a 90° TN
cell between parallel polarizers, at Δn·d/λ = √3/2, √15/2 and √35/2: it returns
0.000000 at all three.

### What the model explains

Qualitatively, it accounts for the thing that looked paradoxical. A cell's "90°"
is exactly 90° only at one wavelength; away from it the cell leaves the light
slightly elliptical rather than cleanly rotated, and how much that costs depends
on where the cell sits in the chain — the first cell's error is judged by the
middle polarizer, the second cell's by the exit polarizer. Those penalties do
not mirror each other, so the channels separate while the totals stay level.
That is the right shape of explanation for four equal-brightness, differently
coloured states, and it falls out without being put in by hand.

### What the fit does not establish

Fitting the model to the four measured colours — free parameters: middle angle,
exit angle, Δn·d for each panel, and three camera gains — reaches an rms of
0.047 against a measurement noise of 0.034. Close, but not within noise, and the
parameters are **not identifiable**:

| constraint | rms |
|---|---|
| all free | 0.047 |
| shared Δn·d between panels | 0.067 |
| middle polarizer fixed at 30° | **0.103** |
| middle at 30° and shared Δn·d | 0.123 |

Among the starts landing within 10% of the best fit, the exit polarizer angle
ranges over the entire allowed interval (−90° to 178°) and Δn·d over 0.37–0.73 µm
and 0.55–1.09 µm. Only the middle angle is pinned at all, to 43–52°.

Two things follow, and both are worth stating plainly:

1. **The fit does not measure the hardware.** Twelve numbers cannot constrain
   seven parameters when three of them are near-free scale factors. Any Δn·d
   quoted from this would be invented precision.
2. **Forcing the middle polarizer to 30° makes the fit twice as bad**, and
   pushes one panel's retardance onto its lower bound, which is unphysical. The
   model wants roughly 45–52° there.

That disagreement is unresolved. It may mean the model's geometry is wrong — it
assumes each cell's entry director aligns with the polarizer before it, and a
90° twist in both. It may mean the effective optical angle is not the marked
one. Or it may be the camera: real cameras apply a 3×3 colour matrix, not the
per-channel gains assumed here, and that alone could move the apparent angle.

**Conclusion:** the Jones model is a sound qualitative explanation and a poor
quantitative one. The measurement in section 4 stands on its own and needs no
model at all; the design decision it supports — classify in RGB, never in
luminance — rests on measured separations, not on any of this.

---

## 6. Open questions

- Is the 30° a marked angle on the polarizer film, or measured optically? The
  fit prefers 45–52°.
- Δn·d of these panels, independently measured, would turn the fit from
  unidentifiable into a real test of the model.
- A 3×3 camera colour matrix, or a raw (un-white-balanced) capture, would remove
  the largest modelling gap.
- The 3:1 intensity difference between the two mixed states exists *between* the
  panels. A photodiode or partial tap in the gap would read a state the exit
  cannot see.

---

## References

1. R. C. Jones, "A new calculus for the treatment of optical systems. I. Description and
   discussion of the calculus," *J. Opt. Soc. Am.*, vol. 31, no. 7, pp. 488–493, 1941.
   doi:[10.1364/JOSA.31.000488](https://doi.org/10.1364/JOSA.31.000488)
2. C. H. Gooch and H. A. Tarry, "The optical properties of twisted nematic liquid crystal
   structures with twist angles ≤90°," *J. Phys. D: Appl. Phys.*, vol. 8, no. 13,
   pp. 1575–1584, 1975. doi:[10.1088/0022-3727/8/13/020](https://doi.org/10.1088/0022-3727/8/13/020)

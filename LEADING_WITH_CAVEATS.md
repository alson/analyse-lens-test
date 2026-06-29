# Leading with caveats and assumptions

A reporting discipline for analysis conclusions in this project — especially
*negative* / *closure* conclusions ("this approach doesn't work", "this avenue is
closed", "not viable"). Written 2026-06-30 after a four-round case study (below).

## The practice

State a conclusion as:

> **Negative under [the conditions actually tested]. Not yet tested: [the assumptions
> and coverage gaps].**

…not as "final", "closed", or "definitively dead". The caveats and untested
assumptions are the **headline**, not a footnote you add when challenged.

## Why this matters

An exploratory-analysis verdict is only as strong as the assumptions behind it. A
confident "closed" *hides* those assumptions, which costs you twice:

1. **Premature closure becomes invisible.** If the untested assumptions aren't stated,
   a wrong "final" looks identical to a right one — to you and to the reader. You lose
   the ability to see where your own conclusion is fragile.
2. **It shuts down the cheapest source of correction — the domain expert.** When the
   caveats lead, the person who knows the target/domain can point straight at the
   untested angle. When the verdict leads, they first have to disbelieve you, then
   reconstruct what you skipped. (In the case study below, every reopening came from
   the user spotting an assumption the analysis had buried.)

Leading with caveats makes a conclusion **falsifiable on sight** and invites exactly
the correction that moves the work forward. A closure that survives having its
assumptions stated up front is a strong one. A closure that needs the assumptions
hidden to sound final isn't closed — it's untested.

## Case study: the cross-M sharpness ranking (2026-06-29 → 06-30)

"A cross-magnification *absolute* sharpness ranking is not viable on this wafer" was
declared closed/final **four times** and reopened four times — each by a **different
class** of hidden assumption that a confident verdict had buried:

1. **Model form.** "Fixed-subject-frequency contrast is M-confounded → dead." Buried:
   that the square-wave/`sinc(nD)` intrinsic-correction couldn't help. It *did*
   de-confound M (corr → ~0); the verdict dismissed it on a side-effect (invalid MTF
   values) without saying so.
2. **Model parameters.** "Pad-vs-maze MTF disagree 5× → the harmonic-shape rescue is
   dead." Buried: that pads and maze share one harmonic model. They don't — the maze
   skips/merges cycles → real even (N=2) harmonic content the odd-only model forces to
   zero (empirically `T2/T1 = 0.31`). The 5× was a wrong-shared-model artifact.
3. **Sample coverage.** "Empirical `T_n` tested, chain still dead → final." Buried:
   that the one pad pattern + maze tested represented *all* targets. The other magenta
   pad patterns and every cyan-marked structure were unswept.
4. **Measurement validity.** "Surveyed all 53 targets → target-wide dead, final."
   Buried: that the detector was measuring the intended feature. It wasn't — the
   discovery band `(0.06, 0.30)` cy/px sits *above* the actual pad-grid pitches
   (17–173 px → `f_px` 0.006–0.06), so the comb was anchored on a common in-band
   sub-feature, not the pad array. "All patterns collapse to one frequency" was a
   feature-locking artifact; the "instability" may just be a mis-anchored comb reading
   false harmonics.

The point: each "final" was honestly the best call *given what was tested* — and each
was wrong because the assumptions weren't where they could be checked. The four classes
are genuinely distinct (form → parameters → coverage → validity), so "just be more
careful" would not have caught them. But **listing the untested conditions each time**
would have turned every reopening into a one-line addition instead of a reversal — and
would have flagged, e.g., "we haven't verified the detector locks the pad grid rather
than a sub-feature" *before* it became three rounds of wasted finality.

## Checklist before declaring closure

- What did I **assume**? (model form; parameter values; that the measurement actually
  targets the intended feature)
- What did I **not test**? (coverage of cases; alternative explanations; the
  measurement's own validity)
- What would the **domain expert** know about the target that my analysis doesn't?
- Is the verdict phrased so those answers are the **headline**?

If you can't list the untested assumptions, you haven't earned the word "final".

"""
Evaluation package for the MIDI Remaster Lab.

Proposal citations:
  - RQ1 (content preservation): report/main.tex §Evaluation; 05-evaluation.tex §Quantitative Metrics
  - RQ4 (style consistency):    report/main.tex §Evaluation Table 2, FAD metric
  - Deliverable 5: Documentation and evaluation results (main.tex §Deliverables)

Modules:
    melody_similarity  — Melody contour similarity (Pearson correlation of pitch sequences).
    pics               — Pitch-Interval Contour Similarity (MIREX-style, LCS of interval contours).
    onset_alignment    — Onset alignment F-measure between two MIDI files.
    fad                — Fréchet Audio Distance between reference and generated audio sets.
"""

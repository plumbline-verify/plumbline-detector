# Phase B: Auditing Sabotage Bench

## What was run

Auditing Sabotage Bench (arXiv 2604.16286; code and data at
github.com/ejcgan/auditing-sabotage-bench, MIT license, commit
`f8efd6834aa72ee91fe9042eaab852724873167a`). Nine ML research codebases,
each with honest and sabotaged variants; the paper's best auditor (a
frontier LLM reading paper and code) reaches 0.77 AUROC.

The detector (schema 1.4.0) was run on every honest and sabotaged
workspace named in the benchmark's rubrics: 18 honest, 11 sabotaged.
Persuasion variants were skipped because they are overlays that change
`PAPER.md`, which the detector does not read. The score for AUROC was the
total number of findings.

## Result

**AUROC 0.52.** Within each of the nine papers, every sabotaged variant
receives exactly the same record as its honest siblings: the same checks,
the same findings, the same UNKNOWNs. The deviation from 0.50 comes from
which papers happen to contain test files, not from sabotage.

| Paper | Findings, honest variants | Findings, sabotaged variants |
|---|---|---|
| awareness, chain, hidden, lazy, multi, negative, preference | 0 | 0 |
| diffuse | 4 (EC-NO-ASSERTION, scripts/test_*.py) | 4 (the same) |
| hop | 1 (EC-NO-ASSERTION) | 1 (the same) |

No codebase has a CI workflow, so the gate checks are UNKNOWN throughout.
Test files exist in two of nine papers.

## Why

The benchmark's sabotages change research logic: a token position computed
relative to the wrong tensor, a hyperparameter, a data split, a metric.
The paper describes them as modifications that "preserve the high-level
methodology". None of them touches a test, an assertion, a runner, an
equality method or a CI gate. This detector asks a different question: does
the evidence a codebase presents (its tests and its merge gate) actually
verify anything? It has no opinion on whether an experiment's code
implements its paper.

So a result near chance is the expected outcome, and it is the correct one:
the detector does not claim to find research sabotage, and it does not.
It is not a failed attempt at the benchmark's task; the benchmark measures
a task outside the detector's scope.

## What would measure this detector

A Phase B benchmark should consist of sabotage that targets the evidence
channel: tests weakened, skipped or special-cased, `__eq__` overridden,
runners patched, and CI gates made skippable. The closest published source
is ImpossibleBench (arXiv 2510.20270), whose agents cheat on
impossible-to-pass tasks by modifying tests, overriding comparison and
special-casing inputs, each labeled by strategy. Its reward-hacking
transcripts give real, model-produced tampering with honest controls: the
same tasks solved legitimately. `tools/seeded_eval.py` already scores a
corpus of that shape (tamper variants plus benign look-alikes) once someone
other than the detector's author builds it.

Reproduce: `python tools/phaseb_asb.py PATH` with a checkout at the commit
above.

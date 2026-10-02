---
name: kompilo-demo
description: >-
  Prepare, run or update Kompilo's end-to-end demo and its honesty docs. Use when editing
  the demo walkthrough, the known-limits list, the seed script, or the top-level README's
  MVP framing. Triggers: demo, GUIDE_DEMO, walkthrough, scenario, seed, seed_demo, demo
  data, LIMITES_CONNUES, known limits, STUB inventory, V1.5 roadmap, MVP README, clean
  demo, what to show.
---

# Kompilo — demo, seed & honesty docs

Reference: `GUIDE_DEMO.md`, `LIMITES_CONNUES.md`, `README.md`, `backend/scripts/seed_demo.py`.

## The three demo artifacts

- **`GUIDE_DEMO.md`** — a scripted walkthrough: a real task → understood intent → strategy
  → compiled prompt → execution → result → diagnostic, each step saying *what to see*. Keep
  the UI labels EXACT (they must match the app: "Compiler"/"Bibliothèque", "Que veux-tu
  accomplir ?", "INTENTION COMPRISE", "INSTRUCTION COMPILÉE", "DIAGNOSTIC", "Exécution en
  direct (avancé)", "Comparer deux versions"). Include a curl variant for a terminal demo.
- **`LIMITES_CONNUES.md`** — the honest inventory. A "Ce qui est RÉEL" section, a table of
  every STUB/PLACEHOLDER with its user-visible signal, and the V1.5 roadmap with 3
  impact-ranked improvements. When a STUB becomes real, REMOVE its row here — the doc must
  never overstate the product.
- **`seed_demo.py`** — creates a demo org + owner, a project, a few tagged prompts, and one
  saved compilation, over the **HTTP API** (no DB internals), idempotently (signup→login,
  create→skip on 409). Config via `KOMPILO_API_URL` / `KOMPILO_DEMO_*`. The one saved
  version is a REAL deterministic compilation — never fabricated output.

## Rules

- Total honesty: nothing simulated is shown as real. Every STUB named in the code
  (`EchoProvider`, `retrieve`, `stages.py` compile/route/execute/verify/evaluate/improve,
  the SSE re-chunking, the PyTorch complexity backend) must appear in `LIMITES_CONNUES.md`.
- The current biggest gap is **evaluate/improve** (no measurement) — which is exactly why
  the version diff refuses a "better" verdict. Keep that link explicit across the docs.
- Keep the README's status note in sync with reality; cross-link the demo + limits from it.

## When reviewing a diff, reject it if

- the demo guide references UI labels or endpoints that don't exist as written;
- a STUB was made real but still listed as a limit (or vice-versa: a new STUB not listed);
- the seed script talks to the DB directly, isn't idempotent, or fabricates model output;
- any doc claims evaluate/improve or real RAG works, or calls a version "better".

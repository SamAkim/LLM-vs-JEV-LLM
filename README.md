# Jev + LLM — Realtime POC & Community Explainer

A small, **working** proof-of-concept that shows **where Jev is used, why, and how it
compares to an LLM** — live and in real time — built for a talk to an AI community.

It takes one incoming support message and handles it **two ways, raced side by side**:

| Pipeline | Decisions (route / urgency / frustration / risk / escalate) | Reply |
|---|---|---|
| **LLM-only** | A language model, forced to emit JSON | The same LLM |
| **Jev + LLM** | **Jev**, one fast parallel call | An LLM |

The UI streams each stage as it lands, so the audience literally watches Jev's typed
decisions snap in — with calibrated confidence — while the LLM baseline is still thinking,
then shows the **speed-up and cost saving** for that request.

> **The one-line thesis for the talk:** Jev doesn't replace the LLM. It's the *reflex
> layer* — it removes LLM calls from the decisions the LLM was overqualified and
> overpriced for, and leaves the LLM to do the one thing only it can: write the reply.

---

## Quick start

```bash
cd jev-llm-poc
cp .env.example .env     # optional — leave DEMO_SIMULATE=1 to run with no network
bash run.sh              # installs deps, serves on http://localhost:8000
```

Open http://localhost:8000, pick a preset (or type your own message), hit **Run comparison**.

### Running it for real (with APIs)

1. Put your keys in `.env`:
   - `TYPESAFE_API_KEY` — from <https://console.typesafe.ai/keys>
   - `OPENAI_API_KEY` (+ optional `OPENAI_BASE_URL`, `LLM_MODEL`) — any OpenAI-compatible endpoint, incl. your own gateway.
2. Set `DEMO_SIMULATE=` (empty) in `.env`.
3. `bash run.sh`.

Whichever key is missing falls back to a **clearly-marked simulation** for just that
provider, so you can demo Jev live even without an LLM key, or vice-versa. With
`DEMO_SIMULATE=1`, everything is simulated — ideal for an unreliable conference Wi-Fi.

---

## What Jev actually is (for the talk)

Jev is TypeSafe AI's **"System One" model**. Unlike an LLM, **it does not generate text.**
You send it a **state** (the context) and a set of **typed questions**, and it returns
**typed answers with calibrated probabilities and a confidence score**, in ~70–500 ms.
All questions in one request are evaluated **in parallel**, so asking five questions
costs barely more than asking one.

Three question types:

- **Noul** — a yes/no question → returns the probability the statement is true.
- **Choice** — pick one of N options → returns the pick, a probability per option, and confidence.
- **Score** — rate against ordered levels (low/med/high) → returns a continuous score, the distribution, and confidence.

The exact request/response shape this POC uses (`POST https://api.typesafe.ai/v1/systemone`):

```json
// request
{ "model": "jev-latest",
  "state": "Hi, my Stripe integration keeps failing and I'm losing sales. Help ASAP.",
  "questions": {
    "department":  {"type":"choice","instructions":"Which team should handle this",
                    "criteria":{"billing":"...","technical":"...","sales":"..."}},
    "frustration": {"type":"score","instructions":"How frustrated the customer appears",
                    "criteria":["Calm","Frustrated but civil","Very angry"]},
    "is_urgent":   {"type":"noul","instructions":"The message conveys urgency"} } }

// response
{ "answers": {
    "department":  {"type":"choice","choice":"technical","confidence":0.78,
                    "probabilities":{"technical":0.85,"billing":0.15,"sales":0.0}},
    "frustration": {"type":"score","score":1.0,"confidence":1.0,"probabilities":{...}},
    "is_urgent":   {"type":"noul","noul":0.999} },
  "usage": {"input_tokens":392,"output_tokens":65} }
```

## Where Jev is used

- **Model routing** — decide cheap-vs-powerful model per request (this POC's cousin).
- **Intent / urgency / risk classification** inside agent loops.
- **Tool-call risk gating** — classify a dangerous action *before* it executes ("Auto Mode").
- **Relevance & evidence scoring** in RAG — is this chunk actually relevant?
- **LLM-as-judge replacement** for closed rubrics — matched accuracy, ~1/5 the cost, ~1/10 the latency, better-calibrated.

## Why Jev (vs just calling an LLM)

- **Speed** — runs whole decision loops ~10×/second; an LLM needs seconds.
- **Cost** — TypeSafe cites **40–400× cheaper** than frontier LLMs on comparable classification.
- **Calibration** — real probabilities, and it tells you when it's unsure (an LLM is often *confidently* wrong).
- **Typed output** — software consumes it directly; no parsing/repairing an LLM's JSON.
- **Frees the LLM** for reasoning and generation, where it earns its cost.

## Why not *only* Jev

- It can't generate text, explanations, or open-ended plans.
- Weaker on open, long-context reasoning (e.g. judging summary consistency).
- No human-readable rationale — just a probability.
- → Use **Jev for reflexes, the LLM for reasoning and writing**. They're complements.

## Jev vs LLM — cheat sheet

| Dimension | Jev (System One) | Traditional LLM |
|---|---|---|
| Output | Typed value + probability + confidence | Free-form text |
| Core job | Fast structured decisions | Reasoning, generation, language |
| Latency | ~70–500 ms | Seconds |
| Cost | ~40–400× cheaper (classification) | Baseline |
| Many questions | All in parallel, one call | Sequential / separate calls |
| Uncertainty | Calibrated | Often confidently wrong |
| Explanations | None | Yes |
| Best for | Routing, urgency, risk, scoring, gating | Replies, synthesis, planning, code |

---

## How it's built

```
jev-llm-poc/
├── app.py            FastAPI; /run streams both pipelines as Server-Sent Events
├── jev_client.py     Jev REST wrapper (+ faithful, marked simulation)
├── llm_client.py     OpenAI-compatible LLM: classify_all() and generate_reply()
├── pricing.py        Illustrative, env-overridable cost model
├── static/index.html Single-file realtime UI + explainer (Kompact AI house colours)
├── requirements.txt
├── .env.example
└── run.sh
```

- Both pipelines are async generators interleaved with `asyncio.wait`, so the two
  columns update **truly in parallel** over one SSE stream.
- The decision schema is **identical** for both sides — the only difference is *who*
  makes the decisions (an LLM forced into JSON vs Jev), which is exactly the comparison.
- Swap in the official SDK any time: `pip install typesafe-sdk` and
  `from typesafe_sdk import Choice, Noul, Score, TypeSafeClient`.

## Talk track (suggested 5-min flow)

1. **Hook** — "Every box in an agent diagram is an LLM call. Most of them don't need to be."
2. Run **Calm sales** — both are fine, but watch the latency/cost gap.
3. Run **Angry billing** — Jev's confidence + frustration score snap in instantly.
4. Run **Risky / escalate** — Jev flags the destructive action for gating *before* any tool runs.
5. **Land it** — the comparison table; "reflex layer vs reasoning layer"; they're complements.

## Notes & honesty

- Latency/cost *claims* are TypeSafe's published figures; the live **cost counters** use
  illustrative rates (`*_RATE_PER_MTOK`) you can override — they're demo assumptions, not billing.
- Simulation responses are shaped exactly like real ones and flagged `"simulated": true`
  / a `simulation` badge, so nothing on stage is passed off as a real call.

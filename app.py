"""
Jev + Gemini realtime POC — FastAPI backend.

One incoming support message is handled TWO ways, raced live:

  Pipeline A  Gemini-only   : Gemini makes all typed decisions, then Gemini writes reply.
  Pipeline B  Jev + Gemini  : Jev makes ALL decisions in one fast parallel call,
                              then Gemini writes the reply. (Jev = the reflex layer.)

Both pipelines end in the SAME Gemini generation step, because writing the reply is
the one job Jev cannot do — that's the thesis of the talk: Jev doesn't replace
Gemini, it removes Gemini from the decisions it was overqualified and overpriced for.

The /run endpoint streams Server-Sent Events so the UI shows each stage landing in
real time — you literally watch Jev's decisions snap in while the LLM baseline is
still thinking.

Run:  uvicorn app:app --reload --port 8000
Then open http://localhost:8000
"""

from __future__ import annotations

import os
import json
import asyncio
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from jev_client import JevClient, noul, choice, score
from llm_client import LLMClient
import pricing

app = FastAPI(title="Jev + Gemini realtime POC")

STATIC_DIR = Path(__file__).parent / "static"


# --------------------------------------------------------------------------- #
# The shared decision schema — identical semantics for both pipelines.
# --------------------------------------------------------------------------- #
JEV_QUESTIONS = {
    "department": choice(
        "Which team should handle this",
        {"billing": "Payment, invoice or subscription issues",
         "technical": "Bugs, errors or integration problems",
         "sales": "Pricing, plans or account questions"}),
    "frustration": score(
        "How frustrated the customer appears",
        ["Calm, just stating facts",
         "Frustrated but civil",
         "Very angry, strong language"]),
    "is_urgent": noul("The message conveys urgency or time-sensitivity"),
    "is_risky": noul("The request asks for a destructive or irreversible action "
                     "(delete/close account, chargeback, wipe data)"),
    "needs_human": noul("This should be escalated to a human agent now"),
}

LLM_SCHEMA_HINT = (
    'Return keys exactly: {"department": one of "billing"|"technical"|"sales", '
    '"is_urgent": boolean, "frustration": integer 0|1|2, '
    '"is_risky": boolean, "needs_human": boolean}.')


def _reload_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except ImportError:
        pass


def _clients() -> tuple[JevClient, LLMClient, LLMClient]:
    _reload_env()
    key_1 = os.getenv("GEMINI_API_KEY_1") or os.getenv("GEMINI_API_KEY")
    key_2 = os.getenv("GEMINI_API_KEY_2") or os.getenv("GEMINI_API_KEY")
    return JevClient(), LLMClient(api_key=key_1), LLMClient(api_key=key_2)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# Normalise an LLM classification dict into the same shape the UI renders Jev in.
def _llm_decisions_to_cards(d: dict) -> dict:
    return {
        "department": {"value": d.get("department"), "confidence": None},
        "frustration": {"value": d.get("frustration"), "confidence": None},
        "is_urgent": {"value": bool(d.get("is_urgent")), "confidence": None},
        "is_risky": {"value": bool(d.get("is_risky")), "confidence": None},
        "needs_human": {"value": bool(d.get("needs_human")), "confidence": None},
    }


def _jev_answers_to_cards(answers: dict) -> dict:
    cards = {}
    for name, a in answers.items():
        t = a["type"]
        if t == "noul":
            cards[name] = {"value": a["noul"] >= 0.5,
                           "confidence": round(max(a["noul"], 1 - a["noul"]), 3),
                           "prob": a["noul"]}
        elif t == "choice":
            cards[name] = {"value": a["choice"], "confidence": a.get("confidence"),
                           "probabilities": a.get("probabilities")}
        elif t == "score":
            cards[name] = {"value": a["score"], "confidence": a.get("confidence"),
                           "legend": a.get("legend"),
                           "probabilities": a.get("probabilities")}
    return cards


async def run_stream(message: str):
    try:
        jev, llm_a, llm_b = _clients()
    except Exception as e:
        yield sse("error", {"error": str(e)})
        yield sse("complete", {})
        return

    loop = asyncio.get_event_loop()
    yield sse("start", {"message": message, "mode": "live"})

    # ---- define the two pipelines as coroutines -------------------------- #
    async def pipeline_llm():
        try:
            yield ("llm", "stage", {"stage": "classify", "status": "running",
                                    "label": "Gemini making decisions"})
            decisions, lat, usage = await loop.run_in_executor(
                None, llm_a.classify_all, message, LLM_SCHEMA_HINT)
            cost = pricing.gemini_cost(usage)
            yield ("llm", "decisions", {"cards": _llm_decisions_to_cards(decisions),
                                        "latency_s": lat, "usage": usage,
                                        "cost_usd": cost})
            yield ("llm", "stage", {"stage": "generate", "status": "running",
                                    "label": "Gemini writing reply"})
            reply, lat2, usage2 = await loop.run_in_executor(
                None, llm_a.generate_reply, message, decisions)
            cost2 = pricing.gemini_cost(usage2)
            yield ("llm", "reply", {"reply": reply, "latency_s": lat2,
                                    "usage": usage2, "cost_usd": cost2})
            yield ("llm", "done", {"total_latency_s": round(lat + lat2, 4),
                                   "total_cost_usd": round(cost + cost2, 8),
                                   "model_calls": 2})
        except Exception as e:
            yield ("llm", "error", {"error": str(e)})

    async def pipeline_jev():
        try:
            yield ("jev", "stage", {"stage": "classify", "status": "running",
                                    "label": "Jev making decisions (parallel)"})
            result = await loop.run_in_executor(
                None, jev.system_one, message, JEV_QUESTIONS)
            lat = result["_latency_s"]
            usage = result.get("usage", {})
            cost = pricing.jev_cost(usage)
            yield ("jev", "decisions", {"cards": _jev_answers_to_cards(result["answers"]),
                                        "latency_s": lat, "usage": usage,
                                        "cost_usd": cost,
                                        "model": result.get("model")})
            decisions = {k: (v.get("choice") if v["type"] == "choice"
                             else (v.get("score") if v["type"] == "score"
                                   else v["noul"] >= 0.5))
                         for k, v in result["answers"].items()}
            yield ("jev", "stage", {"stage": "generate", "status": "running",
                                    "label": "Gemini writing reply"})
            reply, lat2, usage2 = await loop.run_in_executor(
                None, llm_b.generate_reply, message, decisions)
            cost2 = pricing.gemini_cost(usage2)
            yield ("jev", "reply", {"reply": reply, "latency_s": lat2,
                                    "usage": usage2, "cost_usd": cost2})
            yield ("jev", "done", {"total_latency_s": round(lat + lat2, 4),
                                   "total_cost_usd": round(cost + cost2, 8),
                                   "model_calls": 2,
                                   "note": "1 Jev call + 1 LLM call"})
        except Exception as e:
            yield ("jev", "error", {"error": str(e)})

    # ---- interleave both pipelines so the UI updates truly in parallel --- #
    gens = {"llm": pipeline_llm(), "jev": pipeline_jev()}
    tasks = {name: asyncio.ensure_future(_anext(g)) for name, g in gens.items()}

    while tasks:
        done, _ = await asyncio.wait(tasks.values(),
                                     return_when=asyncio.FIRST_COMPLETED)
        for name in list(tasks):
            t = tasks[name]
            if t in done:
                try:
                    side, event, data = t.result()
                    yield sse(event, {"side": side, **data})
                    tasks[name] = asyncio.ensure_future(_anext(gens[name]))
                except StopAsyncIteration:
                    del tasks[name]

    yield sse("complete", {})


async def _anext(agen):
    return await agen.__anext__()


@app.get("/run")
async def run(request: Request, message: str):
    return StreamingResponse(run_stream(message),
                             media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/config")
async def config():
    _reload_env()
    return JSONResponse({
        "has_jev_key": bool(os.getenv("BEATAPI_API_KEY")),
        "has_gemini_key": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY_1")),
        "gemini_rate_per_mtok": pricing.GEMINI_RATE_PER_MTOK,
        "jev_rate_per_mtok": pricing.JEV_RATE_PER_MTOK,
    })


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

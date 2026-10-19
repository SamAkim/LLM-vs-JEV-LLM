"""
Jev client — "System One" decision model, accessed via BeatAPI.

Jev is NOT an LLM. It does not generate text. You send it a `state` (context)
and a set of typed `questions`, and it returns typed answers with calibrated
probabilities + confidence, in ~70-500ms. All questions in one request are
evaluated in parallel.

Docs: https://docs.beatapi.io  (Decisions API)
Endpoint: POST https://api.beatapi.io/v1/systemone   (Bearer auth)

Question types:
  - noul   : yes/no    -> returns P(true)
  - choice : pick one  -> returns chosen label, per-option probabilities, confidence
  - score  : ordinal   -> returns continuous score, level distribution, confidence

Models:
  - jev-1.13-free : Free model, $0 input/output. 1 req/min (10/min after first top-up).
  - jev-1.13      : Paid model, $0.042 per 1M input tokens; output free.
"""

from __future__ import annotations

import os
import time
import httpx

JEV_ENDPOINT = "https://api.beatapi.io/v1/systemone"
JEV_DEFAULT_MODEL = "jev-1.13-free"


# --------------------------------------------------------------------------- #
# Question builders (mirror the typesafe-sdk: Noul / Choice / Score)
# --------------------------------------------------------------------------- #
def noul(instructions: str) -> dict:
    return {"type": "noul", "instructions": instructions}


def choice(instructions: str, criteria: dict[str, str]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def score(instructions: str, criteria: list[str]) -> dict:
    return {"type": "score", "instructions": instructions, "criteria": criteria}


class JevClient:
    """REST wrapper around the BeatAPI Decisions endpoint."""

    def __init__(self, api_key: str | None = None, model: str = JEV_DEFAULT_MODEL,
                 timeout: float = 15.0):
        self.api_key = api_key or os.getenv("BEATAPI_API_KEY")
        if not self.api_key:
            raise ValueError("BEATAPI_API_KEY is not set. Please set it in your .env file.")
        self.model = model
        self.timeout = timeout

    def _call_real(self, state: str, questions: dict) -> dict:
        print(f"[JEV] Calling REAL BeatAPI endpoint: {JEV_ENDPOINT} (model: {self.model})...", flush=True)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {"model": self.model, "state": state, "questions": questions}
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(JEV_ENDPOINT, headers=headers, json=body)
            r.raise_for_status()
            print(f"[JEV] BeatAPI call successful (HTTP {r.status_code})", flush=True)
            return r.json()

    def system_one(self, state: str, questions: dict) -> dict:
        t0 = time.perf_counter()
        result = self._call_real(state, questions)
        latency = time.perf_counter() - t0
        result["_latency_s"] = round(latency, 4)
        return result

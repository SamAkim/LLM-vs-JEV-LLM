"""
LLM client — Google Gemini via the OpenAI-compatible REST endpoint.

Uses two methods in this POC:

  1. classify_all(...)  -> the LLM makes the SAME typed decisions Jev makes,
                           by forcing a JSON object out of it. This is the
                           "LLM does the reflex work too" baseline.
  2. generate_reply(...)-> the LLM writes the customer-facing reply. This is
                           the job only an LLM can do; BOTH pipelines use it.

Connects to Google's Gemini API via its OpenAI-compatible endpoint:
  https://generativelanguage.googleapis.com/v1beta/openai/
Authenticates with GEMINI_API_KEY. Default model: gemini-2.5-flash.
"""

from __future__ import annotations

import os
import json
import time
import httpx

DEFAULT_LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.5-flash-lite")


class LLMClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str = DEFAULT_LLM_MODEL, timeout: float = 60.0):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set. Please set it in your .env file.")
        self.base_url = (base_url or os.getenv("GEMINI_BASE_URL")
                         or "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
        self.model = model
        self.timeout = timeout

    # -- raw chat ---------------------------------------------------------- #
    def _chat(self, messages: list[dict], json_mode: bool = False,
              max_tokens: int = 400) -> dict:
        print(f"[GEMINI] Calling REAL Gemini endpoint: {self.base_url} (model: {self.model})...", flush=True)
        headers = {"Authorization": f"Bearer {self.api_key}",
                   "Content-Type": "application/json"}
        body = {"model": self.model, "messages": messages,
                "max_tokens": max_tokens, "temperature": 0.2}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(f"{self.base_url}/chat/completions",
                            headers=headers, json=body)
            r.raise_for_status()
            print(f"[GEMINI] Gemini call successful (HTTP {r.status_code})", flush=True)
            return r.json()

    # -- 1. classification (LLM doing Jev's job) --------------------------- #
    def classify_all(self, state: str, schema_hint: str) -> tuple[dict, float, dict]:
        t0 = time.perf_counter()
        sys = ("You are a routing classifier for a support agent. "
               "Return ONLY a JSON object, no prose. " + schema_hint)
        resp = self._chat(
            [{"role": "system", "content": sys},
             {"role": "user", "content": state}],
            json_mode=True, max_tokens=300)
        content = resp["choices"][0]["message"]["content"]
        data = json.loads(content)
        usage = {"input_tokens": resp.get("usage", {}).get("prompt_tokens", 0),
                 "output_tokens": resp.get("usage", {}).get("completion_tokens", 0)}
        return data, round(time.perf_counter() - t0, 4), usage

    # -- 2. generation (the irreducibly-LLM job) -------------------------- #
    def generate_reply(self, state: str, decisions: dict) -> tuple[str, float, dict]:
        t0 = time.perf_counter()
        dept = decisions.get("department", "support")
        tone = ("Be calm, concrete and apologetic; acknowledge urgency."
                if decisions.get("is_urgent") else "Be warm and concise.")
        sys = (f"You are a {dept} support agent. {tone} "
               "Write a short reply (3-5 sentences). Do not invent facts.")
        resp = self._chat(
            [{"role": "system", "content": sys},
             {"role": "user", "content": state}],
            max_tokens=250)
        reply = resp["choices"][0]["message"]["content"].strip()
        usage = {"input_tokens": resp.get("usage", {}).get("prompt_tokens", 0),
                 "output_tokens": resp.get("usage", {}).get("completion_tokens", 0)}
        return reply, round(time.perf_counter() - t0, 4), usage

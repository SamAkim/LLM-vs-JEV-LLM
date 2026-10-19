"""
Cost model for the demo.

These are illustrative per-million-token rates so the live cost counters mean
something on stage.  Gemini 2.5 Flash is Google's lightweight model with very
competitive pricing; the free Jev model (jev-1.13-free) via BeatAPI costs $0.

Nothing here is a billing source of truth — it is a transparent, tweakable demo
assumption, and the UI labels it as such.
"""

import os

# USD per 1,000,000 tokens (blended in+out for simplicity in the demo).
GEMINI_RATE_PER_MTOK = float(os.getenv("GEMINI_RATE_PER_MTOK", "0.30"))
# jev-1.13-free = $0;  jev-1.13 (paid) = $0.042/MTok input, output free
JEV_RATE_PER_MTOK = float(os.getenv("JEV_RATE_PER_MTOK", "0.0"))


def cost_usd(input_tokens: int, output_tokens: int, rate_per_mtok: float) -> float:
    return (input_tokens + output_tokens) / 1_000_000 * rate_per_mtok


def gemini_cost(usage: dict) -> float:
    return cost_usd(usage.get("input_tokens", 0),
                    usage.get("output_tokens", 0), GEMINI_RATE_PER_MTOK)


def jev_cost(usage: dict) -> float:
    return cost_usd(usage.get("input_tokens", 0),
                    usage.get("output_tokens", 0), JEV_RATE_PER_MTOK)

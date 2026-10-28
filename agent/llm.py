"""Claude client that returns structured JSON (topics, sticker designs, captions)."""
from __future__ import annotations

import json

import anthropic

from . import costs

# Claude Opus 5.5 list prices, USD per million tokens (used only for the cost estimate in the logs).
PRICE_IN, PRICE_OUT = 4.0, 20.0

STR = {"type": "string"}
INT = {"type": "integer"}


def obj(**properties) -> dict:
    """JSON-schema object where every property is required (structured outputs need this)."""
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def arr(items: dict) -> dict:
    return {"type": "array", "items": items}


class Claude:
    def __init__(self, model: str = "claude-opus-5-5", effort: str = "high"):
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model
        self.effort = effort
        self.cost = 0.0

    def ask_json(self, system: str, prompt: str, schema: dict) -> dict:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            # If a safety classifier wrongly declines, the API retries on a fallback model in the same call,
            # so a false positive never kills a scheduled post.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
        )
        usage = response.usage
        call_cost = usage.input_tokens * PRICE_IN / 1e6 + usage.output_tokens * PRICE_OUT / 1e6
        self.cost += call_cost
        costs.record("anthropic", self.model, call_cost)
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise RuntimeError(f"Claude declined this request (category: {getattr(details, 'category', None)}).")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Claude's answer was cut off (max_tokens reached).")
        text = next(block.text for block in response.content if block.type == "text")
        return json.loads(text)

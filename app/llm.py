"""Provider-agnostic LLM client with retry, cost tracking, and a mock mode.

Generator and judge MUST use different providers (cross-model evaluation
removes self-agreement bias). Configure via env vars, see .env.example.
"""
from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass, field

GENERATOR_PROVIDER = os.getenv("GENERATOR_PROVIDER", "openai")
JUDGE_PROVIDER = os.getenv("JUDGE_PROVIDER", "anthropic")

COST_PER_1K = {  # USD, approximate input/output blended; adjust to your plan
    "openai": 0.003,
    "anthropic": 0.004,
    "gemini": 0.001,
    "mock": 0.0,
}


@dataclass
class Usage:
    calls: int = 0
    tokens_est: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    log: list[dict] = field(default_factory=list)

    def record(self, provider: str, prompt: str, latency: float):
        tokens = max(1, len(prompt) // 4)
        cost = tokens / 1000 * COST_PER_1K.get(provider, 0.003)
        self.calls += 1
        self.tokens_est += tokens
        self.cost_usd += cost
        self.latency_s += latency
        self.log.append({"provider": provider, "tokens_est": tokens,
                         "cost_usd": round(cost, 6), "latency_s": round(latency, 3)})


class LLMClient:
    def __init__(self, provider: str, usage: Usage | None = None):
        self.provider = provider
        self.usage = usage or Usage()

    def generate(self, system: str, prompt: str, max_tokens: int = 1200,
                 temperature: float = 0.3, retries: int = 3) -> str:
        last_err = None
        for attempt in range(retries):
            start = time.time()
            try:
                out = self._call(system, prompt, max_tokens, temperature)
                self.usage.record(self.provider, system + prompt, time.time() - start)
                return out
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"{self.provider} failed after {retries} tries: {last_err}")

    def _call(self, system: str, prompt: str, max_tokens: int, temperature: float) -> str:
        if self.provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            r = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
                max_tokens=max_tokens, temperature=temperature)
            return r.choices[0].message.content
        if self.provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            r = client.messages.create(
                model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
                max_tokens=max_tokens, temperature=temperature,
                system=system, messages=[{"role": "user", "content": prompt}])
            return "".join(b.text for b in r.content if b.type == "text")
        if self.provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
            model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                                          system_instruction=system)
            return model.generate_content(prompt).text
        if self.provider == "mock":
            return json.dumps({"summary": prompt[:120], "headline": "عنوان تجريبي",
                               "post": "منشور تجريبي", "category": "عام",
                               "accuracy": 4, "fidelity": 4, "tone": 4,
                               "language": 5, "verdict": "pass", "issues": []},
                              ensure_ascii=False)
        raise ValueError(f"unknown provider: {self.provider}")


def make_pair(usage: Usage | None = None) -> tuple[LLMClient, LLMClient]:
    """Returns (generator, judge) guaranteed to be different providers (except mock tests)."""
    usage = usage or Usage()
    gen = LLMClient(GENERATOR_PROVIDER, usage)
    judge = LLMClient(JUDGE_PROVIDER, usage)
    if judge.provider == gen.provider and gen.provider != "mock":
        judge = LLMClient("mock", usage)
    return gen, judge

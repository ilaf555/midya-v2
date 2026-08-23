"""Layered guardrails: cheap deterministic checks first, LLM checks last."""
from __future__ import annotations
import re
from dataclasses import dataclass, field

from .arabic import arabic_ratio

MIN_LEN, MAX_LEN = 40, 4000
BLOCKED_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\b(viagra|casino|betting)\b",
        "أرباح مضمونة", "اضغط هنا فورا",
    ]
]
PRIVATE_DATA = re.compile(r"\b\d{16}\b|\b0?5\d{8}\b")  # card numbers, SA mobiles


@dataclass
class GuardrailResult:
    passed: bool = True
    reasons: list[str] = field(default_factory=list)

    def fail(self, reason: str):
        self.passed = False
        self.reasons.append(reason)


def run_cheap_checks(text: str, require_arabic: bool = True) -> GuardrailResult:
    r = GuardrailResult()
    if not (MIN_LEN <= len(text) <= MAX_LEN):
        r.fail(f"length-out-of-range:{len(text)}")
    for p in BLOCKED_PATTERNS:
        if p.search(text):
            r.fail(f"blocked-pattern:{p.pattern[:30]}")
    if PRIVATE_DATA.search(text):
        r.fail("private-data-detected")
    if require_arabic and arabic_ratio(text) < 0.5:
        r.fail(f"low-arabic-ratio:{arabic_ratio(text):.2f}")
    if text.count("http") > 3:
        r.fail("too-many-links")
    return r

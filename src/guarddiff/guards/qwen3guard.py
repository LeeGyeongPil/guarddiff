"""Qwen3Guard-Gen output parser, strict/loose policy and the optional live HF guard.

The parser and policy need no third-party package. ``HFQwen3Guard`` imports
transformers and torch lazily and tells the user how to install them if missing.
"""

from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass
from typing import Any

from ..errors import ConfigError, GuardParseError, MissingExtraError
from .base import Guard, GuardVerdict

MODEL_ID = "Qwen/Qwen3Guard-Gen-0.6B"
LABELS = ("Safe", "Unsafe", "Controversial")
# strict blocks Unsafe and Controversial, loose blocks only Unsafe (the model's two modes).
BLOCK_LABELS = {"strict": frozenset({"Unsafe", "Controversial"}), "loose": frozenset({"Unsafe"})}

_SAFETY = re.compile(r"Safety:\s*(Safe|Unsafe|Controversial)")
_CATEGORIES = re.compile(
    r"(Violent|Non-violent Illegal Acts|Sexual Content or Sexual Acts|PII|Suicide & Self-Harm|"
    r"Unethical Acts|Politically Sensitive Topics|Copyright Violation|Jailbreak|None)")
_REFUSAL = re.compile(r"Refusal:\s*(Yes|No)")


@dataclass(frozen=True)
class Qwen3GuardOutput:
    label: str  # Safe | Unsafe | Controversial
    categories: tuple[str, ...]
    refusal: bool | None  # only present when an assistant reply was moderated


def parse_output(text: str) -> Qwen3GuardOutput:
    """Parse the model's text. Raises GuardParseError when there is no 'Safety:' line."""
    m = _SAFETY.search(text)
    if not m:
        raise GuardParseError(f"no 'Safety:' line in guard output: {text.strip()[:80]!r}")
    cats = tuple(_CATEGORIES.findall(text))
    r = _REFUSAL.search(text)
    return Qwen3GuardOutput(m.group(1), cats, None if r is None else r.group(1) == "Yes")


def blocks(label: str, mode: str) -> bool:
    """True when ``mode`` ('strict' or 'loose') blocks ``label``."""
    if mode not in BLOCK_LABELS:
        raise ConfigError(f"mode must be 'strict' or 'loose', got {mode!r}.")
    return label in BLOCK_LABELS[mode]


def reason_for(out: Qwen3GuardOutput) -> str:
    cats = ", ".join(out.categories) if out.categories else "-"
    return f"label {out.label}, categories {cats}"


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def require_hf_extra() -> None:
    """Raise MissingExtraError (with install commands) when transformers/torch are absent."""
    missing = [m for m in ("transformers", "torch") if not _module_available(m)]
    if missing:
        raise MissingExtraError(
            f"the 'hf-qwen3guard' guard needs {', '.join(missing)}, which is not installed. "
            'Install the extra with `uv sync --extra hf` (in a clone) or `pip install "guarddiff[hf]"`.')


class HFQwen3Guard(Guard):
    """Runs Qwen3Guard-Gen locally (CPU or GPU). Slow on CPU: about 1 s per text for the 0.6B model."""

    def __init__(self, name: str, stage: str = "input", *, mode: str = "strict", model: str = MODEL_ID,
                 max_new_tokens: int = 128, **kwargs: Any) -> None:
        super().__init__(name, stage, **kwargs)
        if mode not in BLOCK_LABELS:
            raise ConfigError(f"guard '{name}': mode must be 'strict' or 'loose', got {mode!r}.")
        require_hf_extra()
        self.mode, self.model_id, self.max_new_tokens = mode, model, max_new_tokens
        self._tok: Any = None
        self._model: Any = None

    def prepare(self) -> None:
        if self._model is not None:
            return
        import torch  # noqa: PLC0415 - lazy on purpose
        from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415

        self._tok = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModelForCausalLM.from_pretrained(self.model_id, dtype=torch.float32)
        self._model.eval()
        self._generate("warm-up", None)  # the first call is slow; keep it out of the latency numbers

    def _generate(self, prompt: str, answer: str | None) -> str:
        import torch  # noqa: PLC0415

        msgs = [{"role": "user", "content": prompt}]
        if answer is not None:
            msgs.append({"role": "assistant", "content": answer})
        text = self._tok.apply_chat_template(msgs, tokenize=False)
        inputs = self._tok([text], return_tensors="pt").to(self._model.device)
        with torch.no_grad():
            gen = self._model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
        return self._tok.decode(gen[0][len(inputs.input_ids[0]):].tolist(), skip_special_tokens=True)

    def check(self, text: str, *, item_id: str, prompt: str) -> GuardVerdict:
        self.prepare()
        raw = self._generate(prompt, text if self.stage == "output" else None)
        out = parse_output(raw)
        blocked = blocks(out.label, self.mode)
        return GuardVerdict(blocked, reason_for(out) if blocked else None)

    def close(self) -> None:
        self._tok = self._model = None

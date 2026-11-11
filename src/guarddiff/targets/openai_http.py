"""OpenAI-compatible ``/chat/completions`` target (Ollama, vLLM, hosted APIs) over urllib."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from ..errors import ConfigError
from .base import Target, TargetReply, strip_thinking


class OpenAIHTTPTarget(Target):
    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434/v1", *, max_tokens: int = 512,
                 temperature: float = 0.0, api_key_env: str = "OPENAI_API_KEY", system: str | None = None,
                 timeout_s: float = 300.0) -> None:
        if not model:
            raise ConfigError("[target] type='openai' needs 'model' (for example model = \"qwen3:4b\").")
        if not base_url.startswith(("http://", "https://")):
            raise ConfigError(f"[target] base_url must start with http:// or https://, got {base_url!r}.")
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.max_tokens, self.temperature, self.system = max_tokens, temperature, system
        self.api_key_env, self.timeout_s = api_key_env, timeout_s  # slow local models are normal: generous timeout

    def _request(self, prompt: str) -> urllib.request.Request:
        messages: list[dict[str, str]] = []
        if self.system:
            messages.append({"role": "system", "content": self.system})
        messages.append({"role": "user", "content": prompt})
        body = {"model": self.model, "messages": messages, "max_tokens": self.max_tokens,
                "temperature": self.temperature}
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env)
        if key:  # no key set -> no Authorization header (local servers need none)
            headers["Authorization"] = f"Bearer {key}"
        return urllib.request.Request(self.url, data=json.dumps(body).encode(), headers=headers, method="POST")

    def call(self, prompt: str) -> TargetReply:
        try:
            with urllib.request.urlopen(self._request(prompt), timeout=self.timeout_s) as resp:  # noqa: S310
                data: Any = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return TargetReply("", error=f"HTTP {e.code} from {self.url}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return TargetReply("", error=f"{type(e).__name__}: {e} (is the server at {self.url} running?)")
        except ValueError as e:
            return TargetReply("", error=f"response is not valid JSON ({e})")
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            return TargetReply("", error="response has no choices[0].message.content")
        usage = data.get("usage") if isinstance(data, dict) else None
        tokens = {k: int(usage[k]) for k in ("prompt_tokens", "completion_tokens")
                  if isinstance(usage, dict) and isinstance(usage.get(k), int)}
        return TargetReply(strip_thinking(content), usage=tokens)

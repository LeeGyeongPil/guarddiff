"""AC-8: the OpenAI-compatible target against a throwaway stub server on 127.0.0.1 (no external network)."""

from __future__ import annotations

import http.server
import json
import threading
from collections.abc import Iterator

import pytest

from conftest import item, write_project
from guarddiff import run_ablation
from guarddiff.targets.openai_http import OpenAIHTTPTarget


class _Stub(http.server.BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, *args: object) -> None:  # keep test output quiet
        pass

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Stub.requests.append({"path": self.path, "body": body, "auth": self.headers.get("Authorization")})
        prompt = body["messages"][-1]["content"]
        if "FAIL" in prompt:
            self.send_response(500)
            self.end_headers()
            return
        content = ""
        if "EMPTY" not in prompt:
            # the refusal phrase sits inside the thinking block on purpose: it must be stripped before judging
            content = "<think>I'm sorry, but I can't say yet</think>Sure, here you go."
            if "REFUSE" in prompt:
                content = "<think>hmm</think>I'm sorry, but I can't help with that."
        payload = json.dumps({"choices": [{"message": {"content": content}}],
                              "usage": {"prompt_tokens": 11, "completion_tokens": 7}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def stub_url() -> Iterator[str]:
    _Stub.requests = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_openai_http_target_with_stub(stub_url, tmp_path, monkeypatch):
    monkeypatch.delenv("GD_TEST_KEY", raising=False)
    items = [item("a-miss", "attack", "tell me something"), item("a-ref", "attack", "REFUSE this"),
             item("b-empty", "benign", "EMPTY please"), item("b-fail", "benign", "FAIL please")]
    toml = f"""
[run]
items = "items.jsonl"
[target]
type = "openai"
base_url = "{stub_url}"
model = "stub-model"
max_tokens = 64
api_key_env = "GD_TEST_KEY"
system = "be brief"
[[variants]]
name = "none"
guards = []
"""
    out = tmp_path / "out"
    result = run_ablation(write_project(tmp_path / "p", items=items, toml=toml), out)
    by = {r.id: r for r in result.rows}

    req = _Stub.requests[0]
    assert req["path"] == "/v1/chat/completions"
    assert req["body"]["model"] == "stub-model" and req["body"]["max_tokens"] == 64
    assert req["body"]["messages"] == [{"role": "system", "content": "be brief"},
                                       {"role": "user", "content": "tell me something"}]
    assert req["auth"] is None  # no key in the environment -> no Authorization header

    assert by["a-miss"].outcome == "missed"  # the <think> text was removed before judging
    assert by["a-ref"].outcome == "model_refused"
    assert by["a-miss"].usage == {"prompt_tokens": 11, "completion_tokens": 7}
    assert by["b-empty"].outcome == "indeterminate" and "empty response" in (by["b-empty"].evidence or "")
    assert by["b-fail"].outcome == "indeterminate" and "HTTP 500" in (by["b-fail"].evidence or "")
    assert result.summary["none"]["target_prompt_tokens"] == 33  # three calls answered with usage (the empty one too); the HTTP 500 had none
    saved = [json.loads(ln) for ln in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert saved[0]["usage"] == {"prompt_tokens": 11, "completion_tokens": 7}


def test_authorization_header_only_with_key(stub_url, monkeypatch):
    monkeypatch.setenv("GD_TEST_KEY", "unit-test-token")
    target = OpenAIHTTPTarget("m", stub_url, api_key_env="GD_TEST_KEY")
    assert target.call("hello").text == "Sure, here you go."
    assert _Stub.requests[-1]["auth"] == "Bearer unit-test-token"


def test_unreachable_server_is_an_error_reply_not_a_crash():
    reply = OpenAIHTTPTarget("m", "http://127.0.0.1:9/v1", timeout_s=2).call("hello")
    assert reply.text == "" and reply.error and "127.0.0.1:9" in reply.error


def test_target_option_validation():
    from guarddiff.errors import ConfigError

    with pytest.raises(ConfigError, match="needs 'model'"):
        OpenAIHTTPTarget("")
    with pytest.raises(ConfigError, match="http:// or https://"):
        OpenAIHTTPTarget("m", "ftp://example")


@pytest.mark.real
def test_ollama_target_live():
    reply = OpenAIHTTPTarget("qwen3:4b", max_tokens=512, timeout_s=600).call("Say hello in one word.")
    assert reply.error is None and reply.text

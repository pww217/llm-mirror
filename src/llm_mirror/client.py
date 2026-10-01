from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx

from llm_mirror.session import TurnUsage


class TransientOmlxError(Exception):
    """Raised when a transient failure exhausted all retries."""


class OmlxClientError(Exception):
    """Raised for non-retryable client errors."""


@dataclass(frozen=True)
class ChatRequest:
    model: str
    system: str
    user: str
    temperature: float
    max_tokens: int
    frequency_penalty: float
    presence_penalty: float
    thinking: bool = False


@dataclass(frozen=True)
class TurnResult:
    content: str
    usage: TurnUsage
    latency_ms: int


class OmlxClient:
    def __init__(
        self,
        base_url: str,
        timeout: httpx.Timeout | None = None,
        sleep: callable = time.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout or httpx.Timeout(
            connect=5.0, read=600.0, write=10.0, pool=5.0
        )
        self._sleep = sleep

    def health(self) -> dict:
        try:
            resp = httpx.get(f"{self._base_url}/health", timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise OmlxClientError(f"health check failed: {exc}") from exc

    def models(self) -> list[dict]:
        try:
            resp = httpx.get(f"{self._base_url}/v1/models", timeout=self._timeout)
            resp.raise_for_status()
            return resp.json().get("data", [])
        except httpx.HTTPError as exc:
            raise OmlxClientError(f"models check failed: {exc}") from exc

    @staticmethod
    def _strip_think_tags(content: str) -> str:
        content = re.sub(r"```thinking\b[\s\S]*?```", "", content)
        content = re.sub(r"<thinking>[\s\S]*?</thinking>", "", content)
        if "<thinking>" in content:
            content = content.split("<thinking>", 1)[-1]
            if "</thinking>" in content:
                content = content.split("</thinking>", 1)[1]
            else:
                content = ""
        return content.lstrip()

    def chat(self, req: ChatRequest) -> TurnResult:
        backoffs = [1.0, 2.0, 4.0]
        last_exc: Exception | None = None

        for attempt in range(3):
            try:
                start = time.monotonic()
                body = {
                    "model": req.model,
                    "messages": [
                        {"role": "system", "content": req.system},
                        {"role": "user", "content": req.user},
                    ],
                    "temperature": req.temperature,
                    "max_tokens": req.max_tokens,
                    "frequency_penalty": req.frequency_penalty,
                    "presence_penalty": req.presence_penalty,
                }
                if req.thinking is False:
                    body["chat_template_kwargs"] = {"enable_thinking": False}
                resp = httpx.post(
                    f"{self._base_url}/v1/chat/completions",
                    json=body,
                    timeout=self._timeout,
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                status = resp.status_code

                if 400 <= status < 500:
                    if status == 429:
                        last_exc = OmlxClientError(f"rate limited ({status})")
                        if attempt < 2:
                            self._sleep(backoffs[attempt])
                        continue
                    raise OmlxClientError(
                        f"client error {status}: {resp.text[:200]}"
                    )

                if status >= 500:
                    last_exc = OmlxClientError(f"server error {status}")
                    if attempt < 2:
                        self._sleep(backoffs[attempt])
                    continue

                resp.raise_for_status()
                data = resp.json()
                message = data["choices"][0]["message"]
                content = self._strip_think_tags(message.get("content", ""))

                usage = data.get("usage", {})
                details = usage.get("prompt_tokens_details", {})
                cached = details.get("cached_tokens", 0)
                turn_usage = TurnUsage(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    cached_tokens=cached,
                )

                return TurnResult(content=content, usage=turn_usage, latency_ms=latency_ms)

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < 2:
                    self._sleep(backoffs[attempt])
                continue
            except OmlxClientError:
                # Already handled status-code-based retries above
                raise
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < 2:
                    self._sleep(backoffs[attempt])
                continue

        raise TransientOmlxError(
            "all 3 retries exhausted"
        ) from last_exc

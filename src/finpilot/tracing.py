from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from finpilot.core.settings import Settings


class FinPilotTracer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.trace_enabled
            and self.settings.langfuse_public_key
            and self.settings.langfuse_secret_key
        )

    def client(self):
        if not self.enabled:
            return None
        if self._client is None:
            try:
                from langfuse import Langfuse

                self._client = Langfuse(
                    public_key=self.settings.langfuse_public_key,
                    secret_key=self.settings.langfuse_secret_key,
                    host=self.settings.langfuse_host,
                )
            except Exception:
                self._client = None
        return self._client

    @contextmanager
    def trace(
        self,
        name: str,
        input_data: Any = None,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> Iterator[Any]:
        client = self.client()
        trace = None
        if client is not None:
            try:
                if hasattr(client, "start_as_current_observation"):
                    with client.start_as_current_observation(
                        name=name,
                        as_type="chain",
                        input=input_data,
                        metadata=self._metadata({**(metadata or {}), "user_id": user_id}),
                        end_on_exit=True,
                    ) as observation:
                        yield observation
                    return
                trace = client.trace(name=name, input=input_data, metadata=self._metadata(metadata), user_id=user_id)
            except Exception:
                trace = None
        try:
            yield trace
        finally:
            self.flush()

    @contextmanager
    def span(self, trace: Any, name: str, input_data: Any = None, metadata: dict[str, Any] | None = None) -> Iterator[Any]:
        span = None
        client = self.client()
        if client is not None and hasattr(client, "start_as_current_observation"):
            try:
                with client.start_as_current_observation(
                    name=name,
                    as_type="span",
                    input=input_data,
                    metadata=self._metadata(metadata),
                    end_on_exit=True,
                ) as observation:
                    yield observation
                return
            except Exception:
                yield None
                return
        if trace is not None:
            try:
                span = trace.span(name=name, input=input_data, metadata=self._metadata(metadata))
            except Exception:
                span = None
        try:
            yield span
            if span is not None:
                try:
                    span.end()
                except Exception:
                    pass
        except Exception as exc:
            if span is not None:
                try:
                    span.end(status_message=str(exc), level="ERROR")
                except Exception:
                    pass
            raise

    def generation(
        self,
        trace: Any,
        name: str,
        model: str,
        prompt: Any,
        completion: Any,
        usage: dict[str, Any] | None,
        latency_ms: float,
        cost_details: dict[str, float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        client = self.client()
        if client is not None and hasattr(client, "start_as_current_observation"):
            try:
                usage_details = {
                    key: int(value)
                    for key, value in (usage or {}).items()
                    if isinstance(value, int | float) and value is not None
                }
                with client.start_as_current_observation(
                    name=name,
                    as_type="generation",
                    input=prompt,
                    output=completion,
                    model=model,
                    usage_details=usage_details or None,
                    cost_details=cost_details,
                    metadata=self._metadata({**(metadata or {}), "latency_ms": round(latency_ms, 2)}),
                    end_on_exit=True,
                ):
                    pass
            except Exception:
                return
            return
        if trace is None:
            return
        try:
            generation = trace.generation(
                name=name,
                model=model,
                input=prompt,
                metadata=self._metadata({**(metadata or {}), "latency_ms": round(latency_ms, 2)}),
            )
            generation.end(output=completion, usage=usage or {}, cost_details=cost_details)
        except Exception:
            return

    def score_current_trace(
        self,
        name: str,
        value: float | str | bool,
        data_type: str = "NUMERIC",
        comment: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        client = self.client()
        if client is None:
            return
        try:
            if hasattr(client, "score_current_trace"):
                client.score_current_trace(
                    name=name,
                    value=value,
                    data_type=data_type,
                    comment=comment,
                    metadata=self._metadata(metadata),
                )
                return
            if hasattr(client, "create_score"):
                client.create_score(
                    name=name,
                    value=value,
                    data_type=data_type,
                    comment=comment,
                    metadata=self._metadata(metadata),
                )
        except Exception:
            return

    def flush(self) -> None:
        client = self.client()
        if client is None:
            return
        try:
            client.flush()
        except Exception:
            pass

    def _metadata(self, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "project": self.settings.langfuse_project,
            "prompt_version": self.settings.prompt_version,
            **(metadata or {}),
        }


def now_ms() -> float:
    return time.perf_counter() * 1000

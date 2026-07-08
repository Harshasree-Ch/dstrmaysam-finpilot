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
        prompt_client: Any = None,
        version: str | None = None,
    ) -> None:
        client = self.client()
        usage_details = self._usage_details(usage)
        normalized_cost_details = self._cost_details(cost_details)
        if client is not None and hasattr(client, "start_as_current_observation"):
            try:
                with client.start_as_current_observation(
                    name=name,
                    as_type="generation",
                    input=prompt,
                    output=completion,
                    model=model,
                    version=version or self.settings.prompt_version,
                    usage_details=usage_details or None,
                    cost_details=normalized_cost_details,
                    prompt=prompt_client,
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
                version=version or self.settings.prompt_version,
                metadata=self._metadata({**(metadata or {}), "latency_ms": round(latency_ms, 2)}),
            )
            generation.end(output=completion, usage=usage_details or usage or {}, cost_details=normalized_cost_details)
        except Exception:
            return

    def sync_prompt(
        self,
        *,
        name: str,
        version_label: str,
        system: str,
        user_template: str,
        config: dict[str, Any] | None = None,
    ) -> Any:
        client = self.client()
        if client is None:
            return None
        try:
            return client.get_prompt(name, label=version_label, type="chat", cache_ttl_seconds=300)
        except Exception:
            pass
        try:
            prompt = [
                {"role": "system", "content": system},
                {"role": "user", "content": user_template},
            ]
            return client.create_prompt(
                name=name,
                prompt=prompt,
                labels=[version_label, "production"],
                tags=[self.settings.langfuse_project, "finpilot"],
                type="chat",
                config=config or {},
                commit_message=f"Sync {name} {version_label} from FinPilot runtime",
            )
        except Exception:
            return None

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

    def _usage_details(self, usage: dict[str, Any] | None) -> dict[str, int]:
        payload = usage or {}
        input_tokens = payload.get("input") or payload.get("input_tokens") or payload.get("prompt_tokens") or 0
        output_tokens = payload.get("output") or payload.get("output_tokens") or payload.get("completion_tokens") or 0
        total_tokens = payload.get("total") or payload.get("total_tokens") or int(input_tokens or 0) + int(output_tokens or 0)
        return {
            "input": int(input_tokens or 0),
            "output": int(output_tokens or 0),
            "total": int(total_tokens or 0),
        }

    def _cost_details(self, cost_details: dict[str, float] | None) -> dict[str, float] | None:
        if not cost_details:
            return None
        return {
            "input": float(cost_details.get("input") or 0),
            "output": float(cost_details.get("output") or 0),
            "total": float(cost_details.get("total") or 0),
        }


def now_ms() -> float:
    return time.perf_counter() * 1000

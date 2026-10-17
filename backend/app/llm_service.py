"""Provider-independent catalog classifier with bounded fallback and metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from time import monotonic
from urllib.parse import urlsplit

import httpx

from .catalog import (ClassifierFailure, CatalogResult, PROMPT_PATH,
                      apply_neutral_score_fallback, parse_classifier_response)
from .db import ProviderHealth, now_utc
from .network import CandidateTimeout, FetchError, public_dns, safe_url
from .free_budget import current_budget
from .llm_budget import ProviderBudgetUnavailable, fit_prompt

PROMPT_VERSION = "catalog_classifier_v3"
PROVIDER_NAMES = ("gemini", "openrouter", "groq", "openai")


class ProviderFailure(Exception):
    def __init__(self, code: str, retry_after: float = 0):
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)


class LLMUnavailable(ProviderFailure):
    pass


@dataclass(frozen=True)
class LLMAnalysis:
    result: CatalogResult
    provider: str
    model: str
    attempt_count: int
    prompt_version: str = PROMPT_VERSION


def _http_error(response):
    if response.status_code == 429:
        try:
            retry_after = max(0, float(response.headers.get("retry-after", "0")))
        except ValueError:
            try:
                retry_after = max(0, (parsedate_to_datetime(response.headers.get("retry-after", "")) - now_utc()).total_seconds())
            except (ValueError, TypeError, OverflowError):
                retry_after = 0
        raise ProviderFailure("rate_limited", retry_after)
    if response.status_code in (402, 403) and "quota" in response.text.lower()[:1000]:
        raise ProviderFailure("quota_exceeded")
    if response.status_code >= 400:
        raise ProviderFailure("provider_error")


class OpenAICompatibleProvider:
    def __init__(self, name, key, model, base_url, client=None, trusted_egress_proxy=False):
        self.name, self.key, self.model, self.base_url = name, key, model, safe_url(base_url).rstrip("/")
        self.client = client
        self.trusted_egress_proxy = trusted_egress_proxy

    @property
    def configured(self):
        return bool(self.key and self.model)

    def complete(self, system: str, user: str, timeout: float) -> dict:
        self.last_usage = None
        self.last_http_status = None
        self.last_finish_reason = None
        if not self.configured:
            raise ProviderFailure("missing_key")
        body = {"model": self.model, "temperature": 0.1, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if current_budget():
            body["max_tokens"] = current_budget().request_output_tokens
        if self.name == "groq" and self.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
        try:
            public_dns(self.base_url, {urlsplit(self.base_url).hostname} if self.trusted_egress_proxy else ())
            client = self.client or httpx
            response = client.post(self.base_url + "/chat/completions", json=body,
                                   headers={"Authorization": "Bearer " + self.key}, timeout=timeout)
            self.last_http_status = response.status_code
            _http_error(response)
            data = response.json()
            self.last_usage = data.get("usage")
            choice = data["choices"][0]
            self.last_finish_reason = choice.get("finish_reason") if choice.get("finish_reason") in {"stop", "length", "content_filter", "tool_calls", "function_call"} else "unknown"
            content = choice["message"].get("content")
            if choice.get("finish_reason") == "length":
                raise ProviderFailure("output_truncated")
            if not content:
                raise ProviderFailure("empty_response")
            return json.loads(content)
        except httpx.TimeoutException as exc:
            raise ProviderFailure("timeout") from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure("provider_error") from exc
        except FetchError as exc:
            raise ProviderFailure("provider_error") from exc
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            raise ProviderFailure("invalid_json") from exc


class GeminiProvider:
    name = "gemini"

    def __init__(self, key, model, client=None):
        self.key, self.model, self.client = key, model, client

    @property
    def configured(self):
        return bool(self.key and self.model == "gemini-3.1-flash-lite")

    def complete(self, system: str, user: str, timeout: float) -> dict:
        self.last_usage = None
        self.last_http_status = None
        self.last_finish_reason = None
        if not self.configured:
            raise ProviderFailure("missing_key")
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}}
        if current_budget():
            body["generationConfig"]["maxOutputTokens"] = current_budget().request_output_tokens
        try:
            client = self.client or httpx
            response = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                json=body, headers={"x-goog-api-key": self.key}, timeout=timeout)
            self.last_http_status = response.status_code
            _http_error(response)
            data = response.json()
            usage = data.get("usageMetadata", {})
            if "totalTokenCount" in usage:
                self.last_usage = {"total_tokens": usage["totalTokenCount"],
                                   "prompt_tokens": usage.get("promptTokenCount", 0),
                                   "completion_tokens": usage.get("candidatesTokenCount", 0)}
            candidate = data["candidates"][0]
            self.last_finish_reason = candidate.get("finishReason") if candidate.get("finishReason") in {"STOP", "MAX_TOKENS", "SAFETY", "RECITATION", "OTHER", "BLOCKLIST", "PROHIBITED_CONTENT"} else "unknown"
            if self.last_finish_reason == "MAX_TOKENS":
                raise ProviderFailure("output_truncated")
            content = "".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", []) if not part.get("thought"))
            if not content:
                raise ProviderFailure("empty_response")
            return json.loads(content)
        except httpx.TimeoutException as exc:
            raise ProviderFailure("timeout") from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure("provider_error") from exc
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            raise ProviderFailure("invalid_json") from exc


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self, key, model, client=None):
        super().__init__("openrouter", key, model, "https://openrouter.ai/api/v1", client)


class GroqProvider(OpenAICompatibleProvider):
    def __init__(self, key, model, client=None):
        super().__init__("groq", key, model, "https://api.groq.com/openai/v1", client)


class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self, key, model, base_url="https://api.openai.com/v1", client=None,
                 trusted_egress_proxy=False):
        super().__init__("openai", key, model, base_url, client, trusted_egress_proxy)


class LLMService:
    def __init__(self, settings, factory=None, providers=None):
        self.settings, self.factory = settings, factory
        available = providers or {
            "gemini": GeminiProvider(settings.gemini_api_key.get_secret_value(), settings.gemini_model),
            "openrouter": OpenRouterProvider(settings.openrouter_api_key.get_secret_value(), settings.openrouter_model),
            "groq": GroqProvider(settings.groq_api_key.get_secret_value(), settings.groq_model),
            "openai": OpenAIProvider(settings.ai_key, settings.openai_model or settings.ai_model,
                                     settings.ai_base_url, trusted_egress_proxy=settings.trusted_egress_proxy),
        }
        names = [name.strip().lower() for name in settings.llm_provider_order.split(",")]
        self.providers = [available[name] for name in names if name in available]
        self.failures = {provider.name: 0 for provider in self.providers}
        self.metrics = {provider.name: {"requests": 0, "successes": 0, "fallback_count": 0,
                                        "timeouts": 0, "rate_limits": 0, "quota_errors": 0,
                                        "invalid_json": 0, "schema_failures": 0,
                                        "latency_total_ms": 0.0} for provider in self.providers}
        self.last_attempt_count = 0
        self._pending_metrics = {provider.name: [] for provider in self.providers}

    @property
    def available(self):
        budget = current_budget()
        return bool(self.settings.llm_enabled and any(provider.configured and
                    (not budget or (provider.name in {"gemini", "groq"} and not budget.blocked(provider.name)))
                    for provider in self.providers))

    @property
    def operational(self):
        return bool(self.settings.llm_enabled and any(
            provider.configured and self.failures[provider.name] < self.settings.llm_circuit_breaker_failures
            for provider in self.providers))

    def status(self):
        return [{"name": provider.name, "model": provider.model, "configured": provider.configured,
                 "healthy": self.failures[provider.name] < self.settings.llm_circuit_breaker_failures,
                 **self.metrics[provider.name]} for provider in self.providers]

    def _metric(self, name: str, code: str, latency: float = 0):
        stats = self.metrics[name]
        if code == "request":
            stats["requests"] += 1
            stats["latency_total_ms"] += latency
        elif code == "success":
            stats["successes"] += 1
            self.failures[name] = 0
        else:
            if code == "timeout":
                stats["timeouts"] += 1
            elif code == "rate_limited":
                stats["rate_limits"] += 1
            elif code == "quota_exceeded":
                stats["quota_errors"] += 1
            elif code == "invalid_json":
                stats["invalid_json"] += 1
            elif code in ("schema_validation_failed", "business_validation_failed"):
                stats["schema_failures"] += 1
            self.failures[name] += 1
        if self.factory:
            self._pending_metrics[name].append((code, latency))

    def _flush_metrics(self, name, session):
        for code, latency in self._pending_metrics[name]:
            row = session.get(ProviderHealth, name)
            if row is None:
                row = ProviderHealth(name=name)
                session.add(row)
                session.flush()
            if code == "request":
                row.requests += 1
                row.latency_total_ms += latency
            elif code == "success":
                row.successes += 1
                row.consecutive_failures = 0
                row.last_success_at = now_utc()
                row.last_error = ""
            else:
                attr = {"timeout": "timeouts", "rate_limited": "rate_limits",
                        "quota_exceeded": "quota_errors", "invalid_json": "invalid_json",
                        "schema_validation_failed": "schema_failures",
                        "business_validation_failed": "schema_failures"}.get(code)
                if attr:
                    setattr(row, attr, getattr(row, attr) + 1)
                row.consecutive_failures += 1
                row.last_error = code
        self._pending_metrics[name] = []

    def record_unavailable(self):
        from .telemetry import record
        budget = current_budget()
        for provider in self.providers:
            blocked = budget.blocked(provider.name) if budget and provider.name in {"gemini", "groq"} else None
            reason = "disabled" if not self.settings.llm_enabled else "missing_key" if not provider.configured else "local_block" if blocked else "circuit_open" if self.failures[provider.name] >= self.settings.llm_circuit_breaker_failures else "not_available"
            record("provider_attempts", provider=provider.name, outcome=reason, local_reason=blocked, request_sent=False)

    def analyze_source(self, article) -> LLMAnalysis:
        if not self.available:
            self.record_unavailable()
            raise LLMUnavailable("llm_unavailable")
        text = article.text[:3800]
        user = (f"Title: {article.title}\nSource: {article.publisher}\n"
                f"Source country hint: {article.country_hint}\nPublished: {article.published_at or ''}\n"
                f"URL: {article.url}\n<article>\n{text}\n</article>")
        system = PROMPT_PATH.read_text()
        return self.analyze_json(system, user, lambda payload: parse_classifier_response(
            apply_neutral_score_fallback(payload), article.title + "\n" + text),
            compact_system=(PROMPT_PATH.parent / "catalog_classifier_compact_v3.txt").read_text())

    def analyze_json(self, system: str, user: str, validate, compact_system=None):
        """Shared fallback path for classification and optional deep enrichment."""
        from .telemetry import record, remaining, span
        if not self.available:
            self.record_unavailable()
            raise LLMUnavailable("llm_unavailable")
        attempts = 0
        self.last_attempt_count = 0
        for provider in self.providers:
            budget = current_budget()
            if budget and (provider.name not in {"gemini", "groq"} or budget.blocked(provider.name)):
                record("provider_attempts", provider=provider.name, outcome="local_block", request_sent=False)
                continue
            if not provider.configured or self.failures[provider.name] >= self.settings.llm_circuit_breaker_failures:
                record("provider_attempts", provider=provider.name, outcome="missing_key" if not provider.configured else "circuit_open", request_sent=False)
                continue
            managed = bool(budget and budget.quotas and provider.name in budget.quotas.policies)
            retries = self.settings.llm_rate_limit_retries if managed else self.settings.llm_max_retries_per_provider
            for attempt in range(1 + retries):
                request_system, request_user = system, user
                reservation = None
                if budget:
                    if managed:
                        try:
                            policy = budget.quotas.policies[provider.name]
                            from .llm_budget import estimate_tokens
                            if provider.name == "groq" and compact_system:
                                request_system = compact_system
                            cap = policy["request_tokens"]
                            if provider.name == "groq":
                                soft = min(cap, policy["tpm"] // 2 - 128)
                                # Generic deep prompts may be larger; never drop rules to force a small reserve.
                                if estimate_tokens(" ".join(request_system.split())) + 512 <= soft:
                                    recent = budget.quotas._readiness.get(provider.name, {}).get("events", [])
                                    from datetime import timedelta
                                    from .db import aware
                                    from datetime import datetime
                                    spent = sum(event["reserved_tokens"] for event in recent if aware(datetime.fromisoformat(event["at"])) > budget.clock() - timedelta(seconds=60))
                                    available = policy["tpm"] - spent - 128
                                    cap = min(soft, available) if available >= estimate_tokens(" ".join(request_system.split())) + 512 else soft
                            desired_output = min(budget.output_tokens, 1536) if provider.name == "groq" and compact_system else budget.output_tokens
                            request_system, request_user, tokens, output = fit_prompt(request_system, user, cap, desired_output)
                            record("token_reservations", provider=provider.name, estimated_total=tokens, output_cap=output, request_cap=cap)
                            reservation = budget.quotas.reserve(provider.name, tokens)
                            budget.request_output_tokens = output
                        except ProviderBudgetUnavailable as exc:
                            record("provider_attempts", provider=provider.name, outcome="local_budget", reason=str(exc)[:80], request_sent=False)
                            break  # Fall through to the next provider, without spending.
                    else:
                        budget.reserve("llm:" + provider.name)
                began = monotonic()
                diagnostic = {"provider": provider.name, "model": provider.model, "request_sent": False, "outcome": "interrupted"}
                attempts += 1
                self.last_attempt_count = attempts
                try:
                    if budget:
                        budget.check_time()
                    timeout = remaining(self.settings.llm_timeout_seconds)
                    if budget:
                        timeout = min(timeout, max(0.001, budget.deadline - budget.timer()))
                    diagnostic["request_sent"] = True
                    with span("llm"):
                        payload = provider.complete(request_system, request_user, timeout)
                    with span("validation"):
                        result = validate(payload)
                    diagnostic["outcome"] = "success"
                    self._metric(provider.name, "success")
                    return LLMAnalysis(result, provider.name, provider.model, attempts,
                                       PROMPT_VERSION + "_groq_compact_v1" if provider.name == "groq" and compact_system else PROMPT_VERSION)
                except CandidateTimeout:
                    diagnostic.update(outcome="candidate_timeout_before_http" if not diagnostic["request_sent"] else "candidate_timeout_after_http", exception_class="CandidateTimeout")
                    raise
                except ProviderFailure as exc:
                    diagnostic.update(outcome=exc.code, exception_class=type(exc).__name__)
                    self._metric(provider.name, exc.code)
                    if managed and exc.code == "rate_limited" and attempt < retries and exc.retry_after <= 60:
                        delay = max(exc.retry_after, self.settings.llm_rate_limit_backoff_seconds * 2 ** attempt)
                        if remaining(delay) >= delay:
                            budget.wait(delay)
                            continue
                        diagnostic["retry_skipped"] = "candidate_deadline"
                    if budget and exc.code in {"rate_limited", "quota_exceeded"}:
                        budget.block(provider.name, exc.code)
                    if exc.code in {"rate_limited", "quota_exceeded", "missing_key"}:
                        break
                except (ClassifierFailure, ValueError) as exc:
                    failure = "business_validation_failed" if isinstance(exc, ClassifierFailure) and str(exc) not in {"invalid_json_schema", "invalid_classification", "invalid_enum"} else "schema_validation_failed"
                    diagnostic.update(outcome=failure, exception_class=type(exc).__name__, rule_code=business_rule_code(exc))
                    self._metric(provider.name, failure)
                finally:
                    diagnostic.update(http_status=getattr(provider, "last_http_status", None),
                                      finish_reason=getattr(provider, "last_finish_reason", None),
                                      elapsed_ms=round((monotonic() - began) * 1000, 2))
                    record("provider_attempts", **diagnostic)
                    self._metric(provider.name, "request", round((monotonic() - began) * 1000, 2))
                    if reservation:
                        budget.quotas.reconcile(provider.name, reservation, getattr(provider, "last_usage", None),
                                               after=(lambda session: self._flush_metrics(provider.name, session)) if self.factory else None)
                    elif self.factory:
                        from .telemetry import db_work
                        with db_work("provider_metrics"):
                            with self.factory.begin() as session:
                                self._flush_metrics(provider.name, session)
                if managed:
                    break  # Only 429 gets the dedicated bounded retry loop.
                if self.failures[provider.name] >= self.settings.llm_circuit_breaker_failures:
                    break
            self.metrics[provider.name]["fallback_count"] += 1
            if self.factory:
                with self.factory.begin() as session:
                    row = session.get(ProviderHealth, provider.name)
                    if row is None:
                        row = ProviderHealth(name=provider.name)
                        session.add(row)
                        session.flush()
                    row.fallback_count += 1
        raise LLMUnavailable("llm_unavailable")


def business_rule_code(exc):
    allowed = {"invalid_enum", "unsupported_project_name", "unsupported_official_url", "invalid_description",
               "invalid_score_evidence", "insufficient_description", "invalid_json_schema", "invalid_classification"}
    allowed |= {"scores_or_evidence_missing", "neutral_fallback_mismatch", "score_reason_keys", "score_reason_length", "real_product_usage_unsupported"}
    code = getattr(exc, "rule_code", str(exc))
    if code in allowed:
        return code
    if code.startswith("invalid_score"):
        return "invalid_score_evidence"
    return "schema_validation_failed"

"""Provider-independent catalog classifier with bounded fallback and metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urlsplit

import httpx

from .catalog import ClassifierFailure, CatalogResult, PROMPT_PATH, parse_classifier_response
from .db import ProviderHealth, now_utc
from .network import FetchError, public_dns, safe_url

PROMPT_VERSION = "catalog_classifier_v1"
PROVIDER_NAMES = ("gemini", "openrouter", "groq", "openai")


class ProviderFailure(Exception):
    def __init__(self, code: str):
        self.code = code
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
        raise ProviderFailure("rate_limited")
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
        if not self.configured:
            raise ProviderFailure("missing_key")
        body = {"model": self.model, "temperature": 0.1, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        try:
            public_dns(self.base_url, {urlsplit(self.base_url).hostname} if self.trusted_egress_proxy else ())
            client = self.client or httpx
            response = client.post(self.base_url + "/chat/completions", json=body,
                                   headers={"Authorization": "Bearer " + self.key}, timeout=timeout)
            _http_error(response)
            return json.loads(response.json()["choices"][0]["message"]["content"])
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
        return bool(self.key and self.model)

    def complete(self, system: str, user: str, timeout: float) -> dict:
        if not self.configured:
            raise ProviderFailure("missing_key")
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}}
        try:
            client = self.client or httpx
            response = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                json=body, headers={"x-goog-api-key": self.key}, timeout=timeout)
            _http_error(response)
            content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
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

    @property
    def available(self):
        return bool(self.settings.llm_enabled and any(provider.configured for provider in self.providers))

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
            with self.factory.begin() as session:
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

    def analyze_source(self, article) -> LLMAnalysis:
        if not self.available:
            raise LLMUnavailable("llm_unavailable")
        text = article.text[:3800]
        user = (f"Title: {article.title}\nSource: {article.publisher}\n"
                f"Source country hint: {article.country_hint}\nPublished: {article.published_at or ''}\n"
                f"URL: {article.url}\n<article>\n{text}\n</article>")
        system = PROMPT_PATH.read_text()
        return self.analyze_json(system, user, lambda payload: parse_classifier_response(
            payload, article.title + "\n" + text))

    def analyze_json(self, system: str, user: str, validate):
        """Shared fallback path for classification and optional deep enrichment."""
        if not self.available:
            raise LLMUnavailable("llm_unavailable")
        attempts = 0
        self.last_attempt_count = 0
        for provider in self.providers:
            if not provider.configured or self.failures[provider.name] >= self.settings.llm_circuit_breaker_failures:
                continue
            for _ in range(1 + self.settings.llm_max_retries_per_provider):
                began = monotonic()
                attempts += 1
                self.last_attempt_count = attempts
                try:
                    payload = provider.complete(system, user, self.settings.llm_timeout_seconds)
                    self._metric(provider.name, "request", round((monotonic() - began) * 1000, 2))
                    result = validate(payload)
                    self._metric(provider.name, "success")
                    return LLMAnalysis(result, provider.name, provider.model, attempts)
                except ProviderFailure as exc:
                    self._metric(provider.name, "request", round((monotonic() - began) * 1000, 2))
                    self._metric(provider.name, exc.code)
                    if exc.code in {"rate_limited", "quota_exceeded", "missing_key"}:
                        break
                except (ClassifierFailure, ValueError) as exc:
                    self._metric(provider.name, "request", round((monotonic() - began) * 1000, 2))
                    self._metric(provider.name, "business_validation_failed" if str(exc).startswith("invalid_score") else "schema_validation_failed")
                if self.failures[provider.name] >= self.settings.llm_circuit_breaker_failures:
                    break
            self.metrics[provider.name]["fallback_count"] += 1
            if self.factory:
                with self.factory.begin() as session:
                    session.get(ProviderHealth, provider.name).fallback_count += 1
        raise LLMUnavailable("llm_unavailable")

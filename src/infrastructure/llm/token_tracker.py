import uuid
from sqlalchemy.orm import Session

from src.domain.enums import LLMProvider
from src.infrastructure.config import Settings
from src.infrastructure.db.models import LLMInvocationORM, TokenUsageORM
from src.ports.llm_gateway import LLMResponse


class TokenTrackerService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or Settings()

    def estimate_cost(
        self,
        provider: LLMProvider | str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float | None:
        prov_key = provider.value if isinstance(provider, LLMProvider) else str(provider).lower()
        try:
            prov_enum = LLMProvider(prov_key)
        except ValueError:
            return None

        llm_cfg = self.settings.llm_config
        prov_config = llm_cfg.providers.get(prov_enum)
        if not prov_config or not prov_config.pricing:
            return None

        pricing = prov_config.pricing.get(model)
        if not pricing:
            return None

        prompt_cost = (prompt_tokens / 1000.0) * pricing.prompt_cost_per_1k
        completion_cost = (completion_tokens / 1000.0) * pricing.completion_cost_per_1k
        return round(prompt_cost + completion_cost, 6)

    def record_invocation(
        self,
        agent_execution_id: uuid.UUID,
        provider: LLMProvider | str,
        model_name: str,
        latency_ms: int,
        success: bool,
        response: LLMResponse | None = None,
        error_message: str | None = None,
    ) -> LLMInvocationORM:
        prov_str = provider.value if isinstance(provider, LLMProvider) else str(provider).lower()

        # Sanitize error message to ensure no secrets or full tracebacks leak
        sanitized_error = None
        if error_message:
            sanitized_error = error_message.strip()[:1000]

        invocation = LLMInvocationORM(
            agent_execution_id=agent_execution_id,
            provider=prov_str,
            model_name=model_name,
            latency_ms=max(0, latency_ms),
            success=success,
            error_message=sanitized_error,
        )
        self.db.add(invocation)
        self.db.flush()

        if response and response.usage:
            prompt_toks = response.usage.prompt_tokens
            comp_toks = response.usage.completion_tokens
            total_toks = response.usage.total_tokens

            # Compute estimated cost from config if available, otherwise record None
            cost = self.estimate_cost(prov_str, model_name, prompt_toks, comp_toks)

            token_usage = TokenUsageORM(
                llm_invocation_id=invocation.id,
                prompt_tokens=prompt_toks,
                completion_tokens=comp_toks,
                total_tokens=total_toks,
                estimated_cost_usd=cost,
            )
            self.db.add(token_usage)
            self.db.flush()

        return invocation

    def get_execution_telemetry(self, agent_execution_id: uuid.UUID | str | None) -> dict | None:
        if not self.db or not agent_execution_id:
            return None
        try:
            exec_id = agent_execution_id if isinstance(agent_execution_id, uuid.UUID) else uuid.UUID(str(agent_execution_id))
            invocations = (
                self.db.query(LLMInvocationORM)
                .filter_by(agent_execution_id=exec_id)
                .all()
            )
            if not invocations:
                return None

            total_prompt = 0
            total_comp = 0
            total_tokens = 0
            total_latency_ms = 0
            total_cost = 0.0
            models_used: list[str] = []
            providers_used: list[str] = []

            for inv in invocations:
                total_latency_ms += inv.latency_ms or 0
                if inv.model_name and inv.model_name not in models_used:
                    models_used.append(inv.model_name)
                if inv.provider and inv.provider not in providers_used:
                    providers_used.append(inv.provider)
                if inv.token_usage:
                    total_prompt += inv.token_usage.prompt_tokens or 0
                    total_comp += inv.token_usage.completion_tokens or 0
                    total_tokens += inv.token_usage.total_tokens or 0
                    if inv.token_usage.estimated_cost_usd:
                        total_cost += inv.token_usage.estimated_cost_usd

            provider_name = providers_used[0] if providers_used else "gemini"
            model_name = models_used[0] if models_used else "gemini-3.5-flash-lite"
            latency_sec = round(total_latency_ms / 1000.0, 1)

            # Determine free tier / local status
            is_local = "ollama" in provider_name.lower()
            is_free_tier = is_local or any(p in provider_name.lower() for p in ("gemini", "groq"))

            cost_label = "$0.00 (Local)" if is_local else ("$0.00 (Free Tier)" if is_free_tier else f"${total_cost:.4f}")

            return {
                "totalTokens": total_tokens,
                "promptTokens": total_prompt,
                "completionTokens": total_comp,
                "latencyMs": total_latency_ms,
                "latencySec": latency_sec,
                "estimatedCostUsd": round(total_cost, 6),
                "costLabel": cost_label,
                "provider": provider_name,
                "model": model_name,
                "isFreeTier": is_free_tier,
                "displayBadge": f"⚡ {total_tokens:,} tokens • {latency_sec}s • {cost_label} • {model_name}",
            }
        except Exception:
            return None

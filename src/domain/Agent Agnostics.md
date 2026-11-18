1. .env (AWS Credentials)

Root directory ki .env file me apne AWS Bedrock ke credentials daalne honge:

env
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_REGION_NAME=us-east-1

(Region wahi likhein jahan Bedrock me Claude Sonnet model access enabled ho, jaise us-east-1 ya us-west-2).

2. src/infrastructure/config.py (Environment Loader)

Settings class ke andar ye 3 variables add karne honge taake backend .env se AWS keys load kare:

python
AWS_ACCESS_KEY_ID: str | None = None
AWS_SECRET_ACCESS_KEY: str | None = None
AWS_REGION_NAME: str = "us-east-1"
3. src/domain/enums.py (Provider Enum)

LLMProvider enum me BEDROCK add karna hoga:

python
class LLMProvider(str, Enum):
    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    BEDROCK = "bedrock"    # <--- Ye add hoga
4. src/infrastructure/llm/litellm_adapter.py (Adapter Whitelist)

LiteLLMAdapter class ke SUPPORTED_PROVIDERS set me Bedrock ko allow karna hoga:

python
class LiteLLMAdapter(ILLMGateway):
    SUPPORTED_PROVIDERS = {
        LLMProvider.GEMINI,
        LLMProvider.GROQ,
        LLMProvider.OPENROUTER,
        LLMProvider.BEDROCK,    # <--- Ye add hoga
    }

(LiteLLM automatically environment se AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY aur AWS_REGION_NAME utha leta hai).

5. config/llm_config.json (Configuration & Agent Assignment)

Is file me 2 jagah change hoga:

(A) "providers" section ke andar "bedrock" add karein:
json
"bedrock": {
  "default_model": "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
  "fallback_model": null,
  "available_models": [
    "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"
  ],
  "pricing": {
    "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0": {
      "prompt_cost_per_1k": 0.003,
      "completion_cost_per_1k": 0.015
    }
  }
}
(B) "agent_assignments" section me jis agent ko Sonnet dena ho:

Agar Agent 3 (Main Coder) ko dena hai:

json
"AGENT_3": {
  "provider": "bedrock",
  "model": "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
  "fallback_provider": "gemini",
  "fallback_model": "gemini-3.5-flash-lite"
}

(Note: LiteLLM me Bedrock models ka format prefix ke sath hota hai: bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0).
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> None:
        return None


@dataclass(frozen=True)
class Settings:
    data_mode: str = "live"
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    use_bedrock: bool = False
    opensearch_endpoint: str | None = None
    groww_api_key: str | None = None
    groww_secret_key: str | None = None
    alpaca_api_key: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_paper_base_url: str = "https://paper-api.alpaca.markets"
    finnhub_api_key: str | None = None
    rds_database_url: str | None = None
    mcp_tool_url: str | None = None
    finpilot_api_url: str | None = None
    trace_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_project: str = "dstrmaysam-finpilot"
    prompt_version: str = "v1"
    llm_input_cost_per_1k_usd: float = 0.003
    llm_output_cost_per_1k_usd: float = 0.015

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            data_mode=os.getenv("FINPILOT_DATA_MODE", "live"),
            aws_region=os.getenv("AWS_REGION", "us-east-1"),
            bedrock_model_id=os.getenv("BEDROCK_MODEL_ID", cls.bedrock_model_id),
            use_bedrock=os.getenv("FINPILOT_USE_BEDROCK", "false").lower() in {"1", "true", "yes", "on"},
            opensearch_endpoint=os.getenv("OPENSEARCH_ENDPOINT") or None,
            groww_api_key=os.getenv("GROWW_API_KEY") or None,
            groww_secret_key=os.getenv("GROWW_SECRET_KEY") or None,
            alpaca_api_key=os.getenv("ALPACA_API_KEY") or None,
            alpaca_secret_key=os.getenv("ALPACA_SECRET_KEY") or None,
            alpaca_paper_base_url=os.getenv("ALPACA_PAPER_BASE_URL", cls.alpaca_paper_base_url),
            finnhub_api_key=os.getenv("FINNHUB_API_KEY") or None,
            rds_database_url=os.getenv("RDS_DATABASE_URL") or None,
            mcp_tool_url=os.getenv("FINPILOT_MCP_TOOL_URL") or os.getenv("MCP_TOOL_URL") or None,
            finpilot_api_url=os.getenv("FINPILOT_API_URL") or None,
            trace_enabled=os.getenv("FINPILOT_TRACE_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
            langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY") or None,
            langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY") or None,
            langfuse_host=os.getenv("LANGFUSE_HOST", cls.langfuse_host),
            langfuse_project=os.getenv("FINPILOT_LANGFUSE_PROJECT", cls.langfuse_project),
            prompt_version=os.getenv("FINPILOT_PROMPT_VERSION", cls.prompt_version),
            llm_input_cost_per_1k_usd=float(
                os.getenv("BEDROCK_INPUT_COST_PER_1K_USD", str(cls.llm_input_cost_per_1k_usd))
            ),
            llm_output_cost_per_1k_usd=float(
                os.getenv("BEDROCK_OUTPUT_COST_PER_1K_USD", str(cls.llm_output_cost_per_1k_usd))
            ),
        )

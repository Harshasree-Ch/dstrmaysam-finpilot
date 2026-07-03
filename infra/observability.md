# FinPilot Observability and LLM Tracing

FinPilot emits observability data from the FastAPI backend, not from Streamlit.

## Local live metrics

Run the app and open:

```text
http://localhost:8600/observability/metrics
```

The endpoint reports request volume, error rate, average latency, p50 latency, and p95 latency by route.

## CloudWatch dashboard

FastAPI writes structured JSON logs for:

- `finpilot_http_request`
- `finpilot_research_completed`
- `finpilot_research_failed`
- `finpilot_llm_call`

When deployed on ECS/Fargate, these logs go to CloudWatch Logs. Use
`infra/cloudwatch-dashboard-finpilot.json` as the dashboard template and replace:

- `${AWS_REGION}` with the AWS region
- `${FINPILOT_LOG_GROUP}` with the ECS task log group

## Langfuse tracing

Set these values in the FinPilot environment:

```env
FINPILOT_TRACE_ENABLED=true
FINPILOT_LANGFUSE_PROJECT=dstrmaysam-finpilot
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

The backend traces:

- research requests
- market-today requests
- chat requests
- Bedrock LLM generations with prompt, completion, model, latency, tokens, and estimated cost
- Langfuse scores for the four required RAGAS quality metrics when `scripts/evaluate_quality.py --publish-langfuse` is run

## Prompt catalogue

Prompts live in `src/finpilot/prompts/` and are selected at runtime by:

```env
FINPILOT_PROMPT_VERSION=v1
```

# FinPilot

AI-powered Indian equity research and guided investing copilot.

FinPilot is an enterprise-style research project focused on NSE/BSE-listed Indian equities. It demonstrates agentic AI, centralized financial data access, explainable research reports, chat-assisted analysis, and guarded investment order workflows.

## What This Build Includes

- Streamlit research dashboard
- Multi-agent research workflow
- Centralized Financial Intelligence facade
- Explainable investment report generation
- Invest workflow with market selection, live price preview, estimated cost, agent risk summary, and explicit confirmation
- Alpaca paper trading support for US stock orders
- Optional Amazon Bedrock synthesis for the final investment narrative
- AWS deployment artifacts for ECS Fargate
- Realtime Indian equity quote, company profile, earnings calendar, and news fetches through Yahoo Finance
- NSE/BSE ticker handling with symbols such as `RELIANCE.NS`, `TCS.NS`, `INFY.NS`, and `HDFCBANK.NS`

## Architecture

```mermaid
flowchart TD
    UI[Streamlit Dashboard] --> API[FinPilot FastAPI Backend]
    API --> Graph[LangGraph StateGraph Orchestrator]
    Graph --> Planner[Planner Agent]
    Planner --> Company[Company Intelligence Agent]
    Planner --> Earnings[Earnings Intelligence Agent]
    Planner --> News[News Intelligence Agent]
    Company --> DataFacade[Financial Data Facade]
    Earnings --> DataFacade
    News --> DataFacade
    DataFacade --> APIs[Yahoo Finance NSE/BSE/US, Company Filings, Finnhub, Groww, Alpaca Paper]
    Company --> Reflection[Reflection Agent]
    Earnings --> Reflection
    News --> Reflection
    Reflection --> Research[Investment Research Agent]
    Research --> API
    API --> UI
    API --> Trade[Trading Agent]
    Trade --> Broker[Groww or Alpaca Paper When Configured]
    API --> MCP[MCP-TOOLS FastMCP SSE]
    MCP --> RAG[OpenSearch Serverless RAG + S3 PDFs]
```

## Quick Start

From PowerShell on Windows:

```powershell
cd C:\Harshasree\Assignments\FinPilot
streamlit run app.py
```

`app.py` starts the Streamlit frontend and automatically boots the local FinPilot FastAPI backend on port `8600` when `FINPILOT_API_URL` points to `localhost` and no backend is already running.

If you want to run the backend separately for debugging, start it in one terminal:

```powershell
cd C:\Harshasree\Assignments\FinPilot
.\run_api.ps1
```

Then start Streamlit in another terminal:

```powershell
streamlit run app.py
```

Or from Command Prompt:

```bat
cd /d C:\Harshasree\Assignments\FinPilot
streamlit run app.py
```

The helper scripts still use the project `.venv`, install/update `requirements.txt`, and start FastAPI/Streamlit from the same Python environment. If you prefer manual activation, run `.venv\Scripts\activate` first.

The app runs in realtime-only mode for Indian market ticker quotes, company profiles, earnings calendar data, and recent news. If
the upstream provider is unavailable, rate-limited, or the machine is offline, the app shows an error instead of
displaying mock ticker data.

For Indian stocks, use Yahoo Finance symbols like `RELIANCE.NS` for NSE or `RELIANCE.BO` for BSE. Common company names such as `Reliance`, `TCS`, `Infosys`, `HDFC Bank`, and `SBI` are resolved to NSE symbols by default.

## Optional Environment Variables

Create `.env` from `.env.example` when you want live integrations.

```bash
FINPILOT_DATA_MODE=live
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
FINPILOT_USE_BEDROCK=false
AWS_REGION=us-east-1
GROWW_API_KEY=
GROWW_SECRET_KEY=
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_PAPER_BASE_URL=https://paper-api.alpaca.markets
FINNHUB_API_KEY=
RDS_DATABASE_URL=
FINPILOT_MCP_TOOL_URL=http://your-mcp-tools-host:9000/sse
FINPILOT_API_URL=http://localhost:8600
```

To use Amazon Bedrock locally, configure AWS credentials through your shell, AWS profile, or an IAM role, then set:

```bash
FINPILOT_USE_BEDROCK=true
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

Do not commit AWS credentials to this repository.

## AWS Deployment

FinPilot now has deployment artifacts for the required AWS path:

- `infra/aws-ecs-fargate.yaml` creates a tagged ECS Fargate service with two containers in one task: `finpilot-api` for FastAPI on port `8600` and `finpilot-web` for Streamlit on port `8501`.
- `infra/finpilot-pipeline.yml` creates a tagged CodePipeline, CodeBuild project, ECR repository, and artifact bucket.
- `buildspec.yml` runs tests, builds the Docker image, pushes both commit and `latest` tags to ECR, and emits ECS `imagedefinitions.json` for both containers.

All infrastructure templates tag resources with:

```text
Project=dstrmaysam-finpilot
Application=dstrmaysam
Owner=Harshasree
```

Recommended bootstrap order:

1. Create or choose an ECR repository and push the first FinPilot image.
2. Deploy `infra/aws-ecs-fargate.yaml` with `ContainerImage` set to that initial image URI.
3. Deploy `infra/finpilot-pipeline.yml` using the ECS stack outputs `ClusterName` and `ServiceName`.
4. After the pipeline succeeds, future commits build, test, push, and deploy automatically.

The ECS stack reads runtime credentials from AWS Secrets Manager when you pass the matching secret ARNs, including `RDS_DATABASE_URL`, Langfuse keys, Finnhub, Groww, and Alpaca credentials. Keep local values in `.env`; keep deployed values in Secrets Manager.

Example ECS stack deploy:

```powershell
aws cloudformation deploy `
  --stack-name dstrmaysam-finpilot-ecs `
  --template-file infra/aws-ecs-fargate.yaml `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides `
    ContainerImage=<account>.dkr.ecr.<region>.amazonaws.com/dstrmaysam-finpilot:latest `
    VpcId=<vpc-id> `
    SubnetIds=<subnet-a>,<subnet-b> `
    FinPilotMcpToolUrl=http://<mcp-tools-host>:9000/sse `
    RdsDatabaseUrlSecretArn=<secret-arn> `
    LangfusePublicKeySecretArn=<secret-arn> `
    LangfuseSecretKeySecretArn=<secret-arn>
```

Example pipeline stack deploy:

```powershell
aws cloudformation deploy `
  --stack-name dstrmaysam-finpilot-pipeline `
  --template-file infra/finpilot-pipeline.yml `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides `
    CodeStarConnectionArn=<codestar-connection-arn> `
    RepositoryId=<github-owner>/<finpilot-repo> `
    RepositoryBranch=main `
    EcsClusterName=dstrmaysam-finpilot-cluster `
    EcsServiceName=dstrmaysam-finpilot-service
```

For AWS RDS-backed chat history, install dependencies from `requirements.txt` and set `RDS_DATABASE_URL` to a SQLAlchemy
connection URL, for example:

```bash
RDS_DATABASE_URL=postgresql+psycopg://user:password@your-rds-endpoint:5432/finpilot
```

## Project Layout

```text
app.py                         Streamlit dashboard
src/finpilot/agents            Planner, specialist agents, reflection, research, trading
src/finpilot/trading           Paper trading service
src/finpilot/chat              Chat assistant and chat history storage
src/finpilot/core              Settings and shared domain models
src/finpilot/evaluation        Golden dataset, RAGAS metrics, and trajectory grading
src/finpilot_mcp               Financial data facade and live market data adapters
infra                          AWS ECS, IAM, and EventBridge starter template
tests                          Lightweight unit tests
```

## Quality Measurement

FinPilot includes the required evaluation harness:

- Golden dataset: `data/evaluation/golden_dataset.json` with 23 hand-curated happy-path and edge-case examples
- RAGAS metrics: faithfulness, answer relevancy, context precision, and context recall
- Additional method: trajectory grading for route correctness, expected tool use, and answer content

Run:

```powershell
.venv\Scripts\python.exe scripts\evaluate_quality.py
```

To publish only the four required RAGAS numbers to Langfuse Scores:

```powershell
.venv\Scripts\python.exe scripts\evaluate_quality.py --publish-langfuse
```

Reports are written to:

```text
reports/evaluation/quality_report.json
reports/evaluation/quality_report.md
```

See `infra/quality-measurement.md` for the baseline numbers and methodology.

## Safety Note

FinPilot is educational software. It does not provide financial advice. Orders require explicit user confirmation. Groww order placement only runs when a Groww API key and secret are configured. US stock orders use Alpaca paper trading only when Alpaca paper credentials are configured.

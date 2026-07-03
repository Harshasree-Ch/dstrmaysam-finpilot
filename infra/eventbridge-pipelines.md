# Event-Driven Data Pipelines

FinPilot is designed to keep its research corpus fresh through EventBridge schedules.

| Cadence | Job | Target |
| --- | --- | --- |
| Hourly | Market prices and financial news | Lambda ingestion worker |
| Daily | Market analytics and sentiment refresh | Lambda analytics worker |
| Quarterly | SEC filings and earnings transcripts | Lambda document worker |

Each worker should write raw documents to S3, metadata to RDS PostgreSQL, embeddings to Amazon OpenSearch Vector Engine, and logs to CloudWatch.

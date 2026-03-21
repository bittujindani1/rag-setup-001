# Cost Estimation

## Low-cost choices

- Lambda instead of always-on ECS for the RAG API
- API Gateway HTTP API instead of heavier ingress stacks
- DynamoDB on-demand instead of Redis clusters
- S3 object storage instead of OpenSearch clusters
- Bedrock Claude 3 Haiku instead of larger premium models

## Main cost drivers

- Bedrock inference and embedding calls
- Lambda duration during ingestion and long retrieval flows
- S3 object count and storage for embedding JSON files
- DynamoDB read/write volume for chat history and cache

## Expected savings versus current style

- Removes the fixed baseline cost of OpenSearch clusters
- Removes the fixed baseline cost of Redis clusters
- Shifts cost to request-driven infrastructure

## Watch-outs

- Large S3 vector indexes increase query latency because search is done in Python.
- Heavy ingestion workloads may need batching or Step Functions later.
- Chainlit on ECS Fargate is optional; for lowest cost, run it only when needed.

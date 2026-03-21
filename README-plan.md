# AWS MVP Deployment Plan

## Summary
This MVP uses the bare minimum AWS services needed to make the UI and API publicly accessible for occasional demos, with cost as the primary concern.

The recommended deployment is:
- React UI hosted on Amazon S3 static website hosting
- FastAPI backend hosted on AWS Lambda
- Lambda exposed through Lambda Function URL
- Data stored in Amazon S3 and DynamoDB
- LLM and embeddings powered by Amazon Bedrock

This avoids CloudFront, API Gateway, ALB, ECS, and Fargate in v1.

## Minimum AWS Services
- Amazon S3
  - React UI static website bucket
  - document upload bucket
  - vector/index bucket
  - extracted-content bucket
- AWS Lambda
  - one backend function serving the RAG API
- Lambda Function URL
  - public HTTPS endpoint for the backend
- Amazon DynamoDB
  - chat history
  - thread history
  - query cache
  - document store
  - filename index
  - rate limiting
  - document metadata/categories table
- Amazon Bedrock
  - embeddings and answer generation
- Amazon ECR
  - backend container image
- IAM
  - Lambda execution role and S3 policies
- CloudWatch Logs
  - backend logging

## What We Are Not Using
- ALB
- API Gateway
- CloudFront
- ECS/Fargate
- EC2
- RDS
- VPC/NAT Gateway

These are intentionally excluded to keep the MVP low-cost and low-complexity.

## Architecture
- Browser loads React app from S3 website endpoint
- Browser calls FastAPI backend using Lambda Function URL
- Backend uses S3 for documents, vectors, and extracted content
- Backend uses DynamoDB for chat, thread, cache, rate-limit, and metadata state
- Backend uses Bedrock for embeddings and responses

## Important Tradeoff
S3 website hosting is HTTP only.

That means:
- The frontend URL will be HTTP
- The Lambda Function URL will be HTTPS
- This is acceptable for an occasional MVP demo
- Browsers allow an HTTP page to call an HTTPS API
- If HTTPS for the frontend is needed later, CloudFront can be added as a follow-up enhancement

## Why React Instead of Chainlit
React is the better fit for this MVP because:
- it can be hosted statically on S3 at very low cost
- it supports custom UI patterns more easily
- it fits the requested features better:
  - 3-dot thread menu with delete
  - document/category panels
  - upload progress/status
  - disambiguation prompts
  - future admin/demo views

Chainlit is faster to prototype, but it is a server UI and would typically require always-on compute when deployed publicly.

## Frontend Scope
The React UI supports:
- thread sidebar
- 3-dot menu per thread
- delete history action
- document upload with 5 MB limit
- category badges and filters
- clarification prompts when questions are ambiguous
- support for insurance docs and synthetic support-ticket demo data

## Backend Scope
The FastAPI backend supports:
- retrieval and ingestion using the current RAG foundation
- Lambda-compatible entrypoint using existing Mangum handler
- thread list and thread delete APIs
- document list APIs
- category list APIs
- upload validation for supported files up to 5 MB
- category-aware retrieval and ambiguity handling

## Upload Recommendation
For lower cost and simpler scaling, the preferred upload flow is:
1. React asks backend for a presigned S3 upload URL
2. Browser uploads file directly to S3
3. Browser calls backend to trigger ingest from the uploaded object

This avoids sending full files through Lambda.

## Terraform Scope
Terraform should deploy the minimum-service stack.

### Keep
- existing Lambda function
- existing S3 data buckets
- existing DynamoDB tables
- existing IAM role structure
- existing ECR image path

### Remove from MVP path
- API Gateway resources
- ECS/Fargate resources

### Add
- S3 bucket for React frontend
- S3 website configuration for React SPA
- S3 bucket policy for public website hosting
- Lambda Function URL resource
- Lambda permission for function URL
- DynamoDB table for document category metadata
- outputs for:
  - frontend website URL
  - Lambda Function URL
  - frontend bucket name

## Testing
The MVP should be validated with:
- React app loads from S3 website endpoint
- backend works from Lambda Function URL
- CORS works between frontend and backend
- valid upload under 5 MB succeeds
- oversize file fails
- delete thread removes thread and linked history
- category detection works
- ambiguous question returns clarification

## Assumptions
- open demo, no login in v1
- no custom domain in v1
- no HTTPS frontend in v1
- occasional usage only
- cost optimization is more important than production polish

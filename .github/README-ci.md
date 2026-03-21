# GitHub Actions Setup

This repo includes a GitHub Actions workflow that builds the Lambda backend image and pushes it to Amazon ECR.

## Workflow

- `.github/workflows/build-lambda-image.yml`

## What it does

- checks out the repo
- authenticates to AWS using GitHub OIDC
- creates the ECR repository if it does not exist
- builds the Lambda-compatible container image
- pushes two tags:
  - commit SHA tag
  - `latest`

## Required GitHub Secret

- `AWS_ROLE_TO_ASSUME`
  - IAM role ARN that GitHub Actions can assume via OIDC

Example:

```text
arn:aws:iam::989126025320:role/github-actions-ecr-push
```

## Optional GitHub Repository Variables

- `AWS_REGION`
  - default in workflow: `ap-south-1`
- `ECR_REPOSITORY`
  - default in workflow: `rag-api`
- `IMAGE_TAG`
  - default in workflow: `latest`

## Recommended IAM permissions for the GitHub role

Minimum ECR permissions:

- `ecr:GetAuthorizationToken`
- `ecr:BatchCheckLayerAvailability`
- `ecr:CompleteLayerUpload`
- `ecr:CreateRepository`
- `ecr:DescribeRepositories`
- `ecr:InitiateLayerUpload`
- `ecr:PutImage`
- `ecr:UploadLayerPart`

## After the workflow runs

Take the pushed image URI from the workflow logs and use it for Terraform if needed:

```text
<account>.dkr.ecr.ap-south-1.amazonaws.com/rag-api:latest
```

Then your local or CI deploy step can pass:

```bash
-var="lambda_image_uri=<image-uri>"
```

## Why this helps

This removes the Docker dependency from your laptop. GitHub Actions performs the build and push in the cloud.

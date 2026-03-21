# Pipeline Handy Guide

This folder contains the Git Bash scripts for validating, planning, triggering, and cleaning up the AWS MVP pipeline.

## Folder

- `scripts/pipeline`

## Scripts

- `common.sh`
  - shared helper functions used by all pipeline scripts
  - resolves Terraform, AWS CLI, Docker, Python, and Node paths

- `preflight.sh`
  - verifies the active AWS identity
  - runs repo AWS service validation
  - validates Terraform
  - builds the frontend locally

- `terraform_plan.sh`
  - runs `terraform init`
  - creates a Terraform plan file before apply

- `build_lambda_image.sh`
  - creates the ECR repository through targeted Terraform apply
  - builds the Lambda-compatible container image
  - pushes the image to ECR
  - prints the final image URI

- `trigger_pipeline.sh`
  - runs preflight by default
  - builds and pushes the backend Lambda image by default
  - applies Terraform
  - syncs the frontend to the S3 website bucket
  - prints the frontend and Lambda URLs

- `sync_frontend.sh`
  - rebuilds the frontend with the deployed Lambda Function URL
  - uploads `frontend/dist` to the S3 frontend bucket

- `show_outputs.sh`
  - prints Terraform outputs like frontend URL, Lambda Function URL, and bucket names

- `cleanup_all.sh`
  - asks for confirmation twice
  - empties the S3 buckets
  - runs `terraform destroy`
  - use only when you want to remove the AWS stack and save cost

## Recommended Usage Order

1. `bash scripts/pipeline/preflight.sh`
2. `bash scripts/pipeline/terraform_plan.sh`
3. `bash scripts/pipeline/build_lambda_image.sh`
4. `bash scripts/pipeline/trigger_pipeline.sh`
5. `bash scripts/pipeline/show_outputs.sh`
6. `bash scripts/preload_demo.sh`

## Cleanup

Run this only when you intentionally want to delete the deployed AWS resources:

```bash
bash scripts/pipeline/cleanup_all.sh
```

This script asks for two confirmations before deleting anything.

## Demo Workspace Seeding

To populate the shared demo workspace after the API is running:

```bash
bash scripts/preload_demo.sh
```

This script:
- generates the synthetic ServiceNow ticket dataset
- uploads the sample insurance PDF
- ingests the generated CSV ticket file into `demo-shared`

## Default Tool Paths

These scripts are already configured to work with the current machine setup:

- Git Bash:
  - `C:\Users\dhairya.jindani\AppData\Local\Programs\Git\bin\bash.exe`
- Terraform:
  - `C:\Users\dhairya.jindani\Documents\AI-coe projects\bkp-1\Call Analyzer\.tools\terraform.exe`
- Docker:
  - must be available on `PATH` or set via `DOCKER_BIN`
- Python for repo:
  - `C:\Users\dhairya.jindani\Documents\AI-coe projects\Rag\.venv_local\Scripts\python.exe`
- AWS CLI fallback Python:
  - `C:\Users\dhairya.jindani\Documents\AI-coe projects\Call Analyzer\.venv\Scripts\python.exe`
- Node:
  - `C:\Users\dhairya.jindani\Downloads\npm code\node-v22.14.0-win-x64`

## Environment Variable Overrides

If needed, you can override the detected paths:

- `TERRAFORM_BIN`
- `PYTHON_BIN`
- `CALL_ANALYZER_AWSCLI_PYTHON`
- `NODE_DIR`
- `DOCKER_BIN`

## Important Note

No deployment is triggered automatically by creating or editing these scripts.
They only run when you execute them manually from Git Bash.

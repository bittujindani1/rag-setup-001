# Pipeline Scripts

These Git Bash scripts are the safe entrypoints for the local MVP deployment pipeline.

## Recommended order

1. `preflight.sh`
2. `terraform_plan.sh`
3. `build_lambda_image.sh`
4. `trigger_pipeline.sh`
5. `show_outputs.sh`

Use `cleanup_all.sh` only when you intentionally want to remove the AWS resources and save cost.

If you do not want Docker on your local machine, use the GitHub Actions workflow in:

- `.github/workflows/build-lambda-image.yml`

## Scripts

- `preflight.sh`
  - verifies AWS identity
  - runs repo AWS service validation
  - validates Terraform
  - builds the frontend locally
- `terraform_plan.sh`
  - runs `terraform init`
  - creates a reusable Terraform plan file
- `trigger_pipeline.sh`
  - runs preflight by default
  - builds and pushes the Lambda image by default
  - applies Terraform
  - syncs the frontend build to S3
  - prints the frontend and Lambda URLs
- `build_lambda_image.sh`
  - creates the ECR repository through targeted Terraform apply
  - logs in to ECR
  - builds the Lambda-compatible backend container image
  - pushes the image and prints the full image URI
- `sync_frontend.sh`
  - rebuilds the frontend with the deployed Lambda Function URL
  - syncs `frontend/dist` to the S3 website bucket
- `show_outputs.sh`
  - prints Terraform outputs
- `cleanup_all.sh`
  - asks for two confirmations
  - empties S3 buckets
  - runs `terraform destroy`

## Tool resolution

The scripts prefer:

- Terraform: the explicit machine path used in this environment, then `terraform` on `PATH`
- AWS CLI: `aws.cmd`, then `aws`, then `Call Analyzer/.venv` via `python -m awscli`
- Docker: `docker` or `docker.exe` on `PATH`
- Python: `.venv_local/Scripts/python.exe`
- Node: `C:/Users/dhairya.jindani/Downloads/npm code/node-v22.14.0-win-x64`

Override them with environment variables if needed:

- `TERRAFORM_BIN`
- `CALL_ANALYZER_AWSCLI_PYTHON`
- `PYTHON_BIN`
- `NODE_DIR`

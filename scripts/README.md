# Scripts

## important

Supported scripts for normal local validation and runtime checks:

- `important/restart_ui.sh`
- `important/run_e2e_job.sh`
- `important/run_local_validation.sh`
- `important/run_aws_service_validation.sh`
- `important/run_support_checks.sh`
- `important/check_idle_billing.sh`
- `preload_demo.sh`
- `pipeline/preflight.sh`
- `pipeline/terraform_plan.sh`
- `pipeline/trigger_pipeline.sh`
- `pipeline/sync_frontend.sh`
- `pipeline/show_outputs.sh`
- `pipeline/cleanup_all.sh`

Notes:

- `important/restart_ui.sh` now starts Chainlit via `python -m chainlit` and forces `DEBUG=false`
- the validation/e2e/support scripts also force `DEBUG=false` so inherited local env values do not break startup
- `important/check_idle_billing.sh` prints current S3, DynamoDB, Bedrock, and Textract billing-relevant details from the configured AWS account
- `important/show_aws_identity.py` prints the active boto3 credential source and STS caller identity; prefer this over machine-wide `python -m awscli`
- use `.venv_local/Scripts/python` for local validation, because the machine-level `python -m awscli` may be version-mismatched and is not the supported repo path
- `pipeline/cleanup_all.sh` is intentionally destructive and asks for two separate confirmations before it empties S3 buckets and runs `terraform destroy`
- `scripts/deploy.sh` now forwards to `pipeline/trigger_pipeline.sh`
- `preload_demo.sh` seeds the `demo-shared` workspace with the sample insurance PDF and generated synthetic tickets through the running API

## maintenance

Legacy deep-dive helpers kept for reference during troubleshooting:

- `maintenance/startup_recheck.sh`
- `maintenance/retrieval_only.sh`
- `maintenance/single_e2e_postfix.sh`
- `maintenance/extractor_only_check.sh`
- `maintenance/extractor_contract_runtime.sh`

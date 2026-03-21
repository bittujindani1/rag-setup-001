import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from config_loader import load_app_config


def main() -> int:
    config = load_app_config()
    region = config["aws_region"]
    buckets = [
        config["s3_bucket_documents"],
        config["s3_bucket_vectors"],
        config["s3_bucket_extracted"],
    ]

    client = boto3.client("s3", region_name=region)
    try:
        for bucket in buckets:
            client.head_bucket(Bucket=bucket)
            print(f"S3 bucket OK: {bucket}")
        return 0
    except (BotoCoreError, ClientError, KeyError) as exc:
        print(f"S3 validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json

import boto3


def main() -> int:
    session = boto3.Session()
    credentials = session.get_credentials()

    if credentials is None:
        print(json.dumps({"status": "missing_credentials"}))
        return 1

    frozen = credentials.get_frozen_credentials()
    payload = {
        "status": "ok",
        "profile": session.profile_name or "default",
        "region": session.region_name or "unset",
        "credential_method": credentials.method,
        "access_key_prefix": (frozen.access_key or "")[:4],
        "has_session_token": bool(frozen.token),
        "identity": session.client("sts", region_name=session.region_name or "ap-south-1").get_caller_identity(),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

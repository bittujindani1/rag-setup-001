import sys

from provider_factory import get_bedrock_client


def main() -> int:
    client = get_bedrock_client()
    try:
        embedding = client.embed_text("Travel insurance helps cover trip cancellations.")
        assert isinstance(embedding, list) and len(embedding) > 0
        print(f"Bedrock embedding OK: vector_size={len(embedding)}")

        reply = client.generate_text(
            prompt="Reply with the exact word READY.",
            system_prompt="Return only the requested word.",
            max_tokens=16,
            temperature=0.0,
        )
        assert isinstance(reply, str) and "READY" in reply.upper()
        print(f"Bedrock LLM OK: {reply.strip()}")
        return 0
    except AssertionError as exc:
        print(f"Bedrock validation failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Bedrock validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""检查 DashScope 模型与向量服务连通性，仅输出状态及模型信息。"""

import argparse
import json
import sys
from typing import Any

import httpx

from app.core.config import Settings, get_settings


def check_provider(settings: Settings, provider: str) -> dict[str, Any]:
    if not settings.dashscope_api_key:
        return {"provider": provider, "status": "not_configured"}
    model = settings.llm_model if provider == "llm" else settings.embedding_model
    payload: dict[str, Any]
    if provider == "llm":
        path = "chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "请只回复 OK。"}],
            "max_tokens": 8,
            "temperature": 0,
        }
    else:
        path = "embeddings"
        payload = {
            "model": model,
            "input": ["TiO2 oxide semiconductor"],
            "dimensions": settings.embedding_dimensions,
            "encoding_format": "float",
        }
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{settings.llm_base_url.rstrip('/')}/{path}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.dashscope_api_key.get_secret_value()}"
                },
            )
            response.raise_for_status()
            body = response.json()
        if provider == "llm":
            valid = bool(body.get("choices", [{}])[0].get("message", {}).get("content"))
            return {
                "provider": provider,
                "model": model,
                "status": "ok" if valid else "empty_response",
            }
        vectors = body.get("data", [])
        dimension = len(vectors[0].get("embedding", [])) if vectors else 0
        valid = len(vectors) == 1 and dimension == settings.embedding_dimensions
        return {
            "provider": provider,
            "model": model,
            "status": "ok" if valid else "invalid_response",
            "dimensions": dimension,
        }
    except httpx.HTTPStatusError as exc:
        return {
            "provider": provider,
            "status": "http_error",
            "http_status": exc.response.status_code,
        }
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        return {"provider": provider, "status": "failed", "error_type": type(exc).__name__}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Bounded live model connectivity checks")
    parser.add_argument("--provider", choices=["all", "llm", "embedding"], default="all")
    args = parser.parse_args()
    settings = get_settings()
    providers = ["llm", "embedding"] if args.provider == "all" else [args.provider]
    results = [check_provider(settings, provider) for provider in providers]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(result["status"] == "ok" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

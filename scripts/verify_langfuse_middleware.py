import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings

os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.LANGFUSE_PUBLIC_KEY)
os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.LANGFUSE_SECRET_KEY)
os.environ.setdefault("LANGFUSE_BASE_URL", settings.LANGFUSE_BASE_URL)
os.environ["LANGFUSE_DEBUG"] = "true"

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.langfuse_middleware import (  # noqa: E402
    LangfuseRequestTracingMiddleware,
    _is_ai_request,
)


class MockTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        body = json.loads(request.content)
        data = {
            "id": "chatcmpl-mock3",
            "object": "chat.completion",
            "created": 123,
            "model": body.get("model", "gpt-4o-mini"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "hello"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10},
        }
        return httpx.Response(200, json=data, request=request)


app = FastAPI()
app.add_middleware(LangfuseRequestTracingMiddleware)


@app.post("/api/chat/message")
async def chat():
    from langfuse.openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key="sk-test",
        base_url="http://mock.local",
        http_client=httpx.AsyncClient(transport=MockTransport()),
    )
    await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
        name="openai-chat-completion",
    )
    return {"ok": True}


@app.get("/health")
async def health():
    return {"ok": True}


def main() -> None:
    print("=== path predicate ===")
    for path in (
        "/api/chat/message",
        "/api/places/ChIJ/question",
        "/api/places/ChIJ/knowledge-sync",
        "/api/compare",
        "/api/health",
        "/api/auth/login",
        "/api/places/saved",
    ):
        print(f"  {path}: traced={_is_ai_request(path)}")

    print("=== request flow ===")
    with TestClient(app) as tc:
        r = tc.post("/api/chat/message")
        print("AI request status:", r.status_code)
        r2 = tc.get("/health")
        print("non-AI request status:", r2.status_code)
        r3 = tc.post("/api/chat/message")
        print("second AI request status:", r3.status_code)

    from langfuse import get_client

    get_client().flush()
    print("=== flushed ===")


if __name__ == "__main__":
    main()

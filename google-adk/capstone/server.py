"""带可信身份入口的本地 HTTP 服务。演示 token 不能用于公网部署。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types
from pydantic import BaseModel, Field

from .agent import build_agent
from .store import ALICE, BOB, VIEWER, RefundStore


class RunRequest(BaseModel):
    session_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    message: str = Field(min_length=1, max_length=4000)


def create_app(data_dir: Path, backend="offline", *, with_knowledge=True) -> FastAPI:
    data_dir.mkdir(parents=True, exist_ok=True)
    store = RefundStore(data_dir / "business.sqlite")
    sessions = DatabaseSessionService(
        db_url="sqlite+aiosqlite:///" + (data_dir / "sessions.sqlite").as_posix())
    # 生产应校验 IdP 签名/受众/有效期，再查询服务端权限。
    identities = {"demo-alice": ALICE, "demo-viewer": VIEWER, "demo-bob": BOB}
    lock = asyncio.Lock()  # 单进程串行示例，避免同一会话并发追加。

    @asynccontextmanager
    async def lifespan(app):
        yield
        await sessions.close()

    app = FastAPI(lifespan=lifespan)

    def authenticate(authorization):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="需要 Bearer 登录凭据")
        token = authorization[len("Bearer "):]
        if token not in identities:
            raise HTTPException(status_code=401, detail="登录凭据无效")
        return identities[token]

    @app.get("/health")
    async def health():
        return {"status": "ok", "pid": os.getpid(), "backend": backend}

    @app.get("/sessions/{session_id}")
    async def history(session_id: str, authorization: str | None = Header(None)):
        principal = authenticate(authorization)
        session = await sessions.get_session(app_name="capstone",
            user_id=f"{principal.tenant_id}:{principal.user_id}", session_id=session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        # 数量相同不代表内容相同；用事件 ID、作者与内容生成稳定指纹。
        payload = [
            {"id": event.id, "author": event.author,
             "content": event.content.model_dump(mode="json") if event.content else None}
            for event in session.events
        ]
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        return {"event_count": len(session.events),
                "event_fingerprint": fingerprint, "session_id": session.id}

    @app.post("/run")
    async def run(request: RunRequest, authorization: str | None = Header(None)):
        principal = authenticate(authorization)
        user_id = f"{principal.tenant_id}:{principal.user_id}"
        async with lock:
            session = await sessions.get_session(app_name="capstone", user_id=user_id,
                                                  session_id=request.session_id)
            if session is None:
                await sessions.create_session(app_name="capstone", user_id=user_id,
                                              session_id=request.session_id)
            agent = build_agent(store, principal, backend, with_knowledge=with_knowledge)
            model_calls = []
            def observe_call(callback_context, llm_request):
                model_calls.append(len(model_calls) + 1)
                return None
            agent.before_model_callback = observe_call
            runner = Runner(agent=agent, app_name="capstone", session_service=sessions)
            try:
                events = [event async for event in runner.run_async(
                    user_id=user_id, session_id=request.session_id,
                    new_message=types.Content(role="user", parts=[types.Part(text=request.message)]),
                    run_config=RunConfig(max_llm_calls=8 if with_knowledge else 4))]
            finally:
                # 工具集属于本次请求；关闭它们，不关闭服务共享的 SessionService。
                for tool in agent.tools:
                    if hasattr(tool, "close"):
                        await tool.close()
        calls = [call.name for event in events for call in event.get_function_calls()]
        outputs = [response.response for event in events
                   for response in event.get_function_responses()]
        finals = ["".join(p.text or "" for p in event.content.parts or [])
                  for event in events if event.author == agent.name
                  and event.is_final_response() and event.content]
        return {"calls": calls, "tool_results": outputs, "final": finals[-1] if finals else "",
                "model_requests": len(model_calls)}

    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--backend", choices=["offline", "deepseek"], default="offline")
    parser.add_argument("--business-only", action="store_true", help="仅业务工具，用于低成本在线冒烟")
    args = parser.parse_args()
    uvicorn.run(create_app(args.data_dir, args.backend, with_knowledge=not args.business_only), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()

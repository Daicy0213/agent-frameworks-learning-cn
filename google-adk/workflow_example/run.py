"""在独立进程中启动、审批或恢复第八章综合案例。"""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from google.adk.artifacts import FileArtifactService
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from .storage import Ledger
from .workflow import FLOW_VERSION, build_workflow, validate_approval


APP, USER, SESSION = "adk_ch08_project", "student", "content_job"


async def run(args) -> dict:
    directory = args.directory.resolve()
    ledger = Ledger(directory / "business.db")
    artifact_service = FileArtifactService(directory / "artifacts")
    service = DatabaseSessionService(
        db_url="sqlite+aiosqlite:///" + (directory / "sessions.db").as_posix()
    )
    try:
        workflow = build_workflow(
            ledger,
            mode=args.mode,
            fail_after_write=args.fail_after_write,
        )
        runner = Runner(
            agent=workflow,
            app_name=APP,
            session_service=service,
            artifact_service=artifact_service,
        )
        invocation_id, message = None, None
        if args.phase == "start":
            await service.create_session(
                app_name=APP,
                user_id=USER,
                session_id=SESSION,
                state={"backend": args.mode, "flow_version": FLOW_VERSION},
            )
            message = types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=args.input.read_text(encoding="utf-8"),
                    )
                ],
            )
        else:
            session = await service.get_session(
                app_name=APP,
                user_id=USER,
                session_id=SESSION,
            )
            if not session:
                raise ValueError("任务不存在，请先启动任务")
            if (
                session.state["backend"] != args.mode
                or session.state["flow_version"] != FLOW_VERSION
            ):
                raise ValueError("恢复必须保持同一内容后端和兼容的流程版本")
            invocation_id = session.events[-1].invocation_id
            if args.phase == "approve":
                requests = [
                    part.function_call
                    for event in session.events
                    for part in (
                        (event.content.parts or []) if event.content else []
                    )
                    if part.function_call
                    and part.function_call.name == "adk_request_input"
                ]
                if len(requests) != 1:
                    raise ValueError("本例需要恰好一个待审核请求")
                call = requests[0]
                response = {
                    "approved": args.decision == "accept",
                    "digest": call.args["payload"]["digest"],
                }
                validate_approval(response, call.args["payload"]["digest"])
                message = types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=call.id,
                                name=call.name,
                                response=response,
                            ),
                        )
                    ],
                )
        output, pending, errors = None, [], []
        failure = None
        try:
            async for event in runner.run_async(
                user_id=USER,
                session_id=SESSION,
                new_message=message,
                invocation_id=invocation_id,
            ):
                invocation_id = event.invocation_id
                if event.error_code:
                    errors.append(
                        {
                            "code": event.error_code,
                            "message": event.error_message,
                        }
                    )
                if event.node_info and event.output is not None:
                    if any(
                        "/" not in path
                        for path in event.node_info.output_for or []
                    ):
                        output = event.output
                for part in (
                    (event.content.parts or []) if event.content else []
                ):
                    if (
                        part.function_call
                        and part.function_call.name == "adk_request_input"
                    ):
                        pending.append(dict(part.function_call.args))
        except ConnectionError as error:
            # 只把本实验指定的故障转换成可检查报告，其他异常直接失败。
            if not args.fail_after_write or "故障注入" not in str(error):
                raise
            failure = str(error)
        session = await service.get_session(
            app_name=APP,
            user_id=USER,
            session_id=SESSION,
        )
        artifacts = []
        for receipt in ledger.snapshot()["receipts"]:
            filename = receipt["filename"]
            versions = await artifact_service.list_versions(
                app_name=APP,
                user_id=USER,
                session_id=SESSION,
                filename=filename,
            )
            content = await artifact_service.load_artifact(
                app_name=APP,
                user_id=USER,
                session_id=SESSION,
                filename=filename,
            )
            artifacts.append(
                {
                    "filename": filename,
                    "versions": versions,
                    "text": content.text,
                }
            )
        return {
            "pid": os.getpid(),
            "phase": args.phase,
            "status": "failed"
            if failure
            else (output["status"] if output else "paused"),
            "invocation_id": invocation_id,
            "output": output,
            "pending": pending,
            "errors": errors,
            "state": session.state,
            "ledger": ledger.snapshot(),
            "artifacts": artifacts,
        }
    finally:
        await service.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["start", "approve", "recover"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument(
        "--mode", choices=["offline", "deepseek"], default="deepseek"
    )
    parser.add_argument(
        "--decision", choices=["accept", "reject"], default="accept"
    )
    parser.add_argument("--fail-after-write", action="store_true")
    args = parser.parse_args()
    if args.phase == "start" and args.input is None:
        parser.error("start 需要 --input")
    # 指定故障以结构化事件展示；其他异常仍由进程失败报告。
    logging.getLogger("google_adk").setLevel(logging.CRITICAL)
    result = asyncio.run(run(args))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

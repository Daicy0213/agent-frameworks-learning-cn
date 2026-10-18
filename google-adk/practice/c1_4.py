"""
4. 封装一个可复用的对话入口（工程）

把第 1 章的代码整理为一个可复用的模块 / 命令行小程序，要求：

  - 首次访问时创建 Session，后续复用；
  - 支持退出命令；
  - API Key 缺失、模型请求失败时给出清晰错误；
  - 业务代码不能散落全局变量。

验收：连续对话可用；重新选择新 Session 后上下文被隔离。

运行：
    cd google-adk/practice

    # 1) 先做配置自检（不需要联网、不需要密钥也能看出缺什么）
    uv run python c1_4.py --check

    # 2) 非交互自检：跑两轮连续对话 + 一次新会话隔离
    uv run --env-file ../../.env python c1_4.py --demo

    # 3) 进入交互式对话
    uv run --env-file ../../.env python c1_4.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

DEFAULT_APP_NAME = "chat_cli"
DEFAULT_USER_ID = "local_user"
DEFAULT_MODEL = "deepseek/deepseek-chat"

EXIT_COMMANDS = {"/exit", "/quit", "/q"}
NEW_SESSION_COMMANDS = {"/new"}


class ConfigError(RuntimeError):
    """配置类问题（比如缺少密钥）。这类错误重试没有意义，必须改配置。"""


class ModelCallError(RuntimeError):
    """模型调用失败。包一层是为了把「哪个会话、什么异常」一起带出来。"""


class ChatApp:
    """一个可复用的对话入口。

    故意做成类而不是一堆全局变量：会话服务、Runner、会话登记表都是实例状态，
    这样同一进程里可以并存多个互不干扰的对话入口（测试时尤其有用）。
    """

    def __init__(
        self,
        app_name: str = DEFAULT_APP_NAME,
        user_id: str = DEFAULT_USER_ID,
        model_name: str = DEFAULT_MODEL,
    ) -> None:
        self.app_name = app_name
        self.user_id = user_id
        self.model_name = model_name
        self._session_service = InMemorySessionService()
        self._runner: Runner | None = None
        self._known_sessions: set[str] = set()

    # ---------------------------------------------------------------- 构建
    def build(self) -> None:
        """延迟构建。

        刻意不在 __init__ 里做：配置检查应该给出**清晰的中文错误**，
        而不是让缺密钥的问题伪装成 import 阶段的奇怪堆栈。
        """
        if not os.getenv("DEEPSEEK_API_KEY"):
            raise ConfigError(
                "缺少环境变量 DEEPSEEK_API_KEY。\n"
                "  请在仓库根目录的 .env 中配置，然后用\n"
                "    uv run --env-file ../../.env python c1_4.py\n"
                "  启动。"
            )

        agent = Agent(
            name="chat_cli_agent",
            model=LiteLlm(model=self.model_name),
            instruction="你是友好、简洁的中文助手。回答控制在三句话以内。",
            description="命令行对话助手",
        )
        self._runner = Runner(
            session_service=self._session_service,
            agent=agent,
            app_name=self.app_name,
        )

    # ---------------------------------------------------------------- 会话
    async def _ensure_session(self, session_id: str) -> None:
        """首次访问时创建 Session，之后复用。"""
        if session_id in self._known_sessions:
            return
        await self._session_service.create_session(
            app_name=self.app_name, user_id=self.user_id, session_id=session_id
        )
        self._known_sessions.add(session_id)

    def new_session_id(self) -> str:
        return f"s{len(self._known_sessions) + 1}"

    # ---------------------------------------------------------------- 对话
    async def send(self, text: str, session_id: str = "s1") -> str:
        """发一句话，返回 Agent 的最终回复文本。"""
        if self._runner is None:
            raise ConfigError("ChatApp 还没 build()，请先调用 build()。")

        await self._ensure_session(session_id)
        message = types.Content(role="user", parts=[types.Part(text=text)])

        reply = ""
        try:
            async for event in self._runner.run_async(
                user_id=self.user_id, session_id=session_id, new_message=message
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    reply += event.content.parts[0].text or ""
        except Exception as error:
            # 把上下文（哪个会话、什么异常）一起包进去，否则排查时只有一句"失败了"
            raise ModelCallError(
                f"模型调用失败（session={session_id}）："
                f"{type(error).__name__}: {error}"
            ) from error

        return reply.strip()

    # ---------------------------------------------------------------- 交互
    async def repl(self, session_id: str = "s1") -> None:
        """一个最小的命令行对话循环。"""
        print("对话已开始。命令：/new 开一个新会话（上下文隔离）  /exit 退出\n")
        while True:
            try:
                line = input(f"[{session_id}] >>> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not line:
                continue
            if line in EXIT_COMMANDS:
                break
            if line in NEW_SESSION_COMMANDS:
                session_id = self.new_session_id()
                print(f"→ 已切换到新会话 {session_id}，之前的上下文不会带过来\n")
                continue

            try:
                print(await self.send(line, session_id), "\n")
            except ModelCallError as error:
                # 交互场景下不该因为一次失败就退出，报清楚再继续
                print(f"⚠️  {error}\n", file=sys.stderr)

        print("再见。")


async def run_demo(app: ChatApp) -> None:
    """非交互自检：连续对话可用 + 新会话上下文隔离。"""
    name = "小林"

    reply1 = await app.send(f"我叫{name}，请记住。", "s1")
    print(f"[s1] 我叫{name}，请记住。\n  -> {reply1}\n")

    reply2 = await app.send("我叫什么名字？", "s1")
    print(f"[s1] 我叫什么名字？\n  -> {reply2}\n")

    # 同一个 Session：必须记得
    assert name in reply2, f"s1 应该记得刚才说的名字，实际回复：{reply2}"

    reply3 = await app.send("我叫什么名字？", "s2")
    print(f"[s2] 我叫什么名字？\n  -> {reply3}\n")

    # 新 Session：不应该记得
    assert name not in reply3, f"s2 是全新会话，不该知道名字，实际回复：{reply3}"

    print("✅ 练习 4 通过：连续对话可用，新 Session 上下文隔离")
    print(f"   （本次共使用会话：{sorted(app._known_sessions)}）")


def run_check() -> int:
    """配置自检：不联网、不调用模型，先告诉你缺什么。"""
    import importlib.metadata as metadata

    print("配置自检")
    print("-" * 60)
    problems: list[str] = []

    try:
        version = metadata.version("google-adk")
    except metadata.PackageNotFoundError:
        version = None
    if version and version.startswith("2.12."):
        print(f"  ✅ google-adk {version}")
    else:
        print(f"  ❌ google-adk 版本：{version}（需要 2.12.x）")
        print(f"     当前解释器：{sys.executable}")
        problems.append("请从项目根目录执行 uv sync，并确认用 .venv 里的 Python 运行")

    if os.getenv("DEEPSEEK_API_KEY"):
        print("  ✅ DEEPSEEK_API_KEY 已配置")
    else:
        print("  ❌ DEEPSEEK_API_KEY 未配置")
        problems.append(
            "请在仓库根目录的 .env 中配置 DEEPSEEK_API_KEY，"
            "并用 uv run --env-file ../../.env 启动"
        )

    print("-" * 60)
    if problems:
        print("发现以下问题：")
        for p in problems:
            print("  -", p)
        return 1
    print("一切就绪。可以运行：uv run --env-file ../../.env python c1_4.py --demo")
    return 0


async def amain(args) -> int:
    app = ChatApp()
    try:
        app.build()
    except ConfigError as error:
        print(f"配置错误：{error}", file=sys.stderr)
        return 2

    if args.demo:
        try:
            await run_demo(app)
        except ModelCallError as error:
            print(f"运行失败：{error}", file=sys.stderr)
            return 3
        return 0

    await app.repl()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="第 1 章练习 4：可复用的对话入口")
    parser.add_argument("--check", action="store_true", help="只做配置自检，不调用模型")
    parser.add_argument("--demo", action="store_true", help="非交互自检：连续对话 + 会话隔离")
    args = parser.parse_args(argv)

    if args.check:
        return run_check()
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())

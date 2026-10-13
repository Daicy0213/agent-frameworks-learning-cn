"""真实模型、业务准入、人工确认和可恢复归档共用一条编排。"""

import hashlib
import json
import os

# 导入 LiteLLM 前选择本地成本表；模型请求仍发送到真实 DeepSeek API。
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

from google.adk import Context, Workflow
from google.adk.agents import Agent
from google.adk.events import RequestInput
from google.adk.models.lite_llm import LiteLlm
from google.adk.workflow import RetryConfig, node
from google.genai import types
from pydantic import BaseModel, Field, model_validator

from .storage import Ledger


FLOW_VERSION = "content-review-v1"


class Item(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    topic: str = Field(min_length=1)
    notes: str = Field(min_length=1)
    required_terms: list[str] = Field(default_factory=list)


class Job(BaseModel):
    flow_version: str = FLOW_VERSION
    items: list[Item] = Field(min_length=1, max_length=4)
    max_revisions: int = Field(default=1, ge=0, le=2, strict=True)

    @model_validator(mode="after")
    def validate_business_identity(self):
        if self.flow_version != FLOW_VERSION:
            raise ValueError("流程版本不兼容，不能直接恢复旧任务")
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("业务 ID 不能重复")
        if any(
            not item.topic.strip() or not item.notes.strip()
            for item in self.items
        ):
            raise ValueError("主题和事实说明不能空白")
        return self


class Draft(BaseModel):
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)


class Approval(BaseModel):
    approved: bool = Field(strict=True)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def candidate_digest(articles: list[dict]) -> str:
    encoded = json.dumps(
        articles, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_approval(response: dict, digest: str) -> bool:
    decision = Approval.model_validate(response)
    if decision.digest != digest:
        raise ValueError("审批摘要与当前候选稿不一致")
    return decision.approved


def review(draft: dict, request: dict) -> dict:
    article = Draft.model_validate(draft)
    findings = []
    if not article.title.strip():
        findings.append("标题不能为空白")
    # 综合案例允许更完整的技术介绍，字数范围独立于第七章。
    if not 60 <= len(article.body) <= 150:
        findings.append(f"正文 {len(article.body)} 字符，要求 60～150")
    for term in dict.fromkeys(["例如", *request["required_terms"]]):
        if term not in article.body:
            findings.append(f"正文必须包含：{term}")
    return {"passed": not findings, "findings": findings}


def build_workflow(ledger: Ledger, *, mode="deepseek", fail_after_write=False):
    """每个独立进程重建相同节点定义；业务数据从 Session 恢复。"""
    if mode not in {"offline", "deepseek"}:
        raise ValueError("未知内容后端")
    active_workers = 0

    def record_response(callback_context, llm_response):
        usage = llm_response.usage_metadata
        ledger.record_model(
            callback_context.agent_name,
            usage.total_token_count if usage else 0,
        )
        return None

    def model():
        return LiteLlm(
            model="deepseek/deepseek-chat",
            max_tokens=768,
            response_format={"type": "json_object"},
        )

    writer = Agent(
        name="project_writer",
        model=model(),
        mode="single_turn",
        instruction="根据输入 topic 和 notes 写中文技术介绍，遵循 notes 的事实。"
        "正文目标 90～110 个字符，验收 60～150，标点和英文也计数。"
        "正文含 required_terms 中的每个词和‘例如’引出的写作审核例子。"
        "审批用暂停和恢复，不是轮询；checkpoint 不冻结 Python 调用栈。"
        '只输出 JSON：{"title":"标题","body":"正文"}。',
        after_model_callback=record_response,
    )
    reviser = Agent(
        name="project_reviser",
        model=model(),
        mode="single_turn",
        instruction="按 findings 修复 draft，遵循 request.notes。已合格的规则不要破坏。"
        "正文目标 90～110 字符，验收 60～150，包含 required_terms 和‘例如’。"
        "保留事实和写作审核例子，审批通过暂停与恢复实现。"
        '只输出 JSON：{"title":"标题","body":"正文"}。',
        after_model_callback=record_response,
    )

    @node
    def read_plan(node_input) -> dict:
        ledger.count("read_plan")
        text = "".join(part.text or "" for part in node_input.parts or [])
        job = Job.model_validate_json(text)
        return {
            **job.model_dump(),
            "items": [
                item.model_dump()
                for item in sorted(job.items, key=lambda x: x.id)
            ],
        }

    @node
    def offline_writer(node_input: dict) -> dict:
        body = (
            "工作流先由代码安排写作与检查，再按结果决定是否修改。"
            "例如候选稿通过规则后暂停等待人工审核，收到对应回复才继续归档。"
            "过程有预算上限，失败与拒绝都不会被当作成功。"
        )
        if node_input["topic"] == "失败样本":
            body = "太短"
        return {"title": node_input["topic"], "body": body}

    @node(rerun_on_resume=True)
    async def article_worker(ctx: Context, node_input: dict) -> dict:
        nonlocal active_workers
        request = node_input["request"]
        ledger.count(f"article:{request['id']}")
        active_workers += 1
        ledger.record_peak(active_workers)
        try:
            if mode == "deepseek":
                draft = Draft.model_validate_json(
                    await ctx.run_node(writer, request)
                ).model_dump()
            else:
                draft = await ctx.run_node(offline_writer, request)
            for revision in range(node_input["max_revisions"] + 1):
                verdict = review(draft, request)
                if (
                    verdict["passed"]
                    or revision == node_input["max_revisions"]
                ):
                    ctx.state[f"article:{request['id']}"] = {
                        "passed": verdict["passed"],
                        "title": draft["title"],
                    }
                    return {
                        "id": request["id"],
                        "draft": draft,
                        **verdict,
                        "revisions": revision,
                    }
                if mode == "deepseek":
                    draft = Draft.model_validate_json(
                        await ctx.run_node(
                            reviser,
                            {
                                "request": request,
                                "draft": draft,
                                "findings": verdict["findings"],
                            },
                        )
                    ).model_dump()
                else:
                    draft = await ctx.run_node(offline_writer, request)
        finally:
            active_workers -= 1

    @node(rerun_on_resume=False)
    def ask_approval(node_input: dict):
        return RequestInput(
            message="请核对全文与摘要，再决定接受或拒绝这一批稿件。",
            payload=node_input,
            response_schema=Approval,
        )

    @node(retry_config=RetryConfig(max_attempts=1))
    async def archive(ctx: Context, node_input: dict) -> dict:
        ledger.count("archive_attempts")
        digest = node_input["digest"]
        filename = f"batch-{digest}.md"
        text = "\n\n".join(
            f"# {item['draft']['title']}\n\n{item['draft']['body']}"
            for item in node_input["articles"]
        )
        existing = await ctx.load_artifact(filename)
        if existing is None:
            version = await ctx.save_artifact(
                filename,
                types.Part.from_text(text=text),
            )
        else:
            if existing.text != text:
                raise ValueError("同一归档身份不能绑定不同内容")
            version_info = await ctx.get_artifact_version(filename)
            version = version_info.version
        ledger.save_receipt(
            FLOW_VERSION + ":archive:" + digest,
            digest,
            filename,
            version,
            len(node_input["articles"]),
        )
        if fail_after_write and ledger.claim_fault():
            raise ConnectionError(
                "故障注入：Artifact 和业务回执已保存，节点尚未完成"
            )
        return {
            "status": "archived",
            "filename": filename,
            "version": version,
            "digest": digest,
            "count": len(node_input["articles"]),
        }

    workers = node(
        article_worker, parallel_worker=True, max_parallel_workers=2
    )

    @node(rerun_on_resume=True)
    async def editor(ctx: Context, node_input):
        ledger.count("parent")
        plan = await ctx.run_node(read_plan, node_input)
        if plan["flow_version"] != FLOW_VERSION:
            raise ValueError("恢复任务的流程版本与当前代码不兼容")
        work = [
            {"request": item, "max_revisions": plan["max_revisions"]}
            for item in plan["items"]
        ]
        articles = await ctx.run_node(workers, work)
        if not all(article["passed"] for article in articles):
            return {"status": "needs_revision", "articles": articles}
        digest = candidate_digest(articles)
        reply = await ctx.run_node(
            ask_approval,
            {
                "flow_version": FLOW_VERSION,
                "digest": digest,
                "articles": articles,
            },
        )
        if not validate_approval(reply, digest):
            return {"status": "rejected", "articles": articles}
        return await ctx.run_node(
            archive, {"digest": digest, "articles": articles}
        )

    return Workflow(name="content_review", edges=[("START", editor)])

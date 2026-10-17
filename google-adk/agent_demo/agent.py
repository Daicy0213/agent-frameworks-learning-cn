"""ADK 标准工程的最小示例：adk web / adk run / adk api_server 都从这个入口加载。"""

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

root_agent = Agent(
    name="study_buddy",
    model=LiteLlm(model="deepseek/deepseek-chat"),
    instruction=(
        "你是一名学习计划助手。"
        "先问清目标、可用时间和当前基础，再给出按天拆分的计划。"
        "信息不足时先追问，不要凭空假设。"
        "计划用 Markdown 表格输出。"
    ),
    description="帮助学习者制定可执行的学习计划",
)

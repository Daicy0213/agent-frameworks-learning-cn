"""
1. 改造第一个 Agent（基础）

把示例 Agent 改造成“学习计划助手”：通过 `instruction` 约束它先追问目标与可用时间，再给出 Markdown 表格计划。
分别输入信息充分和信息不足的请求，确认回复行为符合约束；同时记录模型名、Agent 名称及最终响应。
"""

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

APP_NAME = "study_planner"
USER_ID = "student_01"

# 1. 定义模型：通过 LiteLLM 适配层接入 DeepSeek
deepseek_model = LiteLlm(model="deepseek/deepseek-chat")

# 2. 定义 Agent：名字、模型、指令（system prompt）
study_planner = Agent(
    name="study_planner_assistant",
    model=deepseek_model,
    instruction="你是一个学习计划助手, 根据用户提供的目标和可用时间, 帮助用户制定一个可行的计划."
                "如果用户没有提供具体的目标和可用时间, 你需要提问并让用户进行澄清, 在没有获得具体信息之前, 请不要提供任何计划."
                "你提出的计划必须严格围绕用户的目标和可用时间进行安排, 计划内容切实可行, 可以根据用户提供的信息进行合理的安排."
                "计划使用 Markdown 的表格形式返回给用户, 至少提供时间/内容/目标等条目, 并结合具体的情况适当增加其他内容.",
    description="一个学习计划助手",
)

# 3. 组装 Runner
session_service = InMemorySessionService()
runner = Runner(session_service=session_service, agent=study_planner, app_name=APP_NAME)


# 4. 定义chat函数
async def chat(query: str, session_id: str = "s1") -> str | None:
    """向 Agent 发送一条消息，收集最终回复文本。"""
    # 确保会话存在（重复创建同 id 会话会报错，做个防御）
    try:
        await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
    except Exception:
        pass

    # 输入 message
    message = types.Content(role="user", parts=[types.Part(text=query)])
    final_text = ""

    # 遍历 event 直到 event.is_final_response()
    async for event in runner.run_async(user_id=USER_ID, session_id=session_id, new_message=message):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text
    return final_text


if __name__ == '__main__':
    import asyncio

    print(asyncio.run(chat("我想要练习英语的听力")))

    query = input("\033[36ms01 >> \033[0m")
    print(asyncio.run(chat(query, session_id="s1")))

    """
    好的，为了帮你制定一个切实可行的英语听力练习计划，我需要先了解一些信息：
    
    1. 你目前的英语听力水平大概如何？（例如：初级、中级、高级，或能听懂简单对话/新闻/影视剧等）
    2. 你每天或每周大概能拿出多少时间练习？
    3. 你主要想提升哪方面的听力？（例如：日常对话、考试听力、学术讲座、影视无字幕等）
    4. 你希望计划持续多久？（例如：2周、1个月、3个月）
    5. 你目前有哪些可用资源或工具？（例如：手机App、网课、教材、英文播客等）
    
    请告诉我以上信息，我就能为你制定一个具体的学习计划。
    
    s01 >> 1. 大概是CET6刚刚过线的水平 2.每天大概30~60分钟的时间 3.我目前在外企工作, 想要无障碍地进行日常的工作交流 4.3个月时间 5.主要依赖网络中的视频或者博客等
    
    好的，根据你提供的信息，我为你制定了一个为期 **3 个月**的英语听力练习计划，重点提升 **外企日常沟通场景** 的听力理解能力，每天 **30–60 分钟**，主要利用网络视频和播客资源。
    
    ### 总体思路
    - **第1个月：适应真实语速，积累职场高频表达**  
    - **第2个月：强化会议、电话、闲聊等场景理解**  
    - **第3个月：综合实战，提升反应速度和连贯理解**
    
    ### 学习计划表
    
    | 时间段 | 每日时长 | 学习内容 | 具体方法 | 目标 |
    |--------|----------|----------|----------|------|
    | 第1周 | 30–40 分钟 | 职场日常对话（问候、安排会议、简单汇报） | 观看 YouTube / B站 上的“Business English Conversation”类视频，每段 3–5 分钟，先盲听1遍，再看字幕1遍，再盲听1遍 | 适应外企常见语速，能听懂 60% 以上 |
    | 第2周 | 30–45 分钟 | 电话/视频会议常用表达 | 听播客如《Business English Pod》基础篇，每集 10–15 分钟，做笔记记录高频短语 | 能抓住会议中的关键信息（时间、任务、问题） |
    | 第3周 | 40–50 分钟 | 同事闲聊、非正式沟通 | 看美剧/英剧职场片段（如《The Office》），每段 5 分钟，反复听 3 遍，整理俚语和缩略表达 | 能听懂非正式对话中的语气和意图 |
    | 第4周 | 40–60 分钟 | 综合复习 + 小测 | 回顾前三周笔记，选 2–3 段无字幕视频做听写，对照原文查漏 | 巩固前3周内容，听力稳定在 70% 左右 |
    | 第5周 | 30–50 分钟 | 项目汇报、进度同步 | 听 TED Business 或公司内部英文分享（如可获取），每段 8–10 分钟，边听边记关键词 | 能听懂汇报结构（背景-进展-问题-计划） |
    | 第6周 | 30–50 分钟 | 客户沟通、跨文化表达 | 听《Business English Pod》中级篇，配合跟读练习 | 能理解不同口音的英语（美、英、印等） |
    | 第7周 | 40–60 分钟 | 电话会议 + 快速反应 | 使用 YouTube 上的“Conference Call English”模拟视频，做影子跟读（shadowing） | 提升即时反应能力，减少“卡住” |
    | 第8周 | 40–60 分钟 | 综合场景混合练习 | 随机播放职场播客/视频，不看字幕，听完后用英文复述大意 | 能连贯理解 2–3 分钟职场对话 |
    | 第9周 | 30–50 分钟 | 弱项强化 | 回看前8周笔记，找出最常听不懂的场景（如数字、人名、缩写），专项练习 | 补齐短板，提升细节听力 |
    | 第10周 | 40–60 分钟 | 模拟真实工作场景 | 找同事或语伴进行英文语音/视频练习，或听真实会议录音（脱敏后） | 在真实交流中验证听力提升 |
    | 第11周 | 40–60 分钟 | 综合实战 + 复盘 | 每天听 1 段 5–8 分钟职场内容，做摘要笔记；每周复盘一次 | 能听懂 80% 以上，能抓住逻辑和态度 |
    | 第12周 | 30–60 分钟 | 冲刺 + 自测 | 选 3 段不同场景（会议、闲聊、电话）无字幕测试，对比第1周水平 | 达成“无障碍日常沟通”目标 |
    
    ### 建议使用的资源
    | 类型 | 推荐资源 |
    |------|----------|
    | 视频 | YouTube: BBC Learning English, Business English Pod, TED Talks Business |
    | 播客 | Business English Pod, The English We Speak, All Ears English |
    | 剧集 | The Office (US/UK), Suits, Mad Men（职场片段） |
    | 工具 | 每日英语听力App、欧路词典、Notion/Excel 做笔记 |
    
    ### 执行小贴士
    - **坚持每天听**，哪怕只有 30 分钟，比周末集中听 3 小时更有效。
    - **盲听 → 看字幕 → 再盲听 → 跟读** 是提升听力的核心循环。
    - **记录听不懂的表达**，每周复习一次。
    - 第 6 周和第 12 周可各做一次自测，方便调整后续计划。
    
    如果你希望我根据你的具体行业（如 IT、金融、制造等）进一步细化内容，也可以告诉我。
    """

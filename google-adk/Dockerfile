# 仓库根目录：docker build -f google-adk/Dockerfile -t adk-course-demo .
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
# 只暴露这个演示应用，不把课程答案、评估集或 .env 打进镜像。
COPY google-adk/agent_demo ./apps/agent_demo
ENV PATH="/app/.venv/bin:$PATH" LITELLM_LOCAL_MODEL_COST_MAP=True
EXPOSE 8000
CMD ["adk", "api_server", "apps", "--host", "0.0.0.0", "--port", "8000", "--session_service_uri", "memory://"]

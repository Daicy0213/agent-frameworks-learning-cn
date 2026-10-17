# 第 11 章示例：把标准工程打成可运行的 API 镜像。
# 构建（在仓库根目录）：
#   docker build -f google-adk/Dockerfile -t adk-agent-demo .
# 运行：
#   docker run --rm -p 8000:8000 -e DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" adk-agent-demo

FROM python:3.12-slim

WORKDIR /app

# 使用项目锁文件安装依赖，保证可复现。
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY google-adk ./google-adk

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

CMD ["adk", "api_server", "google-adk", "--host", "0.0.0.0", "--port", "8000"]

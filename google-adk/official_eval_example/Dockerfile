FROM python:3.12-slim
WORKDIR /course/google-adk
COPY google-adk/official_eval_example/requirements-cli.txt /tmp/requirements-cli.txt
RUN pip install --no-cache-dir -r /tmp/requirements-cli.txt
COPY google-adk/official_eval_example ./official_eval_example
ENV LITELLM_LOCAL_MODEL_COST_MAP=True ADK_EVAL_BACKEND=offline PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["adk", "eval", "official_eval_example"]
CMD ["official_eval_example/three_cases.evalset.json", "--config_file_path", "official_eval_example/evaluation_config.json", "--print_detailed_results"]

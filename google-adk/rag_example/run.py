"""从 google-adk 目录运行 python -m rag_example.run。"""
import argparse
import asyncio
import json
from pathlib import Path
from .agent import answer_question
from .retrieval import Scope


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default="退款多久原路退回？")
    parser.add_argument("--tenant", default="shop-a", help="模拟已认证租户；不是生产鉴权")
    parser.add_argument("--as-of", default="2026-10-01")
    parser.add_argument("--backend", choices=["offline", "deepseek"], default="offline")
    args = parser.parse_args()
    if args.backend == "deepseek":
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    result = asyncio.run(answer_question(
        args.question, scope=Scope(args.tenant, args.as_of), backend=args.backend,
    ))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

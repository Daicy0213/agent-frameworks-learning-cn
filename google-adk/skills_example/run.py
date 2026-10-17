"""默认运行拒绝受理的离线案例；--approved 使用已审批的教学身份。"""
import argparse
import asyncio
import json
from pathlib import Path

from .agent import run_skill_case
from .business import Principal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["offline", "deepseek"], default="offline")
    parser.add_argument("--approved", action="store_true")
    parser.add_argument(
        "--scenario",
        choices=["normal", "duplicate", "missing_resource", "no_executor"],
        default="normal",
    )
    args = parser.parse_args()
    if args.backend == "deepseek":
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    principal = (
        Principal(role="approver", approved_orders=frozenset({"A-100"}))
        if args.approved else Principal()
    )
    result = asyncio.run(run_skill_case(
        principal=principal, scenario=args.scenario, backend=args.backend,
    ))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

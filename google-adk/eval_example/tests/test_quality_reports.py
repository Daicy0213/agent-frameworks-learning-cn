"""报告口径与业务副作用回归；不调用模型。"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from eval_example.business_checks import check_refund_effects
from eval_example.rouge_compat import response_match_score
from eval_example.run_quality_eval import evaluate, compare_baseline, _write_reports, validate_dataset
from eval_example.tools import create_refund_request, get_refund_requests, reset_demo_state

ROOT = Path(__file__).resolve().parents[1]


class BusinessEffectsTests(unittest.TestCase):
    def setUp(self):
        reset_demo_state()
        self.expected = [{"idempotency_key": "test-key", "order_id": "A1001",
                          "amount": 299, "reason": "按键失灵", "status": "待审核"}]

    def test_claim_success_without_write_fails(self):
        # 回复即使与参考逐字一致，也没有实现退款业务目标。
        self.assertEqual(response_match_score("退款已提交", "退款已提交"), 1)
        self.assertFalse(check_refund_effects({}, {}, self.expected))

    def test_refusal_with_write_fails(self):
        create_refund_request("A1001", 299, "按键失灵", "APPROVED", "test-key")
        # 期望拒绝的案例声明零新增；不能被正确的拒答文本掩盖。
        self.assertFalse(check_refund_effects({}, get_refund_requests(), []))

    def test_expected_write_passes(self):
        create_refund_request("A1001", 299, "按键失灵", "APPROVED", "test-key")
        self.assertTrue(check_refund_effects({}, get_refund_requests(), self.expected))

    def test_tool_rechecks_approval_without_callback(self):
        result = create_refund_request("A1001", 299, "按键失灵", "FORGED", "test-key")
        self.assertFalse(result["ok"])
        self.assertEqual(get_refund_requests(), {})

    def test_key_cannot_be_reused_for_different_payload(self):
        create_refund_request("A1001", 299, "按键失灵", "APPROVED", "test-key")
        before = get_refund_requests()
        result = create_refund_request("A1001", 100, "按键失灵", "APPROVED", "test-key")
        self.assertEqual(result["error_code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(get_refund_requests(), before)

    def test_nonfinite_amount_cannot_write(self):
        for amount in (float("nan"), float("inf"), True):
            self.assertFalse(create_refund_request("A1001", amount, "故障", "APPROVED", "key")["ok"])
        self.assertEqual(get_refund_requests(), {})


class RougeCompatibilityTests(unittest.TestCase):
    def test_unicode_contract(self):
        self.assertEqual(response_match_score("订单已经签收", "订单已经签收"), 1)
        self.assertEqual(response_match_score("苹果", "香蕉"), 0)

    def test_matches_adk_evaluator(self):
        from google.adk.evaluation.eval_case import Invocation
        from google.adk.evaluation.eval_metrics import EvalMetric
        from google.adk.evaluation.final_response_match_v1 import RougeEvaluator
        from google.genai import types
        def invocation(text):
            return Invocation(user_content=types.Content(role="user", parts=[types.Part(text="查询")]),
                              final_response=types.Content(role="model", parts=[types.Part(text=text)]))
        score = RougeEvaluator(EvalMetric(metric_name="response_match_score", threshold=0.5)).evaluate_invocations(
            [invocation("订单已签收")], [invocation("订单尚未签收")]
        ).overall_score
        self.assertEqual(response_match_score("订单已签收", "订单尚未签收"), score)


class ReportTests(unittest.IsolatedAsyncioTestCase):
    async def test_smoke_pass_does_not_grant_release_or_invent_safety(self):
        dataset = json.loads((ROOT / "eval_sets/after_sales.evalset.json").read_text(encoding="utf-8"))
        gates = json.loads((ROOT / "quality_gates.json").read_text(encoding="utf-8"))
        turn = dataset["eval_cases"][0]["conversation"][0]
        execution = {"response": turn["final_response"]["parts"][0]["text"],
                     "actual_tool_uses": turn["intermediate_data"]["tool_uses"],
                     "latency_ms": 1, "input_tokens": 0, "output_tokens": 0}
        with patch("eval_example.run_quality_eval._run_turn", AsyncMock(return_value=execution)):
            report = await evaluate(dataset, gates, limit=1)
        self.assertTrue(report["passed"])
        self.assertFalse(report["release_ready"])
        self.assertIsNone(report["metrics"]["safety_case_pass_rate"])
        self.assertIsNone(report["gates"]["safety_case_pass_rate_min"])
        with tempfile.TemporaryDirectory() as folder:
            _, md = _write_reports(report, Path(folder))
            self.assertIn("未评估（没有安全案例）", md.read_text(encoding="utf-8"))
            self.assertIn("未评估（冒烟只检查所选案例）", md.read_text(encoding="utf-8"))

    def test_missing_ledger_expectation_is_not_silently_zero_writes(self):
        dataset = json.loads((ROOT / "eval_sets/after_sales.evalset.json").read_text(encoding="utf-8"))
        del dataset["eval_cases"][0]["test_spec"]["turns"][0]["expected_refunds_created"]
        errors = validate_dataset(dataset)
        self.assertTrue(any("expected_refunds_created" in error for error in errors))

    async def test_invalid_limit_fails_before_model_call(self):
        with self.assertRaises(ValueError):
            await evaluate({"eval_cases": []}, {}, limit=0)

    def test_baseline_uses_percentage_points(self):
        keys = ("task_success_rate", "tool_selection_accuracy", "format_compliance_rate",
                "safety_case_pass_rate", "response_match_score")
        def report(value):
            return {"mode": "full", "dataset_id": "same", "cases": [{"eval_id": "one"}],
                    "metrics": {key: value for key in keys}}
        self.assertTrue(all(compare_baseline(report(0.85), report(0.90), 0.05).values()))
        self.assertFalse(all(compare_baseline(report(0.84), report(0.90), 0.05).values()))
        smoke = report(1); smoke["mode"] = "smoke"
        with self.assertRaises(ValueError):
            compare_baseline(smoke, report(1), 0.05)

"""ADK 2.6.3 私有 ROUGE 适配点；升级时先运行契约测试。"""

from importlib.metadata import version


def response_match_score(response: str, reference: str) -> float:
    if version("google-adk") != "2.6.3":
        raise RuntimeError("ROUGE 适配器仅验证过 google-adk 2.6.3，请先运行兼容性测试。")
    from google.adk.evaluation.final_response_match_v1 import _calculate_rouge_1_scores

    return _calculate_rouge_1_scores(response, reference).fmeasure

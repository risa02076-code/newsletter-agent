import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

VERIFY_SYSTEM_PROMPT = """당신은 채용 뉴스레터의 검수 담당자입니다.
[재료]에 실제로 있는 내용만 [요약]/[인사이트]에 쓰였는지 판정하세요.
재료에 없는 숫자·조건·회사명이 하나라도 들어갔으면 hallucinated=true 입니다.
반드시 이 JSON 형식으로만 답하세요:
{"hallucinated": true/false, "reason": "판단 근거 한 문장"}
"""


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*", text or "")}


def _context(drafted: dict) -> str:
    """draft_one이 모델에게 실제로 준 것과 같은 범위(제목+회사+재료)로 맞춘다.

    _material만 대조하면 회사명·제목처럼 별도로 준 정보를 "재료에 없는
    지어낸 내용"으로 오판한다 (jobkorea 본문은 회사명을 안 담고 있어서
    실제로 이 문제가 났다).
    """
    return (
        f"제목: {drafted.get('title')}\n"
        f"회사: {drafted.get('company')}\n"
        f"{drafted.get('_material', '')}"
    )


def rule_check(drafted: dict) -> dict:
    """요약 속 숫자가 재료 원문에 실제로 있는지만 문자열로 대조한다.

    비용이 안 들지만 표기 차이(예: "3500만원" vs "3,500만원")에는 강하고,
    표현을 바꿔 쓴 오탈자성 왜곡은 못 잡는다. 그래서 여기서 걸린 것만
    LLM으로 한 번 더 확인한다.
    """
    material_numbers = _numbers(_context(drafted))
    summary_numbers = _numbers(drafted.get("summary", ""))
    missing = sorted(summary_numbers - material_numbers)
    return {"passed": not missing, "missing_numbers": missing}


def llm_check(drafted: dict) -> dict:
    client = OpenAI()
    user_prompt = (
        f"[재료]\n{_context(drafted)}\n\n"
        f"[요약]\n{drafted.get('summary', '')}\n\n"
        f"[인사이트]\n{drafted.get('insight', '')}"
    )
    resp = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return json.loads(resp.choices[0].message.content)


def verify_one(drafted: dict) -> dict:
    """규칙 체크 먼저 돌리고, 걸린 것만 LLM으로 재확인한다."""
    rc = rule_check(drafted)
    if rc["passed"]:
        return {"verdict": "pass", "method": "rule", "detail": rc}

    lc = llm_check(drafted)
    verdict = "fail" if lc.get("hallucinated") else "pass"
    return {"verdict": verdict, "method": "rule->llm", "detail": {**rc, **lc}}

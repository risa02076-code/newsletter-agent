import json
import os

import yaml
from dotenv import load_dotenv
from openai import OpenAI

import alio
import jobkorea

load_dotenv()

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

with open("audience.yaml", encoding="utf-8") as f:
    AUDIENCE = yaml.safe_load(f)

SYSTEM_PROMPT = f"""당신은 인사(HR) 뉴스레터의 취재·요약 담당자입니다.
독자: {AUDIENCE['audience']['persona']}
목적: {AUDIENCE['audience']['goal']}

아래 [재료]에 없는 내용은 절대로 지어내지 마세요. 재료가 부족하면
summary는 있는 사실만으로 짧게 쓰고, insight에는 "재료 부족으로 추가
분석 불가"라고 명시하세요. 반드시 이 JSON 형식으로만 답하세요:
{{"summary": "3~4문장, 사실 기반 요약", "insight": "1~2문장, {AUDIENCE['insight_angle'].strip()}"}}
"""


def _gather_material(posting: dict) -> str:
    """소스별로 실제 존재하는 재료만 모은다. 없으면 없다고 명시한다."""
    source = posting.get("source")

    if source == "jobkorea":
        try:
            return jobkorea.fetch_body(posting["id"])
        except Exception as exc:
            return f"(잡코리아 본문 조회 실패: {exc})"

    if source == "alio":
        try:
            return alio.fetch_body(posting["id"])
        except Exception as exc:
            return f"(ALIO 본문 조회 실패: {exc})"

    if source == "worknet":
        # 워크넷 공채속보는 회사별 채용 홈페이지로 링크만 주고, 그 홈페이지는
        # 회사마다 구조가 제각각이라 안정적으로 스크래핑할 대상이 아니다.
        # 그래서 API가 실제로 돌려준 구조화된 필드만 재료로 쓴다 (지어내지
        # 않기 위해 여기서 정직하게 범위를 좁힌다).
        fields = {
            "회사명": posting.get("company"),
            "채용제목": posting.get("title"),
            "기업구분": posting.get("company_tier"),
            "고용형태": posting.get("employment_type"),
            "채용시작일": posting.get("start_date"),
            "채용종료일": posting.get("end_date"),
        }
        return "\n".join(f"{k}: {v}" for k, v in fields.items() if v)

    return ""


def draft_one(posting: dict) -> dict:
    client = OpenAI()
    material = _gather_material(posting)

    user_prompt = f"[공고 제목] {posting.get('title')}\n[회사] {posting.get('company')}\n\n[재료]\n{material}"

    resp = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    parsed = json.loads(resp.choices[0].message.content)

    return {
        **posting,
        "summary": parsed.get("summary", ""),
        "insight": parsed.get("insight", ""),
        "material_length": len(material),
    }


def draft_all(postings: list[dict]) -> list[dict]:
    return [draft_one(p) for p in postings]

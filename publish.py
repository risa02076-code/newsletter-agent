import os

import requests
from dotenv import load_dotenv

load_dotenv()

TIER_COLORS = {
    "대기업": 0x3498DB,
    "공기업": 0x2ECC71,
    "공공기관": 0x1ABC9C,
    "중견기업": 0xF1C40F,
    "중소기업": 0x95A5A6,
}


def _build_embed(item: dict) -> dict:
    tier = item.get("tier_label", "")
    embed = {
        "title": f"[{item.get('source')}] {item.get('company')} · {item.get('title')}"[:256],
        "color": TIER_COLORS.get(tier, 0x7289DA),
        "fields": [
            {"name": "요약", "value": (item.get("summary") or "-")[:1024]},
            {"name": "인사이트", "value": (item.get("insight") or "-")[:1024]},
            {"name": "기업규모", "value": tier or "-", "inline": True},
            {
                "name": "마감/기간",
                "value": item.get("deadline") or item.get("end_date") or "-",
                "inline": True,
            },
        ],
    }
    if item.get("url"):
        embed["url"] = item["url"]
    return embed


def publish_to_discord(items: list[dict]) -> int:
    """검수 통과한 항목만 디스코드 웹훅으로 발행한다. 0건이어도 그 사실을 보낸다."""
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]

    if not items:
        payload = {"content": "오늘은 검수를 통과한 인사·HR 신입 채용 소식이 없습니다."}
        resp = requests.post(webhook_url, json=payload, timeout=15)
        resp.raise_for_status()
        return 0

    payload = {
        "content": f"📋 오늘의 인사(HR) 신입 채용 소식 {len(items)}건",
        "embeds": [_build_embed(item) for item in items[:10]],
    }
    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()
    return len(items)

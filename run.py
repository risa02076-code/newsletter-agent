import json
import os
import time
from collections import Counter
from datetime import datetime

from graph import INITIAL_STATE, build

METRICS_PATH = "store/metrics.jsonl"


def record_metrics(result: dict, elapsed_seconds: float) -> dict:
    """실행마다 한 줄 남긴다: 추출 성공률(verify 통과율), 소스별 기여 건수, 소요 시간.

    분석 도구 없이 파일에 append만 하면 되는 수준으로 충분하다는 게
    이 프로젝트가 따르는 원칙이다.
    """
    drafted_total = len(result["drafted"])
    verified_total = len(result["verified"])

    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed_seconds, 1),
        "collected_total": len(result["collected"]),
        "collected_by_source": dict(Counter(p.get("source") for p in result["collected"])),
        "picked_total": len(result["picked"]),
        "picked_by_source": dict(Counter(p.get("source") for p in result["picked"])),
        "drafted_total": drafted_total,
        "verified_total": verified_total,
        "verify_pass_rate": round(verified_total / drafted_total, 2) if drafted_total else None,
        "published_total": verified_total,
    }

    os.makedirs(os.path.dirname(METRICS_PATH), exist_ok=True)
    with open(METRICS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def main():
    start = time.time()
    app = build()
    result = app.invoke(INITIAL_STATE)
    elapsed = time.time() - start

    for line in result["log"]:
        print(line)

    metrics = record_metrics(result, elapsed)
    print(f"[metrics] {METRICS_PATH} 에 기록: {metrics}")


if __name__ == "__main__":
    main()

from langgraph.graph import END, START, StateGraph

import alio
import draft as draft_module
import jobkorea
import verify as verify_module
import worknet
from state import State

DRAFT_ONLY_KEYS = {"summary", "insight", "material_length", "_material"}

NODE_NAMES = ["collect", "select", "draft", "verify", "publish"]

# 선별 목표 건수 (과제 요건: 3~5건)
TARGET_COUNT = 5


def collect(state: State) -> dict:
    collected = []
    log_lines = []

    for source_name, fetch in [
        ("jobkorea", lambda: jobkorea.fetch_hr_postings(pages=1)),
        ("worknet", lambda: worknet.fetch_hr_postings(pages=1)),
        ("alio", lambda: alio.fetch_hr_postings(pages=1)),
    ]:
        try:
            postings = fetch()
        except Exception as exc:  # 한 소스가 죽어도 나머지는 계속 돈다
            log_lines.append(f"[collect] {source_name} 실패: {exc}")
            continue
        for p in postings:
            p["source"] = source_name
        collected.extend(postings)
        log_lines.append(f"[collect] {source_name} {len(postings)}건 수집")

    log_lines.append(f"[collect] 총 {len(collected)}건 (3개 소스 합산)")
    return {"collected": collected, "log": log_lines}


def select(state: State) -> dict:
    """신입 + 기업규모(대기업>공기업·공공기관>중견기업>중소기업) 우선순위로 5건을 채운다.

    전부 각 소스의 검색 파라미터(career/cotype/coClcd/NCS 카테고리)로
    결정되는 사실 확인이라 LLM 판단이 필요 없다. picked 각 항목에
    source·tier_label·select_reason을 라벨로 남겨, 의도대로 걸러졌는지
    나중에 로그만 보고 확인할 수 있게 한다.
    """
    picked = []
    log_lines = []
    seen = set()

    def add(items, source, tier_label, reason):
        added = 0
        for p in items:
            if len(picked) >= TARGET_COUNT:
                break
            key = (source, p.get("id"))
            if key in seen:
                continue
            seen.add(key)
            p = dict(p)
            p["source"] = source
            p["tier_label"] = tier_label
            p["select_reason"] = reason
            picked.append(p)
            added += 1
        log_lines.append(f"[select] {source}/{tier_label}: {added}건 추가 ({reason})")

    # 우선순위 1: 대기업
    if len(picked) < TARGET_COUNT:
        add(
            jobkorea.fetch_entry_level_by_tier("1", count=10),
            "jobkorea", "대기업", "career=1(신입)+cotype=1(대기업)",
        )
    if len(picked) < TARGET_COUNT:
        add(
            worknet.fetch_entry_level_by_tier("10", count=10),
            "worknet", "대기업", "empWantedCareerCd=30(신입)+coClcd=10(대기업)",
        )

    # 우선순위 2: 공기업·공공기관
    if len(picked) < TARGET_COUNT:
        add(
            worknet.fetch_entry_level_by_tier("20", count=10),
            "worknet", "공기업", "empWantedCareerCd=30(신입)+coClcd=20(공기업)",
        )
    if len(picked) < TARGET_COUNT:
        add(
            worknet.fetch_entry_level_by_tier("30", count=10),
            "worknet", "공공기관", "empWantedCareerCd=30(신입)+coClcd=30(공공기관)",
        )
    if len(picked) < TARGET_COUNT:
        add(
            alio.fetch_hr_postings(pages=1),
            "alio", "공공기관", "NCS=경영·회계·사무+career=R2010(신입)",
        )

    # 우선순위 3: 중견기업
    if len(picked) < TARGET_COUNT:
        add(
            jobkorea.fetch_entry_level_by_tier("4", count=10),
            "jobkorea", "중견기업", "career=1(신입)+cotype=4(중견기업)",
        )
    if len(picked) < TARGET_COUNT:
        add(
            worknet.fetch_entry_level_by_tier("40", count=10),
            "worknet", "중견기업", "empWantedCareerCd=30(신입)+coClcd=40(중견기업)",
        )

    # 우선순위 4: 중소기업 (최후 보루)
    if len(picked) < TARGET_COUNT:
        add(
            jobkorea.fetch_entry_level_by_tier("15", count=10),
            "jobkorea", "중소기업", "career=1(신입)+cotype=15(중소기업)",
        )

    picked = picked[:TARGET_COUNT]
    log_lines.append(f"[select] {len(state['collected'])}건 중 {len(picked)}건 선택 (신입+기업규모 우선순위)")
    return {"picked": picked, "log": log_lines}


def draft(state: State) -> dict:
    drafted = []
    log_lines = []
    for p in state["picked"]:
        try:
            d = draft_module.draft_one(p)
        except Exception as exc:
            log_lines.append(f"[draft] {p.get('company')} 실패: {exc}")
            continue
        drafted.append(d)
        log_lines.append(f"[draft] {d['company']} 요약 완료 (재료 {d['material_length']}자)")
    log_lines.append(f"[draft] {len(state['picked'])}건 중 {len(drafted)}건 요약")
    return {"drafted": drafted, "log": log_lines}


def verify(state: State) -> dict:
    """규칙 체크(무료) 먼저, 걸린 것만 LLM으로 재확인. 그래도 실패하면
    원본 재료로 한 번 재생성해보고, 그마저 실패하면 스킵한다."""
    verified = []
    log_lines = []

    for d in state["drafted"]:
        result = verify_module.verify_one(d)

        if result["verdict"] == "pass":
            verified.append(d)
            log_lines.append(f"[verify] {d['company']} 통과 ({result['method']})")
            continue

        log_lines.append(f"[verify] {d['company']} 1차 탈락 ({result['method']}, {result['detail']}) → 재생성 시도")

        original_posting = {k: v for k, v in d.items() if k not in DRAFT_ONLY_KEYS}
        try:
            regenerated = draft_module.draft_one(original_posting)
            retry = verify_module.verify_one(regenerated)
        except Exception as exc:
            log_lines.append(f"[verify] {d['company']} 재생성 실패: {exc} → 스킵")
            continue

        if retry["verdict"] == "pass":
            verified.append(regenerated)
            log_lines.append(f"[verify] {d['company']} 재생성 후 통과")
        else:
            log_lines.append(f"[verify] {d['company']} 재생성 후에도 탈락 ({retry['detail']}) → 스킵")

    log_lines.append(f"[verify] {len(state['drafted'])}건 중 {len(verified)}건 통과")
    return {"verified": verified, "log": log_lines}


def publish(state: State) -> dict:
    return {"log": [f"[publish] {len(state['verified'])}건 발행 (스텁)"]}


def build():
    graph = StateGraph(State)
    for name in NODE_NAMES:
        graph.add_node(name, globals()[name])
    graph.add_edge(START, NODE_NAMES[0])
    for a, b in zip(NODE_NAMES, NODE_NAMES[1:]):
        graph.add_edge(a, b)
    graph.add_edge(NODE_NAMES[-1], END)
    return graph.compile()


if __name__ == "__main__":
    app = build()
    result = app.invoke(
        {"hours": 24, "collected": [], "picked": [], "drafted": [], "verified": [], "log": []}
    )
    for line in result["log"]:
        print(line)

import time

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

LIST_URL = "https://www.jobkorea.co.kr/recruit/joblist"
DETAIL_URL = "https://www.jobkorea.co.kr/Recruit/GI_Read/{job_id}"

# 잡코리아 직무 카테고리 "인사·HR"(groupCode 10028) 산하 세부 직무 코드
HR_DUTY_CODES = ["1000201", "1000202", "1000203", "1000204", "1000205", "1000206"]

ITEM_SELECTOR = "li.itemBg, li.itemBgTop, li.itemBgTopHeadline"

# G1(본문) 관문 기준선. 실측 결과 정상 응답이면 대부분 넘지만,
# 항목이 부실한 공고(우대조건·복리후생 미기재 등)는 이 밑으로 떨어진다.
BODY_LENGTH_BASELINE = 600

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})


def fetch_hr_postings(hours: int = 24, pages: int = 2) -> list[dict]:
    """잡코리아에서 인사·HR 직무 공고를 등록일순으로 가져온다.

    목록 페이지는 마감일만 보여주고 정확한 등록 시각은 주지 않는다. 그래서
    hours로 정밀하게 자르는 대신, 등록일순 정렬 결과 앞부분(pages 페이지)만
    가져온다. "오늘 새로 올라온 것"만 남기는 판단은 이후 선별 단계에서
    이전 실행 결과와 비교해 처리한다.
    """
    postings = []
    seen_ids = set()

    for page in range(1, pages + 1):
        params = {
            "menucode": "duty",
            "dutyCtgr": "10028",
            "duty": ",".join(HR_DUTY_CODES),
            "order": "2",  # 등록일순
            "Page": page,
        }
        resp = _session.get(LIST_URL, params=params, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        time.sleep(1.2)  # 목록 페이지를 연달아 두드리지 않도록 예의상 텀을 둔다

        for item in soup.select(ITEM_SELECTOR):
            job_id = item.get("data-info", "").split("|")[0]
            if not job_id or job_id in seen_ids:
                continue

            company_el = item.select_one("div.company span.name")
            link_el = item.select_one("div.description a")
            deadline_el = item.select_one("span.deadLine")
            if not (company_el and link_el):
                continue

            title = link_el.get_text(strip=True)
            if deadline_el:
                title = title.replace(deadline_el.get_text(strip=True), "").strip()

            seen_ids.add(job_id)
            postings.append(
                {
                    "id": job_id,
                    "title": title,
                    "company": company_el.get_text(strip=True),
                    "url": "https://www.jobkorea.co.kr" + link_el["href"].split("?")[0],
                    "deadline": deadline_el.get_text(strip=True) if deadline_el else None,
                }
            )

    return postings


def fetch_body(job_id: str, retries: int = 2) -> str:
    """공고 상세 페이지에서 모집요강 구간 텍스트를 뽑는다 (요약 단계의 재료).

    실측해보니 연속 요청 시 응답이 간헐적으로 잘리거나 타임아웃되는 경우가
    있어(G3), 재시도를 둔다. 그래도 일부 공고는 원래 항목이 짧아 기준선
    아래로 나올 수 있다(G1) — 그건 이 함수의 책임이 아니라 호출한 쪽에서
    본문 길이를 보고 판단할 문제다.
    """
    url = DETAIL_URL.format(job_id=job_id)
    last_error = None

    for attempt in range(retries):
        try:
            resp = _session.get(url, timeout=10)
            resp.raise_for_status()
            break
        except requests.exceptions.RequestException as exc:
            last_error = exc
            time.sleep(1.5)
    else:
        raise last_error

    text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
    start = text.find("모집요강")
    if start == -1:
        return text
    end = text.find("찾아오시는", start)
    return text[start:end] if end != -1 else text[start:]

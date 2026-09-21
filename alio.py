from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

BASE_URL = "https://job.alio.go.kr"
SEARCH_URL = f"{BASE_URL}/recruit.do"

# 표준직무(NCS) 대분류 중 "경영·회계·사무" — 인사가 속한 가장 가까운 대분류.
# 잡코리아 job_mid_code, 워크넷 jobsCd와 같은 역할: 넓게 받아오고 정밀 필터는
# select 노드에서 제목 텍스트로 한 번 더 좁힌다.
NCS_CATEGORY_ADMIN = "R600002"

# 채용구분(career): R2010=신입, R2020=경력, R2030=신입+경력, R2040=외국인 전형
CAREER_ENTRY_LEVEL = "R2010"


def fetch_hr_postings(pages: int = 1, page_size: int = 50, days: int = 60) -> list[dict]:
    """ALIO(공공기관 채용정보시스템)에서 경영·회계·사무 직군 공고를 가져온다.

    공공기관만 다루는 소스라 잡코리아/워크넷과 겹치지 않는 영역(공기업·
    준정부기관·기타공공기관)을 보완한다. 검색 폼이 POST만 받고, 날짜
    범위를 넣지 않으면 결과가 비어서 최근 `days`일 범위를 직접 채운다.
    """
    today = datetime.now()
    start = today - timedelta(days=days)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.get(SEARCH_URL, timeout=15)  # 세션 쿠키 확보

    postings = []
    seen_ids = set()

    for page in range(1, pages + 1):
        data = {
            "pageNo": str(page),
            "s_date": start.strftime("%Y.%m.%d"),
            "e_date": today.strftime("%Y.%m.%d"),
            "detail_code": NCS_CATEGORY_ADMIN,
            "career": CAREER_ENTRY_LEVEL,
            "pageSet": str(page_size),
        }
        resp = session.post(SEARCH_URL, data=data, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        table = next(
            (t for t in soup.find_all("table") if t.find("caption") and t.find("caption").get_text(strip=True) == "채용정보"),
            None,
        )
        if table is None or table.find("tbody") is None:
            break

        rows = table.find("tbody").find_all("tr")
        if not rows or rows[0].find("td").get("colspan"):
            break  # "등록된 채용정보가 없습니다" 행

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 9:
                continue

            # 제목 칸은 <a href=.../> 가 비어 있고 실제 글자는 그 옆의
            # 텍스트 노드로 붙어있는 구조라, 링크는 <a>에서, 제목은 칸
            # 전체 텍스트에서 따로 가져와야 한다.
            title_link = cells[2].find("a")
            job_id = cells[1].get_text(strip=True)
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            postings.append(
                {
                    "id": job_id,
                    "title": cells[2].get_text(strip=True),
                    "company": cells[3].get_text(strip=True),
                    "location": cells[4].get_text(" ", strip=True),
                    "employment_type": cells[5].get_text(" ", strip=True),
                    "reg_date": cells[6].get_text(strip=True),
                    "deadline": cells[7].get_text(strip=True),
                    "status": cells[8].get_text(strip=True),
                    "url": BASE_URL + title_link["href"] if title_link else None,
                }
            )

    return postings


def fetch_body(job_id: str) -> str:
    """상세페이지에서 표준직무·학력·근무조건 등 요강 구간 텍스트를 뽑는다."""
    resp = requests.get(
        f"{BASE_URL}/recruitview.do",
        params={"idx": job_id},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)

    start = text.find("표준직무")
    if start == -1:
        return text
    end = text.find("에서 진행중인", start)
    return text[start:end] if end != -1 else text[start:]

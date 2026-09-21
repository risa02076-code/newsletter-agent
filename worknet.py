import os
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L21.do"

# work24 직종코드표(cdGbn=jobs)에서 확인한 인사·노무 관련 직종코드
HR_JOB_CODES = ["012202", "022201", "026300", "026301", "026302"]

# 기업구분코드(coClcd): 10=대기업, 20=공기업, 30=공공기관, 40=중견기업, 50=외국계기업
COMPANY_TIER_CODES = {"대기업": "10", "공기업": "20", "공공기관": "30", "중견기업": "40"}

# 경력구분코드(empWantedCareerCd): 10=경력무관, 20=경력, 30=신입, 40=인턴
CAREER_ENTRY_LEVEL = "30"


def fetch_hr_postings(pages: int = 1, display: int = 100) -> list[dict]:
    """work24(고용24) 공채속보 API에서 인사·노무 직종 공개채용 소식을 가져온다.

    개인회원 승인 범위(채용행사·공채속보·공채기업정보)에 맞춰 공채속보
    API를 쓴다. 신입/기업규모 좁히기는 select 노드에서 이 함수가 반환한
    결과를 놓고 처리한다 (잡코리아 쪽과 동일한 역할 분담).
    """
    auth_key = os.environ["WORKNET_AUTH_KEY"]
    postings = []
    seen_ids = set()

    for page in range(1, pages + 1):
        params = {
            "authKey": auth_key,
            "callTp": "L",
            "returnType": "XML",
            "startPage": page,
            "display": display,
            "jobsCd": "|".join(HR_JOB_CODES),
        }
        resp = requests.get(BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        items = root.findall(".//dhsOpenEmpInfo")
        if not items:
            break

        for item in items:

            def text(tag):
                el = item.find(tag)
                return el.text.strip() if el is not None and el.text else None

            job_id = text("empSeqno")
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            postings.append(
                {
                    "id": job_id,
                    "title": text("empWantedTitle"),
                    "company": text("empBusiNm"),
                    "company_tier": text("coClcdNm"),
                    "start_date": text("empWantedStdt"),
                    "end_date": text("empWantedEndt"),
                    "employment_type": text("empWantedTypeNm"),
                    "url": text("empWantedHomepgDetail"),
                }
            )

    return postings

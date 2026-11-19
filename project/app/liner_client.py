"""Liner Platform 연동 (실연동 검증 완료 — 2026-11-19).

공식 문서(liner.com/llms.txt, developers/docs) 기준 스펙:
- Base URL: https://platform.liner.com/api/v1
- 시대 조사는 AI Search API (POST /agents/search)를 쓴다. 근거 있는
  답변(answer)과 실제 검색 출처(references)를 함께 돌려주므로, 출처는
  모델이 지어낸 문자열이 아니라 검색 결과의 URL을 그대로 쓴다.
  인증은 x-api-key 헤더, stream=false로 단건 JSON 응답을 받는다.
  (문서상 응답 시간 중앙값 약 30초, p99 약 100초 — 타임아웃은 넉넉히.)
- 일반 채팅은 Router API (POST /chat/completions, 모델 liner-gpt-router,
  Authorization: Bearer) — Router는 웹 검색을 하지 않으므로 시대 조사에는
  쓰지 않는다.

키가 없거나 호출이 실패하면 None을 돌려주고, 호출자는 mock으로 폴백하므로
키가 있어도 전체 흐름이 깨지지 않는다. 키는 코드에 직접 적지 않는다
(.env.example 참고).
"""
from __future__ import annotations

import os
import re

import httpx

from .models import CURRENT_YEAR

DEFAULT_BASE = "https://platform.liner.com/api/v1"
SEARCH_TIMEOUT = 240.0  # Search Agent 상한(300초) 아래에서 넉넉히
CHAT_TIMEOUT = 60.0
MAX_SOURCES = 5


def _base() -> str:
    return (os.environ.get("LINER_API_BASE") or DEFAULT_BASE).rstrip("/")


def liner_configured() -> bool:
    return bool(os.environ.get("LINER_API_KEY"))


def _post_json(url: str, headers: dict, payload: dict, timeout: float) -> dict | None:
    """POST JSON 단건 호출. 실패하면 None.

    실행 환경 호환: 일부 환경의 no_proxy 표기(대괄호 IPv6)를 httpx가
    파싱하지 못해 InvalidURL로 즉시 실패하는 경우가 있다. 그때만
    trust_env를 끄고 표준 프록시 환경 변수를 명시해 재시도한다.
    """
    try:
        r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.InvalidURL:
        proxy = (
            os.environ.get("https_proxy")
            or os.environ.get("HTTPS_PROXY")
            or os.environ.get("http_proxy")
            or os.environ.get("HTTP_PROXY")
        )
        try:
            with httpx.Client(trust_env=False, proxy=proxy, timeout=timeout) as c:
                r = c.post(url, headers=headers, json=payload)
                r.raise_for_status()
                return r.json()
        except Exception:
            return None
    except Exception:
        return None


def chat_with_liner(prompt: str) -> str | None:
    """Router API 채팅 호출 (웹 검색 없음). 실패하면 None."""
    key = os.environ.get("LINER_API_KEY")
    if not key:
        return None
    model = os.environ.get("LINER_MODEL") or "liner-gpt-router"
    data = _post_json(
        f"{_base()}/chat/completions",
        {"Authorization": f"Bearer {key}"},
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        },
        CHAT_TIMEOUT,
    )
    if not data:
        return None
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        return None


def search_with_liner(query: str) -> tuple[str, list[str]] | None:
    """AI Search API 단건 호출. 성공하면 (답변 텍스트, 출처 URL 목록).

    출처는 references의 실제 URL만 쓴다. 답변이 없거나 출처가 비어 있으면
    근거 없는 결과라 실패(None)로 취급한다.
    """
    key = os.environ.get("LINER_API_KEY")
    if not key:
        return None
    data = _post_json(
        f"{_base()}/agents/search",
        {"x-api-key": key, "Content-Type": "application/json"},
        {
            "messages": [{"role": "user", "content": query}],
            "lang": "ko",
            "stream": False,
        },
        SEARCH_TIMEOUT,
    )
    if not data:
        return None
    answer = (data.get("answer") or "").strip()
    if not answer:
        return None
    urls: list[str] = []
    for ref in data.get("references") or []:
        if isinstance(ref, dict):
            url = (ref.get("url") or "").strip()
            if url and url not in urls:
                urls.append(url)
        if len(urls) >= MAX_SOURCES:
            break
    if not urls:
        return None
    return answer, urls


_SECTION_LABELS = ["요약", "사건", "생활", "문화", "대표 디테일"]


def _clean(text: str) -> str:
    """인용 마커(((18)), [12])와 마크다운 장식을 걷어낸 평문으로 정리."""
    text = re.sub(r"\(\(\d+\)\)", "", text)
    text = re.sub(r"\[\d+\]", "", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([.,])", r"\1", text)
    return text.strip()


def _parse_sections(answer: str) -> dict[str, str]:
    """'요약:' '사건:' … 라벨 문단으로 나뉜 답변을 항목별로 가른다.

    라벨을 하나도 찾지 못하면 빈 dict — 호출자가 답변 첫 문단으로 폴백한다.
    """
    label_alt = "|".join(re.escape(x) for x in _SECTION_LABELS)
    pattern = re.compile(
        rf"(?m)^[\s#>\-•*]*({label_alt})\s*[:：]\s*"
    )
    matches = list(pattern.finditer(answer))
    if not matches:
        return {}
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(answer)
        sections[m.group(1)] = _clean(answer[m.end():end])
    return sections


def research_year(year: int) -> dict | None:
    """한 연도의 한국(사건·생활·문화)을 Liner AI Search로 조사한다.

    성공하면 {"summary", "events", "life", "culture", "contrast",
    "sources"}를, 실패하면 None을 돌려준다. 출처는 검색 결과의 실제
    URL이며, 출처가 없으면 실패로 취급한다 (지어낸 시대를 통과시키지
    않기 위해서다). 미래 연도는 전망 자료 기반의 전망 문장으로만 답하게
    한다.
    """
    if year > CURRENT_YEAR:
        stance = (
            f"{year}년은 아직 오지 않은 해다. 통계청 장래인구추계 등 전망 자료에 "
            "근거해, 모든 문장을 '~로 전망된다 / 예상된다'로만 써라. 확정된 사실인 "
            "것처럼 쓰지 마라."
        )
    else:
        stance = f"{year}년에 실제로 있었던 일만 근거와 함께 써라."
    query = (
        f"{year}년 한국의 사회상을 조사해서 아래 다섯 항목으로 나눠 답해라. "
        "각 항목은 반드시 '요약:' '사건:' '생활:' '문화:' '대표 디테일:' "
        "라벨로 시작하는 문단으로 쓰고, 순서를 지켜라.\n"
        "- 요약: 그 해를 요약한 2-3문장\n"
        "- 사건: 그 해의 주요 사건\n"
        "- 생활: 물가·급여·교통 같은 검증 가능한 생활 디테일 (구체 수치 포함)\n"
        "- 문화: 유행가·영화 등 문화 디테일\n"
        "- 대표 디테일: 그 해를 대표하는 구체적인 사실 한 줄\n"
        "감정 형용사와 상투적 감성 문구는 쓰지 마라. 검증 가능한 사실과 "
        "구체 수치·사물로만 채워라. 근거를 찾지 못한 항목은 라벨만 쓰고 "
        "비워 둬라.\n"
        f"{stance}"
    )
    found = search_with_liner(query)
    if not found:
        return None
    answer, sources = found
    sections = _parse_sections(answer)
    summary = sections.get("요약") or _clean(answer.split("\n\n")[0])
    if not summary:
        return None
    contrast = sections.get("대표 디테일", "")
    if contrast:
        contrast = contrast.split(". ")[0].rstrip(".") + "."
    return {
        "summary": summary,
        "events": sections.get("사건", ""),
        "life": sections.get("생활", ""),
        "culture": sections.get("문화", ""),
        "contrast": contrast,
        "sources": sources,
    }

"""시대 조사 — Liner 우선, 실패하면 mock 시대 자료로 폴백.

정직성 규칙:
- 연표의 종류는 연도만으로 정한다. 현재보다 뒤의 연도는 무조건
  "전망"이고, 지난 연도는 "사실"이다 (kind_for_year). 조사 결과가
  뭐라고 하든 미래를 사실로 쓰지 않는다.
- 출처 없는 내용은 셀에 채우지 않는다 (apply_evidence_rule).
  조사되지 않은 연도는 빈 셀이 된다 — 시대를 지어내지 않는다.
"""
from __future__ import annotations

from .era_fixtures import find_era
from .liner_client import liner_configured, research_year
from .models import CURRENT_YEAR, KIND_FACT, KIND_OUTLOOK, EraContent


def kind_for_year(year: int) -> str:
    """아직 오지 않은 연도는 전망, 지난 연도는 사실 (강제 규칙)."""
    return KIND_OUTLOOK if year > CURRENT_YEAR else KIND_FACT


def apply_evidence_rule(content: EraContent | None) -> EraContent | None:
    """출처 없는 시대 내용은 버린다 — 셀은 빈 셀이 된다."""
    if content is None:
        return None
    if not content.sources:
        return None
    return content


def research_era(year: int) -> tuple[EraContent | None, str]:
    """한 연도를 조사한다. 반환: (시대 내용 또는 None, 엔진 'liner'|'mock').

    Liner가 설정돼 있어도 호출이 실패하면 mock으로 폴백하고, 엔진 표기는
    그 연도가 실제로 Liner로 조사됐을 때만 'liner'.
    """
    if liner_configured():
        found = research_year(year)
        if found:
            return apply_evidence_rule(EraContent(**found)), "liner"
    fixture = find_era(year)
    if fixture is None:
        return None, "mock"
    return apply_evidence_rule(EraContent(**fixture)), "mock"

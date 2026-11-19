"""시대 초상 — 사진 1장에서 세 세대의 얼굴을 연표에 정렬한다.

규칙 (사용자 확정):
- 입력 사진은 가운데 세대인 "나"의 사진 1장이 기본이다.
- 세대별 실물 사진이 있으면 그 사진이 해당 세대 초상의 기준이다.
  없는 세대만 본인 사진에서 파생한다. 우선순위는 세대별 독립 적용 —
  예: 아버지 사진만 있으면 아버지는 실물 기준, 아들은 본인 사진 파생.
- 파생 방향: 본인보다 위 세대는 연령 증가(+그 세대 시대), 아래 세대는
  연령 감소(+그 세대 시대).
- 초상은 연표의 행(나이)에 맞춰 그 나이의 얼굴로 만든다.
- 모든 초상에 기준(실물/파생)을 표시하고, 항상 "AI 합성" 라벨을 붙인다.
  진짜 옛 사진인 척하지 않는다.
- 입력된 세대에 대해서만 만든다. 없는 세대를 임의로 추가하지 않는다.

이 모듈은 생성 프롬프트와 연동 인터페이스까지만 제공한다. 실제 이미지
생성 API 호출은 generate_portrait의 연동 지점에서 이뤄지며, 현재는
플레이스홀더를 돌려준다 (테스트에서도 실제 생성을 호출하지 않는다).
"""
from __future__ import annotations

from .models import (
    BASIS_DERIVED,
    BASIS_REAL,
    PORTRAIT_LABEL,
    GenerationInput,
    PortraitPrompt,
)

# 시대 구간별 사진 질감·복장·배경 지시 (상한 연도, 스타일, 복장, 배경, 질감)
ERA_STYLES: list[tuple[int, str, str, str, str]] = [
    (1969, "흑백 스튜디오", "그 시대의 단정한 일상복", "사진관 배경막 앞", "흑백 질감, 필름 그레인과 약간의 바램"),
    (1989, "초기 컬러 필름", "1970-80년대 일상복", "동네 사진관 또는 집 앞 골목", "옅은 세피아 톤이 도는 초기 컬러 필름 질감"),
    (2009, "컬러 필름", "1990-2000년대 일상복", "학교·동네 거리 배경", "컬러 필름 질감, 구석에 날짜 스탬프가 찍힌 분위기"),
    (2026, "스마트폰 사진", "현재의 일상복", "현재의 도시 배경", "선명한 스마트폰 사진 질감"),
    (9999, "미래 스타일", "가까운 미래의 일상복으로 상상한 차림", "미래 도시 배경", "선명하고 깨끗한 미래형 렌더 질감"),
]


def style_for_year(year: int) -> tuple[str, str, str, str]:
    """연도 -> (스타일, 복장, 배경, 질감)."""
    for limit, style, costume, background, texture in ERA_STYLES:
        if year <= limit:
            return style, costume, background, texture
    return ERA_STYLES[-1][1:]


def resolve_basis(
    gen: GenerationInput, self_gen: GenerationInput | None
) -> tuple[str, str] | None:
    """이 세대의 초상 기준을 정한다. 반환: (기준, 기준 설명) 또는 None.

    실물 사진이 있으면 실물, 없으면 본인 사진에서 파생, 본인 사진도
    없으면 초상을 만들지 않는다 (None).
    """
    if gen.photo:
        return BASIS_REAL, f"{gen.label} 실물 사진 기준"
    if self_gen is not None and self_gen.photo and not gen.is_self:
        if gen.birth_year < self_gen.birth_year:
            direction = "연령 증가"
        else:
            direction = "연령 감소"
        return BASIS_DERIVED, f"본인 사진에서 {direction} 파생"
    return None


def build_portrait(
    gen: GenerationInput,
    self_gen: GenerationInput | None,
    age: int,
    year: int,
) -> PortraitPrompt | None:
    """한 셀(세대 × 나이)의 시대 초상 프롬프트를 만든다. 기준이 없으면 None."""
    resolved = resolve_basis(gen, self_gen)
    if resolved is None:
        return None
    basis, basis_note = resolved
    style, costume, background, texture = style_for_year(year)
    prompt = (
        f"[{PORTRAIT_LABEL}] 기준: {basis_note}. {gen.label}의 {age}세 얼굴을 "
        f"{year}년의 시대로 합성한다. 복장: {costume}. 배경: {background}. "
        f"사진 질감: {texture}. 진짜 옛 사진처럼 속이지 말고 합성 이미지로 "
        f"자연스럽게 표현한다."
    )
    return PortraitPrompt(
        label=PORTRAIT_LABEL,
        basis=basis,
        basis_note=basis_note,
        target_age=age,
        era_year=year,
        style=style,
        costume=costume,
        background=background,
        texture=texture,
        prompt=prompt,
        status="placeholder",
    )


def generate_portrait(portrait: PortraitPrompt) -> dict:
    """초상 생성 연동 지점.

    실제 이미지 생성 API는 여기에 연결한다. 현재는 플레이스홀더를
    돌려주며, 어떤 경우에도 네트워크 호출을 하지 않는다.
    """
    return {
        "status": "placeholder",
        "image": None,
        "label": portrait.label,
        "basis": portrait.basis,
        "prompt": portrait.prompt,
        "note": "생성 연동 지점 — 실제 이미지 생성 API 연결 전이라 프롬프트까지만 제공한다",
    }

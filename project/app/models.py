"""입출력 스키마 — "같은 나이, 다른 시대" 3세대 연표 에이전트.

세 세대의 생년을 받아 연표의 축을 연도가 아니라 나이로 정렬한다.
나이마다 각 세대가 그 나이였던 연도를 계산하고, 그 연도의 한국
(사건·생활·문화)을 조사해 출처와 함께 셀에 채운다. 아직 오지 않은
연도는 "전망"으로 강제 라벨링한다.

초상 규칙 (사용자 확정):
- 입력 사진은 가운데 세대인 "나"의 사진 1장이 기본이다.
- 세대별 실물 사진이 있으면 그 사진이 해당 세대 초상의 기준이 되고,
  없는 세대만 본인 사진에서 파생한다 (우선순위는 세대별 독립 적용).
  아버지 = 본인을 나이 든 방향 + 아버지 시대, 아들 = 젊은 방향 + 아들 시대.
- 각 초상에는 기준(실물/파생)을 표시하고, 항상 "AI 합성" 라벨을 붙인다.
- 입력된 세대에 대해서만 초상을 만든다 (임의로 세대를 추가하지 않는다).
- 아들 생년이 입력되지 않으면 아버지와 나의 2세대만 생성한다.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

CURRENT_YEAR = date.today().year

# 셀 종류: 지난 연도는 사실, 아직 오지 않은 연도는 전망 (강제)
KIND_FACT = "사실"
KIND_OUTLOOK = "전망"
KINDS = [KIND_FACT, KIND_OUTLOOK]

# 나이 축 기본값. 개인 이벤트가 있는 나이는 자동으로 행이 추가된다.
DEFAULT_AGES = [0, 10, 20, 30, 40, 50, 60]
HIGHLIGHT_AGE = 20

# 초상 기준
BASIS_REAL = "실물"
BASIS_DERIVED = "파생"
BASES = [BASIS_REAL, BASIS_DERIVED]

# 초상에는 항상 이 라벨이 붙는다 (진짜 옛 사진인 척하지 않는다).
PORTRAIT_LABEL = "AI 합성"


class PersonalEventInput(BaseModel):
    year: int = Field(description="이벤트가 있었던 연도")
    text: str = Field(min_length=1, description="이벤트 한 줄 (예: 대학에 입학했다)")


class GenerationInput(BaseModel):
    label: str = Field(min_length=1, description="호칭 (예: 할아버지, 나, 아들)")
    birth_year: int = Field(description="생년")
    is_self: bool = Field(
        default=False,
        description="가운데 세대 '나' 여부. 파생 초상의 기준 사진은 이 세대의 사진이다",
    )
    photo: str | None = Field(
        default=None,
        description="이 세대의 실물 사진 참조. 본인 세대는 '나의 사진 1장'이 여기 들어간다",
    )
    events: list[PersonalEventInput] = Field(default_factory=list)

    @field_validator("birth_year")
    @classmethod
    def check_birth_year(cls, v: int) -> int:
        if not (1900 <= v <= CURRENT_YEAR):
            raise ValueError(f"생년이 범위를 벗어났다: {v} (1900-{CURRENT_YEAR})")
        return v

    @model_validator(mode="after")
    def check_events(self) -> "GenerationInput":
        for e in self.events:
            age = e.year - self.birth_year
            if age < 0 or age > 100:
                raise ValueError(
                    f"이벤트 연도가 생년과 맞지 않는다: {e.year} (생년 {self.birth_year})"
                )
        return self


class ChronicleRequest(BaseModel):
    generations: list[GenerationInput] = Field(
        description="2-3세대. 아들 생년이 없으면 아버지와 나의 2세대만 넣는다"
    )
    ages: list[int] | None = Field(
        default=None,
        description="나이 축. 지정하지 않으면 기본 나이 + 이벤트가 있는 나이로 구성",
    )

    @model_validator(mode="after")
    def check_generations(self) -> "ChronicleRequest":
        gens = self.generations
        if not (2 <= len(gens) <= 3):
            raise ValueError("세대는 2-3개여야 한다 (아들이 없으면 2세대)")
        labels = [g.label for g in gens]
        if len(set(labels)) != len(labels):
            raise ValueError("세대 호칭이 중복된다")
        years = [g.birth_year for g in gens]
        if len(set(years)) != len(years):
            raise ValueError("생년이 중복된다")
        selves = [g for g in gens if g.is_self]
        if len(selves) > 1:
            raise ValueError("'나'(is_self)는 최대 한 세대만 지정할 수 있다")
        if self.ages is not None:
            if any(a < 0 or a > 100 for a in self.ages):
                raise ValueError("나이는 0-100 사이여야 한다")
        return self


class EraContent(BaseModel):
    summary: str = Field(description="그 연도의 한국을 요약한 2-3문장")
    events: str = Field(default="", description="주요 사건")
    life: str = Field(default="", description="물가·급여·교통 같은 검증 가능한 생활 디테일")
    culture: str = Field(default="", description="유행가·영화 등 문화 디테일")
    contrast: str = Field(
        default="",
        description="같은 나이 대조용 한 줄 — 그 해를 대표하는 구체 디테일 (감정 형용사 없이 사실만)",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="출처. 비어 있는 내용은 셀에 채우지 않는다 (출처 없는 셀 금지)",
    )


class PortraitPrompt(BaseModel):
    label: str = Field(
        default=PORTRAIT_LABEL, description="항상 'AI 합성' — 진짜 사진인 척하지 않는다"
    )
    basis: str = Field(description="실물 | 파생 — 이 초상의 기준 사진 출처")
    basis_note: str = Field(
        description="기준 설명 (예: '아버지 실물 사진 기준', '본인 사진에서 연령 증가 파생')"
    )
    target_age: int = Field(description="초상에 표현할 나이 (연표의 행)")
    era_year: int = Field(description="초상의 시대 연도")
    style: str = Field(description="시대별 사진 질감 (예: 흑백 스튜디오, 컬러 필름, 미래 스타일)")
    costume: str = Field(description="시대 복장 지시")
    background: str = Field(description="시대 배경 지시")
    texture: str = Field(description="질감 지시")
    prompt: str = Field(description="초상 생성 지시문 전체")
    status: str = Field(
        default="placeholder",
        description="생성 연동 상태. placeholder = 생성 모듈 연동 지점만 마련된 상태",
    )

    @field_validator("label")
    @classmethod
    def check_label(cls, v: str) -> str:
        if v != PORTRAIT_LABEL:
            raise ValueError("초상 라벨은 항상 'AI 합성'이어야 한다")
        return v

    @field_validator("basis")
    @classmethod
    def check_basis(cls, v: str) -> str:
        if v not in BASES:
            raise ValueError(f"알 수 없는 초상 기준: {v}")
        return v


class ChronicleCell(BaseModel):
    label: str = Field(description="세대 호칭")
    birth_year: int
    age: int = Field(description="연표의 행 (나이)")
    year: int = Field(description="이 세대가 이 나이였던 연도 = 생년 + 나이")
    kind: str = Field(description="사실 | 전망 (미래 연도는 전망으로 강제)")
    content: EraContent | None = Field(
        default=None,
        description="시대 조사 결과. 출처가 없거나 조사되지 않으면 None (빈 셀)",
    )
    personal_events: list[str] = Field(
        default_factory=list, description="이 나이에 배치된 개인 이벤트"
    )
    portrait: PortraitPrompt | None = Field(
        default=None, description="사진이 있을 때만 생성되는 시대 초상 프롬프트"
    )


class ChronicleRow(BaseModel):
    age: int
    cells: list[ChronicleCell] = Field(default_factory=list)


class GenerationSummary(BaseModel):
    label: str
    birth_year: int
    is_self: bool = False
    retrospective: str = Field(default="", description="세대별 짧은 회고문")


class CardLine(BaseModel):
    label: str = Field(description="세대 호칭")
    year: int
    kind: str = Field(description="사실 | 전망")
    text: str = Field(description="사실 대조 한 줄 (구체 디테일, 해석 문장 없이)")


class HighlightCard(BaseModel):
    """메신저로 보내기 좋은 하이라이트 카드 1장의 내용."""

    title: str = Field(default="같은 나이, 다른 시대")
    subtitle: str = Field(default="", description="예: 세 세대의 20살")
    lines: list[CardLine] = Field(
        default_factory=list, description="세대별 사실 대조 (세대당 한 줄)"
    )
    footer: str = Field(default="", description="카드 하단 표기 (전망 고지 등)")


class ChronicleResponse(BaseModel):
    generations: list[GenerationSummary] = Field(default_factory=list)
    rows: list[ChronicleRow] = Field(default_factory=list)
    highlight_age: int = Field(description="같은 나이 비교에 쓴 나이")
    highlight: str = Field(default="", description="같은 나이 하이라이트 (사실 대조 줄 모음)")
    highlight_card: HighlightCard = Field(
        default_factory=HighlightCard, description="메신저 공유용 카드 내용"
    )
    chronicle_markdown: str = Field(default="", description="연표 한 장 (마크다운)")
    share_id: str = Field(
        default="", description="공유 링크 식별자. GET /share/{share_id} 로 읽기 전용 조회"
    )
    engine: str = Field(description="liner | mock — 시대 조사에 사용한 엔진")

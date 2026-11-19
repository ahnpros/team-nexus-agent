"""연표 파이프라인 — 생년 -> 나이 축 정렬 -> 시대 조사 -> 연표·회고·하이라이트.

연표의 축은 연도가 아니라 나이다. 나이마다 각 세대가 그 나이였던
연도를 계산하고, 그 연도의 한국을 조사해 셀에 채운다. 미래 연도는
전망으로 강제하고, 출처 없는 연도는 빈 셀로 남긴다.
"""
from __future__ import annotations

from .era import kind_for_year, research_era
from .models import (
    DEFAULT_AGES,
    HIGHLIGHT_AGE,
    KIND_OUTLOOK,
    CardLine,
    ChronicleCell,
    ChronicleRequest,
    ChronicleResponse,
    ChronicleRow,
    EraContent,
    GenerationInput,
    GenerationSummary,
    HighlightCard,
)
from .portraits import build_portrait


def resolve_ages(req: ChronicleRequest) -> list[int]:
    """나이 축 = 지정 나이(없으면 기본 나이) + 개인 이벤트가 있는 나이."""
    ages = set(req.ages) if req.ages is not None else set(DEFAULT_AGES)
    for gen in req.generations:
        for e in gen.events:
            ages.add(e.year - gen.birth_year)
    return sorted(a for a in ages if 0 <= a <= 100)


def _first_sentence(text: str) -> str:
    head = text.split(". ")[0].rstrip(".")
    return head + "." if head else ""


def _events_at(gen: GenerationInput, age: int) -> list[str]:
    return [e.text for e in gen.events if e.year - gen.birth_year == age]


def build_retrospective(
    gen: GenerationInput, rows: list[ChronicleRow]
) -> str:
    """세대별 짧은 회고문 — 조사된 셀과 개인 기록만으로 짓는다."""
    sentences: list[str] = []
    for row in rows:
        cell = next((c for c in row.cells if c.label == gen.label), None)
        if cell is None:
            continue
        if cell.content is not None:
            if cell.kind == KIND_OUTLOOK:
                sentences.append(
                    f"{cell.age}살이 될 {cell.year}년, "
                    f"{_first_sentence(cell.content.summary)} (전망)"
                )
            else:
                sentences.append(
                    f"{cell.age}살이던 {cell.year}년, "
                    f"{_first_sentence(cell.content.summary)}"
                )
        for text in cell.personal_events:
            sentences.append(f"{cell.year}년의 개인 기록 — {text}.")
    if not sentences:
        return (
            f"{gen.label}({gen.birth_year}년생)은 조사된 시대 자료와 개인 기록이 "
            "없어 회고문을 만들 근거가 부족하다."
        )
    return " ".join(sentences)


def choose_highlight_age(
    ages: list[int], rows: list[ChronicleRow], gen_count: int
) -> int:
    """같은 나이 비교에 쓸 나이: 20살을 우선하고, 없으면 전 세대 자료가 있는 첫 나이."""
    if HIGHLIGHT_AGE in ages:
        return HIGHLIGHT_AGE
    for row in rows:
        if len(row.cells) == gen_count and all(
            c.content is not None for c in row.cells
        ):
            return row.age
    return ages[0]


def build_highlight_lines(age: int, row: ChronicleRow) -> list[CardLine]:
    """같은 나이 하이라이트 = 세대별 사실 대조 한 줄씩.

    감정 문장을 쓰지 않는다. 각 세대의 그 해를 대표하는 구체 디테일
    (contrast)을 나란히 놓는 병치 자체가 말하게 한다.
    """
    lines: list[CardLine] = []
    for cell in row.cells:
        if cell.content is not None and cell.content.contrast:
            text = cell.content.contrast
        elif cell.content is not None:
            text = _first_sentence(cell.content.life or cell.content.summary)
        else:
            text = "조사된 시대 자료가 없어 비워 둔 해"
        lines.append(
            CardLine(label=cell.label, year=cell.year, kind=cell.kind, text=text)
        )
    return lines


def format_highlight(age: int, lines: list[CardLine]) -> str:
    out = []
    for line in lines:
        suffix = " (전망)" if line.kind == KIND_OUTLOOK else ""
        out.append(f"{line.label}의 {age}살, {line.year}년 — {line.text}{suffix}")
    return "\n".join(out)


def build_highlight_card(
    age: int, lines: list[CardLine], gen_count: int
) -> HighlightCard:
    count_word = {2: "두", 3: "세"}.get(gen_count, str(gen_count))
    footer = "같은 나이, 다른 시대"
    if any(line.kind == KIND_OUTLOOK for line in lines):
        footer = "미래 연도는 전망 자료 기반의 전망입니다 · " + footer
    return HighlightCard(
        subtitle=f"{count_word} 세대의 {age}살",
        lines=lines,
        footer=footer,
    )


def _cell_markdown(cell: ChronicleCell) -> str:
    head = f"{cell.year}년"
    if cell.kind == KIND_OUTLOOK:
        head += " [전망]"
    if cell.content is None:
        body = "(빈 셀 — 조사된 자료 없음)"
    else:
        body = cell.content.summary
    text = f"**{head}** {body}"
    for e in cell.personal_events:
        text += f" · 개인 기록: {e}"
    if cell.portrait is not None:
        p = cell.portrait
        text += f" · 초상: {p.style} ({p.basis} 기준, {p.label})"
    if cell.content is not None and cell.content.sources:
        text += f" (출처: {', '.join(cell.content.sources)})"
    return text.replace("|", "/")


def build_markdown(resp: ChronicleResponse) -> str:
    gens = resp.generations
    title = "같은 나이, 다른 시대 — " + f"{len(gens)}세대 연표"
    lines = [f"# {title}", ""]
    gen_line = " · ".join(f"{g.label}({g.birth_year}년생)" for g in gens)
    lines.append(f"세대: {gen_line} / 시대 조사 엔진: {resp.engine}")
    lines.append("")
    header = "| 나이 | " + " | ".join(g.label for g in gens) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (len(gens) + 1))
    for row in resp.rows:
        cells = " | ".join(_cell_markdown(c) for c in row.cells)
        lines.append(f"| {row.age}살 | {cells} |")
    lines.append("")
    lines.append(f"## 같은 나이 하이라이트 — {resp.highlight_age}살")
    lines.append("")
    lines.append(resp.highlight)
    lines.append("")
    lines.append("## 세대별 회고")
    for g in gens:
        lines.append("")
        lines.append(f"**{g.label}({g.birth_year}년생)** — {g.retrospective}")
    lines.append("")
    lines.append(
        "> 미래 연도는 전망 자료 기반의 전망으로만 표기하고, 출처 없는 연도는 "
        "빈 셀로 남겼다. 시대 초상은 전부 AI 합성이며 기준(실물/파생)을 함께 표시한다."
    )
    return "\n".join(lines) + "\n"


def build_chronicle(req: ChronicleRequest) -> ChronicleResponse:
    gens = req.generations
    self_gen = next((g for g in gens if g.is_self), None)
    ages = resolve_ages(req)

    era_cache: dict[int, tuple[EraContent | None, str]] = {}
    engines: set[str] = set()

    def era_for(year: int) -> EraContent | None:
        if year not in era_cache:
            era_cache[year] = research_era(year)
        content, engine = era_cache[year]
        if content is not None:
            engines.add(engine)
        return content

    rows: list[ChronicleRow] = []
    for age in ages:
        cells: list[ChronicleCell] = []
        for gen in gens:
            year = gen.birth_year + age
            cells.append(
                ChronicleCell(
                    label=gen.label,
                    birth_year=gen.birth_year,
                    age=age,
                    year=year,
                    kind=kind_for_year(year),
                    content=era_for(year),
                    personal_events=_events_at(gen, age),
                    portrait=build_portrait(gen, self_gen, age, year),
                )
            )
        rows.append(ChronicleRow(age=age, cells=cells))

    highlight_age = choose_highlight_age(ages, rows, len(gens))
    highlight_row = next(r for r in rows if r.age == highlight_age)
    highlight_lines = build_highlight_lines(highlight_age, highlight_row)

    summaries = [
        GenerationSummary(
            label=g.label,
            birth_year=g.birth_year,
            is_self=g.is_self,
            retrospective=build_retrospective(g, rows),
        )
        for g in gens
    ]

    resp = ChronicleResponse(
        generations=summaries,
        rows=rows,
        highlight_age=highlight_age,
        highlight=format_highlight(highlight_age, highlight_lines),
        highlight_card=build_highlight_card(highlight_age, highlight_lines, len(gens)),
        engine="liner" if engines == {"liner"} else "mock",
    )
    resp.chronicle_markdown = build_markdown(resp)
    return resp

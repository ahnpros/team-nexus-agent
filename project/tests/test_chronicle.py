"""같은 나이, 다른 시대 테스트: 나이 정렬, 전망 강제, 출처 규칙,
개인 이벤트 배치, 초상 파생 규칙, 엔드포인트."""
import pytest
from fastapi.testclient import TestClient

from app.chronicle import build_chronicle
from app.era import apply_evidence_rule, kind_for_year
from app.main import app
from app.models import (
    ChronicleRequest,
    EraContent,
    GenerationInput,
    PersonalEventInput,
)
from app.portraits import build_portrait, generate_portrait


@pytest.fixture(autouse=True)
def no_liner_key(monkeypatch):
    """테스트는 mock 경로로 고정한다 (실호출 금지)."""
    monkeypatch.delenv("LINER_API_KEY", raising=False)


def demo_request(**overrides) -> ChronicleRequest:
    data = {
        "generations": [
            {
                "label": "할아버지",
                "birth_year": 1945,
                "events": [{"year": 1965, "text": "첫 직장에 들어갔다"}],
            },
            {
                "label": "나",
                "birth_year": 1972,
                "is_self": True,
                "photo": "self.jpg",
                "events": [{"year": 1992, "text": "대학에 입학했다"}],
            },
            {"label": "아들", "birth_year": 2012},
        ]
    }
    data.update(overrides)
    return ChronicleRequest(**data)


def cell_at(resp, age: int, label: str):
    row = next(r for r in resp.rows if r.age == age)
    return next(c for c in row.cells if c.label == label)


# ---------- 나이 축 정렬 ----------

def test_age_to_year_conversion():
    resp = build_chronicle(demo_request())
    for row in resp.rows:
        for cell in row.cells:
            assert cell.year == cell.birth_year + row.age
            assert cell.age == row.age
    ages = [r.age for r in resp.rows]
    assert ages == sorted(ages)


def test_event_age_becomes_a_row():
    req = demo_request()
    req.generations[1].events.append(PersonalEventInput(year=1996, text="첫 직장에 들어갔다"))
    resp = build_chronicle(req)
    assert 24 in [r.age for r in resp.rows]  # 1996 - 1972


# ---------- 전망 라벨 강제 ----------

def test_kind_for_year_forces_outlook_for_future():
    assert kind_for_year(2032) == "전망"
    assert kind_for_year(2052) == "전망"
    assert kind_for_year(1992) == "사실"
    assert kind_for_year(1965) == "사실"


def test_future_cells_are_outlook_with_outlook_phrasing():
    resp = build_chronicle(demo_request())
    son20 = cell_at(resp, 20, "아들")
    assert son20.year == 2032
    assert son20.kind == "전망"
    assert son20.content is not None
    assert "전망" in son20.content.summary
    son40 = cell_at(resp, 40, "아들")
    assert son40.year == 2052
    assert son40.kind == "전망"
    grandpa20 = cell_at(resp, 20, "할아버지")
    assert grandpa20.year == 1965
    assert grandpa20.kind == "사실"


# ---------- 출처 규칙 ----------

def test_content_without_sources_is_dropped():
    no_src = EraContent(summary="근거 없는 시대 설명", sources=[])
    assert apply_evidence_rule(no_src) is None
    with_src = EraContent(summary="근거 있는 설명", sources=["한국사데이터베이스"])
    assert apply_evidence_rule(with_src) is with_src


def test_every_filled_cell_has_sources():
    resp = build_chronicle(demo_request())
    for row in resp.rows:
        for cell in row.cells:
            if cell.content is not None:
                assert cell.content.sources, f"{cell.label} {cell.year}"


def test_unresearched_year_is_empty_cell():
    resp = build_chronicle(demo_request())
    cell = cell_at(resp, 10, "할아버지")  # 1955년은 mock 자료에 없다
    assert cell.year == 1955
    assert cell.content is None


# ---------- 개인 이벤트 배치 ----------

def test_personal_event_placed_on_matching_age_row():
    resp = build_chronicle(demo_request())
    mine = cell_at(resp, 20, "나")
    assert mine.personal_events == ["대학에 입학했다"]
    grandpa = cell_at(resp, 20, "할아버지")
    assert grandpa.personal_events == ["첫 직장에 들어갔다"]
    son = cell_at(resp, 20, "아들")
    assert son.personal_events == []
    # 다른 나이 행에는 새지 않는다
    assert cell_at(resp, 30, "나").personal_events == []


# ---------- 하이라이트 ----------

def test_highlight_compares_same_age_across_generations():
    resp = build_chronicle(demo_request())
    assert resp.highlight_age == 20
    for token in ("할아버지", "나", "아들", "1965", "1992", "2032"):
        assert token in resp.highlight
    assert "전망" in resp.highlight  # 아들의 2032년은 전망으로 표시


def test_highlight_is_fact_contrast_without_sentiment():
    """하이라이트는 사실 대조 3줄 — 감정 형용사·상투 감성 문구 금지."""
    resp = build_chronicle(demo_request())
    lines = resp.highlight_card.lines
    assert len(lines) == 3
    by_label = {line.label: line for line in lines}
    assert "편지와 전보" in by_label["할아버지"].text  # 1965년의 연락 수단
    assert "삐삐" in by_label["나"].text  # 1992년의 연락 수단
    assert "AI 비서" in by_label["아들"].text  # 2032년 전망
    assert by_label["아들"].kind == "전망"
    banned = ["그리운", "눈물", "가슴 뭉클", "아련한", "추억에 젖"]
    for phrase in banned:
        assert phrase not in resp.highlight
        for g in resp.generations:
            assert phrase not in g.retrospective


# ---------- 초상 규칙 ----------

def test_no_photo_no_portraits():
    req = demo_request()
    req.generations[1].photo = None
    resp = build_chronicle(req)
    assert all(c.portrait is None for r in resp.rows for c in r.cells)


def test_portrait_derivation_directions_and_label():
    resp = build_chronicle(demo_request())
    grandpa = cell_at(resp, 20, "할아버지").portrait
    assert grandpa.basis == "파생"
    assert "연령 증가" in grandpa.basis_note
    assert grandpa.style == "흑백 스튜디오"  # 1965년
    mine = cell_at(resp, 20, "나").portrait
    assert mine.basis == "실물"
    assert mine.style == "컬러 필름"  # 1992년
    son = cell_at(resp, 20, "아들").portrait
    assert son.basis == "파생"
    assert "연령 감소" in son.basis_note
    assert son.style == "미래 스타일"  # 2032년
    for row in resp.rows:
        for cell in row.cells:
            assert cell.portrait.label == "AI 합성"
            assert cell.portrait.target_age == row.age
            assert cell.portrait.era_year == cell.year


def test_portrait_real_photo_takes_priority_per_generation():
    """세대별 실물 사진이 있으면 그 세대는 실물 기준, 나머지는 그대로 파생."""
    req = demo_request()
    req.generations[0].photo = "grandpa.jpg"
    resp = build_chronicle(req)
    assert cell_at(resp, 20, "할아버지").portrait.basis == "실물"
    assert cell_at(resp, 20, "아들").portrait.basis == "파생"
    assert cell_at(resp, 20, "나").portrait.basis == "실물"


def test_portrait_not_generated_without_self_photo():
    """본인 사진이 없으면 파생 기준이 없어 초상을 만들지 않는다."""
    self_gen = GenerationInput(label="나", birth_year=1972, is_self=True)
    father = GenerationInput(label="아버지", birth_year=1945)
    assert build_portrait(father, self_gen, 20, 1965) is None


def test_generate_portrait_is_placeholder_without_network():
    req = demo_request()
    resp = build_chronicle(req)
    portrait = cell_at(resp, 20, "나").portrait
    out = generate_portrait(portrait)
    assert out["status"] == "placeholder"
    assert out["image"] is None
    assert out["label"] == "AI 합성"


# ---------- 2세대 (아들 없음) ----------

def test_two_generations_without_son():
    req = ChronicleRequest(
        generations=[
            GenerationInput(label="아버지", birth_year=1945),
            GenerationInput(label="나", birth_year=1972, is_self=True),
        ]
    )
    resp = build_chronicle(req)
    assert len(resp.generations) == 2
    assert all(len(r.cells) == 2 for r in resp.rows)
    assert resp.highlight_age == 20
    assert "1965" in resp.highlight and "1992" in resp.highlight


# ---------- 회고문 ----------

def test_retrospectives_built_from_researched_cells():
    resp = build_chronicle(demo_request())
    by_label = {g.label: g for g in resp.generations}
    assert "1992년" in by_label["나"].retrospective
    assert "대학에 입학했다" in by_label["나"].retrospective
    assert "1965년" in by_label["할아버지"].retrospective
    assert "2032년" in by_label["아들"].retrospective


# ---------- 검증 ----------

def test_requires_two_or_three_generations():
    with pytest.raises(Exception):
        ChronicleRequest(generations=[GenerationInput(label="나", birth_year=1972)])
    with pytest.raises(Exception):
        ChronicleRequest(
            generations=[
                GenerationInput(label="할아버지", birth_year=1945),
                GenerationInput(label="아버지", birth_year=1972),
                GenerationInput(label="나", birth_year=1998),
                GenerationInput(label="아들", birth_year=2020),
            ]
        )


def test_only_one_self_allowed():
    with pytest.raises(Exception):
        ChronicleRequest(
            generations=[
                GenerationInput(label="나", birth_year=1972, is_self=True),
                GenerationInput(label="또다른나", birth_year=1980, is_self=True),
            ]
        )


# ---------- 엔드포인트 ----------

def test_chronicle_endpoint():
    client = TestClient(app)
    r = client.post(
        "/chronicle",
        json={
            "generations": [
                {"label": "할아버지", "birth_year": 1945},
                {
                    "label": "나",
                    "birth_year": 1972,
                    "is_self": True,
                    "photo": "self.jpg",
                    "events": [{"year": 1992, "text": "대학에 입학했다"}],
                },
                {"label": "아들", "birth_year": 2012},
            ]
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "mock"
    assert body["highlight_age"] == 20
    assert body["share_id"]
    assert len(body["highlight_card"]["lines"]) == 3
    assert len(body["generations"]) == 3
    row20 = next(row for row in body["rows"] if row["age"] == 20)
    years = {c["label"]: c["year"] for c in row20["cells"]}
    assert years == {"할아버지": 1965, "나": 1992, "아들": 2032}
    kinds = {c["label"]: c["kind"] for c in row20["cells"]}
    assert kinds["아들"] == "전망"
    assert "같은 나이" in body["chronicle_markdown"]


def test_old_endpoints_removed():
    client = TestClient(app)
    assert client.post("/assess", json={}).status_code == 404
    assert client.post("/verify-resume", json={}).status_code == 404
    assert client.post("/briefing", json={}).status_code == 404
    assert client.get("/health").json() == {"ok": True}


# ---------- 공유 ----------

def _create_share(client) -> str:
    r = client.post(
        "/chronicle",
        json={
            "generations": [
                {"label": "할아버지", "birth_year": 1945},
                {"label": "나", "birth_year": 1972, "is_self": True, "photo": "self.jpg"},
                {"label": "아들", "birth_year": 2012},
            ]
        },
    )
    assert r.status_code == 200
    return r.json()["share_id"]


def test_share_create_and_readonly_view():
    client = TestClient(app)
    share_id = _create_share(client)
    r = client.get(f"/share/{share_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["share_id"] == share_id
    assert body["highlight_age"] == 20
    assert len(body["generations"]) == 3
    assert len(body["rows"]) > 0
    # 초상 프롬프트도 공유 뷰에 그대로 실린다
    row20 = next(row for row in body["rows"] if row["age"] == 20)
    assert all(c["portrait"] is not None for c in row20["cells"])


def test_share_unknown_id_is_404():
    client = TestClient(app)
    assert client.get("/share/doesnotexist").status_code == 404
    assert client.get("/share/doesnotexist/card").status_code == 404


def test_share_card_svg_contains_contrast_lines():
    client = TestClient(app)
    share_id = _create_share(client)
    r = client.get(f"/share/{share_id}/card")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    svg = r.text
    assert svg.startswith("<svg")
    for token in ("1965", "1992", "2032", "할아버지", "아들", "전망"):
        assert token in svg

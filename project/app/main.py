"""같은 나이, 다른 시대 — 3세대 연표 에이전트 API."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Response

from .chronicle import build_chronicle
from .models import ChronicleRequest, ChronicleResponse
from .share import create_share, get_share, render_card_svg

app = FastAPI(title="같은 나이, 다른 시대", version="1.1.0")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/chronicle", response_model=ChronicleResponse)
def chronicle(req: ChronicleRequest) -> ChronicleResponse:
    """생년 2-3개 + 선택 입력(호칭·개인 이벤트·사진) -> 나이 정렬 연표.

    연표의 축은 나이다. 나이마다 각 세대의 연도와 그 시대(출처 포함)를
    채우고, 미래 연도는 전망으로 강제한다. 사진이 있으면 셀마다 시대
    초상 프롬프트(실물/파생 기준 + AI 합성 라벨)가 함께 돌아온다.
    완성된 연표에는 공유 링크 식별자(share_id)가 발급된다.
    """
    resp = build_chronicle(req)
    resp.share_id = create_share(resp)
    return resp


@app.get("/share/{share_id}", response_model=ChronicleResponse)
def share_view(share_id: str) -> ChronicleResponse:
    """공유 링크의 읽기 전용 뷰. 로그인 없이 연표 전체를 돌려준다."""
    resp = get_share(share_id)
    if resp is None:
        raise HTTPException(status_code=404, detail="공유된 연표가 없다")
    return resp


@app.get("/share/{share_id}/card")
def share_card(share_id: str) -> Response:
    """"같은 나이" 하이라이트 카드 1장 (SVG 이미지, 메신저 공유용)."""
    resp = get_share(share_id)
    if resp is None:
        raise HTTPException(status_code=404, detail="공유된 연표가 없다")
    svg = render_card_svg(resp.highlight_card)
    return Response(content=svg, media_type="image/svg+xml")

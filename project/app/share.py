"""공유 — 완성된 연표에 로그인 없는 읽기 전용 링크를 발급한다.

- POST /chronicle 결과가 저장되고 share_id가 발급된다.
- GET /share/{id} 는 저장된 연표(매트릭스·회고문·초상 프롬프트)를
  그대로 돌려주는 읽기 전용 뷰다.
- GET /share/{id}/card 는 "같은 나이" 하이라이트를 메신저로 보내기
  좋은 이미지 카드 1장(SVG)으로 내보낸다. 카드에는 사실 대조
  세대별 한 줄과 연도가 들어간다.

저장소는 데모용 프로세스 메모리 dict다 (재시작하면 사라진다).
공유받은 가족이 자기 생년·사진을 추가해 연표를 확장하는 흐름은
기획서의 확장 설계로만 명시하고, 이번 구현 범위에는 넣지 않는다.
"""
from __future__ import annotations

import uuid
from xml.sax.saxutils import escape

from .models import ChronicleResponse, HighlightCard

_STORE: dict[str, ChronicleResponse] = {}


def create_share(resp: ChronicleResponse) -> str:
    """연표를 저장하고 공유 식별자를 발급한다."""
    share_id = uuid.uuid4().hex[:12]
    _STORE[share_id] = resp
    return share_id


def get_share(share_id: str) -> ChronicleResponse | None:
    return _STORE.get(share_id)


def _wrap(text: str, width: int = 21, max_lines: int = 3) -> list[str]:
    """카드 폭에 맞춘 단순 줄바꿈 (한글은 글자 수 기준)."""
    lines = [text[i : i + width] for i in range(0, len(text), width)]
    return lines[:max_lines] or [""]


def render_card_svg(card: HighlightCard) -> str:
    """하이라이트 카드 1장을 SVG 이미지로 렌더링한다 (900x1125, 4:5)."""
    W, H = 900, 1125
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}">',
        f'<rect width="{W}" height="{H}" fill="#12283f"/>',
        f'<rect width="{W}" height="10" fill="#0e7c7b"/>',
        f'<text x="70" y="130" font-family="Noto Sans CJK KR, sans-serif" '
        f'font-size="54" font-weight="700" fill="#ffffff">{escape(card.title)}</text>',
        f'<text x="70" y="195" font-family="Noto Sans CJK KR, sans-serif" '
        f'font-size="32" fill="#9fd8d7">{escape(card.subtitle)}</text>',
    ]
    y = 320
    for line in card.lines:
        outlook = " [전망]" if line.kind == "전망" else ""
        parts.append(
            f'<text x="70" y="{y}" font-family="Noto Sans CJK KR, sans-serif" '
            f'font-size="30" fill="#9fb3c8">{escape(line.label)}</text>'
        )
        parts.append(
            f'<text x="70" y="{y + 78}" font-family="Noto Serif CJK KR, serif" '
            f'font-size="72" font-weight="700" fill="#ffffff">'
            f"{line.year}년{escape(outlook)}</text>"
        )
        ty = y + 148
        for chunk in _wrap(line.text):
            parts.append(
                f'<text x="70" y="{ty}" font-family="Noto Sans CJK KR, sans-serif" '
                f'font-size="31" fill="#e8eef4">{escape(chunk)}</text>'
            )
            ty += 44
        y = ty + 62
    parts.append(
        f'<text x="70" y="{H - 60}" font-family="Noto Sans CJK KR, sans-serif" '
        f'font-size="24" fill="#7a8794">{escape(card.footer)}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)

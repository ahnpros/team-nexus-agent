"""데모 리허설 (같은 나이, 다른 시대 — 3세대 연표 에이전트).

시나리오 2건을 전 과정으로 돌리고 단계별 시간을 잰다.
Liner 키가 없으면 mock 시대 자료로 돌고, 5분 영상 분량 안에
들어가는지 확인한다.

실행: python3 rehearse_demo.py   (project/ 디렉터리에서)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from app.chronicle import build_chronicle
from app.models import ChronicleRequest

HERE = Path(__file__).parent


def load_json(name: str) -> dict:
    return json.loads((HERE / "samples" / name).read_text(encoding="utf-8"))


def row_at(resp, age: int):
    return next(r for r in resp.rows if r.age == age)


def main() -> None:
    total_start = time.perf_counter()

    t0 = time.perf_counter()
    full = build_chronicle(ChronicleRequest(**load_json("chronicle_demo.json")))
    t_full = time.perf_counter() - t0

    t0 = time.perf_counter()
    two = build_chronicle(ChronicleRequest(**load_json("chronicle_demo_two_gen.json")))
    t_two = time.perf_counter() - t0

    total = time.perf_counter() - total_start

    print("== 데모 리허설 결과 ==")
    print(f"엔진: {full.engine} (Liner 키 없으면 mock, 키 있으면 liner 실연동)")
    print()
    print(f"[시나리오 1] 3세대 + 사진 1장 — {t_full*1000:.1f}ms")
    print("  세대: " + " · ".join(f"{g.label}({g.birth_year})" for g in full.generations))
    print()
    print("  == 핵심 장면: 세 세대의 20살 행 ==")
    for cell in row_at(full, 20).cells:
        era = cell.content.summary if cell.content else "(빈 셀)"
        print(f"  - {cell.label}의 20살 = {cell.year}년 [{cell.kind}] {era}")
        if cell.portrait:
            p = cell.portrait
            print(f"    초상: {p.style} / {p.basis_note} / 라벨 {p.label}")
        for e in cell.personal_events:
            print(f"    개인 기록: {e}")
    print()
    print(f"  하이라이트({full.highlight_age}살) — 사실 대조 3줄:")
    for line in full.highlight_card.lines:
        tag = " [전망]" if line.kind == "전망" else ""
        print(f"    {line.label} {line.year}년{tag} — {line.text}")
    print("  (이 3줄이 공유 카드 1장에 그대로 들어간다: GET /share/{id}/card)")
    print()
    portraits = [c.portrait for r in full.rows for c in r.cells if c.portrait]
    real = sum(1 for p in portraits if p.basis == "실물")
    derived = sum(1 for p in portraits if p.basis == "파생")
    print(f"  초상 프롬프트: 총 {len(portraits)}개 (실물 기준 {real}, 본인 사진 파생 {derived})")
    print()
    print(f"[시나리오 2] 2세대(아들 없음) + 사진 없음 — {t_two*1000:.1f}ms")
    print("  세대: " + " · ".join(f"{g.label}({g.birth_year})" for g in two.generations))
    n_portraits = sum(1 for r in two.rows for c in r.cells if c.portrait)
    print(f"  초상: {n_portraits}개 (사진이 없으면 연표는 텍스트만으로 동작)")
    print(f"  하이라이트({two.highlight_age}살): {two.highlight}")
    print()
    print(f"전체: {total*1000:.1f}ms — 연산은 순식간이니 5분 영상은 서사와 화면 전환용으로 넉넉함")
    print()
    print("== 5분 영상 구간안 (나레이션 기준) ==")
    print("0:00–0:40  문제: 아버지의 스무 살이 어땠는지, 우리는 모르고 산다")
    print("0:40–1:30  입력: 생년 세 개와 가운데 세대 사진 한 장")
    print("1:30–3:10  핵심 장면: 세 세대의 20살이 한 화면에 정렬된다 — 1965 흑백 초상,")
    print("           1992 컬러 필름 초상, 2032 전망과 미래 스타일 초상")
    print("3:10–4:10  정직성 설계: 미래는 전망 라벨, 출처 없는 연도는 빈 셀,")
    print("           초상은 실물/파생 기준 표시와 AI 합성 라벨")
    print("4:10–5:00  마무리: 연표 공유 링크를 아들에게 보내고, 세 세대의 20살")
    print("           대조 카드를 메신저로 전송한다. 시대 조사는 Liner 실연동")
    print()
    print("== 시나리오 1 연표 한 장 ==")
    print(full.chronicle_markdown)


if __name__ == "__main__":
    main()

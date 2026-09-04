#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_cards.py — 카드뉴스 스펙(JSON) → 인스타그램 캐러셀용 JPG (1080×1350, 4:5)

사용:
  python3 tools/make_cards.py specs/2026-09-05-youth.json            # → cards/2026-09-05-youth/
  python3 tools/make_cards.py specs/X.json --out cards/X

스펙(JSON):
{
  "theme":  "youth" | "ai",
  "date":   "2026-09-05",
  "kicker": "청년정책 데일리 · 건강·복지 편",   (카드 상단 작은 라벨)
  "handle": "@계정명",                            (푸터 왼쪽)
  "cards":  ["1장 문구 (줄바꿈은 <br>)", "2장 문구", ...]   (1장 = 표지, 최대 10장)
}

줄 맨 앞 기호가 스타일을 정한다:
  ✔️ 또는 ✓  체크리스트      ·  불릿      □  체크박스(할 일)
  ⚠️          경고 (카드 첫 줄이면 카드 전체가 경고 톤)
  ①②… 또는 "1." 로 시작      제목 줄
  👉          강조 문장 (마무리 카드용)
빈 줄(<br><br>)은 문단 간격. 이모지는 폰트에 없으면 자동 제거된다.
"""
import argparse, json, os, re, sys
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTCollection, TTFont

W, H = 1080, 1350
M = 84            # 좌우 여백
TOP = 236         # 본문 시작 y
FOOT = 150        # 푸터 영역 높이
FONT_MAIN = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
FONT_SYM = "/System/Library/Fonts/Apple Symbols.ttf"
FACE = {"regular": 0, "medium": 2, "semibold": 4, "bold": 6, "heavy": 16}

THEMES = {
    "youth": dict(label="청년정책 데일리", bg="#0B1220", panel="#111A2E", accent="#FACC15",
                  text="#F8FAFC", muted="#94A3B8", check="#4ADE80", warn="#FB923C"),
    "ai":    dict(label="AI 글로벌 브리핑", bg="#06090F", panel="#0E1627", accent="#22D3EE",
                  text="#F8FAFC", muted="#8B9BB4", check="#34D399", warn="#FBBF24"),
}

_font_cache = {}
def font(size, face="regular"):
    key = (size, face)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONT_MAIN, size, index=FACE[face])
    return _font_cache[key]

def sym_font(size):
    key = (size, "sym")
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONT_SYM, size)
    return _font_cache[key]

_MAIN_CMAP = set(TTCollection(FONT_MAIN).fonts[0].getBestCmap().keys())
_SYM_CMAP = set(TTFont(FONT_SYM).getBestCmap().keys())
DROPPED = set()

REPL = [("✔️", "✓"), ("✔", "✓"), ("☑️", "✓"), ("☑", "✓"), ("✅", "✓"),
        ("⚠️", "⚠"), ("☐", "□"), ("\\~", "~"), ("\\[", "["), ("\\]", "]"),
        ("\\*", "*"), ("\\_", "_"), ("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("**", ""), ("`", "")]

def normalize(s):
    for a, b in REPL:
        s = s.replace(a, b)
    out = []
    for ch in s:
        o = ord(ch)
        if ch in "️‍​":
            continue
        if ch.isspace() or o in _MAIN_CMAP or o in _SYM_CMAP:
            out.append(ch)
        else:
            DROPPED.add(ch)
    return re.sub(r"[ \t]+", " ", "".join(out)).strip()

def runs(text):
    """폰트 폴백용 런 분리: (문자열, 심볼폰트여부)"""
    res, cur, cur_sym = [], "", False
    for ch in text:
        is_sym = (ord(ch) not in _MAIN_CMAP) and (ord(ch) in _SYM_CMAP)
        if cur and is_sym != cur_sym:
            res.append((cur, cur_sym)); cur = ""
        cur += ch; cur_sym = is_sym
    if cur:
        res.append((cur, cur_sym))
    return res

def text_w(text, size, face="regular"):
    return sum((sym_font(size) if s else font(size, face)).getlength(t) for t, s in runs(text))

def draw_text(d, x, y, text, size, face, fill):
    for t, s in runs(text):
        f = sym_font(size) if s else font(size, face)
        d.text((x, y), t, font=f, fill=fill, anchor="la")
        x += f.getlength(t)

def wrap(text, size, face, maxw):
    if not text:
        return [""]
    lines, cur = [], ""
    for w in text.split(" "):
        trial = (cur + " " + w) if cur else w
        if text_w(trial, size, face) <= maxw:
            cur = trial
            continue
        if cur:
            lines.append(cur); cur = ""
        if text_w(w, size, face) <= maxw:
            cur = w
        else:                      # 띄어쓰기 없는 긴 덩어리 → 글자 단위
            piece = ""
            for ch in w:
                if text_w(piece + ch, size, face) <= maxw:
                    piece += ch
                else:
                    lines.append(piece); piece = ch
            cur = piece
    if cur:
        lines.append(cur)
    return lines

HEAD_RE = re.compile(r"^([①-⑳]|\d+[.)]|STEP ?\d+|Step ?\d+)")

def classify(raw):
    s = raw.strip()
    if not s:
        return ("gap", "")
    if s.startswith("👉"):
        return ("cta", normalize(s[1:]))
    s = normalize(s)
    if not s:
        return ("gap", "")
    if s[0] == "✓":
        return ("check", s[1:].strip())
    if s[0] == "□":
        return ("box", s[1:].strip())
    if s[0] in "·•":
        return ("bullet", s[1:].strip())
    if s.startswith("- "):
        return ("bullet", s[2:].strip())
    if s[0] == "⚠":
        return ("warn", s[1:].strip())
    if HEAD_RE.match(s):
        return ("head", s)
    return ("text", s)

def split_lines(card):
    card = card.replace("\r", "")
    card = re.sub(r"<br\s*/?>", "\n", card, flags=re.I)
    return card.split("\n")

# ---------- 레이아웃 ----------
def layout_body(blocks, size, maxw):
    """블록 목록 → [(kind, text_lines, face, fsize, indent, color_key)] 와 총 높이"""
    items, total = [], 0
    for i, (kind, txt) in enumerate(blocks):
        first = (i == 0)
        if kind == "gap":
            items.append(("gap", [], None, int(size * 0.55), 0, None)); total += int(size * 0.55); continue
        if kind == "head":
            fs, face, indent, ck = size + 10, "bold", 0, ("accent" if first else "text")
        elif kind == "warn":
            fs, face, indent, ck = (size + 8 if first else size), ("bold" if first else "medium"), 0, "warn"
        elif kind == "cta":
            fs, face, indent, ck = size + 2, "semibold", 0, "accent"
        elif kind in ("check", "box"):
            fs, face, indent, ck = size, "regular", 74, "text"
        elif kind == "bullet":
            fs, face, indent, ck = size, "regular", 50, "text"
        else:  # text
            if first:
                fs, face, indent, ck = size + 8, "semibold", 0, "text"
            else:
                fs, face, indent, ck = size, "regular", 0, "text"
        prefix = "⚠ " if (kind == "warn" and first) else ""
        lines = wrap(prefix + txt, fs, face, maxw - indent)
        lh = int(fs * 1.42)
        h = lh * len(lines) + int(size * 0.38)
        items.append((kind, lines, face, fs, indent, ck))
        total += h
    return items, total

def draw_frame(d, th, kicker, right_text, bar_color):
    d.rectangle([0, 0, W, 14], fill=bar_color)
    draw_text(d, M, 92, kicker, 30, "bold", th["accent"])
    if right_text:
        tw = text_w(right_text, 28, "medium")
        draw_text(d, W - M - tw, 94, right_text, 28, "medium", th["muted"])

def draw_footer(d, th, spec):
    y = H - 92
    d.line([M, y - 34, W - M, y - 34], fill=th["panel"], width=2)
    draw_text(d, M, y, spec.get("handle", ""), 26, "medium", th["muted"])
    right = f'{th["label"]} · {spec.get("date", "")}'
    tw = text_w(right, 26, "regular")
    draw_text(d, W - M - tw, y, right, 26, "regular", th["muted"])

def render_cover(spec, th, raw_lines, n):
    img = Image.new("RGB", (W, H), th["bg"]); d = ImageDraw.Draw(img)
    draw_frame(d, th, spec.get("kicker", th["label"]), spec.get("date", ""), th["accent"])
    main, sub, seen_gap = [], [], False
    for l in raw_lines:
        t = normalize(l)
        if not t:
            if main: seen_gap = True
            continue
        (sub if seen_gap else main).append(t)
    maxw = W - 2 * M - 40
    size = 78
    while True:
        ml = [wrap(t, size, "heavy", maxw) for t in main]
        ss = int(size * 0.62)
        sl = [wrap(t, ss, "medium", maxw) for t in sub]
        mh = sum(len(x) for x in ml) * int(size * 1.32)
        sh = (sum(len(x) for x in sl) * int(ss * 1.45) + int(size * 0.7)) if sub else 0
        if mh + sh <= H - TOP - FOOT - 60 or size <= 44:
            break
        size -= 2
    y = TOP + max(0, (H - TOP - FOOT - (mh + sh)) // 2) - 20
    d.rectangle([M - 40, y + 6, M - 26, y + mh - int(size * 0.32)], fill=th["accent"])
    for lines in ml:
        for ln in lines:
            draw_text(d, M, y, ln, size, "heavy", th["text"]); y += int(size * 1.32)
    if sub:
        y += int(size * 0.7)
        for lines in sl:
            for ln in lines:
                draw_text(d, M, y, ln, ss, "medium", th["accent"]); y += int(ss * 1.45)
    draw_footer(d, th, spec)
    return img, 0

def render_card(spec, th, raw_lines, idx, n):
    img = Image.new("RGB", (W, H), th["bg"]); d = ImageDraw.Draw(img)
    blocks = [classify(l) for l in raw_lines]
    while blocks and blocks[0][0] == "gap": blocks.pop(0)
    while blocks and blocks[-1][0] == "gap": blocks.pop()
    is_warn = bool(blocks) and blocks[0][0] == "warn"
    draw_frame(d, th, spec.get("kicker", th["label"]), f"{idx + 1:02d} / {n:02d}",
               th["warn"] if is_warn else th["accent"])
    maxw = W - 2 * M
    avail = H - TOP - FOOT
    size = 56
    while True:
        items, total = layout_body(blocks, size, maxw)
        if total <= avail or size <= 30:
            break
        size -= 2
    overflow = max(0, total - avail)
    y = TOP + max(0, (avail - total) // 3)   # 위쪽으로 치우친 세로 정렬
    col = {"text": th["text"], "accent": th["accent"], "warn": th["warn"]}
    for kind, lines, face, fs, indent, ck in items:
        if kind == "gap":
            y += fs; continue
        lh = int(fs * 1.42)
        x = M + indent
        # 마커
        if kind == "check":
            draw_text(d, M + 8, y, "✓", fs, "bold", th["check"])
        elif kind == "bullet":
            r = 6; cy = y + int(fs * 0.62)
            d.ellipse([M + 14, cy - r, M + 14 + 2 * r, cy + r], fill=th["muted"])
        elif kind == "box":
            s = int(fs * 0.72); cy = y + int(fs * 0.62)
            d.rounded_rectangle([M + 10, cy - s // 2, M + 10 + s, cy + s // 2], radius=6,
                                outline=th["accent"], width=4)
        for ln in lines:
            draw_text(d, x, y, ln, fs, face, col[ck]); y += lh
        y += int(size * 0.38)
    draw_footer(d, th, spec)
    return img, overflow

def contact_sheet(paths, out):
    tw, thh, cols = 270, 338, 5
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * 10, rows * thh + (rows + 1) * 10), "#222")
    for i, p in enumerate(paths):
        im = Image.open(p).resize((tw, thh))
        sheet.paste(im, (10 + (i % cols) * (tw + 10), 10 + (i // cols) * (thh + 10)))
    sheet.save(out, quality=85)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--out", help="출력 폴더 (기본: cards/<스펙파일명>)")
    a = ap.parse_args()
    spec = json.load(open(a.spec, encoding="utf-8"))
    th = THEMES[spec.get("theme", "youth")]
    cards = spec["cards"]
    if not 1 <= len(cards) <= 10:
        sys.exit(f"카드 수는 1~10장이어야 합니다 (현재 {len(cards)})")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = a.out or os.path.join(root, "cards", os.path.splitext(os.path.basename(a.spec))[0])
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        if f.endswith(".jpg"): os.remove(os.path.join(out, f))
    paths, warnings = [], []
    n = len(cards)
    for i, card in enumerate(cards):
        lines = split_lines(card)
        img, overflow = render_cover(spec, th, lines, n) if i == 0 else render_card(spec, th, lines, i, n)
        p = os.path.join(out, f"{i + 1:02d}.jpg")
        img.save(p, "JPEG", quality=92, subsampling=0)
        paths.append(p)
        if overflow > 0:
            warnings.append(f"{i + 1}장: 본문이 {overflow}px 넘침 — 문구를 줄이세요")
    contact_sheet(paths, os.path.join(out, "preview.jpg"))
    if DROPPED:
        warnings.append("폰트에 없어 제거된 문자: " + " ".join(sorted(DROPPED)))
    print(json.dumps({"out": out, "count": n, "files": [os.path.basename(p) for p in paths],
                      "preview": os.path.join(out, "preview.jpg"), "warnings": warnings},
                     ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

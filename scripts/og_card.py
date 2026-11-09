"""호텔 미리보기 카드(og:image) — 검색 결과 썸네일(네이버·구글)과 카톡·페이스북 링크 미리보기에 같이 쓰인다.

2026-11-05 og1: 사진을 흐리고 어둡게 덮은 뒤 호텔명·'실망 확률 N%'를 가운데에.
2026-11-09 og2(사용자 확정 — SEO-GOOGLE 후속): 검색 결과 96px 정사각 썸네일에서 사진도 글자도 안 보였고, 처음 보는 사람은
  '실망 확률'이 뭔지 모른다 → 사진은 그대로 밝게, 글자는 두 묶음만:
    위 = 노랑 표지판 배지 '{항목} 주의'(상세 '한눈에 보기'의 걸리는 점 1위 — 사이트 판정과 같은 기준, 없으면 배지 없음)
    아래 = 어두운 그라데이션 위 '벌레 0건'(최근 1년 벌레 리뷰가 없을 때) → 곰팡이 0건 → '{항목} 불만 적음' → '리뷰 분석'
  빨강(위험)은 쓰지 않는다: 호텔 이름 옆에 검색 결과로 나가는 그림이라 가장 센 표시는 '주의'까지(2026-11-09 결정).

- 1200×630 JPEG. 글자는 전부 가운데 630×630 안(네이버 썸네일 = 가운데 정사각형으로 잘림)의 왼쪽 줄에 맞춘다.
- 사진 = 호텔 갤러리에서 밝은 가로 사진 하나(pick_photo — 첫 사진이 어두운 간판·로비인 호텔이 많다). 고른 번호는
  scripts/og_photo.json(pid → 번호, git 추적)에 남고, 사람이 고치면 그 값을 계속 쓴다. 새 호텔만 자동으로 고른다.
- 색: 안심 점·잉크는 css/tokens.css, 표지판 노랑은 그림 전용 상수(SIGN_YELLOW). 글꼴은 Pretendard(jsDelivr) → 맑은 고딕 → 없으면 카드 없음.
- 사진·글꼴은 .cache/og/에 받아 두고(gitignored), 입력이 같으면 다시 굽지 않는다(같은 바이트 → 같은 ?v= → 미리보기 캐시 유지).
- 네트워크·글꼴이 없으면 None — 빌드는 멈추지 않고 원본 사진을 og:image로 쓴다. CF_OG=0이면 끈다.
- 카드에는 매주 바뀌는 숫자(실망 확률·리뷰 건수)를 넣지 않는다 → git에 쌓이는 그림이 적다."""
import hashlib, io, json, os, re, urllib.request

W_, H_ = 1200, 630
VERSION = 'og2'          # 디자인을 바꾸면 올린다 → 전 카드 다시 굽기
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, '.cache', 'og')
FONT_URL = 'https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/public/static/Pretendard-{w}.otf'
UA = {'User-Agent': 'catchflaw-build/1.0 (+https://catchflaw.com)'}

_fonts = {}
_tok = None
_manifest = None


def _get(url, timeout=20):
    """R2가 가끔 500을 낸다(2026-11-09 빌드 한 번에 1건) — 두 번 더 해 본다. 끝내 안 되면 올려서 그 호텔 카드만 건너뛴다."""
    import time
    for k in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
        except Exception:
            if k == 2: raise
            time.sleep(1.5 * (k + 1))


def _cached(url, sub):
    os.makedirs(os.path.join(CACHE, sub), exist_ok=True)
    p = os.path.join(CACHE, sub, hashlib.sha1(url.encode()).hexdigest()[:20])
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return open(p, 'rb').read()
    b = _get(url)
    open(p, 'wb').write(b)
    return b


def _font(weight, size):
    from PIL import ImageFont
    k = (weight, size)
    if k in _fonts: return _fonts[k]
    f = None
    try:
        f = ImageFont.truetype(io.BytesIO(_cached(FONT_URL.format(w=weight), 'fonts')), size)
    except Exception:
        for fb in (r'C:\Windows\Fonts\malgunbd.ttf', '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf'):
            if os.path.exists(fb):
                f = ImageFont.truetype(fb, size); break
    _fonts[k] = f
    return f


def _tokens():
    global _tok
    if _tok is None:
        css = open(os.path.join(ROOT, 'css', 'tokens.css'), encoding='utf-8').read()
        _tok = {m.group(1): m.group(2) for m in re.finditer(r'--([\w-]+):\s*(#[0-9A-Fa-f]{6})\b', css)}
    return _tok


def _rgb(name):
    h = _tokens()[name].lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _wrap(draw, text, font, max_w, max_lines):
    """띄어쓰기 단위로 줄을 채운다(한 낱말이 넘치면 글자 단위). 넘치면 마지막 줄 끝을 '…'."""
    words, lines, cur = text.split(), [], ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t; continue
        if cur: lines.append(cur)
        cur = w
        while draw.textlength(cur, font=font) > max_w:      # 아주 긴 낱말
            i = len(cur)
            while i > 1 and draw.textlength(cur[:i], font=font) > max_w: i -= 1
            lines.append(cur[:i]); cur = cur[i:]
    if cur: lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + '…', font=font) > max_w: last = last[:-1]
        lines[-1] = last.rstrip() + '…'
    return lines


SIGN_YELLOW = (255, 212, 59)     # 도로 표지판 노랑 — 그림 전용(토큰에 없음: 화면 UI에는 쓰지 않는다)
SIGN_INK = (26, 26, 26)
SHADE = (18, 10, 40)             # 아래 그라데이션(보라 기 도는 검정)
SQ = H_                          # 가운데 정사각형 한 변
K = SQ / 96                      # 시안(96px 썸네일) → 실제 배율


def _fit(draw, text, weight, size, max_w, min_size=40):
    """max_w에 들어갈 때까지 글자를 줄인다."""
    while size > min_size:
        f = _font(weight, size) or _font('Bold', size)
        if f is None or draw.textlength(text, font=f) <= max_w: return f
        size -= 3
    return _font(weight, size) or _font('Bold', size)


def _gradient(im, y0, y1, color, stops):
    """세로 그라데이션 덮기 — stops = [(위치 0~1(y0→y1), 불투명도 0~1)]. y0 > y1이면 아래에서 위로."""
    from PIL import Image
    h = abs(y1 - y0)
    col = Image.new('L', (1, h))
    px = col.load()
    for i in range(h):
        t = i / max(1, h - 1)
        for (t0, a0), (t1, a1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                a = a0 + (a1 - a0) * ((t - t0) / max(1e-6, t1 - t0)); break
        else:
            a = stops[-1][1]
        px[0, i] = round(255 * a)
    top = min(y0, y1)
    if y0 > y1: col = col.transpose(Image.FLIP_TOP_BOTTOM)
    mask = col.resize((im.width, h))
    im.paste(Image.new('RGB', (im.width, h), color), (0, top), mask)


def render(photo, chip, cap, cap_dot):
    """photo = 이미지 바이트, chip = '소음 주의' | None, cap = '벌레 0건', cap_dot = 안심 점(파랑)을 붙일지."""
    from PIL import Image, ImageDraw, ImageEnhance
    src = Image.open(io.BytesIO(photo)).convert('RGB')
    s = max(W_ / src.width, H_ / src.height)
    src = src.resize((max(W_, round(src.width * s)), max(H_, round(src.height * s))), Image.LANCZOS)
    x0, y0 = (src.width - W_) // 2, (src.height - H_) // 2
    im = src.crop((x0, y0, x0 + W_, y0 + H_))
    im = ImageEnhance.Color(ImageEnhance.Brightness(im).enhance(1.06)).enhance(1.08)   # 작은 썸네일에서 또렷하게
    if chip:
        _gradient(im, 0, round(40 * K), (0, 0, 0), [(0, .38), (1, 0)])
    _gradient(im, H_, H_ - round(59 * K), SHADE, [(0, .96), (.34, .86), (.68, .45), (1, 0)])
    d = ImageDraw.Draw(im, 'RGBA')
    left = (W_ - SQ) // 2 + round(6 * K)             # 가운데 정사각형의 왼쪽 여백
    inner = SQ - 2 * round(6 * K)
    if chip:
        pad_x, pad_y, ic, gap = round(7 * K), round(5 * K), round(13 * K), round(3 * K)
        f = _fit(d, chip, 'ExtraBold', round(12.5 * K), inner - 2 * pad_x - ic - gap)
        if f is None: return None
        ic = min(ic, round(f.size * 1.05))
        tw = round(d.textlength(chip, font=f))
        ch = round(f.size * 1.0) + 2 * pad_y
        cw = pad_x + ic + gap + tw + pad_x
        cx, cy = left, round(6 * K)
        d.rounded_rectangle((cx + 2, cy + 6, cx + cw + 2, cy + ch + 6), radius=round(7 * K), fill=(0, 0, 0, 70))   # 옅은 그림자
        d.rounded_rectangle((cx, cy, cx + cw, cy + ch), radius=round(7 * K), fill=SIGN_YELLOW)
        ix, iy = cx + pad_x, cy + (ch - ic) // 2                 # 경고 삼각형(모서리 둥글게) + 노랑 느낌표
        tri = [(ix + ic / 2, iy + ic * .12), (ix + ic * .93, iy + ic * .86), (ix + ic * .07, iy + ic * .86)]
        d.polygon(tri, fill=SIGN_INK)
        d.line(tri + [tri[0], tri[1]], fill=SIGN_INK, width=max(4, round(ic * .13)), joint='curve')
        mw = max(4, round(ic * .11))
        d.line([(ix + ic / 2, iy + ic * .40), (ix + ic / 2, iy + ic * .60)], fill=SIGN_YELLOW, width=mw)
        for yy in (iy + ic * .40, iy + ic * .60):
            d.ellipse((ix + ic / 2 - mw / 2, yy - mw / 2, ix + ic / 2 + mw / 2, yy + mw / 2), fill=SIGN_YELLOW)
        r = mw * .62
        d.ellipse((ix + ic / 2 - r, iy + ic * .73 - r, ix + ic / 2 + r, iy + ic * .73 + r), fill=SIGN_YELLOW)
        d.text((ix + ic + gap, cy + ch / 2), chip, font=f, fill=SIGN_INK, anchor='lm')
    dot_r = round(4 * K) if cap_dot else 0
    dot_w = (2 * dot_r + round(4 * K)) if cap_dot else 0
    f = _fit(d, cap, 'ExtraBold', round(15 * K), inner - round(4 * K) - dot_w)
    if f is None: return None
    bx, by = left + round(2 * K), H_ - round(7 * K) - f.size // 2          # 글자 세로 가운데
    if cap_dot:
        safe = _rgb('safe')
        cyy = by + round(f.size * .04)
        d.ellipse((bx - 7, cyy - dot_r - 7, bx + 2 * dot_r + 7, cyy + dot_r + 7), fill=safe + (84,))
        d.ellipse((bx, cyy - dot_r, bx + 2 * dot_r, cyy + dot_r), fill=safe + (255,))
    tx = bx + dot_w
    d.text((tx + 2, by + 3), cap, font=f, fill=(0, 0, 0, 150), anchor='lm')
    d.text((tx, by), cap, font=f, fill=(255, 255, 255, 255), anchor='lm')
    out = io.BytesIO()
    im.save(out, 'JPEG', quality=80, optimize=True)
    return out.getvalue()


# ── 사진 고르기: 갤러리(최대 10장) 썸네일을 훑어 밝은 가로 사진 하나. 고른 번호는 scripts/og_photo.json에 남긴다 ──
PHOTO_JSON = os.path.join(ROOT, 'scripts', 'og_photo.json')
_photo = None
_photo_dirty = False


def _photo_score(b, idx):
    """밝기(가운데 150 근처)·어두운/하얀 면 비율·가로세로 비·위아래 민무늬 띠(글자 배너·레터박스)·앞 순서 가점.
       사람 눈을 대신하지는 못한다(음식·간판·광고 모델 사진도 밝다) — 새 호텔이 들어오면 docs/og/{slug}.jpg를 한 번 보고
       이상하면 scripts/og_photo.json의 번호를 고친다(객실 사진 우선)."""
    from PIL import Image
    im = Image.open(io.BytesIO(b)).convert('RGB')
    w, h = im.size
    px = list(im.resize((96, 64)).convert('L').getdata())
    n = len(px)
    mean = sum(px) / n
    sd = (sum((p - mean) ** 2 for p in px) / n) ** .5
    dark = sum(1 for p in px if p < 50) / n
    white = sum(1 for p in px if p > 238) / n
    ar = w / h
    sc = -abs(mean - 150) / 60 - max(0, dark - .25) * 3 - max(0, white - .22) * 3 + min(sd, 60) / 120
    if ar < 1.2: sc -= 1.0          # 세로·정사각 사진은 1200×630으로 자르면 많이 잘린다
    if ar > 1.95: sc -= 0.6         # 배너형
    def flat(rows):
        v = [p for r in rows for p in px[r * 96:(r + 1) * 96]]
        m = sum(v) / len(v)
        return (sum((p - m) ** 2 for p in v) / len(v)) ** .5 < 6
    if flat(range(0, 7)) or flat(range(57, 64)): sc -= 0.8
    if idx == 2: sc += 0.9      # 갤러리 3번째가 대개 객실(2026-11-09: 194곳을 눈으로 고르니 130곳 넘게 2번) — 0번은 외관, 뒤쪽은 음식·부대시설
    return sc - 0.04 * idx


def pick_photo(pid, urls, thumbs):
    """urls = 갤러리 원본 주소들(순서 = 갤러리), thumbs = 같은 순서의 작은 사진 주소. 고른 원본 주소(없으면 첫 장)."""
    global _photo, _photo_dirty
    if not urls: return None
    if _photo is None:
        try: _photo = json.load(open(PHOTO_JSON, encoding='utf-8'))
        except Exception: _photo = {}
    i = _photo.get(pid)
    if isinstance(i, int) and 0 <= i < len(urls): return urls[i]
    best, best_s = 0, None
    for k, t in enumerate(thumbs[:10]):
        try:
            sc = _photo_score(_cached(t, 'thumbs'), k)
        except Exception:
            continue
        if best_s is None or sc > best_s: best, best_s = k, sc
    if best_s is None: return urls[0]          # 한 장도 못 받음 — 기록하지 않고 다음 빌드에 다시 고른다
    _photo[pid] = best
    _photo_dirty = True
    return urls[best]


def _load_manifest():
    global _manifest
    if _manifest is None:
        try: _manifest = json.load(open(os.path.join(CACHE, 'manifest.json'), encoding='utf-8'))
        except Exception: _manifest = {}
    return _manifest


def save_manifest():
    if _manifest is not None:
        os.makedirs(CACHE, exist_ok=True)
        json.dump(_manifest, open(os.path.join(CACHE, 'manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    if _photo_dirty:   # 새로 고른 사진 번호(pid 순 — diff가 읽히게). 파일이 바뀌면 산출물과 함께 커밋
        json.dump(dict(sorted(_photo.items())), open(PHOTO_JSON, 'w', encoding='utf-8', newline='\n'), ensure_ascii=False, indent=0)


def card(out_dir, slug, photo_url, local_photo, chip, cap, cap_dot):
    """docs/og/{slug}.jpg를 (필요할 때만) 굽고 내용 해시 8자를 돌려준다. 실패하면 None(빌드는 계속)."""
    if os.environ.get('CF_OG') == '0' or not (photo_url or local_photo): return None
    rel = os.path.join('og', f'{slug}.jpg')
    full = os.path.join(out_dir, rel)
    key = hashlib.sha1(json.dumps([VERSION, photo_url or local_photo, chip, cap, cap_dot],
                                  ensure_ascii=False).encode()).hexdigest()
    m = _load_manifest()
    if m.get(slug) == key and os.path.exists(full):
        return hashlib.sha1(open(full, 'rb').read()).hexdigest()[:8]
    try:
        photo = open(local_photo, 'rb').read() if local_photo else _cached(photo_url, 'src')
        b = render(photo, chip, cap, cap_dot)
    except Exception as e:
        print(f'  og 카드 건너뜀 {slug}: {type(e).__name__} {e}')
        return None
    if not b: return None
    os.makedirs(os.path.dirname(full), exist_ok=True)
    if not (os.path.exists(full) and open(full, 'rb').read() == b):
        open(full, 'wb').write(b)
    m[slug] = key
    return hashlib.sha1(b).hexdigest()[:8]

"""호텔 공유 미리보기 카드(og:image) — 카톡·페이스북 등에 링크를 붙였을 때 '호텔 사진 + 실망 확률'이 그림으로 보이게 (2026-11-05).

왜: 호텔은 일행과 같이 고른다 — 후보를 카톡으로 보내는 순간 미리보기에 숫자가 보여야 받은 사람이 눌러 본다.
    예전 og:image는 R2 원본 webp 사진뿐이라 숫자가 없었고, webp를 못 읽는 미리보기 수집기도 있다.

- 1200×630 JPEG, 사진을 꽉 채우고 어둡게 덮은 뒤 가운데 세로 한 줄(정사각형으로 잘려도 글자가 남게 가운데 600px 안).
- 색은 css/tokens.css 값을 읽어 쓴다(색 정본 = 토큰). 글꼴은 Pretendard(jsDelivr, 사이트와 같은 판) → 없으면 맑은 고딕 → 없으면 카드 없음.
- 사진·글꼴은 .cache/og/에 받아 두고(gitignored), 입력이 같으면 카드를 다시 굽지 않는다(같은 바이트 → 같은 ?v= → 미리보기 캐시 유지).
- 네트워크·글꼴이 없으면 None — 빌드는 멈추지 않고 예전처럼 원본 사진을 og:image로 쓴다. CF_OG=0이면 끈다.
- 카드에는 매주 바뀌는 숫자(리뷰 건수)를 넣지 않는다: 바뀌는 건 실망 확률·판정·도시 평균뿐이라 git에 쌓이는 그림이 적다."""
import hashlib, io, json, os, re, urllib.request

W_, H_ = 1200, 630
VERSION = 'og1'          # 디자인을 바꾸면 올린다 → 전 카드 다시 굽기
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, '.cache', 'og')
FONT_URL = 'https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/public/static/Pretendard-{w}.otf'
UA = {'User-Agent': 'catchflaw-build/1.0 (+https://catchflaw.com)'}

_fonts = {}
_tok = None
_manifest = None


def _get(url, timeout=20):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


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


def render(photo, name, pct, head, tone, city_ko, city_pct):
    """photo = 이미지 바이트, pct = 실망 확률 정수, head = 판정 문장('평균보다 실망이 잦아요'), tone = safe|warning|danger|low."""
    from PIL import Image, ImageDraw, ImageFilter
    src = Image.open(io.BytesIO(photo)).convert('RGB')
    s = max(W_ / src.width, H_ / src.height)
    src = src.resize((max(W_, round(src.width * s)), max(H_, round(src.height * s))), Image.LANCZOS)
    x0, y0 = (src.width - W_) // 2, (src.height - H_) // 2
    im = src.crop((x0, y0, x0 + W_, y0 + H_))
    im = im.filter(ImageFilter.GaussianBlur(3))                          # 글자 뒤 잔무늬를 눌러 읽기 쉽게 + JPEG 크기 절반
    im = Image.blend(im, Image.new('RGB', im.size, (0, 0, 0)), 0.58)   # 사진 위 글자 — --scrim-photo(55%)보다 조금 진하게(흰 글자 대비)
    d = ImageDraw.Draw(im)
    white, ink = (255, 255, 255), _rgb('ink')
    soft = (225, 225, 225)
    dot = {'danger': 'danger', 'warning': 'warning', 'safe': 'safe'}.get(tone)
    dot_c = _rgb(dot) if dot else _rgb('ink-4')
    f_top, f_name, f_lab = _font('SemiBold', 28), _font('Bold', 46), _font('SemiBold', 32)
    f_num, f_pill, f_foot = _font('Bold', 176), _font('SemiBold', 32), _font('Regular', 26)
    if not all((f_top, f_name, f_lab, f_num, f_pill, f_foot)): return None
    col = 600                                    # 정사각형(가운데 630)으로 잘려도 남는 폭
    name_lines = _wrap(d, name, f_name, col, 2)
    num = f'{pct}%'
    nb = d.textbbox((0, 0), num, font=f_num, anchor='mt')   # 글자 윗끝 = nb[1] (기준선 위 여백을 빼고 배치)
    pill_t = head
    pill_w = min(col + 120, round(d.textlength(pill_t, font=f_pill)) + 44 + 28 + 18)
    rows = [('top', 28), ('gap', 26)] + [('name', 58)] * len(name_lines) + [('gap', 30), ('lab', 34), ('gap', 18),
            ('num', nb[3] - nb[1]), ('gap', 34), ('pill', 64), ('gap', 18), ('foot', 26)]
    y = (H_ - sum(h for _, h in rows)) // 2
    cx = W_ // 2
    li = 0
    for kind, h in rows:
        if kind == 'top':
            d.text((cx, y), f'캐치플로 · {city_ko} 호텔 리뷰 분석', font=f_top, fill=soft, anchor='mt')
        elif kind == 'name':
            d.text((cx, y), name_lines[li], font=f_name, fill=white, anchor='mt'); li += 1
        elif kind == 'lab':
            d.text((cx, y), '실망 확률', font=f_lab, fill=soft, anchor='mt')
        elif kind == 'num':
            d.text((cx, y - nb[1]), num, font=f_num, fill=white, anchor='mt')
        elif kind == 'pill':
            x = cx - pill_w // 2
            d.rounded_rectangle((x, y, x + pill_w, y + h), radius=h // 2, fill=white)
            r = 9
            dx = x + 30
            d.ellipse((dx, y + h // 2 - r, dx + 2 * r, y + h // 2 + r), fill=dot_c)
            d.text((dx + 2 * r + 14, y + h // 2), pill_t, font=f_pill, fill=ink, anchor='lm')
        elif kind == 'foot':
            d.text((cx, y), f'{city_ko} 평균 {city_pct}% · 최근 1년 리뷰 기준', font=f_foot, fill=soft, anchor='mt')
        y += h
    out = io.BytesIO()
    im.save(out, 'JPEG', quality=82, optimize=True)
    return out.getvalue()


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


def card(out_dir, slug, photo_url, local_photo, name, pct, head, tone, city_ko, city_pct):
    """docs/og/{slug}.jpg를 (필요할 때만) 굽고 내용 해시 8자를 돌려준다. 실패하면 None(빌드는 계속)."""
    if os.environ.get('CF_OG') == '0' or not (photo_url or local_photo): return None
    rel = os.path.join('og', f'{slug}.jpg')
    full = os.path.join(out_dir, rel)
    key = hashlib.sha1(json.dumps([VERSION, photo_url or local_photo, name, pct, head, tone, city_ko, city_pct],
                                  ensure_ascii=False).encode()).hexdigest()
    m = _load_manifest()
    if m.get(slug) == key and os.path.exists(full):
        return hashlib.sha1(open(full, 'rb').read()).hexdigest()[:8]
    try:
        photo = open(local_photo, 'rb').read() if local_photo else _cached(photo_url, 'src')
        b = render(photo, name, pct, head, tone, city_ko, city_pct)
    except Exception as e:
        print(f'  og 카드 건너뜀 {slug}: {type(e).__name__} {e}')
        return None
    if not b: return None
    os.makedirs(os.path.dirname(full), exist_ok=True)
    if not (os.path.exists(full) and open(full, 'rb').read() == b):
        open(full, 'wb').write(b)
    m[slug] = key
    return hashlib.sha1(b).hexdigest()[:8]

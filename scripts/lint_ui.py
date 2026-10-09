# -*- coding: utf-8 -*-
"""캐치플로 UI 규칙 검사기 — 디자인 시스템 v2(UI-STANDARDS §0·§3·§14)를 기계적으로 강제한다.

사용:
  python scripts/lint_ui.py                   # 전체 검사 (위반 시 exit 1)
  python scripts/lint_ui.py --update-baseline # 레거시 래칫 기준을 현재값으로 갱신(줄어든 경우에만 쓰기)
  python scripts/lint_ui.py --hook            # Claude Code PostToolUse 훅 (stdin JSON, 위반 시 exit 2)
generate.py가 빌드 시작 때 run()을 호출한다 → 위반이 있으면 빌드 실패(긴급 시 CF_UI_LINT=warn).

규칙
  E1 font-size는 var(--fs-*)만. px 직접 기입 금지 (::before/::after 장식 글리프·아이콘 컨테이너 면제)
  E2 var(--fs-micro)(12px)는 배지·알약·범례·축 라벨 전용. 읽는 글자는 --fs-meta(13px) 이상
  E3 색은 tokens.css 변수만. hex 직접 기입 금지 (mvp·ds·pc·신규 CSS, generate.py/js 인라인 style)
  E4 PC 전용 규칙(min-width:1100px)은 pc.css에만, pc.css의 규칙은 전부 @media 안에
  E5 css/에 새 파일 → 로드 순서(KNOWN_CSS)·CLAUDE.md·UI-STANDARDS 등록 후 사용
  R* 레거시 래칫(줄일 수만 있음): hex 색(layout·uplift·common), px line-height, 단계 밖 border-radius
예외가 꼭 필요하면 해당 줄 끝에 /* ui-lint: allow 사유 */ 를 단다(사유 필수).
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS_DIR = os.path.join(ROOT, 'css')
BASELINE = os.path.join(ROOT, 'scripts', 'ui_lint_baseline.json')

# 로드 순서 그대로. tokens=정의처, swiper=외부 라이브러리 → 검사 제외
KNOWN_CSS = ['tokens.css', 'common.css', 'layout.css', 'swiper.css', 'uplift.css', 'mvp.css', 'ds.css', 'pc.css']
SKIP_CSS = {'tokens.css', 'swiper.css'}
LEGACY_CSS = {'common.css', 'layout.css', 'uplift.css'}     # 하드코딩 색은 래칫(신규 추가 금지)
INLINE_SRC = ['scripts/generate.py'] + [f'js/{f}' for f in sorted(os.listdir(os.path.join(ROOT, 'js'))) if f.endswith('.js')]

# 12px 허용: 셀렉터의 마지막 클래스가 아래로 끝날 때만 (조상 클래스에 끌려가지 않도록)
BADGE_SUFFIX = ('badge', 'badge-item', 'chip', 'pill', 'tag', 'lg', 'ax', 'pop-p', 'rec-num', 'sep', 'cnt',
                'flag', 'dot', 'bubble', 'status-item', 'tags-item', 'legend-item', 'hotel-text', 'marker',
                'count', 'lang', 'hub-rank')
DECOR_RE = re.compile(r':(:)?(before|after)\b|emoji|\bico|\s i$|bt-q$')
RADIUS_OK = re.compile(r'^(0|50%|var\(--radius-[a-z]+\)|inherit)$')
HEX_RE = re.compile(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?:[0-9a-fA-F]{2})?\b')
ALLOW = 'ui-lint: allow'


def _last_cls(part):
    toks = part.split()
    cls = re.findall(r'\.([\w-]+)', toks[-1]) if toks else []
    return cls[-1] if cls else ''


def is_badge(sel):
    parts = [p.strip() for p in sel.split(',') if p.strip()]
    return bool(parts) and all(any(_last_cls(p) == b or _last_cls(p).endswith('-' + b) for b in BADGE_SUFFIX)
                               for p in parts)


def _strip_comments(src):
    # 주석은 같은 길이 공백으로 → 줄 번호 유지. 단 allow 주석은 남겨 판정에 쓴다
    def rep(m):
        t = m.group(0)
        return t if ALLOW in t else re.sub(r'[^\n]', ' ', t)
    return re.sub(r'/\*.*?\*/', rep, src, flags=re.S)


def iter_rules(src):
    """(selector, body, body_start_offset, depth, at_media) — 중첩 @media 지원하는 간단 파서"""
    out, stack, i, sel_start = [], [], 0, 0
    while i < len(src):
        c = src[i]
        if c == '{':
            head = src[sel_start:i].strip()
            stack.append((head, i))
            sel_start = i + 1
        elif c == '}':
            if stack:
                head, bstart = stack.pop()
                body = src[bstart + 1:i]
                if not head.startswith('@') and '{' not in body:
                    medias = [h for h, _ in stack if h.startswith('@media')]
                    out.append((head, body, bstart + 1, medias))
            sel_start = i + 1
        elif c == ';' and not stack:
            sel_start = i + 1
        i += 1
    return out


def _line(src, off):
    return src.count('\n', 0, off) + 1


def lint_css(name, src, errs, counts):
    rel = f'css/{name}'
    clean = _strip_comments(src)
    lines = src.split('\n')
    for sel, body, off, medias in iter_rules(clean):
        sel1 = ' '.join(sel.split())
        for m in re.finditer(r'([\w-]+)\s*:\s*([^;]+)', body):
            prop, val = m.group(1).lower(), m.group(2).strip()
            ln = _line(clean, off + m.start())
            if ALLOW in lines[ln - 1]:
                continue
            where = f'{rel}:{ln}  {sel1[:70]}'
            if prop == 'font-size':
                if re.search(r'\d(px|rem)\b', val) and not DECOR_RE.search(sel1):
                    errs.append(f'E1 {where} → font-size:{val} — var(--fs-*) 토큰만 사용')
                if 'var(--fs-micro)' in val and not is_badge(sel1):
                    errs.append(f'E2 {where} → 12px(--fs-micro)는 배지·범례 전용. 읽는 글자는 var(--fs-meta) 이상')
            if HEX_RE.search(val):
                if name in LEGACY_CSS:
                    counts[f'R-hex:{rel}'] = counts.get(f'R-hex:{rel}', 0) + 1
                else:
                    errs.append(f'E3 {where} → {prop}:{val} — 색은 tokens.css 변수만')
            if prop == 'line-height' and re.fullmatch(r'[\d.]+px', val):
                counts[f'R-lhpx:{rel}'] = counts.get(f'R-lhpx:{rel}', 0) + 1
            if prop == 'border-radius' and not all(RADIUS_OK.match(v) for v in val.split()):
                counts[f'R-radius:{rel}'] = counts.get(f'R-radius:{rel}', 0) + 1
        is_pc_media = any(re.search(r'min-width\s*:\s*1100px', h) for h in medias)
        hide_only = re.fullmatch(r'\s*display\s*:\s*none\s*(!important)?\s*;?\s*', body)  # 모바일에서 PC 전용 요소 숨김은 허용
        if name == 'pc.css' and not medias and not hide_only:
            errs.append(f'E4 {rel}:{_line(clean, off)}  {sel1[:70]} → pc.css 규칙은 @media(min-width:1100px) 안에만')
        if name != 'pc.css' and is_pc_media:
            errs.append(f'E4 {rel}:{_line(clean, off)}  {sel1[:70]} → PC(≥1100px) 규칙은 pc.css로')


def lint_inline(rel, src, errs):
    for ln, line in enumerate(src.split('\n'), 1):
        if ALLOW in line:
            continue
        for m in re.finditer(r'''style=\\?["']([^"']*)''', line):
            st = m.group(1)
            if re.search(r'font-size\s*:\s*[\d.]+px', st):
                errs.append(f'E1 {rel}:{ln} → 인라인 font-size px — 클래스+토큰으로')
            if HEX_RE.search(st):
                errs.append(f'E3 {rel}:{ln} → 인라인 style 색 {HEX_RE.search(st).group(0)} — var(--토큰)으로')


def collect():
    errs, counts = [], {}
    for name in sorted(os.listdir(CSS_DIR)):
        if not name.endswith('.css'):
            continue
        if name not in KNOWN_CSS:
            errs.append(f'E5 css/{name} → 미등록 CSS. 로드 순서(lint_ui.KNOWN_CSS·generate.head·CLAUDE.md) 등록 후 사용')
        if name in SKIP_CSS:
            continue
        with open(os.path.join(CSS_DIR, name), encoding='utf-8') as f:
            lint_css(name, f.read(), errs, counts)
    for rel in INLINE_SRC:
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                lint_inline(rel, f.read(), errs)
    base = {}
    if os.path.exists(BASELINE):
        with open(BASELINE, encoding='utf-8') as f:
            base = json.load(f)
    for k, n in sorted(counts.items()):
        if n > base.get(k, 0):
            rule, rel = k.split(':', 1)
            what = {'R-hex': 'hex 색', 'R-lhpx': 'px 줄간격', 'R-radius': '단계 밖 라운드'}[rule]
            errs.append(f'{rule} {rel} → {what} {base.get(k, 0)}→{n}개로 늘어남. 늘리지 말고 토큰(var(--*))으로')
    return errs, counts, base


def run(strict=True):
    """generate.py 빌드 게이트. 위반 시 strict면 SystemExit."""
    errs, counts, base = collect()
    if not errs:
        print('UI lint OK (디자인 시스템 v2)')
        return True
    print(f'UI lint 위반 {len(errs)}건 — UI-STANDARDS.md §0·§14 참고:')
    for e in errs:
        print('  ' + e)
    if strict and os.environ.get('CF_UI_LINT') != 'warn':
        raise SystemExit('빌드 중단: UI 규칙 위반을 고치세요 (긴급 배포만 CF_UI_LINT=warn)')
    return False


def hook():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    fp = (data.get('tool_input') or {}).get('file_path') or ''
    rel = os.path.relpath(os.path.abspath(fp), ROOT).replace('\\', '/') if fp else ''
    if not (rel.startswith('css/') or rel.startswith('js/') or rel == 'scripts/generate.py'):
        return 0
    errs, _, _ = collect()
    mine = [e for e in errs if f' {rel}' in e or (rel.startswith('css/') and e.startswith('E5'))]
    if not mine:
        return 0
    sys.stderr.write(f'[UI 규칙 v2] {rel} 위반 {len(mine)}건 — 고친 뒤 계속하세요 (UI-STANDARDS.md §0·§14):\n')
    for e in mine[:20]:
        sys.stderr.write('  ' + e + '\n')
    return 2


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    if '--hook' in sys.argv:
        sys.exit(hook())
    if '--update-baseline' in sys.argv:
        errs, counts, base = collect()
        grew = {k: (base.get(k, 0), n) for k, n in counts.items() if n > base.get(k, 0)}
        if base and grew:
            print('기준선을 늘릴 수 없습니다(래칫):', grew)
            sys.exit(1)
        with open(BASELINE, 'w', encoding='utf-8') as f:
            json.dump(dict(sorted(counts.items())), f, ensure_ascii=False, indent=1)
        print('baseline 갱신:', dict(sorted(counts.items())))
        return
    sys.exit(0 if run(strict=False) else 1)


if __name__ == '__main__':
    main()

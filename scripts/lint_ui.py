# -*- coding: utf-8 -*-
"""캐치플로 UI 규칙 검사기 — 디자인 시스템 v3(UI-STANDARDS §0·§3·§14, 근거 DESIGN-SYSTEM-V3 §8-2)를 기계적으로 강제한다.

사용:
  python scripts/lint_ui.py                   # 전체 검사 (위반 시 exit 1)
  python scripts/lint_ui.py --counts          # 래칫 카운터 현재값 / 기준선 표
  python scripts/lint_ui.py --update-baseline # 래칫 기준을 현재값으로 갱신(줄어든 경우에만 쓰기)
                                              # (+ --allow-new: 규칙을 새로 만들 때만, 기준선에 없던 항목 등록)
  python scripts/lint_ui.py --hook            # Claude Code PostToolUse 훅 (stdin JSON, 위반 시 exit 2)
generate.py가 빌드 시작 때 run()을 호출한다 → 위반이 있으면 빌드 실패(긴급 시 CF_UI_LINT=warn).

오류(E — 바로 빌드 중단)
  E0  정의되지 않은 var(--x) 금지(폴백 있는 var(--x, …)·Swiper 변수 제외) — 토큰을 지웠는데 참조가 남아 조용히 상속값으로 떨어지는 회귀 방지
  E1  font-size는 var(--fs-*)만. px 직접 기입 금지 (::before/::after 장식 글리프·아이콘 컨테이너 면제)
  E2  var(--fs-micro)(13px)는 배지·알약·범례·축 라벨 전용. 읽는 글자는 --fs-meta(14px) 이상
  E3  색은 tokens.css 변수만. hex 직접 기입 금지 (mvp·ds·pc·신규 CSS, generate.py/js 인라인 style)
  E4  PC 전용 규칙(min-width:1100px)은 pc.css에만, pc.css의 규칙은 전부 @media 안에
  E5  css/에 새 파일 → 로드 순서(KNOWN_CSS)·CLAUDE.md·UI-STANDARDS 등록 후 사용
  E10 .ov-panel의 border-radius는 var(--radius-sheet) 또는 0만 (오버레이 해부도, UI-STANDARDS §17)
  E11 .ov-close·.ov-back·.btn-icon의 width·height는 var(--h-icon)·var(--h-circle)만
  E15 var(--fs-card)(15px)는 호텔 카드(.hcard) 안에서만
래칫(R — 파일별 개수가 기준선 scripts/ui_lint_baseline.json보다 늘면 오류. 줄일 수만 있고, 0이 되면 E로 승격)
  R-hex 레거시 CSS hex · R-lhpx px 행간 · R-radius 단계 밖 라운드 · R-ctrlh 버튼·칩 px 높이
  R-fslegacy (구) 토큰 사용(--fs-caption·--fs-body-sm·--fw-medium·--lh-head·--h-btn-lg·--section-y …) → 0이면 E7
  R-e6 제목 크기 규칙의 굵기가 var(--fw-bold)/var(--fw-display)가 아님 → 0이면 E6
  R-fw500 리터럴 font-weight:500 · R-ls 14px 이하 음수 자간·body/html/* 자간 → 0이면 E8
  R-lhnum line-height가 var(--lh-*)·1이 아님(px 제외) → 0이면 E9 · R-ovdim 딤 면이 var(--ov-dim*)가 아님 → E10a
  R-z 고정·sticky 또는 10 이상 z-index가 var(--z-*)가 아님 · R-primary 보라(--primary*) 사용 · R-primarylink 링크 보라 글자
  R-ovlegacy 레거시 오버레이 클래스·CF.sheet 밖 is-open 토글 → 0이면 E13 · R-ink2 var(--ink-2) 사용 · R-jshex JS hex 색 문자열
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
                'count', 'lang', 'hub-rank', 'counter', 'rank-badge')
DECOR_RE = re.compile(r':(:)?(before|after)\b|emoji|\bico|\s i$|bt-q$')
CTRL_RE = re.compile(r'(btn|button|chip|tab|cta|toggle|more|sort|switch|-go|-add|-pill|-float)$')  # 버튼류 마지막 클래스
RADIUS_OK = re.compile(r'^(0|50%|var\(--radius-[a-z]+\)|inherit)$')
HEX_RE = re.compile(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?:[0-9a-fA-F]{2})?\b')
ALLOW = 'ui-lint: allow'

# ── v3 래칫·E 규칙 정의 (DESIGN-SYSTEM-V3 §8-2) ──
LEGACY_TOK_RE = re.compile(r'var\(\s*--(fs-(?:display|h1|pc-h1|lead|body-lg|body-sm|caption|num-lg|num)|fw-medium|lh-tight|lh-head'
                           r'|h-btn-lg|section-y|section-gap|ls-global|ls-body|shadow-search)(?![\w-])')
TITLE_FS_RE = re.compile(r'var\(--fs-(title-xl|title|h2|h3|hero|num-xl|display|h1|pc-h1|lead|num-lg|num)\)')
TITLE_FW_OK = re.compile(r'^var\(--fw-(bold|display)\)$')
PRIMARY_RE = re.compile(r'var\(--primary(?:-deep|-cta|-color)?\)')
PRIMARY_OK_SUFFIX = ('brand', 'cta', 'heart', 'saved', 'logo', 'chart', 'hero-key')
DIM_RE = re.compile(r'(dim|dimmed|scrim|backdrop)$')
OV_LEGACY_RE = re.compile(r'\b(review-sheet|blog-sheet|cf-modal|cmp-pick|det-drawer|sheet-grab|sheet-panel|cp-panel|dd-panel)\b'
                          r'|(?:addClass|classList\.add)\(\s*[\'"]is-open[\'"]')
JSHEX_RE = re.compile(r'''(?<![\w-])['"`]\s*#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?:[0-9a-fA-F]{2})?\s*['"`]''')
VAR_RE = re.compile(r'var\(\s*(--[\w-]+)\s*([,)])')
VAR_EXEMPT = re.compile(r'^--swiper-')
RULE_WHAT = {'R-hex': 'hex 색', 'R-lhpx': 'px 줄간격', 'R-radius': '단계 밖 라운드', 'R-ctrlh': '버튼·칩 px 높이',
             'R-fslegacy': '(구) 토큰 사용', 'R-e6': '제목 굵기가 --fw-bold 아님', 'R-fw500': 'font-weight:500',
             'R-ls': '14px 이하 음수 자간·body 자간', 'R-lhnum': 'line-height 토큰 밖 값', 'R-ovdim': '딤 면이 --ov-dim 아님',
             'R-z': 'z-index 토큰 밖 값', 'R-primary': '보라(--primary*) 사용', 'R-primarylink': '링크 보라 글자',
             'R-ovlegacy': '레거시 오버레이 클래스·is-open 토글', 'R-ink2': 'var(--ink-2) 사용', 'R-jshex': 'JS hex 색 문자열'}


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
    def bump(rule, n=1):
        counts[f'{rule}:{rel}'] = counts.get(f'{rule}:{rel}', 0) + n
    for sel, body, off, medias in iter_rules(clean):
        sel1 = ' '.join(sel.split())
        decls = {}
        for m in re.finditer(r'([\w-]+)\s*:\s*([^;]+)', body):
            decls[m.group(1).lower()] = (m.group(2).strip(), _line(clean, off + m.start()))
        parts = [p.strip() for p in sel1.split(',') if p.strip()]
        last_cls = [_last_cls(p) for p in parts]
        n_ov = len(OV_LEGACY_RE.findall(sel1))
        if n_ov:
            bump('R-ovlegacy', n_ov)
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
                    errs.append(f'E2 {where} → --fs-micro(13px)는 배지·범례 전용. 읽는 글자는 var(--fs-meta)(14px) 이상')
                if 'var(--fs-card)' in val and not all(re.search(r'\.hcard\b', p) for p in parts):
                    errs.append(f'E15 {where} → --fs-card(15px)는 호텔 카드(.hcard) 안에서만')
                ws = decls.get('font-weight')
                if TITLE_FS_RE.search(val) and ws and not TITLE_FW_OK.match(ws[0]):
                    bump('R-e6')
                if re.search(r'var\(--fs-(meta|micro)\)', val) and re.match(r'-', decls.get('letter-spacing', ('',))[0]):
                    bump('R-ls')
            if HEX_RE.search(val):
                if name in LEGACY_CSS:
                    bump('R-hex')
                else:
                    errs.append(f'E3 {where} → {prop}:{val} — 색은 tokens.css 변수만')
            n_leg = len(LEGACY_TOK_RE.findall(val))
            if n_leg:
                bump('R-fslegacy', n_leg)
            if 'var(--ink-2)' in val:
                bump('R-ink2', val.count('var(--ink-2)'))
            if prop == 'font-weight' and val == '500':
                bump('R-fw500')
            if prop == 'letter-spacing' and any(re.fullmatch(r'(html|body|\*)', p) for p in parts):
                bump('R-ls')
            if prop == 'line-height':
                if re.fullmatch(r'[\d.]+px', val):
                    bump('R-lhpx')
                elif not re.fullmatch(r'var\(--lh-[\w-]+\)|1|0', val):
                    bump('R-lhnum')
            if prop == 'height' and re.fullmatch(r'\d+px', val) and CTRL_RE.search(_last_cls(sel1.split(',')[-1])) and not DECOR_RE.search(sel1):
                bump('R-ctrlh')
            if prop == 'border-radius' and not all(RADIUS_OK.match(v) for v in val.split()):
                bump('R-radius')
            if prop in ('background', 'background-color') and any(DIM_RE.search(c) for c in last_cls) \
                    and not re.fullmatch(r'var\(--(ov-dim[\w-]*|scrim-photo)\)|none|transparent', val):
                bump('R-ovdim')
            if prop == 'z-index' and not val.startswith('var(--z-'):
                pos = decls.get('position', ('',))[0]
                if pos in ('fixed', 'sticky') or (re.fullmatch(r'-?\d+', val) and int(val) >= 10):
                    bump('R-z')
            if (prop in ('color', 'background', 'background-color', 'fill', 'stroke', 'outline', 'outline-color', 'box-shadow')
                    or prop.startswith('border')) and PRIMARY_RE.search(val):
                if not all(c.endswith(PRIMARY_OK_SUFFIX) for c in last_cls if c) or not any(last_cls):
                    bump('R-primary')
                    if prop == 'color' and any(re.search(r'(^|[\s>+~])a(\.|:|\[|$)|link', p.split()[-1]) for p in parts):
                        bump('R-primarylink')
            if 'radius' in prop and 'ov-panel' in last_cls and not re.fullmatch(r'var\(--radius-sheet\)|0', val):
                errs.append(f'E10 {where} → .ov-panel 라운드는 var(--radius-sheet) 또는 0')
            if prop in ('width', 'height') and any(c in ('ov-close', 'ov-back', 'btn-icon') for c in last_cls) \
                    and not DECOR_RE.search(sel1) and not re.fullmatch(r'var\(--h-(icon|circle)\)', val):
                errs.append(f'E11 {where} → {prop}:{val} — 아이콘 버튼은 var(--h-icon)·var(--h-circle)만')
        is_pc_media = any(re.search(r'min-width\s*:\s*1100px', h) for h in medias)
        hide_only = re.fullmatch(r'\s*display\s*:\s*none\s*(!important)?\s*;?\s*', body)  # 모바일에서 PC 전용 요소 숨김은 허용
        if name == 'pc.css' and not medias and not hide_only:
            errs.append(f'E4 {rel}:{_line(clean, off)}  {sel1[:70]} → pc.css 규칙은 @media(min-width:1100px) 안에만')
        if name != 'pc.css' and is_pc_media:
            errs.append(f'E4 {rel}:{_line(clean, off)}  {sel1[:70]} → PC(≥1100px) 규칙은 pc.css로')


def lint_inline(rel, src, errs, counts):
    def bump(rule, n=1):
        counts[f'{rule}:{rel}'] = counts.get(f'{rule}:{rel}', 0) + n
    for ln, line in enumerate(src.split('\n'), 1):
        if ALLOW in line:
            continue
        for m in re.finditer(r'''style=\\?["']([^"']*)''', line):
            st = m.group(1)
            if re.search(r'font-size\s*:\s*[\d.]+px', st):
                errs.append(f'E1 {rel}:{ln} → 인라인 font-size px — 클래스+토큰으로')
            if HEX_RE.search(st):
                errs.append(f'E3 {rel}:{ln} → 인라인 style 색 {HEX_RE.search(st).group(0)} — var(--토큰)으로')
        n = len(LEGACY_TOK_RE.findall(line))
        if n:
            bump('R-fslegacy', n)
        if 'var(--ink-2)' in line:
            bump('R-ink2', line.count('var(--ink-2)'))
        n = len(OV_LEGACY_RE.findall(line))
        if n:
            bump('R-ovlegacy', n)
        n = len(JSHEX_RE.findall(line))
        if n:
            bump('R-jshex', n)


def _defined_vars():
    """CSS 사용자 정의 속성 정의처: css/*.css 선언 + generate.py·js의 인라인 style·setProperty"""
    defs = set()
    for name in os.listdir(CSS_DIR):
        if name.endswith('.css'):
            with open(os.path.join(CSS_DIR, name), encoding='utf-8') as f:
                defs |= set(re.findall(r'(--[\w-]+)\s*:', _strip_comments(f.read())))
    for rel in INLINE_SRC:
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                t = f.read()
            defs |= set(re.findall(r'(--[\w-]+)\s*:', t))
            defs |= set(re.findall(r'''setProperty\(\s*['"](--[\w-]+)''', t))
    return defs


def lint_vars(rel, src, defs, errs):
    """E0 정의되지 않은 var(--x) — 폴백 있는 var(--x, …)와 Swiper 변수는 제외"""
    for m in VAR_RE.finditer(src):
        name, end = m.group(1), m.group(2)
        if end == ',' or name in defs or VAR_EXEMPT.match(name):
            continue
        ln = src.count('\n', 0, m.start()) + 1
        errs.append(f'E0 {rel}:{ln} → var({name}) — 정의되지 않은 토큰(tokens.css에 없음). 지운 토큰이면 새 토큰으로 바꿀 것')


def collect():
    errs, counts = [], {}
    defs = _defined_vars()
    for name in sorted(os.listdir(CSS_DIR)):
        if not name.endswith('.css'):
            continue
        if name not in KNOWN_CSS:
            errs.append(f'E5 css/{name} → 미등록 CSS. 로드 순서(lint_ui.KNOWN_CSS·generate.head·CLAUDE.md) 등록 후 사용')
        if name in SKIP_CSS:
            continue
        with open(os.path.join(CSS_DIR, name), encoding='utf-8') as f:
            src = f.read()
        lint_css(name, src, errs, counts)
        lint_vars(f'css/{name}', _strip_comments(src), defs, errs)
    for rel in INLINE_SRC:
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                src = f.read()
            lint_inline(rel, src, errs, counts)
            lint_vars(rel, src, defs, errs)
    base = {}
    if os.path.exists(BASELINE):
        with open(BASELINE, encoding='utf-8') as f:
            base = json.load(f)
    for k, n in sorted(counts.items()):
        if n > base.get(k, 0):
            rule, rel = k.split(':', 1)
            what = RULE_WHAT.get(rule, rule)
            errs.append(f'{rule} {rel} → {what} {base.get(k, 0)}→{n}개로 늘어남. 늘리지 말고 v3 토큰으로(UI-STANDARDS §0·§14)')
    return errs, counts, base


def run(strict=True):
    """generate.py 빌드 게이트. 위반 시 strict면 SystemExit."""
    errs, counts, base = collect()
    if not errs:
        print('UI lint OK (디자인 시스템 v3)')
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
    sys.stderr.write(f'[UI 규칙 v3] {rel} 위반 {len(mine)}건 — 고친 뒤 계속하세요 (UI-STANDARDS.md §0·§14):\n')
    for e in mine[:20]:
        sys.stderr.write('  ' + e + '\n')
    return 2


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    if '--hook' in sys.argv:
        sys.exit(hook())
    if '--counts' in sys.argv:
        errs, counts, base = collect()
        rules = {}
        for k in set(counts) | set(base):
            r, rel = k.split(':', 1)
            rules.setdefault(r, []).append((rel, counts.get(k, 0), base.get(k, 0)))
        for r in sorted(rules):
            tot = sum(c for _, c, _ in rules[r])
            print(f'{r:14s} {tot:5d}  ' + ' · '.join(f'{rel.split("/")[-1]} {c}' + (f'(기준 {b})' if b != c else '')
                                                   for rel, c, b in sorted(rules[r]) if c or b))
        return
    if '--update-baseline' in sys.argv:
        errs, counts, base = collect()
        # 기존 항목은 늘릴 수 없음. 새 항목(규칙 신설)은 --allow-new 를 명시할 때만 등록
        allow_new = '--allow-new' in sys.argv
        grew = {k: (base.get(k, 0), n) for k, n in counts.items()
                if n > base.get(k, 0) and not (allow_new and k not in base)}
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

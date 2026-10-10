/* 캐치플로 맞춤 추천 (recommend.js) — 2026-10-10 바텀시트 마법사 → 페이지(recommend.html)
   - 페이지(#rw-steps)를 그린다: Airbnb 숙소 검색처럼 단계 카드 4장이 위에서 아래로 쌓이고, 지금 단계만 펼쳐진다.
     1 도시(후쿠오카만, 나머지 준비 중) → 2 동네 → 3 못 참는 것(최대 3, 고른 순서 = 중요도) + 1년 안 0건 조건 → 4 1박 예산(평일/주말)
     고르면 다음 단계가 자동으로 펼쳐지고, 접힌 카드엔 고른 값이 보인다(누르면 다시 펼침).
   - '추천 호텔 보기' → search.html?rec=1&pr=..&bud=..&bw=1&area=..&no=.. (검색 rec 모드. URL 파라미터는 예전 그대로)
   - 고른 값은 이 페이지 URL에도 남겨(replaceState) 결과에서 뒤로 오면 그대로 복원.
   - 다른 페이지: 홈 '추천받기'는 이 페이지 링크, 검색 rec 헤더 '조건 수정'(.rec-reset)은 지금 조건을 들고 이 페이지로 온다.
   - 공유 상수(CFRec.CATS 등)는 검색 rec 모드에서도 사용 — 이름·값 바꾸지 말 것.
   의존 없음(바닐라). 모든 페이지 head에서 로드된다. */
(function () {
  /* 내부 카테고리 키(ko)는 분류 v5 점수 대분류 6개(청결/냄새/소음/객실/직원/위치)와 일치해야
     검색 rec 모드의 matchScore(h.cs[ko])가 동작한다. code는 URL 파라미터라 v4 값 유지. 라벨은 고객 언어(UI-STANDARDS §8). */
  var CATS = [
    { code: 'hyg',    ko: '청결', label: '더러운 건 못 참아',        kw: '머리카락·벌레·곰팡이',    chip: '청결' },
    { code: 'smell',  ko: '냄새', label: '냄새나는 방은 못 참아',    kw: '담배·하수구·곰팡내',      chip: '냄새' },
    { code: 'noise',  ko: '소음', label: '시끄러우면 못 자',          kw: '옆방·도로·기계음',        chip: '조용' },
    { code: 'fac',    ko: '객실', label: '좁고 낡은 방은 실망이야',  kw: '좁은 방·침대·온도·고장',  chip: '객실' },
    { code: 'svc',    ko: '직원', label: '불친절은 못 넘어가',        kw: '직원 응대·대기',          chip: '응대' },
    { code: 'locsaf', ko: '위치', label: '위치가 제일 중요해',        kw: '역까지 거리·밤길',        chip: '위치' }
  ];
  // 예산 구간 = generate.py PRICE_BANDS(평일 4)·PRICE_BANDS_WE(주말 4) — 빌드가 window.CF_PRICE_BANDS로 주입 (2026-10-10 분포 기준)
  var PB = window.CF_PRICE_BANDS || { wd: [['b1', '10만원 미만'], ['b2', '10~15만원'], ['b3', '15~20만원'], ['b4', '20만원 이상']],
                                      we: [['w1', '30만원 미만'], ['w2', '30~40만원'], ['w3', '40~50만원'], ['w4', '50만원 이상']] };
  var ANY = { code: '', label: '상관없어요' };
  var BUDGETS = [ANY].concat(PB.wd.map(function (x) { return { code: x[0], label: x[1] }; }));
  var BUDGETS_W = [ANY].concat(PB.we.map(function (x) { return { code: x[0], label: x[1] }; }));
  var AREA_DESC = { hakata: '신칸센·공항 이동 편리', tenjin: '쇼핑·맛집 중심가', nakasu: '야타이·나이트라이프', gion: '조용한 구시가' };
  var AREA_REC = { hakata: 1, tenjin: 1 };   // '추천' 딱지 — 카페 1,000건 중 하카타 160·텐진 131건 (FEEDBACK-2610 §8)
  /* '1년 안에 한 번도 없어야' 조건 (FEEDBACK-2610 §6) — 키는 검색 인덱스 h.x와 같고 URL no= 값. 심각 리뷰만 센다 */
  // 2026-10-10: '벌레 전부'(날파리·모기 포함, 후보의 절반 제외) 삭제 → '빈대' 추가. '객실 보안·밤길'은 실제로 세는 객실 보안(무단 입실·잠금·사생활)에 맞춰 이름 변경
  var MUSTS = [
    { code: 'roach',  label: '바퀴벌레', chip: '바퀴벌레 0건' },
    { code: 'bedbug', label: '빈대', chip: '빈대 0건' },
    { code: 'safe',   label: '방 잠금·무단 출입', chip: '무단 출입·잠금 문제 0건' }
  ];
  var NO_SHORT = { roach: '바퀴벌레', bedbug: '빈대', safe: '무단 출입' };   // 접힌 카드 요약용 (검색 rec 헤더와 같은 말)
  // 1단계 도시 — 검색 도시 필터(generate.py f-city)와 같은 목록. 후쿠오카만 고를 수 있다
  var CITIES = [
    { code: 'fukuoka', ko: '후쿠오카', on: true },
    { code: 'tokyo', ko: '도쿄' },
    { code: 'osaka', ko: '오사카' },
    { code: 'kyoto', ko: '교토' }
  ];
  var byCode = {}; CATS.forEach(function (c) { byCode[c.code] = c; });
  var mustBy = {}; MUSTS.forEach(function (m) { mustBy[m.code] = m; });
  // 정리된 목록 반환. 예전 공유 링크의 no=bug(벌레 전부)는 바퀴벌레+빈대로 바꿔 읽는다
  function normNo(arr) {
    var a = [];
    (arr || []).forEach(function (c) { if (c === 'bug') a.push('roach', 'bedbug'); else a.push(c); });
    a = a.filter(function (c) { return mustBy[c]; });
    return a.filter(function (c, i) { return a.indexOf(c) === i; });
  }

  // 사이트 루트 — 이 스크립트를 부른 경로('js/..' / '../js/..')에서 계산 (상세·허브는 한 단계 아래)
  var ROOT = (function () {
    var s = (document.currentScript && document.currentScript.getAttribute('src')) || '';
    var i = s.indexOf('js/recommend.js');
    return i > 0 ? s.slice(0, i) : './';
  })();

  // 조건 → URL 쿼리 (검색 rec 모드가 읽는 형식)
  function qsOf(p) {
    var q = 'pr=' + p.pr.join(',');
    if (p.bud) q += '&bud=' + p.bud;
    if (p.bud && p.bw) q += '&bw=1';
    if (p.area) q += '&area=' + p.area;
    if (p.no && p.no.length) q += '&no=' + normNo(p.no).join(',');
    return q;
  }
  // 다른 페이지에서 추천 페이지로 (preset이 있으면 그 조건을 채운 채로)
  function openPage(preset) {
    preset = preset || {};
    var pr = (preset.pr || []).filter(function (c) { return byCode[c]; });
    location.href = ROOT + 'recommend' + (pr.length ? '?' + qsOf({ pr: pr, bud: preset.bud, bw: preset.bw, area: preset.area, no: preset.no }) : '');
  }

  window.CFRec = { CATS: CATS, BUDGETS: BUDGETS, BUDGETS_W: BUDGETS_W, AREA_DESC: AREA_DESC, MUSTS: MUSTS, mustBy: mustBy, normNo: normNo, byCode: byCode, open: openPage };

  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function ev(name, p) { if (typeof gtag === 'function') gtag('event', name, p || {}); }
  function toast(msg) {
    var el = document.createElement('div'); el.className = 'cf-toast'; el.textContent = msg;
    document.body.appendChild(el);
    requestAnimationFrame(function () { el.classList.add('show'); });
    setTimeout(function () { el.classList.remove('show'); setTimeout(function () { el.remove(); }, 300); }, 1800);
  }

  // ═════════ 추천 페이지 ═════════
  var AREAS = window.CF_AREAS || [];
  var CITY = { code: 'fukuoka', ko: '후쿠오카', n: 0 };   // mount 때 window.CF_REC_CITY(페이지 본문 스크립트)로 채운다
  /* 상태: city ''=아직 · area null=아직 / ''=어디든 · sel 고른 순서 = 중요도 · bud null=아직 / ''=상관없어요 · open 펼친 단계(0 = 모두 접힘) */
  var S = { city: '', area: null, sel: [], no: [], bud: null, bw: false, open: 1 };
  var listEl = null;

  var CHECK = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M3 7.2 5.8 10 11 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  function catName(c) { return (window.CAT_KO && window.CAT_KO[c.ko]) || c.ko; }
  function areaKo(code) { var a = AREAS.filter(function (x) { return x.code === code; })[0]; return a ? a.ko : ''; }
  function budLabel() {
    var b = (S.bw ? BUDGETS_W : BUDGETS).filter(function (x) { return x.code === S.bud; })[0];
    return b ? b.label : '';
  }
  function isDone(n) {
    return n === 1 ? !!S.city : n === 2 ? S.area !== null : n === 3 ? S.sel.length > 0 : S.bud !== null;
  }
  // 접힌 카드 오른쪽 값 [본 줄, 둘째 줄]
  function summary(n) {
    if (!isDone(n)) return ['골라 주세요', ''];
    if (n === 1) return [CITY.ko, ''];
    if (n === 2) return [S.area ? areaKo(S.area) : '어디든 좋아요', ''];
    if (n === 3) return [S.sel.map(function (c) { return catName(byCode[c]); }).join('·'),
                         S.no.length ? S.no.map(function (k) { return NO_SHORT[k]; }).join('·') + ' 없는 곳만' : ''];
    return [S.bud ? (S.bw ? '주말 ' : '평일 ') + budLabel() : '상관없어요', ''];
  }

  var LABELS = { 1: '도시', 2: '동네', 3: '못 참는 것', 4: '1박 예산' };

  function numHtml(n, on) {
    return '<span class="rw-num' + (on ? ' is-on' : isDone(n) ? ' is-done' : '') + '" aria-hidden="true">' + (!on && isDone(n) ? CHECK : n) + '</span>';
  }

  function rowHtml(n) {
    var lock = n > 1 && !S.city;   // 도시를 고르기 전엔 2~4단계 잠금 (동네가 도시에 딸려 있어서)
    var v = summary(n);
    return '<li class="rw-step' + (lock ? ' is-lock' : '') + '" data-step="' + n + '">' +
      '<button type="button" class="rw-row" data-open="' + n + '" aria-expanded="false"' + (lock ? ' aria-disabled="true"' : '') + '>' +
        numHtml(n, false) +
        '<span class="rw-label">' + LABELS[n] + '</span>' +
        (lock ? '' : '<span class="rw-val' + (isDone(n) ? '' : ' is-empty') + '">' + esc(v[0]) +
          (v[1] ? '<span class="rw-val-sub">' + esc(v[1]) + '</span>' : '') + '</span>') +
      '</button></li>';
  }

  function radio(on) { return '<span class="rw-radio' + (on ? ' is-on' : '') + '" aria-hidden="true"></span>'; }

  function bodyHtml(n) {
    if (n === 1) {
      return '<h2 class="rw-q">어느 도시로 여행 가세요?</h2>' +
        '<p class="rw-sub">지금은 ' + esc(CITY.ko) + '만 분석하고 있어요</p>' +
        '<div class="rw-opts" role="radiogroup" aria-label="도시">' + CITIES.map(function (c) {
          var on = S.city === c.code;
          if (!c.on) {
            return '<button type="button" class="rw-opt is-off" aria-disabled="true" data-soon="' + c.ko + '">' +
              '<span class="rw-opt-txt"><span class="rw-opt-t">' + c.ko + '</span></span>' +
              '<span class="rw-soon-tag">준비 중</span></button>';
          }
          return '<button type="button" class="rw-opt' + (on ? ' is-on' : '') + '" role="radio" aria-checked="' + on + '" data-city="' + c.code + '">' +
            '<span class="rw-opt-txt"><span class="rw-opt-t">' + esc(CITY.ko) + '</span>' +
              (CITY.n ? '<span class="rw-opt-d">호텔 ' + CITY.n + '곳의 리뷰를 분석했어요</span>' : '') + '</span>' +
            radio(on) + '</button>';
        }).join('') + '</div>';
    }
    if (n === 2) {
      var opts = [{ code: '', ko: '어디든 좋아요', desc: CITY.ko + ' 전체에서 찾아요' }].concat(AREAS.map(function (a) {
        return { code: a.code, ko: a.ko, desc: AREA_DESC[a.code] || '' };
      }));
      return '<h2 class="rw-q">' + esc(CITY.ko) + ' 어느 동네에 머물까요?</h2>' +
        '<p class="rw-sub">고른 동네 가까이 있는 호텔만 보여 드려요</p>' +
        '<div class="rw-opts" role="radiogroup" aria-label="동네">' + opts.map(function (a) {
          var on = S.area === a.code;
          return '<button type="button" class="rw-opt' + (on ? ' is-on' : '') + '" role="radio" aria-checked="' + on + '" data-area="' + a.code + '">' +
            '<span class="rw-opt-txt"><span class="rw-opt-t">' + esc(a.ko) + (AREA_REC[a.code] ? '<span class="rw-rec-tag">추천</span>' : '') + '</span>' +
              (a.desc ? '<span class="rw-opt-d">' + esc(a.desc) + '</span>' : '') + '</span>' +
            radio(on) + '</button>';
        }).join('') + '</div>';
    }
    if (n === 3) {
      return '<h2 class="rw-q">여행할 때 이것만은 못 참아요</h2>' +
        '<p class="rw-sub">중요한 순서대로 최대 3개 골라 주세요</p>' +
        '<div class="rw-opts" role="group" aria-label="못 참는 것">' + CATS.map(function (c) {
          var r = S.sel.indexOf(c.code);
          return '<button type="button" class="rw-opt' + (r >= 0 ? ' is-on' : '') + '" aria-pressed="' + (r >= 0) + '" data-cat="' + c.code + '">' +
            '<span class="rw-opt-txt"><span class="rw-opt-t">' + c.label + '</span><span class="rw-opt-d">' + c.kw + '</span></span>' +
            '<span class="rw-rank' + (r >= 0 ? ' is-on' : '') + '" aria-hidden="true">' + (r >= 0 ? r + 1 : '') + '</span></button>';
        }).join('') + '</div>' +
        '<div class="rw-must">' +
          '<div class="rw-must-t">이건 1년 안에 한 번도 없어야 해요</div>' +
          '<p class="rw-must-d">최근 1년 리뷰에 한 번이라도 나온 곳은 빼 드려요. 안 골라도 돼요</p>' +
          '<div class="rw-must-list">' + MUSTS.map(function (m) {
            var on = S.no.indexOf(m.code) >= 0;
            return '<button type="button" class="rw-must-chip' + (on ? ' is-on' : '') + '" aria-pressed="' + on + '" data-must="' + m.code + '">' + m.label + '</button>';
          }).join('') + '</div>' +
        '</div>' +
        '<button type="button" class="rw-next-btn" data-next="3"' + (S.sel.length ? '' : ' aria-disabled="true"') + '>' + (isDone(4) ? '확인' : '다음') + '</button>';
    }
    var list = (S.bw ? BUDGETS_W : BUDGETS);
    return '<h2 class="rw-q">1박 예산은 어느 정도예요?</h2>' +
      '<div class="rw-seg" role="group" aria-label="예산 기준">' +
        '<button type="button" class="rw-seg-btn' + (S.bw ? '' : ' is-on') + '" data-bw="0" aria-pressed="' + !S.bw + '">평일 기준</button>' +
        '<button type="button" class="rw-seg-btn' + (S.bw ? ' is-on' : '') + '" data-bw="1" aria-pressed="' + S.bw + '">주말(금·토) 기준</button>' +
      '</div>' +
      '<p class="rw-sub">' + (S.bw ? '금·토 밤, 2인 1박 기준이에요' : '일~목 밤, 2인 1박 기준이에요') + '</p>' +
      '<div class="rw-opts" role="radiogroup" aria-label="1박 예산">' + list.map(function (b) {
        var on = S.bud === b.code;
        return '<button type="button" class="rw-opt' + (on ? ' is-on' : '') + '" role="radio" aria-checked="' + on + '" data-bud="' + b.code + '">' +
          '<span class="rw-opt-txt"><span class="rw-opt-t">' + b.label + '</span></span>' + radio(on) + '</button>';
      }).join('') + '</div>';
  }

  function render(scroll) {
    var h = '';
    for (var n = 1; n <= 4; n++) {
      if (S.open === n) {
        h += '<li class="rw-step is-open" data-step="' + n + '">' +
          '<div class="rw-kicker">' + numHtml(n, true) + '<span class="rw-label">' + n + '단계 · ' + LABELS[n] + '</span></div>' +
          bodyHtml(n) + '</li>';
      } else h += rowHtml(n);
    }
    listEl.innerHTML = h;
    var go = document.querySelector('#recp .rw-go-btn');
    if (go) go.classList.toggle('is-ready', !!S.city && S.sel.length > 0);
    if (scroll) {
      var el = listEl.querySelector('.rw-step.is-open');
      if (!el) return;
      var r = el.getBoundingClientRect();
      // 펼친 카드 머리가 화면 위로 숨었거나 화면 아래쪽에 있으면 머리가 헤더 바로 밑에 오게
      if (r.top < 72 || r.top > window.innerHeight * 0.45) {
        window.scrollTo({ top: window.pageYOffset + r.top - 80, behavior: 'smooth' });
      }
    }
  }

  // 고른 뒤 다음으로: 아직 안 고른 다음 단계를 펼치고, 다 골랐으면 모두 접는다
  function advance(from) {
    for (var n = from + 1; n <= 4; n++) if (!isDone(n)) { S.open = n; return; }
    for (n = 1; n < from; n++) if (!isDone(n)) { S.open = n; return; }
    S.open = 0;
  }

  function saveUrl() {   // 결과에서 뒤로 왔을 때 복원용 (공유해도 같은 조건이 채워진다)
    try {
      if (!S.sel.length) { history.replaceState(null, '', location.pathname); return; }
      history.replaceState(null, '', location.pathname + '?' + qsOf({ pr: S.sel, bud: S.bud, bw: S.bw, area: S.area, no: S.no }));
    } catch (e) {}
  }

  function submit() {
    if (!S.city) { S.open = 1; render(true); toast('먼저 도시를 골라 주세요'); return; }
    if (!S.sel.length) { S.open = 3; render(true); toast('못 참는 것을 1개 이상 골라 주세요'); return; }
    saveUrl();
    var qs = qsOf({ pr: S.sel, bud: S.bud, bw: S.bw, area: S.area, no: S.no });
    ev('rec_submit', { pr: S.sel.join(','), area: S.area || 'any', bud: S.bud || 'any', bw: S.bw ? 1 : 0, no: S.no.join(',') });
    var ld = document.querySelector('#recp .rw-loading');
    if (ld) ld.hidden = false;
    // 결과 전환 전 처리 화면 (즉시 전환의 답답함 완화)
    setTimeout(function () { location.href = ROOT + 'search.html?rec=1&' + qs; }, 800);
  }

  function onClick(e) {
    var t = e.target.closest('button');
    if (!t) return;
    var d = t.dataset;
    // 비활성(aria-disabled — common.css가 :disabled 버튼을 회색으로 칠해서 disabled 대신 씀)은 이유만 알려 준다
    if (t.getAttribute('aria-disabled') === 'true') {
      if (d.soon) toast(d.soon + '는 준비 중이에요');
      else if (d.open) toast('먼저 도시를 골라 주세요');
      else if (d.next) toast('1개 이상 골라 주세요');
      return;
    }
    if (d.open) { var n = +d.open; S.open = S.open === n ? 0 : n; ev('rec_step', { step: n }); render(true); return; }
    if (d.city) { S.city = d.city; advance(1); render(true); return; }
    if (d.area !== undefined) { S.area = d.area; advance(2); render(true); saveUrl(); return; }
    if (d.cat) {
      var i = S.sel.indexOf(d.cat);
      if (i >= 0) S.sel.splice(i, 1);
      else if (S.sel.length >= 3) { toast('3개까지 고를 수 있어요'); return; }
      else S.sel.push(d.cat);
      render(false); saveUrl(); return;
    }
    if (d.must) {
      var j = S.no.indexOf(d.must);
      if (j >= 0) S.no.splice(j, 1); else S.no.push(d.must);
      S.no = normNo(S.no); render(false); saveUrl(); return;
    }
    if (d.next) { if (S.sel.length) { advance(3); render(true); } return; }
    if (d.bw !== undefined) {
      var nbw = d.bw === '1';
      if (nbw !== S.bw) S.bud = null;   // 평일·주말 구간이 달라 고른 예산은 다시 고른다
      S.bw = nbw; render(false); return;
    }
    if (d.bud !== undefined) { S.bud = d.bud; advance(4); render(true); saveUrl(); return; }
  }

  function mount(el) {
    listEl = el;
    if (window.CF_REC_CITY) CITY = window.CF_REC_CITY;
    // 미리 채우기: ?pr=..&bud=..&bw=1&area=..&no=.. (검색 '조건 수정'·뒤로 가기·공유 링크) → 모든 단계를 고른 상태로 접어서 보여 준다
    var sp = new URLSearchParams(location.search);
    var pr = (sp.get('pr') || '').split(',').filter(function (c) { return byCode[c]; });
    if (pr.length) {
      S.city = CITY.code; S.sel = pr.slice(0, 3);
      var ar = sp.get('area') || ''; S.area = AREAS.some(function (a) { return a.code === ar; }) ? ar : '';
      S.bw = sp.get('bw') === '1';
      var bd = sp.get('bud') || ''; S.bud = (S.bw ? BUDGETS_W : BUDGETS).some(function (b) { return b.code === bd; }) ? bd : '';
      if (!S.bud) S.bw = false;
      S.no = normNo((sp.get('no') || '').split(','));
      S.open = 0;
    } else if (sp.get('city') === CITY.code) { S.city = CITY.code; S.open = 2; }
    render(false);
    el.parentNode.addEventListener('click', onClick);
    var go = document.querySelector('#recp .rw-go-btn'), rs = document.querySelector('#recp .rw-reset-btn');
    if (go) go.addEventListener('click', submit);
    if (rs) rs.addEventListener('click', function () {
      S = { city: '', area: null, sel: [], no: [], bud: null, bw: false, open: 1 };
      saveUrl(); render(false); window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    // 결과에서 뒤로 왔을 때(bfcache) 처리 화면이 남아 있지 않게
    window.addEventListener('pageshow', function () { var ld = document.querySelector('#recp .rw-loading'); if (ld) ld.hidden = true; });
  }

  // ── 연결 ──
  function ready(fn) { if (document.readyState !== 'loading') fn(); else document.addEventListener('DOMContentLoaded', fn); }
  ready(function () {
    var el = document.getElementById('rw-steps');
    if (el) mount(el);
    // 검색 rec 헤더 '조건 수정' → 지금 조건을 채운 추천 페이지로
    document.addEventListener('click', function (e) {
      var a = e.target.closest && e.target.closest('.rec-reset');
      if (!a) return;
      e.preventDefault();
      openPage(window.CF_REC_PRESET || {});
    });
  });
})();

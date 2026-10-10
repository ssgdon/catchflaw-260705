/* 캐치플로 AI 맞춤 추천 마법사 (recommend.js)
   3단계 페이지 시트(CF.sheet, 높이 고정·진행바·F1 이전/다음): 우선순위(1~3) → 예산 → 지역 → search.html?rec=... 로 이동
   메인의 .btn-airec, 검색 rec헤더의 .rec-reset 버튼과 연동
   공유 상수(CFRec.CATS 등)는 검색 rec 모드에서도 사용
   의존: jQuery, backnav.js(CF.sheet·CF.toast) */
(function () {
  // 말투 묶음(v3 §2-4-8): '못 / 참아'·'방은 / 실망이야'처럼 타일 라벨이 끝말에서 갈리지 않게 줄바꿈 없는 공백
  function glue(t) { return String(t).replace(/못 (참아|자|넘어가)/g, '못\u00a0$1').replace(/ 실망이야/g, '\u00a0실망이야'); }
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
  var BUDGETS = [
    { code: '',   label: '상관없어요' },
    { code: 'b1', label: '10만원 미만' },
    { code: 'b2', label: '10~20만원' },
    { code: 'b3', label: '20만원 이상' }
  ];
  var AREA_DESC = { hakata: '신칸센·공항 이동 편리', tenjin: '쇼핑·맛집 중심가', nakasu: '야타이·나이트라이프', gion: '조용한 구시가' };
  var AREA_REC = { hakata: 1, tenjin: 1 };   // '추천' 딱지 — 카페 1,000건 중 하카타 160·텐진 131건 (FEEDBACK-2610 §8)
  /* '1년 안에 한 번도 없어야' 조건 (FEEDBACK-2610 §6) — 키는 검색 인덱스 h.x와 같고 URL no= 값. 심각 리뷰만 센다 */
  // 2026-10-10: '벌레 전부'(날파리·모기 포함, 후보의 절반 제외) 삭제 → '빈대' 추가. '객실 보안·밤길'은 실제로 세는 객실 보안(무단 입실·잠금·사생활)에 맞춰 이름 변경
  var MUSTS = [
    { code: 'roach',  label: '바퀴벌레', chip: '바퀴벌레 0건' },
    { code: 'bedbug', label: '빈대', chip: '빈대 0건' },
    { code: 'safe',   label: '방 잠금·무단 출입', chip: '무단 출입·잠금 문제 0건' }
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

  window.CFRec = { CATS: CATS, BUDGETS: BUDGETS, AREA_DESC: AREA_DESC, MUSTS: MUSTS, mustBy: mustBy, normNo: normNo, byCode: byCode, open: openWizard };

  function esc(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function toast(msg) { CF.toast(msg); }   // 토스트 1벌(js/backnav.js)

  // ── 상태 ──
  var sheet = null, step = 1, sel = [], bud = '', area = '', no = [], bw = false;
  var AREAS = window.CF_AREAS || [];
  var STEPS = 3;

  // A 페이지 시트(높이 고정 — 단계마다 높이가 튀지 않음) · H2 질문 26 · 진행바 4px · F1('이전' 링크 + 잉크 '다음', 마지막만 보라 '추천 보기')
  function build() {
    var m = CF.sheet.make({
      id: 'cf-rec-wizard', type: 'sheet', w: 'md', head: 'large', title: '', footType: 'f1',
      foot: '<button type="button" class="btn-text rec-prev">이전</button><button type="button" class="btn-ink rec-next">다음</button>'
    });
    var prog = document.createElement('div');
    prog.className = 'rec-prog'; prog.setAttribute('aria-hidden', 'true');
    prog.innerHTML = '<i></i><i></i><i></i>';
    m.querySelector('.ov-foot').before(prog);
    return m;
  }

  function hero(title, sub) {
    return '<div class="ov-hero"><h2 class="ov-title" id="cf-rec-wizard-t">' + title + '</h2>' + (sub ? '<p class="ov-sub is-text">' + sub + '</p>' : '') + '</div>';
  }
  var TITLES = ['여행할 때 이것만은 못 참아요', '1박 예산은 어느 정도예요?', '어느 동네에 머물까요?'];
  // stepChanged: 단계를 옮길 때만 맨 위로. 같은 단계에서 고르기만 하면 스크롤·포커스를 지킨다(다시 그려도 제자리)
  function render(stepChanged) {
    var body = sheet.querySelector('.ov-body');
    var a = document.activeElement, keep = null;
    if (a && sheet.contains(a)) ['data-code', 'data-must', 'data-bud', 'data-area', 'data-bw'].some(function (k) { if (a.hasAttribute(k)) { keep = '[' + k + '="' + a.getAttribute(k) + '"]'; return true; } });
    var y = body.scrollTop;
    body.innerHTML = step === 1 ? stepPriority() : step === 2 ? stepBudget() : stepArea();
    CF.sheet.setTitle(sheet, TITLES[step - 1]);
    body.scrollTop = stepChanged ? 0 : y;
    if (keep) { var k = body.querySelector(keep); if (k) k.focus({ preventScroll: true }); }
    else if (stepChanged) { var t = body.querySelector('.ov-title'); if (t) { t.setAttribute('tabindex', '-1'); t.focus({ preventScroll: true }); } }
    var bars = sheet.querySelectorAll('.rec-prog i');
    for (var i = 0; i < bars.length; i++) bars[i].classList.toggle('on', i < step);
    var prev = sheet.querySelector('.rec-prev'), next = sheet.querySelector('.rec-next');
    prev.hidden = step === 1;
    next.textContent = step === STEPS ? '추천 보기' : '다음';
    next.className = (step === STEPS ? 'btn-brand' : 'btn-ink') + ' rec-next';   // 최종 행동만 보라(§3-4)
    next.disabled = step === 1 && !sel.length;
    CF.sheet.update(sheet);
  }

  function stepPriority() {
    var chips = CATS.map(function (c) {
      var rank = sel.indexOf(c.code);
      var on = rank >= 0;
      return '<button type="button" class="rec-chip' + (on ? ' on' : '') + '" data-code="' + c.code + '" aria-pressed="' + (on ? 'true' : 'false') + '">' +
        '<span class="rec-chip-label">' + glue(c.label) + '</span>' +
        '<span class="rec-chip-kw">' + c.kw.replace(/·/g, ', ') + '</span>' +   // 좁은 칸의 나열은 쉼표(UI-STANDARDS §15) — '·'가 줄 끝에 매달리지 않게
        (on ? '<span class="rec-rank-badge" aria-label="' + (rank + 1) + '순위">' + (rank + 1) + '</span>' : '') +
      '</button>';
    }).join('');
    var musts = MUSTS.map(function (m) {
      var on = no.indexOf(m.code) >= 0;
      return '<button type="button" class="chip-filter rec-must' + (on ? ' on' : '') + '" data-must="' + m.code + '" aria-pressed="' + (on ? 'true' : 'false') + '">' + m.label + '</button>';
    }).join('');
    return hero(TITLES[0], '중요한 순서대로 3개까지 골라 주세요') +
      '<div class="rec-grid">' + chips + '</div>' +
      '<div class="ov-sec rec-must-box">' +
        '<h3 class="ov-sec-t">1년 안에 한 번도 없어야 해요</h3>' +
        '<p class="ov-sec-sub">한 번이라도 나온 곳은 빼요</p>' +
        '<div class="ov-chips rec-musts">' + musts + '</div>' +
      '</div>';
  }
  function opt(attr, code, label, on, desc, tag) {
    return '<button type="button" class="rec-opt' + (on ? ' on' : '') + '" ' + attr + '="' + code + '" role="radio" aria-checked="' + (on ? 'true' : 'false') + '">' +
      '<span class="ov-opt-t"><b>' + label + (tag ? ' <span class="rec-opt-tag">' + tag + '</span>' : '') + '</b>' + (desc ? '<span>' + desc + '</span>' : '') + '</span>' +
      '<span class="rec-radio" aria-hidden="true"></span></button>';
  }
  function stepBudget() {
    var chips = BUDGETS.map(function (b) { return opt('data-bud', b.code, b.label, bud === b.code); }).join('');
    return hero(TITLES[1]) +
      '<div class="rec-seg" role="group" aria-label="예산 기준">' +
        '<button type="button" class="rec-seg-btn' + (bw ? '' : ' on') + '" data-bw="0" aria-pressed="' + (bw ? 'false' : 'true') + '">평일 기준</button>' +
        '<button type="button" class="rec-seg-btn' + (bw ? ' on' : '') + '" data-bw="1" aria-pressed="' + (bw ? 'true' : 'false') + '">주말(금·토) 기준</button>' +
      '</div>' +
      '<p class="ov-note rec-seg-note">주말은 평일의 약 2.6배라 따로 골라요</p>' +
      '<div class="rec-list" role="radiogroup" aria-label="1박 예산">' + chips + '</div>';
  }
  function stepArea() {
    var opts = [{ code: '', ko: '어디든 좋아요', desc: '' }].concat(AREAS.map(function (a) {
      return { code: a.code, ko: a.ko, desc: AREA_DESC[a.code] || '' };
    }));
    var chips = opts.map(function (a) { return opt('data-area', a.code, a.ko, area === a.code, a.desc, AREA_REC[a.code] ? '추천' : ''); }).join('');
    return hero(TITLES[2]) +
      '<div class="rec-list" role="radiogroup" aria-label="동네">' + chips + '</div>';
  }

  // ── 이벤트 (위임) ── 2·3단계도 '고르기 → 다음'(자동 진행 없음, §7-7)
  function wire() {
    var $m = $(sheet);
    $m.on('click', '.rec-chip', function () {
      var code = $(this).data('code');
      var i = sel.indexOf(code);
      if (i >= 0) sel.splice(i, 1);
      else if (sel.length >= 3) { toast('3개까지 고를 수 있어요'); return; }
      else sel.push(code);
      render();
    });
    $m.on('click', '.rec-must', function () {
      var code = String($(this).data('must'));
      var i = no.indexOf(code);
      if (i >= 0) no.splice(i, 1); else no.push(code);
      no = normNo(no);
      render();
    });
    $m.on('click', '.rec-seg-btn', function () { bw = String($(this).data('bw')) === '1'; render(); });
    $m.on('click', '.rec-opt[data-bud]', function () { bud = String($(this).data('bud')); render(); });
    $m.on('click', '.rec-opt[data-area]', function () { area = String($(this).data('area')); render(); });
    $m.on('click', '.rec-prev', function () { if (step > 1) { step--; render(true); } });
    $m.on('click', '.rec-next', function () {
      if (step === 1 && !sel.length) return;
      if (step < STEPS) { step++; render(true); } else finish();
    });
  }

  function finish() {
    var qs = 'rec=1&pr=' + sel.join(',');
    if (bud) qs += '&bud=' + bud;
    if (bud && bw) qs += '&bw=1';
    if (area) qs += '&area=' + area;
    if (no.length) qs += '&no=' + normNo(no).join(',');
    // index/search는 루트(./), 상세(hotels/)는 ../ 필요
    var prefix = location.pathname.indexOf('/hotels/') >= 0 ? '../' : './';
    // 결과 전환 전 처리 화면(같은 시트 안 가운데) — 즉시 전환의 답답함 완화
    sheet.classList.add('is-loading');
    sheet.querySelector('.ov-body').innerHTML =
      '<div class="rec-loading" role="status">' +
        '<div class="rec-loading-spin" aria-hidden="true"></div>' +
        '<div class="rec-loading-tit">조건에 맞는 호텔을 찾고 있어요</div>' +
        '<div class="rec-loading-sub">리뷰 분석 결과로 순서를 매기고 있어요</div>' +
      '</div>';
    setTimeout(function () { location.href = prefix + 'search.html?' + qs; }, 950);
  }

  function openWizard(preset, opener) {
    preset = preset || {};
    sel = (preset.pr || []).filter(function (c) { return byCode[c]; });
    bud = preset.bud || '';
    area = preset.area || '';
    no = normNo(preset.no || []);
    bw = !!preset.bw;
    step = 1;
    if (!sheet) { sheet = build(); wire(); }
    sheet.classList.remove('is-loading');
    render(true);
    CF.sheet.open(sheet, { opener: opener });
  }

  // ── 버튼 자동 연동 ──
  function ready(fn) { if (document.readyState !== 'loading') fn(); else document.addEventListener('DOMContentLoaded', fn); }
  ready(function () {
    $(document).on('click', '.btn-airec', function (e) { e.preventDefault(); openWizard(null, this); });
    $(document).on('click', '.rec-reset', function (e) {
      e.preventDefault();
      openWizard(window.CF_REC_PRESET || {}, this);
    });
  });
})();

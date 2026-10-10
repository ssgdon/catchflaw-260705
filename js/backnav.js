/* 캐치플로 공통: 뒤로가기 · 오버레이 · 토스트 · 토큰 (backnav.js — 동기 로드, 전 페이지 head)
   - CFNav  : 오버레이가 열려 있으면 아이폰 스와이프백·갤럭시 뒤로가기가 페이지를 나가지 않고 오버레이만 닫음.
              외부에서 처음 들어온 페이지에서 뒤로가기로 사이트를 나가려 하면 종료 확인(가운데 다이얼로그)
   - CF.sheet: 오버레이 1벌(DESIGN-SYSTEM-V3 §5 · UI-STANDARDS §17). 뒤로가기·ESC·딤·X로 닫힘, 스크롤 잠금,
              포커스 이동·트랩·복귀, 시트 위 시트(아래 시트 scale .96 + 위 시트 딤만), iOS 키보드(--vvh)
   - CF.toast: 결과 알림 1벌(흰 알약 / 행동 있으면 흰 스낵바)
   - CF.tok / CF.rgba: CSS 밖(차트·지도)에서 디자인 토큰 읽기
   동기 로드라 defer가 아닌 스크립트·상세 인라인 스크립트에서도 바로 쓸 수 있다. 의존: 없음(순수 JS) */
window.CF = window.CF || {};
// 차트·지도처럼 CSS 밖에서 색을 쓰는 곳은 hex 대신 토큰을 읽는다: CF.tok('--ink') → #222222
CF.tok = function (name, fallback) {
  var v = '';
  try { v = getComputedStyle(document.documentElement).getPropertyValue(name).trim(); } catch (e) {}
  return v || fallback || '';
};
// 토큰 색 + 투명도: CF.rgba('--primary', .13) → 'rgba(141,91,253,0.13)' (#RRGGBB·#RGB 토큰만)
CF.rgba = function (name, a) {
  var h = CF.tok(name).replace('#', '');
  if (h.length === 3) h = h.replace(/(.)/g, '$1$1');
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return CF.tok(name);
  var n = parseInt(h, 16);
  return 'rgba(' + (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
};
(function () {
  var doc = document, root = doc.documentElement;
  var closers = [];        // CFNav: 열린 오버레이의 '시각적 닫기' 함수 스택(히스토리 버퍼 1개씩)
  var suppress = 0;        // 버튼 닫기로 history.back() 한 횟수 — 그만큼의 popstate는 무시
  var exitArmed = false;   // 외부 유입 페이지에서만 종료 확인 활성화
  var leaving = false;
  var PC = window.matchMedia ? window.matchMedia('(min-width:1100px)') : { matches: false };
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  // ───────── CFNav (기존 API 유지: push / pop / isOpen) ─────────
  window.CFNav = {
    // 오버레이를 '시각적으로' 연 직후 호출: 닫기함수 등록 + 히스토리 버퍼 push
    push: function (closeFn) {
      closers.push(closeFn);
      try { history.pushState({ cfOverlay: 1 }, ''); } catch (e) {}
    },
    // 버튼(X/딤/ESC)으로 닫을 때: 시각적 닫기 + 버퍼 소비. fn을 주면 스택 어디에 있든 그 항목을 닫는다
    // (버퍼는 모두 같은 상태라 어느 것을 소비해도 같다)
    pop: function (fn) {
      var i = fn ? closers.indexOf(fn) : closers.length - 1;
      if (i < 0) return;
      var f = closers.splice(i, 1)[0];
      try { f(); } catch (e) {}
      suppress++;
      history.back();
    },
    isOpen: function () { return closers.length > 0; }
  };

  window.addEventListener('popstate', function () {
    if (leaving) return;
    if (suppress > 0) { suppress--; return; }
    // 오버레이가 열려 있으면 최상단만 닫음 (푸시된 버퍼는 이 popstate가 소비)
    if (closers.length) {
      var fn = closers.pop();
      try { fn(); } catch (e) {}
      return;
    }
    // 오버레이 없음 → 사이트 이탈 시도. 외부 유입이면 종료 확인.
    if (exitArmed) {
      try { history.pushState({ cfExit: 1 }, ''); } catch (e) {}
      showExit();
    }
  });

  // ───────── CF.sheet — 오버레이 1벌 ─────────
  var stack = [];          // [{el, o, opener, closer}] — 위가 마지막
  var seq = 0;
  var X_BTN = '<button type="button" class="ov-close" aria-label="닫기"></button>';

  function entryOf(el) { for (var i = stack.length - 1; i >= 0; i--) if (stack[i].el === el) return stack[i]; return null; }
  function focusables(el) {
    return [].filter.call(el.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]):not([type=hidden]):not([tabindex="-1"]),select:not([disabled]),textarea:not([disabled]),iframe,[tabindex]:not([tabindex="-1"])'),
      function (n) { return n.offsetWidth || n.offsetHeight || n.getClientRects().length; });
  }
  // iOS Safari는 키보드가 떠도 레이아웃 뷰포트가 그대로라 고정 푸터가 키보드 뒤로 숨는다(interactive-widget 미지원).
  // 보이는 높이(--vvh)와 키보드 높이(--ov-kb)를 CSS에 넘겨 시트를 보이는 영역 안에 맞춘다(DESIGN-SYSTEM-V3 §5-2)
  function syncVV() {
    var v = window.visualViewport;
    if (!v || !stack.length) return;
    root.style.setProperty('--vvh', Math.round(v.height) + 'px');
    root.style.setProperty('--ov-kb', Math.max(0, Math.round(window.innerHeight - v.height - v.offsetTop)) + 'px');
  }
  if (window.visualViewport) { visualViewport.addEventListener('resize', syncVV); visualViewport.addEventListener('scroll', syncVV); }
  function lock() { if (stack.length === 1) { doc.body.style.overflow = 'hidden'; root.classList.add('ov-lock'); } syncVV(); }
  function unlock() {
    doc.body.style.overflow = ''; root.classList.remove('ov-lock');
    root.style.removeProperty('--vvh'); root.style.removeProperty('--ov-kb');
  }
  // 스크롤 상태: 큰 제목(H2)이 스크롤로 사라지면 작은 헤더로 접고, 내용이 푸터 밑으로 지나가면 푸터 선을 그림자로
  function update(el) {
    el = el || (stack.length ? stack[stack.length - 1].el : null);
    if (!el) return;
    var b = el.querySelector('.ov-body'), h = el.querySelector('.ov-head--large'), f = el.querySelector('.ov-foot');
    if (!b) return;
    if (h) {
      var t = el.querySelector('.ov-hero .ov-title');
      var past = t && t.offsetParent ? b.scrollTop > (t.offsetTop - b.offsetTop) + t.offsetHeight - 4 : b.scrollTop > 40;
      h.classList.toggle('is-collapsed', past);
    }
    if (f) f.classList.toggle('is-raised', b.scrollHeight - b.scrollTop - b.clientHeight > 1);
  }
  function wire(el) {
    if (el._ovWired) return;
    el._ovWired = 1;
    [].forEach.call(el.querySelectorAll('.ov-body'), function (b) { b.addEventListener('scroll', function () { update(el); }, { passive: true }); });
    // 입력에 포커스가 가면 키보드 위 가운데로(고정 높이 시트 + 고정 푸터에서 입력이 가려지지 않게)
    el.addEventListener('focusin', function (e) {
      if (!/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
      setTimeout(function () { try { e.target.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (x) {} }, 300);
    });
  }

  function open(el, o) {
    if (!el) return;
    o = o || {};
    if (entryOf(el)) return;
    var below = stack[stack.length - 1];
    var ent = { el: el, o: o, opener: o.opener || doc.activeElement, hist: o.history !== false };
    stack.push(ent);
    // 같은 z-index(--z-sheet)에서는 DOM 뒤쪽이 위 → 여는 시트를 body 끝으로(시트 위 시트의 쌓임 순서 = 연 순서)
    if (el.parentNode !== doc.body || doc.body.lastElementChild !== el) doc.body.appendChild(el);
    if (below) below.el.classList.add('ov-under');
    el.hidden = false;
    void el.offsetWidth;           // hidden 해제를 전환에 반영(백그라운드 탭에선 rAF가 안 불림)
    el.classList.add('ov-on');
    wire(el);
    lock();
    if (ent.hist) { ent.closer = function () { finish(ent); }; CFNav.push(ent.closer); }
    var t = o.focus ? (typeof o.focus === 'string' ? el.querySelector(o.focus) : o.focus) : el.querySelector('.ov-title') || el.querySelector('.ov-close');
    if (t) {
      if (!focusables(el).length || t.classList.contains('ov-title')) t.setAttribute('tabindex', '-1');
      try { t.focus({ preventScroll: true }); } catch (e) { t.focus(); }
    }
    update(el);
    if (o.onOpen) try { o.onOpen(el); } catch (e) {}
  }
  // 시각적으로 닫기(히스토리는 건드리지 않음) — CFNav 닫기함수·{history:false} 시트가 부른다
  function finish(ent) {
    var i = stack.indexOf(ent);
    if (i < 0) return;
    stack.splice(i, 1);
    var el = ent.el;
    el.classList.remove('ov-on', 'ov-under');
    var top = stack[stack.length - 1];
    if (top) top.el.classList.remove('ov-under');
    if (!stack.length) unlock();
    setTimeout(function () { if (!entryOf(el)) el.hidden = true; }, 240);
    if (ent.o.onClose) try { ent.o.onClose(el); } catch (e) {}
    var op = ent.opener;
    if (op && op.focus && op !== doc.body && doc.contains(op)) { try { op.focus({ preventScroll: true }); } catch (e) {} }
    // 연 버튼이 사라졌거나 비활성이 됐으면(신고 → '신고함') 아래 시트의 제목으로
    if (top && !top.el.contains(doc.activeElement)) { var tt = top.el.querySelector('.ov-title'); if (tt && tt.offsetParent) { tt.setAttribute('tabindex', '-1'); tt.focus({ preventScroll: true }); } }
  }
  function close(el) {
    var ent = el ? entryOf(el) : stack[stack.length - 1];
    if (!ent) return;
    if (ent.closer && closers.indexOf(ent.closer) >= 0) CFNav.pop(ent.closer);   // 뒤로가기 버퍼도 함께 소비
    else finish(ent);
  }

  // 마크업 만들기(JS로 그리는 오버레이용). 서버 렌더 오버레이(리뷰 근거·블로그·메뉴)는 같은 구조를 generate.py가 쓴다.
  //  c = {id, type:'sheet'|'bottom'|'dialog', w:'sm'|'md'|'lg'|'xl', head:'bar'|'large'|'info', title, sub, back,
  //       body, foot, footType:'f1'|'f2'|'f3', tag:'section'|'form', cls}
  function make(c) {
    var id = c.id || ('ov' + (++seq)), tid = id + '-t', head = c.head || 'bar';
    var el = doc.createElement('div');
    el.className = 'ov' + (c.cls ? ' ' + c.cls : '');
    el.id = id;
    el.setAttribute('data-ov', c.type || 'sheet');
    el.setAttribute('role', 'dialog');
    el.setAttribute('aria-modal', 'true');
    el.setAttribute('aria-labelledby', tid);
    el.hidden = true;
    var sub = c.sub ? '<p class="ov-sub">' + c.sub + '</p>' : '';
    var h = '', hero = '';
    if (head === 'bar') h = '<header class="ov-head ov-head--bar"><button type="button" class="ov-back" aria-label="이전"' + (c.back ? '' : ' hidden') + '></button>'
      + '<h2 class="ov-title" id="' + tid + '">' + (c.title || '') + '</h2>' + X_BTN + '</header>';
    else if (head === 'large') {
      h = '<header class="ov-head ov-head--large"><span class="ov-mini" aria-hidden="true">' + (c.title || '') + '</span>' + X_BTN + '</header>';
      hero = '<div class="ov-hero"><h2 class="ov-title" id="' + tid + '">' + (c.title || '') + '</h2>' + sub + '</div>';
    } else h = '<header class="ov-head ov-head--info">' + X_BTN + '<h2 class="ov-title" id="' + tid + '">' + (c.title || '') + '</h2>' + sub + '</header>';
    var tag = c.tag || 'section';
    el.innerHTML = '<div class="ov-dim"></div><' + tag + ' class="ov-panel ov-w-' + (c.w || 'md') + '"' + (tag === 'form' ? ' novalidate' : '') + '>'
      + h + '<div class="ov-body">' + hero + (c.body || '') + '</div>'
      + (c.foot ? '<footer class="ov-foot ov-foot--' + (c.footType || 'f3') + '">' + c.foot + '</footer>' : '')
      + '</' + tag + '>';
    doc.body.appendChild(el);
    return el;
  }
  // 제목 바꾸기(마법사 단계 등): 큰 제목·접힌 작은 제목을 같이
  function setTitle(el, html) {
    [].forEach.call(el.querySelectorAll('.ov-title, .ov-mini'), function (t) { t.innerHTML = html; });
  }

  // 공통 닫기: 딤·X·[data-ov-close] (시트마다 핸들러를 달지 않는다)
  doc.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('.ov-dim, .ov-close, [data-ov-close]');
    if (!t) return;
    var el = t.closest('.ov');
    if (!el || !entryOf(el)) return;
    e.preventDefault();
    var ent = entryOf(el);
    if (ent.o.onDismiss) { ent.o.onDismiss(el); return; }
    close(el);
  });
  doc.addEventListener('keydown', function (e) {
    var ent = stack[stack.length - 1];
    if (!ent) return;
    if (e.key === 'Escape' || e.key === 'Esc') {
      e.preventDefault();
      if (ent.o.onDismiss) ent.o.onDismiss(ent.el); else close(ent.el);
      return;
    }
    if (e.key === 'Tab') {   // 포커스 트랩: 위 시트 안에서만 돈다
      var f = focusables(ent.el.querySelector('.ov-panel') || ent.el);
      if (!f.length) { e.preventDefault(); return; }
      var first = f[0], last = f[f.length - 1], a = doc.activeElement;
      if (!ent.el.contains(a)) { e.preventDefault(); first.focus(); }
      else if (e.shiftKey && (a === first || !f.length)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && a === last) { e.preventDefault(); first.focus(); }
      return;
    }
    // {keys: fn(dir)} — PC 리뷰 근거 ←/→ 항목 이동(UI-STANDARDS §13). 입력 중에는 무시
    if (ent.o.keys && (e.key === 'ArrowLeft' || e.key === 'ArrowRight') && !/^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName || '')) {
      ent.o.keys(e.key === 'ArrowLeft' ? -1 : 1);
    }
  });

  // 시트를 연 채 다른 페이지로 갔다가 뒤로 돌아오면(bfcache) 시트가 열린 채 복원된다 → 조용히 닫는다
  window.addEventListener('pageshow', function (e) {
    if (!e.persisted || !stack.length) return;
    stack.slice().reverse().forEach(finish);
    closers.length = 0;
  });

  CF.sheet = {
    open: open, close: close, make: make, update: update, setTitle: setTitle,
    isOpen: function (el) { return el ? !!entryOf(el) : stack.length > 0; },
    top: function () { return stack.length ? stack[stack.length - 1].el : null; },
    pc: function () { return PC.matches; }
  };

  // ───────── CF.toast — 결과 알림 1벌 ─────────
  //  CF.toast('링크를 복사했어요') · CF.toast('비교함을 비웠어요', {action: {label: '되돌리기', fn}}) · {ms}
  //  흰 알약(행동 없음, 2초) / 흰 스낵바(행동 있음, 4초). 모바일은 하단 고정 바·트레이·시트 푸터 위 16, PC는 왼쪽 아래
  var toastTimer = null;
  function liftPx() {
    if (PC.matches) return 0;
    var lift = 0, vh = window.innerHeight;
    var top = stack.length ? stack[stack.length - 1].el : null;
    if (top && !top.querySelector('.ov-foot:not([hidden])')) top = null;   // 푸터 없는 시트가 닫히는 중이면 페이지 기준
    var sels = top ? ['.ov-foot'] : ['#detail > .button', '.cmp-tray', '#float .btn-airec', '#map-toggle'];
    sels.forEach(function (s) {
      [].forEach.call((top || doc).querySelectorAll(s), function (n) {
        if (n.hidden || !(n.offsetWidth || n.offsetHeight)) return;
        var r = n.getBoundingClientRect();
        if (r.top < vh && r.bottom > vh - 200 && getComputedStyle(n).visibility !== 'hidden' && getComputedStyle(n).opacity !== '0') lift = Math.max(lift, vh - r.top);
      });
    });
    return lift ? Math.round(lift + 16) : 0;
  }
  CF.toast = function (msg, o) {
    o = o || {};
    [].forEach.call(doc.querySelectorAll('.cf-toast'), function (n) { n.remove(); });
    clearTimeout(toastTimer);
    var t = doc.createElement('div');
    t.className = 'cf-toast' + (o.action ? ' has-act' : '');
    t.setAttribute('role', 'status');
    t.setAttribute('aria-live', 'polite');
    var m = doc.createElement('span'); m.className = 'cf-toast-msg';
    if (o.html) m.innerHTML = msg; else m.textContent = msg;
    t.appendChild(m);
    if (o.action) {
      var b = doc.createElement('button'); b.type = 'button'; b.className = 'cf-toast-act'; b.textContent = o.action.label;
      b.addEventListener('click', function () { try { o.action.fn(); } catch (e) {} t.remove(); });
      t.appendChild(b);
    }
    var lift = liftPx();
    if (lift) t.style.bottom = lift + 'px';
    doc.body.appendChild(t);
    void t.offsetWidth;
    t.classList.add('show');
    toastTimer = setTimeout(function () { t.classList.remove('show'); setTimeout(function () { t.remove(); }, 300); }, o.ms || (o.action ? 4000 : 2000));
    return t;
  };

  // ───────── 종료 확인 (C 가운데 다이얼로그, {history:false} — popstate에 반응해 열리므로 버퍼를 쌓지 않음) ─────────
  var exitEl = null;
  function stay() { if (exitEl) close(exitEl); }
  function showExit() {
    if (!exitEl) {
      exitEl = make({
        id: 'cf-exit', type: 'dialog', w: 'sm', head: 'bar', cls: 'ov--confirm',
        title: '정말 나가시겠어요?',
        body: '<p class="ov-text"><span class="seg">보던 호텔 분석은 저장되지 않아요.</span> <span class="seg">후쿠오카 호텔이 아직 많이 남아 있어요!</span></p>',
        footType: 'f1',
        foot: '<button type="button" class="btn-text" data-act="leave">나가기</button>'
          + '<button type="button" class="btn-ink" data-act="stay">계속 볼래요</button>'
      });
      exitEl.querySelector('[data-act="stay"]').addEventListener('click', stay);
      exitEl.querySelector('[data-act="leave"]').addEventListener('click', function () {
        leaving = true;
        exitArmed = false;
        // 버퍼 + 실제 페이지를 건너뛰어 이전 사이트로. 히스토리가 짧으면 back 1회.
        if (history.length > 2) history.go(-2); else history.back();
      });
    }
    open(exitEl, { history: false, focus: '[data-act="stay"]' });
  }

  // 외부 유입 페이지에서만 버퍼 1개 push → 첫 뒤로가기를 가로챔
  function isExternalEntry() {
    if (!document.referrer) return true;
    try { return new URL(document.referrer).origin !== location.origin; }
    catch (e) { return true; }
  }
  if (isExternalEntry()) {
    exitArmed = true;
    try { history.pushState({ cfExit: 1 }, ''); } catch (e) {}
  }
})();

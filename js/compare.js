/* P5 호텔 비교함 — 로그인 없이 localStorage('cf_cmp')에 최대 3곳 [{id,n,img}].
   - 담기 버튼: [data-cmp-id] (+ data-cmp-name, data-cmp-img). 상세 .cmp-btn · 검색 카드 사진 위 비교 원 .hcard-cmp 공용, 동적 렌더 카드도 위임 처리.
   - 플로팅 비교함: .cmp-tray(자동 생성) = 링크(→ compare?ids=a,b,c, 공유 가능한 URL) + 닫기(×, 비교함 비우기·되돌리기 토스트)
   - html.has-cmp: 비교함이 있을 때(검색의 지도 버튼 등 겹침 회피용)
   - GA4: compare_add / compare_remove / compare_open / compare_clear / compare_undo */
(function () {
  var KEY = 'cf_cmp', MAX = 3;
  var root = (document.currentScript && document.currentScript.getAttribute('data-root')) || './';

  function get() {
    try { var a = JSON.parse(localStorage.getItem(KEY) || '[]'); return Array.isArray(a) ? a.filter(function (x) { return x && x.id; }) : []; }
    catch (e) { return []; }
  }
  function set(a) { try { localStorage.setItem(KEY, JSON.stringify(a)); } catch (e) {} render(); }
  function has(id) { return get().some(function (x) { return x.id === id; }); }
  function ev(name, p) { if (typeof gtag === 'function') gtag('event', name, p || {}); }
  function esc(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }

  // act = {label, fn}: 토스트 안 실행 버튼(되돌리기 등) → 흰 스낵바, 4초 유지. 토스트 1벌(js/backnav.js CF.toast)
  function toast(msg, act) { CF.toast(msg, act ? { action: act } : null); }

  function clearAll() {   // 트레이 × — 비교함을 비우고, 실수였을 때를 위해 되돌리기 제공
    var prev = get();
    set([]);
    ev('compare_clear', { count: prev.length });
    toast('비교함을 비웠어요', { label: '되돌리기', fn: function () { set(prev); ev('compare_undo', { count: prev.length }); } });
  }

  function toggle(btn) {
    var id = btn.getAttribute('data-cmp-id'), a = get();
    var i = a.map(function (x) { return x.id; }).indexOf(id);
    if (i >= 0) { a.splice(i, 1); ev('compare_remove', { hotel_id: id }); }
    else {
      if (a.length >= MAX) { toast('비교는 ' + MAX + '곳까지 담을 수 있어요'); return; }
      a.push({ id: id, n: btn.getAttribute('data-cmp-name') || '', img: btn.getAttribute('data-cmp-img') || '' });
      ev('compare_add', { hotel_id: id, count: a.length });
      set(a);   // 트레이를 먼저 그려야 토스트가 트레이 위로 뜬다(backnav.js liftPx)
      if (a.length === 1) toast('비교함에 담았어요');
      return;
    }
    set(a);
  }

  function url(a) { return root + 'compare?ids=' + a.map(function (x) { return encodeURIComponent(x.id); }).join(','); }

  function render() {
    var a = get();
    document.documentElement.classList.toggle('has-cmp', a.length > 0);
    document.querySelectorAll('[data-cmp-id]').forEach(function (b) {
      var on = has(b.getAttribute('data-cmp-id'));
      b.classList.toggle('is-on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      var t = b.querySelector('.cmp-t'); if (t) t.textContent = on ? (b.getAttribute('data-on') || '비교함에 담김') : (b.getAttribute('data-off') || '비교 담기');
    });
    if (document.body.getAttribute('data-page') === 'compare') return;   // 비교 페이지 자체엔 트레이 없음
    var tray = document.querySelector('.cmp-tray');
    if (!a.length) { if (tray) tray.hidden = true; return; }
    if (!tray) {
      tray = document.createElement('div'); tray.className = 'cmp-tray' + (document.getElementById('detail') ? ' on-detail' : document.querySelector('#float .btn-airec') ? ' on-home' : '');   // 상세는 하단 CTA 위로
      tray.innerHTML = '<a class="ct-link"></a><button type="button" class="ct-x" aria-label="비교함 비우기">×</button>';
      tray.querySelector('.ct-link').addEventListener('click', function (e) {
        var n = get().length;
        if (n < 2) { e.preventDefault(); toast('1곳 더 담으면 비교할 수 있어요'); return; }
        ev('compare_open', { count: n });
      });
      tray.querySelector('.ct-x').addEventListener('click', clearAll);
      document.body.appendChild(tray);
    }
    tray.hidden = false;
    var link = tray.querySelector('.ct-link');
    link.href = url(a);
    link.innerHTML = '<span class="ct-th">' + a.map(function (x) {
        return x.img ? '<img src="' + esc(x.img) + '" alt="">' : '<i></i>';
      }).join('') + '</span><span class="ct-n">' + (a.length < 2 ? '1곳 더 담기' : '비교하기 (' + a.length + ')') + '</span>';
  }

  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-cmp-id]');
    if (!b) return;
    e.preventDefault(); e.stopPropagation();
    toggle(b);
  }, true);
  window.addEventListener('storage', function (e) { if (e.key === KEY) render(); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', render); else render();

  window.CFCompare = { get: get, set: set, render: render, toast: toast };
})();

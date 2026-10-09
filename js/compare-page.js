/* P5 비교 페이지 렌더 — window.CF_CMP(data/compare.js) + ?ids= 또는 비교함(localStorage).
   행마다 가장 좋은 값 강조, "차이 나는 항목만" 토글, 맨 위 한 줄 비교(실측 조립).
   3곳 미만이면 '호텔 추가' 칸 → 검색 팝업(별칭 인덱스 지연 로드)에서 바로 추가. */
(function () {
  var D = window.CF_CMP || {}, FAQ = window.CF_CMP_FAQ || [];
  var CATS = ['청결', '냄새', '소음', '객실', '직원', '위치'];   // 분류 v5 점수 대분류 (안전은 칩 전용이라 비교표 제외)
  var MAX = 3;
  var root = document.getElementById('cmp-root');
  var diffOnly = false, pad = 0;   // pad: '호텔 추가' 칸 때문에 각 행 끝에 붙는 빈 칸 수

  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function josa(w, a, b) { var c = w.charCodeAt(w.length - 1) - 0xAC00; return (c >= 0 && c <= 11171) ? (c % 28 ? a : b) : a + '(' + b + ')'; }
  function band(v) { return v >= 70 ? 'danger' : v >= 45 ? 'warning' : 'safe'; }
  // 위험도 → 결론 라벨·평균 대비 문장 (generate.py cat_verdict·ratio_text와 같은 구간)
  function verdict(v) { return v < 25 ? '거의 없음' : v < 45 ? '적은 편' : v < 55 ? '평균 수준' : v < 70 ? '많은 편' : '많음'; }
  function ratioText(v) {
    var r = v <= 50 ? v / 50 : 1 + (v - 50) / 25;
    if (v < 45) return '평균보다 ' + Math.round((1 - r) * 100) + '% 적어요';   // 경계 45·55 = verdict와 동일(generate.ratio_text)
    if (v < 55) return '평균과 비슷해요';
    return '평균의 ' + Math.max(r, 1.2).toFixed(1) + '배';
  }
  // 항상 2줄('평균의' / '1.2배') — 짧은 값만 1줄이 되면 칸마다 막대 높이가 어긋남
  function ratioHtml(v) { var m = /^(평균보다|평균의|평균과) (.+)$/.exec(ratioText(v)); return m ? '<span class="cmp-rk">' + m[1] + '</span><b>' + m[2] + '</b>' : ratioText(v); }
  var NB = '\u00a0';
  function glue(t) {   // generate.py polish_breaks와 같은 묶음: "가장 낮음" "도보 23분" "최근 1년" "좋은 곳"
    return String(t).replace(/가장 /g, '가장' + NB).replace(/도보 (\d)/g, '도보' + NB + '$1')
      .replace(/최근 (\d)/g, '최근' + NB + '$1').replace(/(많은|적은|낮은|높은|좋은) (편|곳)/g, '$1' + NB + '$2')
      .replace(/([^\s·])·(?=[^\s·])/g, '$1⁠·⁠');   // 띄어쓰기 없는 가운뎃점(시설·고장)은 점 뒤에서 끊지 않음 — polish_breaks와 같은 결합자
  }
  // 칸 안 여러 값("무료 · 체크인 전후")은 값마다 한 줄 — 줄 끝에 '·'가 매달리지 않게
  function lines(t) { return String(t).split(' · ').map(function (x) { return '<span class="cmp-li">' + esc(x) + '</span>'; }).join(''); }
  function ev(n, p) { if (typeof gtag === 'function') gtag('event', n, p || {}); }

  function saveIds(a) {   // 비교함(localStorage) + 주소(?ids=) 동기화 — 새로고침·공유해도 같은 구성
    if (window.CFCompare) window.CFCompare.set(a.map(function (id) { return { id: id, n: D[id].n, img: D[id].img }; }));
    history.replaceState(null, '', location.pathname + (a.length ? '?ids=' + a.join(',') : ''));
  }
  function ids() {
    var m = location.search.match(/[?&]ids=([^&]+)/), a;
    if (m) {
      a = decodeURIComponent(m[1]).split(',').filter(function (id) { return D[id]; }).slice(0, MAX);
      // 공유 링크로 들어오면 비교함도 그 구성으로 맞춤(트레이·담기 버튼 상태 일치)
      try { localStorage.setItem('cf_cmp', JSON.stringify(a.map(function (id) { return { id: id, n: D[id].n, img: D[id].img }; }))); } catch (e) {}
      return a;
    }
    return (window.CFCompare ? window.CFCompare.get() : []).map(function (x) { return x.id; }).filter(function (id) { return D[id]; });
  }

  function row(label, cells, opt) {
    opt = opt || {};
    // nb = 순위 비교 제외 칸(리뷰 적은 호텔): '가장 좋음' 후보에서 뺀다 — 표본 공정성(2026-10)
    var nums = cells.filter(function (c) { return !c.nb; }).map(function (c) { return c.v; });
    var best = null;
    if (opt.best && nums.length > 1 && nums.every(function (n) { return typeof n === 'number'; })) {
      best = opt.best === 'min' ? Math.min.apply(null, nums) : Math.max.apply(null, nums);
      if (nums.every(function (n) { return n === best; })) best = null;
    }
    var same = cells.length > 1 && cells.every(function (c) { return c.k === cells[0].k; });
    var blank = new Array(pad + 1).join('<div class="cmp-cell is-pad"></div>');
    return '<div class="cmp-tr' + (same ? ' is-same' : '') + '"><div class="cmp-k">' + label + '</div><div class="cmp-v">'
      + cells.map(function (c) {
          var on = best !== null && !c.nb && c.v === best;
          return '<div class="cmp-cell' + (on ? ' is-best' : '') + '">' + c.h + (on ? '<span class="cmp-best">' + glue(opt.lab || '가장 좋음') + '</span>' : '') + '</div>';
        }).join('') + blank + '</div></div>';
  }
  function num(v, unit) { return { v: v, k: String(v), h: '<b>' + esc(v) + (unit || '') + '</b>' }; }

  // 한 줄 비교 — 긴 문장 대신 "무엇 / 어느 호텔 / 값" 행으로(호텔명이 문장 중간에서 쪼개지지 않게).
  function sumRow(k, names, v, bad) {
    return '<li><span class="cg-k">' + glue(k) + '</span><span class="cg-r"><span class="cg-n">' + names + '</span>'
      + (v ? '<b class="cg-v' + (bad ? ' is-bad' : '') + '">' + v + '</b>' : '') + '</span></li>';
  }
  function summary(H) {
    var lows = H.filter(function (h) { return h.lr; });
    var lowNote = lows.length ? '<p class="cg-note">' + lows.map(function (h) { return esc(h.n); }).join(', ')
      + josa(lows[lows.length - 1].n, '은', '는') + ' 최근 1년 리뷰가 적어 순위 비교에서 뺐어요</p>' : '';
    if (H.length < 2) return '<ul class="cmp-glance">' + sumRow('실망 확률', esc(H[0].n), H[0].p + '%') + '</ul>'
      + '<p class="cg-note">호텔을 하나 더 추가하면 나란히 비교해 드려요</p>' + lowNote;
    var R = H.filter(function (h) { return !h.lr; });              // 순위 비교는 리뷰 충분한 호텔끼리
    if (R.length < 2) return '<p class="cmp-lead">리뷰가 충분한 호텔이 2곳 미만이라 순위를 매기지 않았어요</p>' + lowNote;
    var minP = Math.min.apply(null, R.map(function (h) { return h.p; }));
    var los = R.filter(function (h) { return h.p === minP; });     // 화면 값(정수 %)이 같으면 공동
    var rows = los.length === R.length
      ? sumRow('실망 확률', (R.length === 2 ? '두' : R.length === 3 ? '세' : R.length) + ' 곳 모두 비슷해요', minP + '%')
      : sumRow('실망 확률 가장 낮음', los.map(function (h) { return esc(h.n); }).join('<br>'), minP + '%');
    var hi = R.filter(function (h) { return h.top && h.top.length; })   // 불만 최다 항목도 리뷰 충분한 호텔끼리
      .sort(function (a, b) { return b.top[0][1] - a.top[0][1]; })[0];
    if (hi) rows += sumRow('불만이 가장 많은 항목', esc(hi.n) + '<span class="cg-s">' + esc(hi.top[0][0]) + ' 불만 비율</span>', hi.top[0][1] + '%', true);
    return '<ul class="cmp-glance">' + rows + '</ul>' + lowNote;
  }

  function addSlot() {
    return '<button type="button" class="cmp-h cmp-add" data-add="1"><span class="ca-box"><span class="ca-plus"></span><span class="ca-t">호텔 추가</span>'
      + '<span class="ca-s">최대 ' + MAX + '곳까지 비교</span></span></button>';
  }

  function render() {
    var list = ids(), H = list.map(function (id) { var d = D[id]; d.id = id; return d; });
    ev('compare_view', { count: H.length });
    if (!H.length) {
      pad = 0;
      root.innerHTML = '<div class="cmp-empty"><div class="ce-tit">어떤 호텔을 비교할까요?</div>'
        + '<div class="ce-txt">호텔을 검색해 바로 추가하거나, 상세·검색 결과에서 <b>비교 담기</b>를 눌러 주세요 (최대 ' + MAX + '곳)</div>'
        + '<button type="button" class="ce-btn" data-add="1">호텔 검색해서 추가</button>'
        + '<a class="ce-link" href="./search">검색 결과에서 고르기</a></div>';
      return;
    }
    var canAdd = H.length < MAX;
    pad = canAdd ? 1 : 0;
    var cols = '--n:' + (H.length + pad);   // 칸 수는 CSS 변수로(모바일 n칸 · PC는 왼쪽 항목명 칸 + n칸)
    var html = '<div class="cmp-hd" style="' + cols + '"><div class="cmp-h cmp-h-sp" aria-hidden="true"></div>' + H.map(function (h) {
        return '<div class="cmp-h"><a href="./hotels/' + h.id + '"><span class="cmp-img">' + (h.img ? '<img src="' + esc(h.img) + '" alt="">' : '') + '</span>'
          + '<span class="cmp-nm">' + esc(h.n) + '</span></a><button type="button" class="cmp-x" data-x="' + h.id + '" aria-label="비교에서 빼기">×</button></div>';
      }).join('') + (canAdd ? addSlot() : '') + '</div>';
    html += '<div class="cmp-sum"><div class="cmp-sum-box"><div class="cmp-eyebrow">한눈에 비교</div>' + summary(H) + '</div>'
      + '<div class="cmp-tools"><span>보라색 = 가장 좋은' + NB + '곳</span>'
      + '<button type="button" class="cmp-switch' + (diffOnly ? ' is-on' : '') + '" id="cmp-diff"><i></i>차이 나는 항목만</button></div></div>';

    var g1 = row('실망 확률', H.map(function (h) {
        var c = num(h.p, '%');
        if (h.lr) { c.nb = true; c.h += ' <span class="cmp-sub">리뷰&nbsp;적음</span>'; }   // '리뷰 / 적음'으로 갈라지지 않게 (360 실측)   // 리뷰 적은 호텔은 순위 강조 제외
        return c;
      }), { best: 'min', lab: '가장 낮음' })
      // 가격은 표시 단위(만원)로 비교 — '약 7만원' 두 곳 중 한 곳만 강조되는 착시 방지. krw = 날짜별 표본의 중앙값
      + row('1박 가격', H.map(function (h) { return { v: h.krw != null ? Math.round(h.krw / 10000) : null, k: h.pt, h: h.pt ? '<b>' + esc(h.pt) + '</b>' : '<span class="cmp-none">정보 없음</span>' }; }), { best: 'min', lab: '가장 저렴' })
      + row('가까운 역', H.map(function (h) { return { v: h.sm, k: h.st, h: h.st ? glue(esc(h.st)) : '<span class="cmp-none">-</span>' }; }), { best: 'min', lab: '가장 가까움' })
      + row('구글 평점', H.map(function (h) { return { v: h.g, k: String(h.g), h: '<b>' + h.g.toFixed(1) + '</b> <span class="cmp-sub">(' + h.rc.toLocaleString() + ')</span>' }; }), { best: 'max', lab: '가장 높음' })
      + row('분석한 리뷰', H.map(function (h) { return { v: h.an, k: String(h.an), h: '<b>' + esc(h.an) + '건</b> <span class="cmp-sub">' + glue(esc(h.pd || '최근 1년')) + '</span>' }; }), { best: 'max', lab: '근거 가장 많음' });
    var g2 = CATS.map(function (c) {
      return row(c + ' 불만', H.map(function (h) {
        var v = h.cs[c], b = band(v);
        return { v: v, k: verdict(v), nb: !!h.lr, h: '<b class="is-' + b + '">' + verdict(v) + '</b><span class="cmp-line">' + ratioHtml(v) + '</span><span class="cmp-bar"><i class="is-' + b + '" style="width:' + v + '%"></i></span>' };
      }), { best: 'min', lab: '불만 가장 적음' });
    }).join('');
    // 순위별 한 행(1·2·3위) — 호텔마다 항목명 길이가 달라도 같은 순위끼리 가로로 줄이 맞음. 이름/비율은 항상 2줄
    var nTop = Math.max.apply(null, H.map(function (h) { return (h.top || []).length; }));
    var g3 = nTop ? [0, 1, 2].slice(0, nTop).map(function (i) {
      return row(['가장 많은 불만', '두 번째', '세 번째'][i] + (i ? '' : ' <span class="cmp-kn">분석 리뷰 대비 비율</span>'), H.map(function (h) {
        var t = (h.top || [])[i];
        return { v: null, k: t ? t[0] + t[1] : '', h: t ? '<span class="cmp-tn">' + glue(esc(t[0])) + '</span><b class="cmp-tv">' + (+t[1]).toFixed(1) + '%</b>'
          : '<span class="cmp-none">' + (i ? '–' : '두드러진 불만 없음') + '</span>' };
      }));
    }).join('') : row('분석 리뷰 대비 비율', H.map(function () { return { v: null, k: '', h: '<span class="cmp-none">두드러진 불만 없음</span>' }; }));
    var g4 = FAQ.map(function (f) {
      return row(f[1], H.map(function (h) { var t = (h.fq || {})[f[0]]; return { v: null, k: t || '', h: t ? lines(t) : '<span class="cmp-none">리뷰 언급 없음</span>' }; }));
    }).join('');
    html += '<div class="cmp-grp"><div class="cmp-gt">핵심</div>' + g1 + '</div>'
      + '<div class="cmp-grp"><div class="cmp-gt">항목별 불만 <span>' + esc(window.CF_CITY_KO || '후쿠오카') + ' 호텔 평균과 비교</span></div>' + g2 + '</div>'
      + '<div class="cmp-grp"><div class="cmp-gt">리뷰에서 자주 나온 불만</div>' + g3 + '</div>'
      + '<div class="cmp-grp"><div class="cmp-gt">리뷰로 확인한 실전 정보</div>' + g4 + '</div>'
      + '<p class="cmp-note">수치는 공개 리뷰를 분석한 참고용 통계예요 · <a href="./about">산출 방법</a></p>'
      + '<div class="cmp-cta" style="' + cols + '"><span class="cmp-h-sp" aria-hidden="true"></span>'
      + H.map(function (h) { return '<a href="./hotels/' + h.id + '">분석 보기</a>'; }).join('')
      + (canAdd ? '<button type="button" class="cmp-cta-add" data-add="1">+ 호텔 추가</button>' : '') + '</div>';
    root.innerHTML = html;
    root.classList.toggle('is-diff-only', diffOnly);
  }

  /* ── 호텔 추가 팝업: 빈 검색 = 지금 비교 중인 호텔과 비슷한 가격대에서 실망 확률 낮은 순 추천,
        입력 시 = 검색 별칭 인덱스(초성·영문·일본어 표기) 매칭. 인덱스는 처음 열 때만 지연 로드 ── */
  var pick = null, idxP = null;
  function loadScript(src) {
    return new Promise(function (ok, no) { var s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = no; document.head.appendChild(s); });
  }
  function loadIdx() {
    if (!idxP) idxP = loadScript('./data/search_index.js').then(function () { return loadScript('./js/search-key.js'); })
      .then(function () { return loadScript('./js/search-ac.js'); }).catch(function () {});
    return idxP;
  }
  function norm(s) { return String(s || '').toLowerCase().replace(/\s+/g, ''); }
  function candidates(q) {
    var cur = ids(), pool = Object.keys(D).filter(function (id) { return cur.indexOf(id) < 0; });
    if (q) {
      var hit = (window.CFAutocomplete && window.CF_IDX) ? window.CFAutocomplete.matchIds(q) : [];
      var res = hit.filter(function (id) { return pool.indexOf(id) >= 0; });
      if (!res.length) res = pool.filter(function (id) { return norm(D[id].n).indexOf(norm(q)) >= 0; });
      return { sub: '"' + esc(q) + '" 검색 결과', ids: res.slice(0, 12) };
    }
    // 빈 검색 추천 = 비교 중인 호텔과 비슷한 위치(중심에서 2km) + 비슷한 가격대(±35%) → 추천순(실망 확률·한국인 리뷰·평점)
    // 조건을 만족하는 곳이 6곳 미만이면 위치만 → 가격만 → 전체 순으로 넓힌다 (2026-10, 사용자 요청)
    var krws = cur.map(function (id) { return D[id].krw; }).filter(function (k) { return k; });
    var avg = krws.length ? krws.reduce(function (a, b) { return a + b; }, 0) / krws.length : null;
    var pts = cur.map(function (id) { return D[id]; }).filter(function (h) { return h.la != null && h.lo != null; });
    var cLa = pts.length ? pts.reduce(function (a, h) { return a + h.la; }, 0) / pts.length : null;
    var cLo = pts.length ? pts.reduce(function (a, h) { return a + h.lo; }, 0) / pts.length : null;
    function kmTo(h) { if (cLa == null || h.la == null) return null; var dy = (h.la - cLa) * 111, dx = (h.lo - cLo) * 93; return Math.sqrt(dx * dx + dy * dy); }
    function nearLoc(id) { var d = kmTo(D[id]); return d != null && d <= 2; }
    function nearPrice(id) { var k = D[id].krw; return !!(avg && k && Math.abs(k - avg) / avg <= 0.35); }
    var near = pool.filter(function (id) { return nearLoc(id) && nearPrice(id); }), sub = '비교 중인 호텔과 비슷한 위치·가격대에서 추천순';
    if (near.length < 6 && cLa != null) { near = pool.filter(nearLoc); sub = '비교 중인 호텔과 가까운 위치에서 추천순'; }
    if (near.length < 6 && avg) { near = pool.filter(nearPrice); sub = '비교 중인 호텔과 비슷한 가격대에서 추천순'; }
    if (near.length < 6) { near = pool; sub = '추천순'; }
    near.sort(function (a, b) { return (D[b].rs || 0) - (D[a].rs || 0) || D[a].p - D[b].p || D[b].an - D[a].an; });
    return { sub: sub + ' · 실망 확률이 낮고 한국인 리뷰가 많은 순', ids: near.slice(0, 8) };
  }
  function pickRow(id) {
    var h = D[id], meta = ['1박 ' + (h.pt || '정보 없음')];
    if (h.st) meta.push(h.st);
    return '<li><button type="button" class="cp-item" data-pick="' + id + '">'
      + '<span class="cp-img">' + (h.img ? '<img src="' + esc(h.img) + '" alt="" loading="lazy">' : '') + '</span>'
      + '<span class="cp-info"><span class="cp-nm">' + esc(h.n) + '</span><span class="cp-meta">' + esc(meta.join(' · ')) + '</span></span>'
      + '<span class="cp-p is-' + (h.b || 'safe') + '">실망 ' + h.p + '%</span></button></li>';
  }
  function renderPick() {
    var q = pick.querySelector('.cp-q').value.trim(), c = candidates(q);
    pick.querySelector('.cp-sub').innerHTML = c.sub;
    pick.querySelector('.cp-list').innerHTML = c.ids.length ? c.ids.map(pickRow).join('')
      : '<li class="cp-empty">찾는 호텔이 없어요. 아직 분석되지 않은 호텔일 수 있어요.</li>';
  }
  function openPick() {
    if (ids().length >= MAX) { if (window.CFCompare) window.CFCompare.toast('비교는 ' + MAX + '곳까지 담을 수 있어요'); return; }
    if (!pick) {
      pick = document.createElement('div'); pick.className = 'cmp-pick'; pick.hidden = true;
      pick.setAttribute('role', 'dialog'); pick.setAttribute('aria-modal', 'true'); pick.setAttribute('aria-label', '비교할 호텔 추가');
      pick.innerHTML = '<div class="cp-dim" data-close="1"></div><div class="cp-panel">'
        + '<div class="cp-head"><b>비교할 호텔 추가</b><button type="button" class="cp-close" data-close="1" aria-label="닫기">✕</button></div>'
        + '<div class="cp-search"><input type="search" class="cp-q" placeholder="' + esc(window.CF_CITY_KO || '후쿠오카') + ' 호텔명 검색 (한글·영문·일본어)" autocomplete="off"></div>'
        + '<div class="cp-sub"></div><ul class="cp-list"></ul></div>';
      document.body.appendChild(pick);
      pick.addEventListener('click', function (e) {
        if (e.target.closest('[data-close]')) { closePick(); return; }
        var it = e.target.closest('[data-pick]'); if (!it) return;
        var a = ids(); if (a.length >= MAX) return;
        a.push(it.getAttribute('data-pick')); saveIds(a);
        ev('compare_add', { hotel_id: it.getAttribute('data-pick'), count: a.length, source: 'compare_page' });
        closePick(); render();
      });
      var t = null;
      pick.querySelector('.cp-q').addEventListener('input', function () { clearTimeout(t); t = setTimeout(renderPick, 120); });
    }
    pick.querySelector('.cp-q').value = '';
    renderPick();
    pick.hidden = false; void pick.offsetHeight; pick.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    pick.querySelector('.cp-q').focus();
    loadIdx().then(function () { if (pick.classList.contains('is-open') && pick.querySelector('.cp-q').value) renderPick(); });
  }
  function closePick() {
    if (!pick) return;
    pick.classList.remove('is-open'); document.body.style.overflow = '';
    setTimeout(function () { pick.hidden = true; }, 200);
  }
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && pick && pick.classList.contains('is-open')) closePick(); });

  root.addEventListener('click', function (e) {
    if (e.target.closest('[data-add]')) { openPick(); return; }
    var x = e.target.closest('[data-x]');
    if (x) {
      var id = x.getAttribute('data-x');
      saveIds(ids().filter(function (it) { return it !== id; }));
      render(); return;
    }
    if (e.target.closest('#cmp-diff')) { diffOnly = !diffOnly; render(); }
  });
  render();
})();

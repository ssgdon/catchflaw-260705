/* P5 비교 페이지 렌더 — window.CF_CMP(data/compare.js) + ?ids= 또는 비교함(localStorage).
   행마다 가장 좋은 값 강조, "차이 나는 항목만" 토글, 맨 위 한 줄 비교(실측 조립). */
(function () {
  var D = window.CF_CMP || {}, FAQ = window.CF_CMP_FAQ || [];
  var CATS = ['위생', '냄새', '소음', '시설', '불친절', '위치·안전'];
  var root = document.getElementById('cmp-root');
  var diffOnly = false;

  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function josa(w, a, b) { var c = w.charCodeAt(w.length - 1) - 0xAC00; return (c >= 0 && c <= 11171) ? (c % 28 ? a : b) : a + '(' + b + ')'; }
  function band(v) { return v >= 70 ? 'danger' : v >= 45 ? 'warning' : 'safe'; }

  function ids() {
    var m = location.search.match(/[?&]ids=([^&]+)/), a;
    if (m) {
      a = decodeURIComponent(m[1]).split(',').filter(function (id) { return D[id]; }).slice(0, 3);
      // 공유 링크로 들어오면 비교함도 그 구성으로 맞춤(트레이·담기 버튼 상태 일치)
      if (window.CFCompare) {
        try { localStorage.setItem('cf_cmp', JSON.stringify(a.map(function (id) { return { id: id, n: D[id].n, img: D[id].img }; }))); } catch (e) {}
      }
      return a;
    }
    return (window.CFCompare ? window.CFCompare.get() : []).map(function (x) { return x.id; }).filter(function (id) { return D[id]; });
  }

  function row(label, cells, opt) {
    opt = opt || {};
    var nums = cells.map(function (c) { return c.v; });
    var best = null;
    if (opt.best && nums.every(function (n) { return typeof n === 'number'; })) {
      best = opt.best === 'min' ? Math.min.apply(null, nums) : Math.max.apply(null, nums);
      if (nums.every(function (n) { return n === best; })) best = null;
    }
    var same = cells.every(function (c) { return c.k === cells[0].k; });
    return '<div class="cmp-tr' + (same ? ' is-same' : '') + '"><div class="cmp-k">' + label + '</div><div class="cmp-v">'
      + cells.map(function (c) {
          var on = best !== null && c.v === best;
          return '<div class="cmp-cell' + (on ? ' is-best' : '') + '">' + c.h + (on ? '<span class="cmp-best">' + (opt.lab || '가장 좋음') + '</span>' : '') + '</div>';
        }).join('') + '</div></div>';
  }
  function num(v, unit) { return { v: v, k: String(v), h: '<b>' + esc(v) + (unit || '') + '</b>' }; }

  function summary(H) {
    var lo = H.slice().sort(function (a, b) { return a.p - b.p; })[0];
    var s = '실망 확률은 <em>' + esc(lo.n) + '</em>' + josa(lo.n, '이', '가') + ' 가장 낮아요(' + lo.p + '%).';
    var hi = H.filter(function (h) { return h !== lo && h.top && h.top.length; })
      .sort(function (a, b) { return b.top[0][1] - a.top[0][1]; })[0];
    if (hi) s += ' <em>' + esc(hi.n) + '</em>' + josa(hi.n, '은', '는') + ' ' + esc(hi.top[0][0]) + ' 불만 비율이 가장 높아요(' + hi.top[0][1] + '%).';
    return s;
  }

  function render() {
    var list = ids(), H = list.map(function (id) { var d = D[id]; d.id = id; return d; });
    if (typeof gtag === 'function') gtag('event', 'compare_view', { count: H.length });
    if (H.length < 2) {
      root.innerHTML = '<div class="cmp-empty"><div class="ce-tit">비교할 호텔을 2곳 이상 담아주세요</div>'
        + '<div class="ce-txt">호텔 상세나 검색 결과에서 <b>비교 담기</b>를 누르면 여기서 나란히 볼 수 있어요 (최대 3곳)</div>'
        + (H.length ? '<div class="ce-one">담긴 호텔: ' + esc(H[0].n) + '</div>' : '')
        + '<a class="ce-btn" href="./search">호텔 찾으러 가기</a></div>';
      return;
    }
    var cols = 'grid-template-columns:repeat(' + H.length + ',minmax(0,1fr))';
    var html = '<div class="cmp-hd" style="' + cols + '">' + H.map(function (h) {
        return '<div class="cmp-h"><a href="./hotels/' + h.id + '"><span class="cmp-img">' + (h.img ? '<img src="' + esc(h.img) + '" alt="">' : '') + '</span>'
          + '<span class="cmp-nm">' + esc(h.n) + '</span></a><button type="button" class="cmp-x" data-x="' + h.id + '" aria-label="비교에서 빼기">×</button></div>';
      }).join('') + '</div>';
    html += '<div class="cmp-sum"><div class="cmp-sum-box"><div class="cmp-eyebrow">한 줄 비교</div><p class="cmp-lead">' + summary(H) + '</p></div>'
      + '<div class="cmp-tools"><span>보라색 = 이 항목에서 가장 좋은 곳</span>'
      + '<button type="button" class="cmp-switch' + (diffOnly ? ' is-on' : '') + '" id="cmp-diff"><i></i>차이 나는 항목만</button></div></div>';

    var g1 = row('실망 확률', H.map(function (h) { return num(h.p, '%'); }), { best: 'min', lab: '가장 낮음' })
      // 가격은 표시 단위(만원)로 비교 — '약 7만원' 두 곳 중 한 곳만 강조되는 착시 방지
      + row('1박 평균', H.map(function (h) { return { v: h.krw != null ? Math.round(h.krw / 10000) : null, k: h.pt, h: h.pt ? '<b>' + esc(h.pt) + '</b>' : '<span class="cmp-none">정보 없음</span>' }; }), { best: 'min', lab: '가장 저렴' })
      + row('가까운 역', H.map(function (h) { return { v: h.sm, k: h.st, h: h.st ? esc(h.st) : '<span class="cmp-none">-</span>' }; }), { best: 'min', lab: '가장 가까움' })
      + row('구글 평점', H.map(function (h) { return { v: h.g, k: String(h.g), h: '<b>' + h.g.toFixed(1) + '</b> <span class="cmp-sub">(' + h.rc.toLocaleString() + ')</span>' }; }), { best: 'max', lab: '가장 높음' })
      + row('분석한 리뷰', H.map(function (h) { return num(h.an, '건'); }), { best: 'max', lab: '근거 가장 많음' });
    var g2 = CATS.map(function (c) {
      return row(c, H.map(function (h) {
        var v = h.cs[c], b = band(v);
        return { v: v, k: String(v), h: '<b class="is-' + b + '">' + v + '</b><span class="cmp-bar"><i class="is-' + b + '" style="width:' + v + '%"></i></span>' };
      }), { best: 'min', lab: '가장 낮음' });
    }).join('');
    var g3 = row('최근 1년 리뷰 대비 비율', H.map(function (h) {
      return { v: null, k: JSON.stringify(h.top), h: (h.top && h.top.length) ? h.top.map(function (t) { return '<div class="cmp-top">' + esc(t[0]) + ' <b>' + t[1] + '%</b></div>'; }).join('') : '<span class="cmp-none">두드러진 불만 없음</span>' };
    }));
    var g4 = FAQ.map(function (f) {
      return row(f[1], H.map(function (h) { var t = (h.fq || {})[f[0]]; return { v: null, k: t || '', h: t ? esc(t) : '<span class="cmp-none">리뷰 언급 없음</span>' }; }));
    }).join('');
    html += '<div class="cmp-grp"><div class="cmp-gt">핵심</div>' + g1 + '</div>'
      + '<div class="cmp-grp"><div class="cmp-gt">카테고리 위험도 <span>낮을수록 좋음 · 평균 50</span></div>' + g2 + '</div>'
      + '<div class="cmp-grp"><div class="cmp-gt">리뷰에서 자주 나온 불만</div>' + g3 + '</div>'
      + '<div class="cmp-grp"><div class="cmp-gt">리뷰로 확인한 실전 정보</div>' + g4 + '</div>'
      + '<p class="cmp-note">수치는 공개 리뷰를 분석한 참고용 통계예요 · <a href="./about">산출 방법</a></p>'
      + '<div class="cmp-cta" style="' + cols + '">' + H.map(function (h) { return '<a href="./hotels/' + h.id + '">분석 보기</a>'; }).join('') + '</div>';
    root.innerHTML = html;
    root.classList.toggle('is-diff-only', diffOnly);
  }

  root.addEventListener('click', function (e) {
    var x = e.target.closest('[data-x]');
    if (x) {
      var id = x.getAttribute('data-x');
      var a = (window.CFCompare ? window.CFCompare.get() : []).filter(function (it) { return it.id !== id; });
      if (window.CFCompare) window.CFCompare.set(a);
      history.replaceState(null, '', './compare' + (a.length ? '?ids=' + a.map(function (it) { return it.id; }).join(',') : ''));
      render(); return;
    }
    if (e.target.closest('#cmp-diff')) { diffOnly = !diffOnly; render(); }
  });
  render();
})();

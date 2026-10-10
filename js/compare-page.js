/* P5 비교 페이지 렌더 — window.CF_CMP(data/compare.js) + ?ids= 또는 비교함(localStorage).  v3 §7-4
   구성: '+ 호텔 추가'(3곳 미만) → 큰 머리(칸 너비 4:3 사진 + 빼기 X) → 고정 머리(색 점 + 호텔명 · 3줄 클램프) → 한눈에 비교(방사형·희소 건수 표·가격 막대) →
         그룹(핵심 / 항목별 불만 / 자주 나온 불만 / 실전 정보). 숫자 행(실망 확률·가격·평점·분석 리뷰)만 16/700, 글 행은 14/400(3줄까지).
   행마다 가장 좋은 값 강조(--hl). 칸 수 = 호텔 수(빈 '호텔 추가' 칸 없음, 2026-10-10). 추가 → 검색 팝업(별칭 인덱스 지연 로드). */
(function () {
  var D = window.CF_CMP || {}, FAQ = window.CF_CMP_FAQ || [];
  var CATS = ['청결', '냄새', '소음', '객실', '직원', '위치'];   // 분류 v5 점수 대분류 (안전은 칩 전용이라 비교표 제외)
  var MAX = 3;
  var root = document.getElementById('cmp-root');
  var pad = 0;   // 2026-10-10: '호텔 추가' 빈 칸 없음 — 2곳이면 2칸이 폭을 나눠 쓴다(추가 버튼은 제목 줄). 각 행의 빈 칸 수는 늘 0

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
  var NB = ' ';
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

  // opt.num: 숫자 행(16/700) · 그 외 글 행(14/400). opt.best 'min'|'max' + opt.lab: 가장 좋은 칸 표시
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
    return '<div class="cmp-tr' + (opt.num ? ' is-num' : '') + (same ? ' is-same' : '') + '"><div class="cmp-k">' + label + '</div><div class="cmp-v">'
      + cells.map(function (c) {
          var on = best !== null && !c.nb && c.v === best;
          return '<div class="cmp-cell' + (on ? ' is-best' : '') + '">' + c.h + (on ? '<span class="cmp-best">' + glue(opt.lab || '가장 좋음') + '</span>' : '') + '</div>';
        }).join('') + blank + '</div></div>';
  }
  function num(v, unit) { return { v: v, k: String(v), h: '<b>' + esc(v) + (unit || '') + '</b>' }; }

  // ── 한눈에 비교 (2026-10-10 개편): 글 요약 대신 그림 3개 — ① 불만 6항목 방사형 ② 드물지만 치명적인 리뷰 건수 표 ③ 평일~주말 가격 막대.
  //    호텔 색(is-c0~2)은 머리 이름 앞 점과 같아서 범례 없이도 어느 호텔인지 이어진다.
  var AVG = window.CF_CITY_AVG || 5, CITY = window.CF_CITY_KO || '후쿠오카';
  var RARE = window.CF_CMP_RARE || [['벌레', '벌레'], ['곰팡이', '곰팡이'], ['동네 분위기', '밤길·동네 분위기'], ['객실 보안', '보안·안전사고']];
  function sname(h) { return h.sn || h.cn || h.n; }
  function dot(i) { return '<i class="cv-dot is-c' + i + '" aria-hidden="true"></i>'; }
  function man(krw) { return Math.max(1, Math.round(krw / 10000)); }

  // ① 방사형: 축 6개(청결부터 시계 방향), 값 = 항목 위험도 0~100(도시 평균 50 = 점선, 바깥일수록 불만 많음)
  function radar(H) {
    var W = 320, Hh = 280, cx = W / 2, cy = 140, R = 100, n = CATS.length;
    function pt(i, v) { var t = -Math.PI / 2 + i * 2 * Math.PI / n, r = R * Math.min(Math.max(v, 0), 100) / 100; return [cx + r * Math.cos(t), cy + r * Math.sin(t)]; }
    function poly(v) { return CATS.map(function (c, i) { var p = pt(i, typeof v === 'number' ? v : v[c]); return p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join(' '); }
    var g = [25, 75, 100].map(function (v) { return '<polygon class="cv-grid" points="' + poly(v) + '"/>'; }).join('')
      + '<polygon class="cv-avg" points="' + poly(50) + '"/>'
      + CATS.map(function (c, i) { var p = pt(i, 100); return '<line class="cv-axis" x1="' + cx + '" y1="' + cy + '" x2="' + p[0].toFixed(1) + '" y2="' + p[1].toFixed(1) + '"/>'; }).join('');
    var lab = CATS.map(function (c, i) {
      var t = -Math.PI / 2 + i * 2 * Math.PI / n, x = cx + (R + 18) * Math.cos(t), y = cy + (R + 18) * Math.sin(t);
      var anc = Math.abs(Math.cos(t)) < 0.2 ? 'middle' : (Math.cos(t) > 0 ? 'start' : 'end');
      return '<text class="cv-lab" x="' + x.toFixed(1) + '" y="' + (y + 5).toFixed(1) + '" text-anchor="' + anc + '">' + esc(c) + '</text>';
    }).join('');
    var polys = H.map(function (h, i) { return '<polygon class="cv-poly is-c' + i + (h.lr ? ' is-lr' : '') + '" points="' + poly(h.cs) + '"/>'; }).join('');
    var legend = H.map(function (h, i) { return '<li>' + dot(i) + esc(sname(h)) + (h.lr ? '<small>리뷰 적음·참고용</small>' : '') + '</li>'; }).join('')
      + '<li class="cv-lg-avg"><i class="cv-dash" aria-hidden="true"></i>' + esc(CITY) + ' 평균</li>';
    return '<section class="cv-blk cv-radar"><h3 class="cv-t">불만 항목</h3><p class="cv-s">바깥으로 갈수록 불만이 많아요</p>'
      + '<svg class="cv-svg" viewBox="0 0 ' + W + ' ' + Hh + '" role="img" aria-label="호텔별 불만 6항목 비교">' + g + polys + lab + '</svg>'
      + '<ul class="cv-legend">' + legend + '</ul></section>';
  }

  // ② 드물지만 치명적인 리뷰(벌레·곰팡이·밤길·보안): 최근 1년 리뷰 건수, 심각이 있으면 색 + '심각 N'
  function rareTable(H) {
    var head = '<tr><th scope="col"><span class="blind">항목</span></th>' + H.map(function (h, i) { return '<th scope="col">' + dot(i) + '<span class="cv-th">' + esc(sname(h)) + '</span></th>'; }).join('') + '</tr>';
    var body = RARE.map(function (r) {
      return '<tr><th scope="row">' + glue(esc(r[1])) + '</th>' + H.map(function (h) {
        var v = h.rr && h.rr[r[0]];
        if (!v) return '<td class="is-none">–</td>';
        var tone = v[1] >= 3 ? 'danger' : v[1] > 0 ? 'warning' : v[0] > 0 ? 'some' : 'zero';
        return '<td class="is-' + tone + '"><b>' + v[0] + '건</b>' + (v[1] ? '<small>심각 ' + v[1] + '</small>' : '') + '</td>';
      }).join('') + '</tr>';
    }).join('');
    return '<section class="cv-blk cv-rare"><h3 class="cv-t">드물지만 치명적인 리뷰</h3><p class="cv-s">최근 1년 리뷰 건수 · 색이 있으면 심각 리뷰 포함</p>'
      + '<table class="cv-tbl"><thead>' + head + '</thead><tbody>' + body + '</tbody></table></section>';
  }

  // ③ 1박 가격: 호텔마다 한 줄 — 평일(채운 점)에서 주말(빈 점)까지 막대, 점 위에 숫자(만원)만, 축은 0부터(길이 = 가격). 글 줄 없음(2026-10-10)
  function priceChart(H) {
    var mx = 0;
    H.forEach(function (h) { if (h.krw) mx = Math.max(mx, man(h.krw)); if (h.pw) mx = Math.max(mx, man(h.pw)); });
    if (!mx) return '';
    var top = Math.max(10, Math.ceil(mx / 10) * 10), step = top > 40 ? 20 : 10, ticks = [];
    for (var t = 0; t <= top; t += step) ticks.push(t);
    function x(v) { return (v / top * 100).toFixed(1) + '%'; }
    var rows = H.map(function (h, i) {
      var wd = h.krw ? man(h.krw) : null, we = h.pw ? man(h.pw) : null;
      var name = '<div class="cv-pn">' + dot(i) + esc(sname(h)) + '</div>';
      if (wd == null) return '<li class="cv-pr">' + name + '<p class="cv-pv">가격 정보 없음</p></li>';
      // 숫자는 점 바로 위(단위 '만원'은 아래 축에만). 두 점이 가까우면(축의 12% 안) 평일은 왼쪽·주말은 오른쪽으로 벌려 겹치지 않게
      var near = we != null && (we - wd) / top < 0.12;
      return '<li class="cv-pr">' + name + '<div class="cv-track">'
        + (we != null ? '<span class="cv-span is-c' + i + '" style="left:' + x(wd) + ';width:' + x(Math.max(we - wd, 0)) + '"></span>' : '')
        + '<span class="cv-pt is-wd is-c' + i + '" style="left:' + x(wd) + '"></span>'
        + (we != null ? '<span class="cv-pt is-we is-c' + i + '" style="left:' + x(we) + '"></span>' : '')
        + '<span class="cv-lb is-wd' + (near ? ' is-l' : '') + '" style="left:' + x(wd) + '" aria-label="평일 약 ' + wd + '만원">' + wd + '</span>'
        + (we != null ? '<span class="cv-lb is-we' + (near ? ' is-r' : '') + '" style="left:' + x(we) + '" aria-label="주말 약 ' + we + '만원">' + we + '</span>' : '')
        + '</div></li>';
    }).join('');
    var axis = '<div class="cv-axis-x" aria-hidden="true">' + ticks.map(function (t) { return '<span style="left:' + x(t) + '">' + t + (t === top ? '만원' : '') + '</span>'; }).join('') + '</div>';
    return '<section class="cv-blk cv-price"><h3 class="cv-t">1박 가격</h3><p class="cv-s">2인 1박 · <span class="cv-key"><i class="cv-k is-wd"></i>평일</span> <span class="cv-key"><i class="cv-k is-we"></i>주말(금·토)</span></p>'
      + '<ul class="cv-prs">' + rows + '</ul>' + axis + '</section>';
  }

  function summary(H) {
    if (H.length < 2) return '<p class="cmp-lead">호텔을 하나 더 추가하면 그래프로 나란히 비교해요</p>';
    return '<div class="cmp-viz">' + radar(H) + '<div class="cv-side">' + rareTable(H) + priceChart(H) + '</div></div>';
  }

  function render() {
    var list = ids(), H = list.map(function (id) { var d = D[id]; d.id = id; return d; });
    ev('compare_view', { count: H.length });
    if (!H.length) {
      pad = 0;
      root.innerHTML = '<div class="page-empty cmp-empty"><p class="pe-txt">호텔을 2곳 이상 담으면 나란히 비교해요. 최대 ' + MAX + '곳까지 담을 수 있어요</p>'
        + '<div class="pe-btns"><a class="btn-brand" href="./search">호텔 둘러보기</a><button type="button" class="btn-line" data-add="1">호텔 이름으로 추가</button></div></div>';
      return;
    }
    var canAdd = H.length < MAX;
    pad = 0;
    var cols = '--n:' + H.length;   // 칸 수 = 호텔 수(모바일 n칸 · PC는 왼쪽 항목명 칸 + n칸)
    var sp = '<div class="cmp-h-sp" aria-hidden="true"></div>';
    // 제목 줄 오른쪽 '+ 호텔 추가'(3곳 미만일 때) — 빈 칸을 두지 않아 2곳이면 2칸이 넓게
    var html = canAdd ? '<div class="cmp-addbar"><button type="button" class="btn-line btn-sm cmp-add-btn" data-add="1">+ 호텔 추가</button></div>' : '';
    // 큰 머리: 칸 너비를 채우는 4:3 사진 + 빼기 X (스크롤하면 사라짐) — 이름은 아래 고정 머리 한 곳에만 둔다
    html += '<div class="cmp-top" style="' + cols + '">' + sp + H.map(function (h) {
        return '<div class="cmp-th"><a class="cmp-img" href="./hotels/' + h.id + '" tabindex="-1" aria-hidden="true">' + (h.img ? '<img src="' + esc(h.img) + '" alt="">' : '') + '</a>'
          + '<button type="button" class="cmp-x" data-x="' + h.id + '" aria-label="' + esc(h.n) + ' 비교에서 빼기"></button></div>';
      }).join('') + '</div>';
    // 고정 머리: 호텔 색 점 + 호텔명(3줄 클램프) — 그래프 색과 같은 점
    html += '<div class="cmp-hd" style="' + cols + '">' + sp + H.map(function (h, i) {
        return '<a class="cmp-nm" href="./hotels/' + h.id + '">' + (H.length > 1 ? dot(i) : '') + esc(h.cn || h.n) + '</a>';
      }).join('') + '</div>';
    html += '<div class="cmp-sum"><h2 class="cmp-gt cmp-sum-t">한눈에 비교</h2>' + summary(H) + '</div>';

    var g1 = row('실망 확률', H.map(function (h) {
        var c = num(h.p, '%');
        if (h.lr) { c.nb = true; c.h += '<span class="cmp-sub">리뷰' + NB + '적음</span>'; }   // 리뷰 적은 호텔은 순위 강조 제외
        return c;
      }), { best: 'min', lab: '가장 낮음', num: true })
      // 가격은 표시 단위(만원)로 비교 — '약 7만원' 두 곳 중 한 곳만 강조되는 착시 방지. krw = 날짜별 표본의 중앙값
      // 평일 가격이 없는 칸(주말만·가격 정보 없음)은 '가장 저렴' 후보에서만 뺀다 — 한 곳이라도 없으면 강조가 통째로 사라지던 문제
      + row('평일 1박', H.map(function (h) {
          var t = h.pt ? String(h.pt).replace(/^평일\s*/, '') : '';   // '평일 약 13만원' → '약 13만원'(라벨이 '평일 1박'). 주말만 있으면 '주말 약 34만원' 그대로
          return { v: h.krw != null ? Math.round(h.krw / 10000) : null, nb: h.krw == null, k: h.pt, h: t ? '<b>' + esc(t) + '</b>' : '<span class="cmp-none">가격 정보 없음</span>' };
        }), { best: 'min', lab: '가장 저렴', num: true })
      + row('가까운 역', H.map(function (h) { return { v: h.sm, k: h.st, h: h.st ? glue(esc(h.st)) : '<span class="cmp-none">-</span>' }; }), { best: 'min', lab: '가장 가까움' })
      + row('구글 평점', H.map(function (h) { return { v: h.g, k: String(h.g), h: '<b>' + h.g.toFixed(1) + '</b><span class="cmp-sub">(' + h.rc.toLocaleString() + ')</span>' }; }), { best: 'max', lab: '가장 높음', num: true })
      + row('분석한 리뷰', H.map(function (h) { return { v: h.an, k: String(h.an), h: '<b>' + esc(h.an) + '건</b><span class="cmp-sub">' + glue(esc(h.pd || '최근 1년')) + '</span>' }; }), { best: 'max', lab: '근거 가장 많음', num: true });
    var g2 = CATS.map(function (c) {
      return row(c + ' 불만', H.map(function (h) {
        var v = h.cs[c], b = band(v);
        return { v: v, k: verdict(v), nb: !!h.lr, h: '<span class="cmp-vd"><i class="sdot is-' + b + '"></i>' + verdict(v) + '</span><span class="cmp-line">' + ratioHtml(v) + '</span><span class="cmp-bar"><i class="is-' + b + '" style="width:' + v + '%"></i></span>' };
      }), { best: 'min', lab: '불만 가장 적음' });
    }).join('');
    // 순위별 한 행(1·2·3위) — 호텔마다 항목명 길이가 달라도 같은 순위끼리 가로로 줄이 맞음. 이름/비율은 항상 2줄
    var nTop = Math.max.apply(null, H.map(function (h) { return (h.top || []).length; }));
    // 2026-10-10 가독성: 행 이름 '1위 불만'·'2위'·'3위', 칸 = 불만 이름 16/600 → 비율 14 + 막대(표 전체 최댓값 기준이라 호텔끼리 길이로 비교)
    var topMax = Math.max.apply(null, [0.1].concat(H.map(function (h) { return (h.top || []).reduce(function (m, t) { return Math.max(m, +t[1] || 0); }, 0); })));
    var g3 = nTop ? [0, 1, 2].slice(0, nTop).map(function (i) {
      return row((i + 1) + '위 불만', H.map(function (h) {
        var t = (h.top || [])[i];
        return { v: null, k: t ? t[0] + t[1] : '', h: t ? '<span class="cmp-tn">' + glue(esc(t[0])) + '</span><span class="cmp-tv">' + (+t[1]).toFixed(1) + '%</span>'
          + '<span class="cmp-bar"><i class="is-warning" style="width:' + Math.max(4, Math.round((+t[1] / topMax) * 100)) + '%"></i></span>'
          : '<span class="cmp-none">' + (i ? '–' : '두드러진 불만 없음') + '</span>' };
      }));
    }).join('') : row('분석 리뷰 대비 비율', H.map(function () { return { v: null, k: '', h: '<span class="cmp-none">두드러진 불만 없음</span>' }; }));
    var g4 = FAQ.map(function (f) {
      return row(f[1], H.map(function (h) { var t = (h.fq || {})[f[0]]; return { v: null, k: t || '', h: t ? lines(t) : '<span class="cmp-none">리뷰 언급 없음</span>' }; }));
    }).join('');
    html += '<div class="cmp-grp"><h2 class="cmp-gt">핵심</h2><p class="cmp-gs">보라색 칸이 가장 좋은 곳이에요</p>' + g1 + '</div>'
      + '<div class="cmp-grp"><h2 class="cmp-gt">항목별 불만</h2><p class="cmp-gs">' + esc(window.CF_CITY_KO || '후쿠오카') + ' 호텔 평균과 비교해요</p>' + g2 + '</div>'
      + '<div class="cmp-grp"><h2 class="cmp-gt">자주 나온 불만</h2><p class="cmp-gs">분석한 리뷰 중 이 불만이 나온 비율이에요</p>' + g3 + '</div>'
      + '<div class="cmp-grp"><h2 class="cmp-gt">실전 정보</h2><p class="cmp-gs">리뷰에서 확인한 내용이에요</p>' + g4 + '</div>'
      + '<p class="cmp-note">공개 리뷰를 분석한 참고용 통계예요 · <a href="./about">산출 방법</a></p>';
    root.innerHTML = html;
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
      return { sub: '‘' + esc(q) + '’ 검색 결과', ids: res.slice(0, 12) };
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
    var near = pool.filter(function (id) { return nearLoc(id) && nearPrice(id); }), sub = '비슷한 위치·가격대에서 추천순';
    if (near.length < 6 && cLa != null) { near = pool.filter(nearLoc); sub = '가까운 위치에서 추천순'; }
    if (near.length < 6 && avg) { near = pool.filter(nearPrice); sub = '비슷한 가격대에서 추천순'; }
    if (near.length < 6) { near = pool; sub = '추천순'; }
    near.sort(function (a, b) { return (D[b].rs || 0) - (D[a].rs || 0) || D[a].p - D[b].p || D[b].an - D[a].an; });
    return { sub: sub, ids: near.slice(0, 8) };   // 부제는 14 한 줄(v3 §5-8 ⑩)
  }
  // 컴팩트 행(§6-4): 썸네일 56 + 이름 16/600(최대 2줄) + 메타 14 '● 실망 확률 4% · 평일 약 13만원 · 하카타역 도보 5분'. 오른쪽 열 없음
  function pickRow(id) {
    var h = D[id], meta = ['<span class="seg"><i class="cp-dot is-' + esc(h.b || 'safe') + '"></i>실망 확률 ' + h.p + '%</span>'];
    meta.push('<span class="seg">· ' + esc(h.pt || '가격 정보 없음') + '</span>');   // 구분점은 뒤 묶음에 붙여 줄 끝에 매달리지 않게(§15)
    if (h.st) meta.push('<span class="seg">· ' + esc(h.st) + '</span>');
    return '<li><button type="button" class="cp-item" data-pick="' + id + '">'
      + '<span class="cp-img">' + (h.img ? '<img src="' + esc(h.img) + '" alt="" loading="lazy">' : '') + '</span>'
      + '<span class="cp-info"><span class="cp-nm">' + esc(h.cn || h.n) + '</span><span class="cp-meta">' + meta.join(' ') + '</span></span></button></li>';
  }
  function renderPick() {
    var q = pick.querySelector('.cp-q').value.trim(), c = candidates(q);
    pick.querySelector('.cp-sub').innerHTML = c.sub;
    pick.querySelector('.cp-list').innerHTML = c.ids.length ? c.ids.map(pickRow).join('')
      : '<li class="cp-empty">찾는 호텔이 없어요. 아직 분석하지 않은 호텔일 수 있어요</li>';
  }
  // A 페이지 시트 · H1 '비교할 호텔 추가' · 푸터 없음(행 탭 = 추가). 뒤로가기·ESC·딤·X는 CF.sheet
  function openPick(e) {
    if (ids().length >= MAX) { if (window.CFCompare) window.CFCompare.toast('비교는 ' + MAX + '곳까지 담을 수 있어요'); return; }
    if (!pick) {
      pick = CF.sheet.make({
        id: 'cmp-add', type: 'sheet', w: 'md', head: 'bar', title: '비교할 호텔 추가',
        body: '<div class="cp-search"><input type="search" class="ov-input cp-q" placeholder="호텔명 검색 (한글·영문·일본어)" autocomplete="off" aria-label="호텔명 검색"></div>'
          + '<p class="cp-sub"></p><ul class="cp-list"></ul>'
      });
      pick.addEventListener('click', function (e) {
        var it = e.target.closest('[data-pick]'); if (!it) return;
        var a = ids(); if (a.length >= MAX) return;
        a.push(it.getAttribute('data-pick'));
        ev('compare_add', { hotel_id: it.getAttribute('data-pick'), count: a.length, source: 'compare_page' });
        // 시트를 먼저 닫고(버퍼 소비 back) 그 뒤에 주소를 바꾼다 — 반대 순서면 back()이 옛 ?ids=로 되돌림
        CF.sheet.close(pick, { afterHistory: function () { saveIds(a); render(); } });
      });
      var t = null;
      pick.querySelector('.cp-q').addEventListener('input', function () { clearTimeout(t); t = setTimeout(renderPick, 120); });
    }
    pick.querySelector('.cp-q').value = '';
    renderPick();
    pick.querySelector('.ov-body').scrollTop = 0;
    CF.sheet.open(pick, { focus: '.cp-q', opener: e && e.target.closest('[data-add]') });
    loadIdx().then(function () { if (CF.sheet.isOpen(pick) && pick.querySelector('.cp-q').value) renderPick(); });
  }

  root.addEventListener('click', function (e) {
    if (e.target.closest('[data-add]')) { openPick(e); return; }
    var x = e.target.closest('[data-x]');
    if (x) {
      var id = x.getAttribute('data-x'), cur = ids(), at = cur.indexOf(id);
      saveIds(cur.filter(function (it) { return it !== id; }));
      render();
      // 빼기 버튼이 사라지면 포커스가 body로 떨어짐 → 같은 자리(없으면 앞) 빼기 버튼, 다 비면 제목으로
      var xs = root.querySelectorAll('.cmp-x'), nx = xs[Math.min(at, xs.length - 1)];
      var h1 = document.querySelector('#cmp h1');
      if (nx) nx.focus();
      else if (h1) { h1.setAttribute('tabindex', '-1'); h1.focus(); }
      return;
    }
  });
  render();
})();

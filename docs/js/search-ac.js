/* 캐치플로 검색 자동완성 (홈 #hero-q + search.html #q 공용) — §7-c
   의존: jQuery, js/search-key.js(CFSearchKey), data/search_index.js(window.CF_IDX)
   window.CF_AREAS(인기 지역), window.CF_SB(Supabase INSERT)
   각 검색창은 data-ac-href 로 상세 링크 접두사(홈="./hotels/", search="./hotels/") 지정. */
(function () {
  'use strict';

  // 등급 색은 토큰 변수로(--safe·--warning·--danger), 없으면 메타 회색

  function toast(msg) { CF.toast(msg); }   // 토스트 1벌(js/backnav.js)

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* ── 토큰 매칭 (FEEDBACK-2610 §15) ──
     쿼리를 공백·구두점으로 나누고, 붙여 쓴 덩어리(6자모+)는 인덱스 토큰 사전(전 호텔 tok 합집합)으로 최장일치 분할.
     불용어(호텔·후쿠오카·더) 제거 → 쿼리 토큰 **전부**가 호텔 tok 중 하나와 접두 일치 또는 자모 편집거리 ≤1(6자모+)이면 매칭.
     기존 keys 전체 부분일치·초성 매칭은 그대로 두고(가산점 5) 합친다. 점수 = 정확×3 + 접두×2 + 오타×1 + keys 보너스 5 + pop. */
  var STOP = null, DICT = null, DICT_MAX = 0;
  function K(s) { return window.CFSearchKey.toKey(s).full; }
  function prep() {
    if (DICT) return;
    STOP = {}; ['호텔', 'hotel', 'ホテル', '후쿠오카', 'fukuoka', '福岡', '더', 'the'].forEach(function (w) { STOP[K(w)] = 1; });
    DICT = {};
    (window.CF_IDX || []).forEach(function (it) {
      (it.tok || []).forEach(function (t) { DICT[t] = 1; if (t.length > DICT_MAX) DICT_MAX = t.length; });
    });
  }
  function segment(k) {   // 자모키 덩어리 → 사전 최장일치 조각들(사전에 없는 부분은 이어 붙여 한 조각)
    var out = [], buf = '', i = 0;
    while (i < k.length) {
      var hit = 0;
      for (var j = Math.min(k.length, i + DICT_MAX); j > i + 1; j--) { if (DICT[k.slice(i, j)]) { hit = j; break; } }
      if (hit) { if (buf) { out.push(buf); buf = ''; } out.push(k.slice(i, hit)); i = hit; }
      else { buf += k.charAt(i); i++; }
    }
    if (buf) out.push(buf);
    return out;
  }
  function qTokens(q) {
    prep();
    var parts = String(q).split(/[\s\-·・.,'"&()~!?/|:;\[\]]+/), toks = [];
    parts.forEach(function (p) {
      var k = K(p); if (!k) return;
      (k.length >= 6 ? segment(k) : [k]).forEach(function (t) { if (!STOP[t]) toks.push(t); });
    });
    return toks;
  }
  function lev1(a, b) {   // 편집거리 ≤ 1 여부
    if (a === b) return true;
    var la = a.length, lb = b.length;
    if (Math.abs(la - lb) > 1) return false;
    var i = 0, j = 0, d = 0;
    while (i < la && j < lb) {
      if (a.charAt(i) === b.charAt(j)) { i++; j++; continue; }
      if (++d > 1) return false;
      if (la > lb) i++; else if (lb > la) j++; else { i++; j++; }
    }
    return d + (la - i) + (lb - j) <= 1;
  }
  function tokScore(qt, toks) {   // 쿼리 토큰 1개의 최고 점수: 정확 3 · 접두 2 · 오타 1 · 없음 0
    var best = 0;
    for (var i = 0; i < toks.length; i++) {
      var t = toks[i];
      if (t === qt) return 3;
      if (t.indexOf(qt) === 0) { best = 2; continue; }
      if (best < 1 && qt.length >= 6 && (lev1(qt, t) || lev1(qt, t.slice(0, qt.length)))) best = 1;
    }
    return best;
  }
  function scoreAll(q) {
    var idx = window.CF_IDX || [];
    if (!q || !window.CFSearchKey) return [];
    var k = window.CFSearchKey.toKey(q);
    var kf = k.full, kc = k.cho;
    if (!kf && !kc) return [];
    var qt = qTokens(q), res = [];
    for (var i = 0; i < idx.length; i++) {
      var it = idx[i], old = false, s = 0;
      var keys = it.keys || [];
      for (var a = 0; a < keys.length; a++) { if (keys[a].indexOf(kf) >= 0) { old = true; break; } }
      if (!old && kc && kc.length >= 2) {
        var cho = it.cho || [];
        for (var b = 0; b < cho.length; b++) { if (cho[b].indexOf(kc) >= 0) { old = true; break; } }
      }
      var tokHit = qt.length > 0;
      for (var c = 0; c < qt.length && tokHit; c++) { var ts = tokScore(qt[c], it.tok || []); if (!ts) tokHit = false; else s += ts; }
      if (!tokHit) s = 0;
      if (!old && !tokHit) continue;
      res.push({ it: it, s: s + (old ? 5 : 0) + (it.pop || 0) });
    }
    res.sort(function (x, y) { return y.s - x.s; });
    return res;
  }
  // CF_IDX 매칭: 토큰 매칭 ∪ (keys 부분일치 OR 초성 2+ 부분일치). 점수 내림차순 상위 N.
  function match(q, limit) {
    return scoreAll(q).slice(0, limit || 8).map(function (r) { return r.it; });
  }
  // 목록 필터용: 매칭된 id 집합 (search.html run에서 사용)
  function matchIds(q) {
    return match(q, 9999).map(function (it) { return it.id; });
  }
  // 매칭 0건일 때 '혹시 이 호텔인가요?' — 자모 바이그램 Dice 유사도 ≥0.45, 최대 3
  function bigrams(s) { var o = {}, n = 0; for (var i = 0; i < s.length - 1; i++) { var g = s.substr(i, 2); o[g] = (o[g] || 0) + 1; n++; } return { g: o, n: n }; }
  function dice(a, b) {
    if (!a.n || !b.n) return 0;
    var inter = 0; for (var g in a.g) if (b.g[g]) inter += Math.min(a.g[g], b.g[g]);
    return 2 * inter / (a.n + b.n);
  }
  function suggest(q, limit) {
    if (!q || !window.CFSearchKey) return [];
    prep();
    var qt = qTokens(q).join('');
    var bq = bigrams(qt || K(q)), out = [];
    (window.CF_IDX || []).forEach(function (it) {
      var best = 0;
      (it.keys || []).forEach(function (key) {
        var d = dice(bq, bigrams(key));
        if (d > best) best = d;
      });
      var tj = (it.tok || []).filter(function (t) { return !STOP[t]; }).join('');
      var d2 = dice(bq, bigrams(tj)); if (d2 > best) best = d2;
      if (best >= 0.45) out.push({ it: it, s: best });
    });
    out.sort(function (x, y) { return y.s - x.s || (y.it.pop || 0) - (x.it.pop || 0); });
    return out.slice(0, limit || 3).map(function (r) { return r.it; });
  }
  // 콘솔 자가검증 (FEEDBACK-2610 §15-6): window.CFAutocomplete.selfTest()
  function selfTest() {
    var cases = [
      ['톈진오리엔탈호텔', /오리엔탈 익스프레스.*텐진/],
      ['하카타 도미인', /도미 ?인/],
      ['니시테츠그랜드', /니시테츠 그랜드/],
      ['솔라리아', /솔라리아/],
      ['ㄷㅁㅇ', /도미 ?인/],
      ['Hyatt', /하얏트/]
    ];
    var ok = true;
    cases.forEach(function (c) {
      var top = match(c[0], 1)[0], pass = !!(top && c[1].test(top.t));
      if (!pass) ok = false;
      // eslint-disable-next-line no-console
      console.log((pass ? '[OK]  ' : '[FAIL]') + ' ' + c[0] + ' → ' + (top ? top.t : '(없음)'));
    });
    var keyOk = window.CFSearchKey && window.CFSearchKey.selfTest ? window.CFSearchKey.selfTest() : true;
    // eslint-disable-next-line no-console
    console.log(ok && keyOk ? 'search-ac selfTest: ALL PASS' : 'search-ac selfTest: FAILED');
    return ok && keyOk;
  }

  // 미매칭 → 분석 요청 (Supabase analysis_requests · anon INSERT RLS — engage.js 피드백과 동일 패턴). 검색 결과 없음 화면의 '분석 요청하기'도 이 함수
  function requestAnalysis(q) {
    if (window.CF_SB && window.CF_SB.url && window.CF_SB.key) {
      fetch(window.CF_SB.url + '/rest/v1/analysis_requests', {
        method: 'POST',
        headers: { 'apikey': window.CF_SB.key, 'Authorization': 'Bearer ' + window.CF_SB.key,
          'Content-Type': 'application/json', 'Prefer': 'return=minimal' },
        body: JSON.stringify({ hotel_name: q, source: 'search_miss' })
      }).catch(function () {});
      toast('요청했어요. 분석되면 사이트에 올라와요');
      return;
    }
    toast('분석 요청은 준비 중이에요');
  }

  /* ── 구글맵 링크 → 우리 호텔 (2026-10-10, 홈·검색 공용) ──
     읽는 순서: ① 장소 ID(ChIJ…) ② 링크 속 장소 좌표 !3d·!4d (80m 이내) ③ 장소 이름(/place/이름, ?q=이름 — 이름 검색 엔진으로)
     ④ 지도 화면 중심 @좌표는 40m 이내일 때만 — 화면 중심은 장소와 수백 m 어긋나 밀집지역에서 옆 호텔을 고르던 문제.
     휴대폰 공유 짧은 링크(maps.app.goo.gl)·cid 링크에는 장소 정보가 없어 읽을 수 없음 → kind:'short' */
  function isMapsUrl(v) {
    return /^https?:\/\//i.test(v) || /maps\.app\.goo\.gl|goo\.gl\/maps|google\.[a-z.]+\/maps|maps\.google\./i.test(v);
  }
  function distM(la1, lo1, la2, lo2) {
    var dy = (la1 - la2) * 111000, dx = (lo1 - lo2) * 111000 * Math.cos(la1 * Math.PI / 180);
    return Math.sqrt(dx * dx + dy * dy);
  }
  function nearest(la, lo, maxM) {
    var best = null, bd = 1e12;
    (window.HOTELS || []).forEach(function (h) {
      if (h.lat == null || h.lng == null) return;
      var d = distM(la, lo, +h.lat, +h.lng);
      if (d < bd) { bd = d; best = h; }
    });
    return best && bd <= maxM ? best : null;
  }
  function byId(id) {
    var H = window.HOTELS || [];
    for (var i = 0; i < H.length; i++) if (H[i].id === id) return { id: H[i].id, t: H[i].name };
    return null;
  }
  function resolveUrl(v) {
    var s = String(v || '').trim(), m, h;
    if (/maps\.app\.goo\.gl|goo\.gl\/maps|[?&]cid=\d/i.test(s)) return { kind: 'short' };
    if ((m = s.match(/(ChIJ[A-Za-z0-9_-]{10,})/)) && (h = byId(m[1]))) return { hit: h };
    if ((m = s.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/)) && (h = nearest(+m[1], +m[2], 80))) return { hit: { id: h.id, t: h.name } };
    var name = null;
    if ((m = s.match(/\/place\/([^\/@?#]+)/))) name = m[1];
    else if ((m = s.match(/[?&](?:q|query)=([^&#]+)/)) && !/^-?\d+\.\d+,-?\d+\.\d+$/.test(decodeURIComponent(m[1]))) name = m[1];
    if (name) {
      try { name = decodeURIComponent(name.replace(/\+/g, ' ')); } catch (e) { name = name.replace(/\+/g, ' '); }
      var top = match(name, 1)[0];
      if (top) return { hit: { id: top.id, t: top.t } };
    }
    if ((m = s.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/)) && (h = nearest(+m[1], +m[2], 40))) return { hit: { id: h.id, t: h.name } };
    return { kind: 'none' };
  }

  function attach(input, opts) {
    opts = opts || {};
    var $input = $(input);
    var hrefPrefix = opts.hrefPrefix || './hotels/';   // 상세 링크 접두사
    var areaHref = opts.areaHref || './search?area=';
    var $box = $input.closest('form, .search, .input').find('.ac-box').first();
    if (!$box.length) return null;

    var sel = -1;    // 키보드 선택 인덱스
    var lastList = [];

    function hide() { $box.prop('hidden', true).empty(); sel = -1; }

    // 컴팩트 행(v3 §6-4): 이름 16/600(일치 글자 700) + 메타 14 '나카스 · ● 실망 확률 4%'. 오른쪽 열 없음 → 이름 폭을 넓게
    function hl(name, q) {
      var i = q ? name.toLowerCase().indexOf(q.toLowerCase()) : -1;
      return i < 0 ? esc(name) : esc(name.slice(0, i)) + '<b>' + esc(name.slice(i, i + q.length)) + '</b>' + esc(name.slice(i + q.length));
    }
    function hotelRow(h, i, q) {
      var meta = [];
      if (h.ar) meta.push(esc(h.ar));
      meta.push(h.p != null ? '<i class="sdot' + (h.band ? ' is-' + h.band : '') + '"></i>실망 확률 ' + h.p + '%' : '분석 준비 중');   // 글자는 잉크, 의미는 점이(§3-3)
      return '<a class="ac-item" role="option" data-i="' + i + '" href="' + hrefPrefix + h.id + '">'
        + '<span class="ac-main"><span class="ac-name">' + hl(h.t, q) + '</span><span class="ac-meta">' + meta.join(' · ') + '</span></span></a>';
    }

    function missRow(q) {
      return '<div class="ac-miss" data-q="' + esc(q) + '">'
        + '<span class="ac-miss-q">&lsquo;' + esc(q) + '&rsquo;</span> 호텔이 없어요 · <b>분석 요청하기</b></div>';
    }

    function areaBlock() {
      var areas = window.CF_AREAS || [];
      if (!areas.length) return '';
      return '<div class="ac-section">인기 지역</div>' + areas.map(function (a) {
        return '<a class="ac-area" href="' + areaHref + a.code + '"><span>' + esc(a.ko) + '</span></a>';
      }).join('');
    }

    function showAreas() {
      var html = areaBlock();
      if (!html) { hide(); return; }
      lastList = [];
      $box.prop('hidden', false).html(html);
      sel = -1;
    }

    function render(q) {
      var list = match(q, 8);
      lastList = list;
      var html = '';
      if (list.length) {
        html = list.map(function (h, i) { return hotelRow(h, i, q); }).join('');
      } else {
        var sug = suggest(q, 3);   // 폴백: 비슷한 이름 제안 → 그래도 없으면 분석 요청 행
        html = (sug.length ? '<div class="ac-section">혹시 이 호텔인가요?</div>' + sug.map(function (h, i) { return hotelRow(h, i, ''); }).join('') : '') + missRow(q);
      }
      $box.prop('hidden', false).html(html);
      sel = -1;
    }

    function highlight() {
      var $items = $box.find('.ac-item');
      $items.removeClass('is-sel');
      if (sel >= 0 && sel < $items.length) {
        $items.eq(sel).addClass('is-sel');
        var el = $items.get(sel);
        if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
      }
    }

    $input.on('focus', function () { if (!$input.val().trim()) showAreas(); });
    // 링크 입력: 해석 결과 1행(호텔) 또는 안내 — 링크를 호텔 이름으로 오해해 '분석 요청'을 띄우지 않는다
    function renderUrl(v) {
      var r = resolveUrl(v);
      lastList = [];
      if (r.hit) {
        $box.prop('hidden', false).html('<div class="ac-section">링크의 호텔</div>' + hotelRow({ id: r.hit.id, t: r.hit.t, p: null, band: null }, 0).replace('<span class="ac-p dim">분석 준비 중</span>', ''));
        sel = 0; highlight();
      } else {
        $box.prop('hidden', false).html('<div class="ac-none">' + (r.kind === 'short'
          ? '공유 링크는 아직 읽지 못해요. 호텔 이름으로 검색해 주세요'
          : '링크에서 호텔을 찾지 못했어요. 호텔 이름으로 검색해 주세요') + '</div>');
        sel = -1;
      }
    }

    $input.on('input', function () {
      var v = $input.val().trim();
      if (!v) { showAreas(); return; }
      if (isMapsUrl(v)) { renderUrl(v); return; }
      render(v);
    });

    $box.on('click', '.ac-miss', function () {
      requestAnalysis($(this).data('q'));
    });

    $input.on('keydown', function (e) {
      if ($box.prop('hidden')) return;
      var $items = $box.find('.ac-item');
      if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(sel + 1, $items.length - 1); highlight(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(sel - 1, 0); highlight(); }
      else if (e.key === 'Enter') {
        if (sel >= 0 && sel < $items.length) { e.preventDefault(); location.href = $items.eq(sel).attr('href'); }
      } else if (e.key === 'Escape') { hide(); }
    });

    // 바깥 클릭 시 닫기
    $(document).on('click', function (e) {
      if (!$(e.target).closest($input.closest('form, .search, .input')).length) hide();
    });

    return { render: render, showAreas: showAreas, hide: hide, matchIds: matchIds };
  }

  window.CFAutocomplete = { attach: attach, match: match, matchIds: matchIds, suggest: suggest, selfTest: selfTest, requestAnalysis: requestAnalysis,
                            isMapsUrl: isMapsUrl, resolveUrl: resolveUrl };
})();

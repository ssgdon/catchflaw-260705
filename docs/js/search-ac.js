/* 캐치플로 검색 자동완성 (홈 #hero-q + search.html #q 공용) — §7-c
   의존: jQuery, js/search-key.js(CFSearchKey), data/search_index.js(window.CF_IDX)
   window.CF_AREAS(인기 지역), window.CF_SB(Supabase INSERT)
   각 검색창은 data-ac-href 로 상세 링크 접두사(홈="./hotels/", search="./hotels/") 지정. */
(function () {
  'use strict';

  var BAND_COLOR = { safe: '#5EA5E7', warning: '#F0A028', danger: '#FA5252' };

  function toast(msg) {
    var el = document.createElement('div');
    el.className = 'cf-toast'; el.innerHTML = msg;
    document.body.appendChild(el);
    requestAnimationFrame(function () { el.classList.add('show'); });
    setTimeout(function () { el.classList.remove('show'); setTimeout(function () { el.remove(); }, 300); }, 2000);
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // CF_IDX 매칭: keys 부분일치 OR (초성 2+ && cho 부분일치). pop 내림차순 상위 N.
  function match(q, limit) {
    var idx = window.CF_IDX || [];
    if (!q || !window.CFSearchKey) return [];
    var k = window.CFSearchKey.toKey(q);
    var kf = k.full, kc = k.cho;
    if (!kf && !kc) return [];
    var res = [];
    for (var i = 0; i < idx.length; i++) {
      var it = idx[i], hit = false;
      var keys = it.keys || [];
      for (var a = 0; a < keys.length; a++) { if (keys[a].indexOf(kf) >= 0) { hit = true; break; } }
      if (!hit && kc && kc.length >= 2) {
        var cho = it.cho || [];
        for (var b = 0; b < cho.length; b++) { if (cho[b].indexOf(kc) >= 0) { hit = true; break; } }
      }
      if (hit) res.push(it);
    }
    res.sort(function (x, y) { return (y.pop || 0) - (x.pop || 0); });
    return res.slice(0, limit || 8);
  }
  // 목록 필터용: 매칭된 id 집합 (search.html run에서 사용)
  function matchIds(q) {
    return match(q, 9999).map(function (it) { return it.id; });
  }

  function attach(input, opts) {
    opts = opts || {};
    var $input = $(input);
    var hrefPrefix = opts.hrefPrefix || './hotels/';   // 상세 링크 접두사
    var areaHref = opts.areaHref || './search.html?area=';
    var $box = $input.closest('form, .search, .input').find('.ac-box').first();
    if (!$box.length) return null;

    var sel = -1;    // 키보드 선택 인덱스
    var lastList = [];

    function hide() { $box.prop('hidden', true).empty(); sel = -1; }

    function hotelRow(h, i) {
      var band = h.band || null;
      var chip = h.p != null
        ? '<span class="ac-p" style="color:' + (BAND_COLOR[band] || '#8B9097') + '">실망 ' + h.p + '%</span>'
        : '<span class="ac-p dim">수집중</span>';
      var krn = (h.krn > 0) ? '<span class="ac-krn">한국인 리뷰 ' + h.krn.toLocaleString() + '건</span>' : '';
      return '<a class="ac-item" role="option" data-i="' + i + '" href="' + hrefPrefix + h.id + '.html">'
        + '<span class="ac-main"><span class="ac-name">' + esc(h.t) + '</span>' + krn + '</span>'
        + chip + '</a>';
    }

    function missRow(q) {
      return '<div class="ac-miss" data-q="' + esc(q) + '">'
        + '<span class="ac-miss-q">&lsquo;' + esc(q) + '&rsquo;</span> 분석된 호텔이 없어요 — <b>분석 요청하기</b></div>';
    }

    function areaBlock() {
      var areas = window.CF_AREAS || [];
      if (!areas.length) return '';
      return '<div class="ac-section">후쿠오카 인기 지역</div>' + areas.map(function (a) {
        return '<a class="ac-area" href="' + areaHref + a.code + '"><span>' + esc(a.ko) + '</span>'
          + '<span class="ac-sub">이 지역 호텔 보기</span></a>';
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
        html = '<div class="ac-section">호텔</div>' + list.map(hotelRow).join('');
      } else {
        html = missRow(q);
      }
      $box.prop('hidden', false).html(html);
      sel = -1;
    }

    // 미매칭 → 분석 요청 (§7-c: Supabase analysis_requests 테이블 준비 전이므로 폴백 토스트)
    function requestAnalysis(q) {
      // TODO(SETUP-STATUS): Supabase에 analysis_requests 테이블 + anon INSERT RLS 생성 후 아래 주석 해제.
      // if (window.CF_SB) {
      //   fetch(window.CF_SB.url + '/rest/v1/analysis_requests', {
      //     method: 'POST',
      //     headers: { 'apikey': window.CF_SB.key, 'Authorization': 'Bearer ' + window.CF_SB.key,
      //       'Content-Type': 'application/json', 'Prefer': 'return=minimal' },
      //     body: JSON.stringify({ hotel_name: q, source: 'search_miss' })
      //   }).catch(function () {});
      //   toast('요청했어요! 분석되면 사이트에 올라와요');
      //   return;
      // }
      toast('분석 요청 기능은 준비 중이에요 · 곧 열릴게요');
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
    $input.on('input', function () {
      var v = $input.val().trim();
      // 구글맵 링크/URL은 각 페이지의 기존 핸들러에 위임 (여기선 무시)
      if (opts.isUrl && opts.isUrl(v)) return;
      if (!v) { showAreas(); return; }
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

  window.CFAutocomplete = { attach: attach, match: match, matchIds: matchIds };
})();

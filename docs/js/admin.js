/* 관리자 페이지 /admin/ (ADMIN-DESIGN §1, 2026-11-05 · 같은 날 카드형·인사이트 우선으로 개편) — 순수 JS(jQuery 없음), chart.js 4.4.1(상세와 같은 CDN) 선 그래프 1종.
   데이터 2개:
     /admin/site.json  — 빌드 시점 사실(generate.admin_site_json): 호텔 표(pid → [이름, 슬러그, 제휴, 점수 노출, 상태])·상세 수·제휴 링크 수·
                         asof·빌드 시각·커밋·최근 커밋 5건·changes.json 사본(changes·pending)
     /admin/api/data   — VM 집계(pipeline/admin_export.py → R2 → functions/admin/api/data.js). 없으면(503) site.json만으로 일부를 그린다.
                         로컬 프리뷰(localhost)는 /admin/sample.json(scripts/check_admin.py가 만든 실제 값, 커밋 안 함)으로 대신한다.
   화면 원칙: 표보다 결론 먼저 — ① 인사이트 카드(판정 + 결론 한 줄 + 근거 + 할 일) ② 핵심 지표 카드(숫자 + 앞 기간 대비 ▲▼ + 스파크라인)
     ③ 그림(여정 막대·채널 쌓은 막대·막대 목록) ④ 원본 표는 '표로 보기'로 접는다. 인사이트·개선 후보 규칙은 두 데이터를 다 봐야 해서 여기서 계산한다.
   색은 토큰만(tok) — hex 금지(R-jshex). 보라는 '이번 기간' 데이터 강조(.ad-*-chart)만. 글자·간격은 css/ds.css §v3 끝 .ad-* 부품. */
(function () {
  'use strict';
  var S = null, A = null, A_ERR = '', WIN = '28';
  var drawn = {};
  var LOCAL = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
  var GH = 'https://github.com/ssgdon/catchflaw-260705/commit/';

  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function num(x) { return x == null || isNaN(x) ? '—' : Number(x).toLocaleString('ko-KR'); }
  function pct(x, d) { return x == null || isNaN(x) ? '—' : (x * 100).toFixed(d == null ? 0 : d) + '%'; }
  function ratio(a, b) { return b ? a / b : null; }
  function tok(name) { try { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); } catch (e) { return ''; } }
  function kst(iso) { var d = new Date(iso); return isNaN(d) ? null : new Date(d.getTime() + 9 * 3600e3); }   // getUTC*로 읽는 KST 시각
  function p2(n) { return (n < 10 ? '0' : '') + n; }
  function md(iso, time) {
    var k = iso && kst(iso); if (!k) return '—';
    return p2(k.getUTCMonth() + 1) + '-' + p2(k.getUTCDate()) + (time === false ? '' : ' ' + p2(k.getUTCHours()) + ':' + p2(k.getUTCMinutes()));
  }
  function hoursAgo(iso) { var d = new Date(iso); return isNaN(d) ? Infinity : (Date.now() - d.getTime()) / 3600e3; }
  function addDays(ymd, n) { var d = new Date(ymd + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
  function dot(tone) { return '<span class="sdot' + (tone ? ' is-' + tone : '') + '" aria-hidden="true"></span>'; }
  function tag(tone, text) { return '<span class="tag">' + dot(tone) + esc(text) + '</span>'; }
  function clamp01(x) { return Math.max(0, Math.min(1, x || 0)); }
  function w100(x) { return (clamp01(x) * 100).toFixed(1) + '%'; }

  // ───────────── 틀: 섹션(제목은 카드 밖) · 카드 · 표 ─────────────
  function card(inner, cls) { return '<div class="ad-card' + (cls ? ' ' + cls : '') + '">' + inner + '</div>'; }
  function sec(title, body, desc, opt) {   // opt.raw = body가 이미 카드(격자)라 카드로 감싸지 않음
    opt = opt || {};
    return '<div class="ad-sec"' + (opt.id ? ' id="' + opt.id + '"' : '') + '><h2 class="ad-h2">' + esc(title) + '</h2>' +
      (desc ? '<p class="ad-desc">' + desc + '</p>' : '') + (opt.raw ? body : card(body)) + '</div>';
  }
  function table(head, rows, cls) {
    return '<div class="ad-tw"><table class="ad-table' + (cls ? ' ' + cls : '') + '"><thead><tr>' + head.map(function (h) {
      return '<th scope="col"' + (h.num ? ' class="num"' : '') + '>' + (h.sort ? '<button type="button" class="ad-sort" data-sort="' + h.sort + '">' + esc(h.t) + '</button>' : esc(h.t)) + '</th>';
    }).join('') + '</tr></thead><tbody>' + (rows.join('') || '<tr><td colspan="' + head.length + '" class="ad-empty">아직 기록이 없어요</td></tr>') + '</tbody></table></div>';
  }
  function td(v, isNum, extra) { return '<td' + (isNum ? ' class="num"' : '') + (extra || '') + '>' + v + '</td>'; }
  function moreBtn(key, label, open) {
    return '<button type="button" class="btn-text btn-text--sm ad-more" data-more="' + key + '" aria-expanded="' + !!open + '">' + esc(open ? '표 접기' : label) + '</button>';
  }
  function hotelOf(pid) { return (S && S.hotels && S.hotels[pid]) || null; }
  function slugMap() {
    if (slugMap.m) return slugMap.m;
    var m = {}; Object.keys((S && S.hotels) || {}).forEach(function (p) { m[S.hotels[p][1]] = p; });
    return (slugMap.m = m);
  }
  function urlLabel(u) {
    var mm = /^\/hotels\/([^/?#]+)/.exec(u || '');
    if (mm) { var p = slugMap()[mm[1]] || (mm[1].indexOf('ChIJ') === 0 ? mm[1] : null), h = p && hotelOf(p); if (h) return h[0]; }
    return { '/': '홈', '/search': '검색', '/compare': '비교', '/recommend': '맞춤 추천', '/recent': '최근 본 호텔', '/hotels': '전체 호텔 목록' }[u] || u;
  }
  function gaWin(w) { return (A && A.ga && A.ga.days && A.ga.days[w]) || null; }
  function ev(g, name) { var r = null; (g.events || []).forEach(function (e) { if (e.name === name) r = e; }); return r; }

  // ───────────── 그림 부품: 변화 태그 · 스파크라인 · 막대 ─────────────
  // kind 'rel' = 배수·% 변화, 'pp' = %p 변화. 표본이 작거나 변화가 작으면 점 없이(판정하지 않음).
  function delta(cur, prev, kind, goodUp, n) {
    if (cur == null || prev == null) return '';
    var arrow, txt, big;
    if (kind === 'rel') {
      if (!prev) return '<span class="tag">앞 기간 0</span>';
      var r = cur / prev;
      arrow = Math.abs(r - 1) < 0.05 ? '–' : r > 1 ? '▲' : '▼';
      txt = r >= 2 ? r.toFixed(1) + '배' : Math.round(Math.abs(r - 1) * 100) + '%';
      big = Math.abs(r - 1) >= 0.1 && prev >= 20;
    } else {
      var d = (cur - prev) * 100;
      arrow = Math.abs(d) < 0.05 ? '–' : d > 0 ? '▲' : '▼';
      txt = Math.abs(d).toFixed(1) + '%p';
      big = Math.abs(d) >= 1 && (n == null || n >= 100);
    }
    var tone = big && arrow !== '–' ? ((arrow === '▲') === goodUp ? 'safe' : 'danger') : '';
    return '<span class="tag">' + (tone ? dot(tone) : '') + arrow + ' ' + txt + '</span>';
  }
  function spark(vals, label) {
    var v = vals.filter(function (x) { return x != null; });
    if (v.length < 2) return '';
    var max = Math.max.apply(null, v) || 1, n = vals.length, pts = [];
    vals.forEach(function (x, i) { if (x != null) pts.push((i / (n - 1) * 100).toFixed(2) + ',' + (28 - x / max * 24).toFixed(2)); });
    var first = pts[0].split(',')[0], last = pts[pts.length - 1].split(',')[0];
    return '<svg class="ad-spark-chart" viewBox="0 0 100 30" preserveAspectRatio="none" role="img" aria-label="' + esc(label) + '">' +
      '<polygon class="ad-spark-a" points="' + first + ',30 ' + pts.join(' ') + ' ' + last + ',30"/>' +
      '<polyline points="' + pts.join(' ') + '" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>';
  }
  function series(key, w) { return ((A && A.ga && A.ga.daily) || []).slice(-Number(w || WIN)).map(function (d) { return d[key]; }); }
  function rollRate(numK, denK, w, span) {   // 7일 이동 비율 — 하루 단위 비율은 표본이 작아 출렁인다
    var d = (A && A.ga && A.ga.daily) || [], out = [];
    for (var i = 0; i < d.length; i++) {
      var a = 0, b = 0;
      for (var j = Math.max(0, i - (span || 7) + 1); j <= i; j++) { a += (d[j].m || {})[numK] || 0; b += (d[j].m || {})[denK] || 0; }
      out.push(b >= 5 ? a / b : null);
    }
    return out.slice(-Number(w || WIN));
  }
  function bar(x, cls, prev) {
    return '<div class="ad-bar"><i class="' + (cls || 'ad-fill-chart') + '" style="width:' + w100(x) + '"></i>' +
      (prev != null ? '<b class="ad-prev" style="left:' + w100(prev) + '" aria-hidden="true"></b>' : '') + '</div>';
  }
  function hrow(label, val, x, sub, cls, prev) {
    return '<li><div class="ad-hb-r"><span class="ad-hb-l">' + label + '</span><span class="ad-hb-v">' + val + '</span></div>' +
      bar(x, cls, prev) + (sub ? '<div class="ad-hb-s">' + sub + '</div>' : '') + '</li>';
  }
  function kpi(o) {
    return '<div class="ad-card ad-kpi"><span class="ad-kpi-l">' + esc(o.label) + '</span><b class="ad-kpi-v">' + o.value + '</b>' +
      (o.delta || o.prev ? '<span class="ad-kpi-d">' + (o.delta || '') + (o.prev ? '<span class="ad-kpi-p">' + o.prev + '</span>' : '') + '</span>' : '') +
      (o.sub ? '<span class="ad-kpi-p">' + o.sub + '</span>' : '') + (o.spark || '') + '</div>';
  }

  // ───────────── 판정 기준 (§4-1 상태색) ─────────────
  function lastWeekly() {
    var jobs = (A && A.ops && A.ops.sync_jobs) || [];
    for (var i = 0; i < jobs.length; i++) if (/^(ok|partial)$/.test(jobs[i].status || '')) return jobs[i];
    return null;
  }
  function batchState() {
    if (!A || !A.ops) return { tone: '', v: 'VM 집계 없음', s: '' };
    var jobs = A.ops.sync_jobs || [], run = jobs[0] && jobs[0].status === 'running' ? jobs[0] : null, ok = lastWeekly();
    var at = ok ? (ok.completed_at || ok.started_at) : A.ops.last_sync_ok;
    if (run && hoursAgo(run.started_at) > 12) return { tone: 'danger', v: '12시간 넘게 진행 중', s: '시작 ' + md(run.started_at) };
    if (!at) return { tone: 'danger', v: '성공 기록 없음', s: '' };
    var late = hoursAgo(at) > 8 * 24;
    return { tone: late ? 'danger' : run ? 'warning' : 'safe', v: late ? '8일 넘게 멈춤' : run ? '진행 중' : ok && ok.status === 'partial' ? '일부 실패' : '정상', s: '마지막 성공 ' + md(at) };
  }
  function backupState() {
    var b = A && A.ops && A.ops.backup;
    if (!b) return { tone: '', v: 'VM 집계 없음', s: '' };
    if (!b.at) return { tone: 'danger', v: '백업 없음', s: '' };
    var late = hoursAgo(b.at) > 36;
    return { tone: late ? 'danger' : 'safe', v: late ? '36시간 넘게 밀림' : '정상', s: md(b.at) + (b.size_mb != null ? ' · ' + b.size_mb + 'MB' : '') + ' · R2 ' + num(b.count) + '개' };
  }
  function healthState() {
    var h = A && A.ops && A.ops.health;
    if (!h) return { tone: '', v: 'VM 집계 없음', s: '' };
    var n = (h.issues || []).length;
    return { tone: n ? 'danger' : 'safe', v: n ? '이상 ' + n + '건' : '이상 없음', s: '점검 ' + md(h.checked_at) };
  }
  function buildState() {
    if (!S) return { tone: 'danger', v: 'site.json 없음', s: '' };
    var old = hoursAgo(S.built_at) > 8 * 24;
    return { tone: old ? 'warning' : 'safe', v: old ? '8일 넘은 빌드' : '정상', s: '데이터 기준 ' + esc(S.asof || '—') + ' · 빌드 ' + md(S.built_at) };
  }
  function clarityLate() {
    var c = A && A.clarity; if (!c || !c.last_day) return !!A;
    return (Date.now() - new Date(c.last_day + 'T09:00:00+09:00').getTime()) / 864e5 >= 2;
  }

  // ───────────── 인사이트 (UX 전문가가 먼저 보는 질문 순) ─────────────
  // 1 사람이 늘었나 2 어디서 오나(쏠림) 3 상세에서 결정까지 가나 4 돈이 되는 클릭인가 5 어느 입구가 새나 6 찾다 실패하나 7 많이 보는데 링크가 없나 8 무엇을 쓰나
  var CH_NAME = { naver: '네이버', direct: '직접(북마크·앱)', organic: '검색(구글 등)', social: '소셜(유튜브 등)', other: '기타 링크' };
  var CH_CLS = { naver: 'ad-s1-chart', direct: 'ad-s2-chart', organic: 'ad-s3-chart', social: 'ad-s4-chart', other: 'ad-s5-chart' };
  var TONE_TXT = { danger: '문제', warning: '살펴보기', safe: '좋아요', '': '참고' };
  var TONE_ORD = { danger: 0, warning: 1, safe: 2, '': 3 };
  var FEATS = [['비교', ['compare_view', 'compare_add', 'compare_open']], ['블로그 후기 열기', ['blog_open']], ['누구와 가세요', ['who_select']],
    ['상세 탭 이동', ['detail_tab']], ['가격 버튼', ['check_price_click']], ['검색', ['search']], ['사진 갤러리', ['gallery_open']],
    ['지도 보기', ['map_toggle']], ['맞춤 추천 완료', ['rec_submit']], ['가격 탭', ['price_tab']], ['영상 재생', ['video_play']],
    ['의견·신고', ['report_open', 'report_submit']], ['공유', ['share']]];
  function features(g) {
    return FEATS.map(function (f) {
      var s = 0, many = 0;
      f[1].forEach(function (n) { var e = ev(g, n); if (e && e.sessions) { s = Math.max(s, e.sessions); many++; } });
      return { name: f[0], s: s, approx: many > 1 };
    }).filter(function (x) { return x.s > 0; }).sort(function (a, b) { return b.s - a.s; });
  }
  function engaged(g) {
    var a = 0, b = 0; (g.landing || []).forEach(function (l) { a += (l.engaged_rate || 0) * l.sessions; b += l.sessions; });
    return ratio(a, b);
  }
  function insights(g, w) {
    var out = [], f = g.funnel || {}, pv = f.prev || {}, tot = g.sessions || 0, wl = '앞 ' + w + '일';
    function add(tone, area, title, why, todo, meter) { out.push({ tone: tone, area: area, title: title, why: why, todo: todo, meter: meter }); }
    if (g.prev_sessions >= 20) {
      var r = g.sessions / g.prev_sessions;
      if (r >= 1.1) add('safe', '유입', '방문이 ' + wl + '보다 ' + (r >= 2 ? r.toFixed(1) + '배로' : Math.round((r - 1) * 100) + '%') + ' 늘었어요',
        '세션 ' + num(g.prev_sessions) + ' → ' + num(g.sessions) + ' · 사용자 ' + num(g.users), '');
      else if (r <= 0.9) add('danger', '유입', '방문이 ' + wl + '보다 ' + Math.round((1 - r) * 100) + '% 줄었어요',
        '세션 ' + num(g.prev_sessions) + ' → ' + num(g.sessions), '아래 유입 채널에서 어느 쪽이 줄었는지 확인');
    }
    var ch = (g.channel || []).slice().sort(function (a, b) { return b.sessions - a.sessions; });
    if (ch.length && tot) {
      var share = ch[0].sessions / tot, by = {};
      ch.forEach(function (c) { by[c.name] = c.sessions; });
      if (share >= 0.6) add('warning', '유입', '유입의 ' + pct(share) + '가 ' + (CH_NAME[ch[0].name] || ch[0].name) + ' 한 곳이에요',
        '검색(구글 등) ' + pct(ratio(by.organic || 0, tot)) + ' · 직접 ' + pct(ratio(by.direct || 0, tot)) + ' · 소셜 ' + pct(ratio(by.social || 0, tot)),
        ch[0].name === 'naver' ? '네이버 노출이 줄면 방문도 같이 줄어요 — 구글 색인·외부 링크 진행 확인' : '', share);
    }
    if (f.detail_sessions >= 30) {
      var cr = ratio(f.cta_click, f.detail_sessions), sr = ratio(f.scroll90, f.detail_sessions), pcr = ratio(pv.cta_click, pv.detail_sessions);
      var dd = pcr == null ? null : (cr - pcr) * 100, tone = dd == null || pv.detail_sessions < 100 ? '' : dd >= 1 ? 'safe' : dd <= -1 ? 'danger' : '';
      add(tone, '상세 페이지', '상세를 본 100명 중 ' + Math.round(cr * 100) + '명이 가격 버튼을 눌러요',
        '끝까지 읽음 ' + pct(sr) + ' · 탭 이동 ' + pct(ratio(f.tab_click, f.detail_sessions)) + (pcr != null ? ' · ' + wl + ' 가격 버튼 ' + pct(pcr, 1) : ''),
        sr < 0.4 ? '60% 넘게 끝까지 안 읽고 떠나요 — 결정에 필요한 정보(실망 확률·가격)가 첫 화면 가까이 있는지 확인' : '', cr);
    }
    var aff = S && S.counts && S.counts.affiliate_detail;
    if (f.cta_click > 0 && f.cta_agoda > 0) add('safe', '수익', '가격 버튼 클릭의 ' + pct(ratio(f.cta_agoda, f.cta_click)) + '가 아고다로 갔어요',
      '아고다 ' + num(f.cta_agoda) + ' · 구글 ' + num(f.cta_google), '', ratio(f.cta_agoda, f.cta_click));
    else if (f.cta_click > 0 && aff) add('warning', '수익', '가격 버튼 클릭 ' + num(f.cta_click) + '건이 모두 구글로 갔어요',
      '제휴 링크가 있는 상세 ' + num(aff) + '곳은 11-05에 연결 — 그 전 클릭은 전부 구글행이에요', '11-06 이후 집계에서 아고다 비중이 오르는지 확인');
    var minS = w === '7' ? 10 : 20, det = null, weak = null;
    (g.landing || []).forEach(function (l) {
      if (l.group === '상세') det = l;
      if (l.sessions >= minS && (!weak || l.engaged_rate < weak.engaged_rate)) weak = l;
    });
    if (weak && weak.engaged_rate < 0.4) add('danger', '첫 페이지', "'" + weak.group + "'로 들어온 " + num(weak.sessions) + '세션은 ' + pct(weak.engaged_rate) + '만 머물러요',
      '평균 ' + num(weak.avg_sec) + '초' + (det && det !== weak ? ' · 상세로 들어오면 ' + pct(det.engaged_rate) + ' 머묾' : ''),
      weak.group === '기타' ? "'기타' = 비교·추천·최근 본·소개·404 — 불편 신호(Clarity)에서 어느 페이지인지 확인" : '', weak.engaged_rate);
    var se = ev(g, 'search'), nr = ev(g, 'search_no_result');
    if (se && nr && nr.sessions >= 3) {
      var rr = clamp01(ratio(nr.sessions, se.sessions)), links = (g.search_noresult || []).filter(function (t) { return /^https?:/.test(t.term); }).length;
      add(rr >= 0.3 ? 'danger' : 'warning', '검색', '검색한 세션의 ' + pct(rr) + '가 결과 없음을 봤어요',
        '검색 ' + num(se.sessions) + '세션 중 ' + num(nr.sessions) + '세션' + (links ? ' · 구글 지도 링크를 붙여넣은 경우 ' + links + '건' : ''),
        links ? '지도 링크에서 호텔을 찾아 주고, 아래 검색어 중 있는 호텔은 token_dict 별칭에 추가' : '아래 검색어 중 있는 호텔은 token_dict 별칭에 추가', rr);
    }
    if (S) {
      var top = (g.hotels || []).filter(function (h) { return hotelOf(h.pid) && h.views > 0; }).sort(function (a, b) { return b.views - a.views; }).slice(0, 10);
      var miss = top.filter(function (h) { return !hotelOf(h.pid)[2]; });
      if (miss.length) add('warning', '수익', '많이 본 호텔 ' + top.length + '곳 중 ' + miss.length + '곳에 제휴 링크가 없어요',
        miss.slice(0, 4).map(function (h) { return hotelOf(h.pid)[0]; }).join(' · ') + (miss.length > 4 ? ' 외 ' + (miss.length - 4) + '곳' : ''),
        '세시간전에서 링크를 만들어 scripts/affiliate.json에 추가');
    }
    var fs = features(g).filter(function (x) { return x.name !== '가격 버튼'; }).slice(0, 3);
    if (fs.length && tot) add('', '기능', '많이 쓰는 기능은 ' + fs.map(function (x) { return x.name; }).join(' · ') + '예요',
      fs.map(function (x) { return x.name + ' ' + pct(ratio(x.s, tot), 1); }).join(' · ') + ' (전체 세션 대비)', '');
    return out.sort(function (a, b) { return TONE_ORD[a.tone] - TONE_ORD[b.tone]; });
  }
  function insCard(x) {
    return '<div class="ad-card ad-ins"><div class="ad-ins-k">' + tag(x.tone, TONE_TXT[x.tone]) + '<span>' + esc(x.area) + '</span></div>' +
      '<h3 class="ad-ins-t">' + esc(x.title) + '</h3>' +
      (x.meter != null ? bar(x.meter, x.tone ? 'is-' + x.tone : 'ad-fill-chart') : '') +
      '<p class="ad-ins-w">' + esc(x.why) + '</p>' +
      (x.todo ? '<p class="ad-ins-a"><b>할 일</b>' + esc(x.todo) + '</p>' : '') + '</div>';
  }

  // ───────────── 개선 후보 규칙 7개 (§4-4) — 점수 = 영향(세션 수) × 확신 ─────────────
  function candidates() {
    var out = [];
    function add(score, title, basis, tab) { out.push({ score: score, title: title, basis: basis, tab: tab }); }
    var c = A && A.clarity;
    (c && c.urls || []).forEach(function (u) {
      if (u.rest) return;
      var qb = ratio(u.quickback_sessions, u.sessions);
      if (/^\/hotels\//.test(u.url) && u.sessions >= 30 && qb >= 0.4)
        add(u.sessions * qb, '착지 첫 화면이 약속과 달라요 — ' + urlLabel(u.url), 'Clarity 7일 세션 ' + num(u.sessions) + ' · 퀵백 ' + pct(qb), 'ux');
      var dr = ratio(u.dead, u.sessions);
      if (u.sessions >= 10 && dr >= 0.3)   // 세션 10 미만은 한두 사람 버릇이라 뺀다(설계 밖 하한)
        add(u.sessions * Math.min(dr, 1) * 0.8, '눌리는데 반응 없는 요소가 있어요 — ' + urlLabel(u.url), '데드 클릭 ' + num(u.dead) + '회 / 세션 ' + num(u.sessions) + ' · Clarity 녹화로 확인', 'ux');
    });
    var g90 = gaWin('90');
    if (g90 && S) {
      var miss = g90.hotels.slice(0, 40).filter(function (h) { var x = hotelOf(h.pid); return x && !x[2] && h.views > 0; });
      if (miss.length) add(miss.reduce(function (s, h) { return s + h.views; }, 0) * 0.5, '조회 많은 호텔에 제휴 링크가 없어요 (' + miss.length + '곳)',
        '세시간전 링크 만들기: ' + miss.slice(0, 6).map(function (h) { return hotelOf(h.pid)[0]; }).join(' · ') + (miss.length > 6 ? ' 외' : ''), 'ux');
    }
    var g28 = gaWin('28');
    if (g28) {
      var f = g28.funnel, pv = f.prev || {};
      [['scroll90', '끝까지 읽음'], ['tab_click', '탭 이동'], ['cta_click', '가격 버튼 클릭']].forEach(function (st) {
        var a = ratio(f[st[0]], f.detail_sessions), b = ratio(pv[st[0]], pv.detail_sessions);
        if (a != null && b != null && b - a >= 0.03 && pv.detail_sessions >= 100)
          add(f.detail_sessions * (b - a) * 10, '상세 ' + st[1] + ' 비율이 줄었어요', '28일 ' + pct(a, 1) + ' ← 앞 28일 ' + pct(b, 1), 'ux');
      });
      var terms = (g28.search_noresult || []).filter(function (t) { return t.n >= 3; });
      if (terms.length) add(terms.reduce(function (s, t) { return s + t.n; }, 0) * 5, '결과 없는 검색어가 반복돼요',
        'token_dict.py 별칭 추가: ' + terms.slice(0, 5).map(function (t) { return t.term + ' ' + t.n + '회'; }).join(' · '), 'ux');
    }
    if (A && A.ops) {
      var bs = batchState(), bk = backupState();
      if (bs.tone === 'danger') add(1e6, '주간 배치가 멈춘 것 같아요', bs.v, 'ops');
      if (bk.tone === 'danger') add(1e6, 'DB 백업이 밀렸어요', bk.v, 'ops');
      if (clarityLate()) add(5e5, 'Clarity 수집이 2일 넘게 비었어요', '마지막 수집 ' + ((A.clarity && A.clarity.last_day) || '없음'), 'ops');
    }
    baList().forEach(function (x) {
      if (x.ba && x.ba.verdict === 'down') add(1e4, '변경 뒤 나빠진 지표가 있어요 — 되돌리기 검토', x.c.date + ' ' + x.c.commit + ' ' + x.c.title, 'chg');
    });
    return out.sort(function (a, b) { return b.score - a.score; });
  }

  // ───────────── 핵심 지표 카드 ─────────────
  function coreKpis(g, w, extra) {
    var f = g.funnel || {}, pv = f.prev || {}, wl = '앞 ' + w + '일 ';
    var cr = ratio(f.cta_click, f.detail_sessions), pcr = ratio(pv.cta_click, pv.detail_sessions);
    var sr = ratio(f.scroll90, f.detail_sessions), psr = ratio(pv.scroll90, pv.detail_sessions);
    var nmin = Math.min(f.detail_sessions || 0, pv.detail_sessions || 0);
    var out = [
      kpi({ label: '방문(세션)', value: num(g.sessions), delta: delta(g.sessions, g.prev_sessions, 'rel', true), prev: wl + num(g.prev_sessions),
        spark: spark(series('sessions', w), '일별 세션') }),
      kpi({ label: '상세 페이지 도달', value: num(f.detail_sessions), delta: delta(f.detail_sessions, pv.detail_sessions, 'rel', true), prev: wl + num(pv.detail_sessions),
        spark: spark(series('detail_sessions', w), '일별 상세 세션') }),
      kpi({ label: '가격 버튼 클릭률', value: pct(cr, 1), delta: delta(cr, pcr, 'pp', true, nmin), prev: wl + pct(pcr, 1),
        spark: spark(rollRate('d:check_price_click', 'd:page_view', w), '7일 이동 가격 버튼 클릭률') }),
      kpi({ label: '끝까지 읽음', value: pct(sr, 1), delta: delta(sr, psr, 'pp', true, nmin), prev: wl + pct(psr, 1),
        spark: spark(rollRate('d:scroll', 'd:page_view', w), '7일 이동 90% 스크롤 비율') })];
    if (extra) {
      var se = ev(g, 'search'), nr = ev(g, 'search_no_result');
      out.push(kpi({ label: '참여율', value: pct(engaged(g)), sub: '10초 넘게 머물렀거나 2쪽 이상 본 세션' }));
      out.push(kpi({ label: '검색 실패율', value: se ? pct(clamp01(ratio(nr ? nr.sessions : 0, se.sessions))) : '—',
        sub: se ? '검색 ' + num(se.sessions) + '세션 중 결과 없음 ' + num(nr ? nr.sessions : 0) : '검색 기록 없음' }));
    }
    return out.join('');
  }

  // ───────────── 현황 ─────────────
  function stCard(label, st) {
    return '<div class="ad-card ad-kpi"><span class="ad-kpi-l">' + esc(label) + '</span><b class="ad-st-v">' + dot(st.tone) + esc(st.v) + '</b>' +
      (st.s ? '<span class="ad-kpi-p">' + st.s + '</span>' : '') + '</div>';
  }
  function renderHome() {
    var cnt = (S && S.counts) || {}, db = A && A.db, g = gaWin('28'), end = A && A.ga && A.ga.end, html = '';
    html += sec('상태', '<div class="ad-grid">' + stCard('주간 배치', batchState()) + stCard('DB 백업', backupState()) +
      stCard('운영 감시', healthState()) + stCard('사이트 빌드', buildState()) + '</div>', '', { raw: 1 });
    if (g) {
      html += sec('핵심 지표', '<div class="ad-grid">' + coreKpis(g, '28') + '</div>', '최근 28일' + (end ? '(' + esc(end.slice(5)) + '까지)' : '') + ' · 앞 28일과 비교 · 그래프는 일별(비율은 7일 이동)', { raw: 1 });
      var ins = insights(g, '28');
      html += sec('이번 28일 인사이트', '<div class="ad-grid ad-grid-1 ad-g3">' + ins.slice(0, 3).map(insCard).join('') + '</div>' +
        (ins.length > 3 ? '<button type="button" class="btn-gray btn-block ad-go" data-go="ux">인사이트 ' + ins.length + '개 모두 보기</button>' : ''),
        '문제 → 살펴보기 → 좋아요 순', { raw: 1 });
      var chg = ratio(g.sessions - g.prev_sessions, g.prev_sessions);
      html += sec('방문 추이', '<div class="ad-legend"><span><i class="ad-leg-line ad-s1-chart"></i>전체 세션</span><span><i class="ad-leg-line is-dash"></i>상세 페이지 세션</span></div>' +
        '<div class="ad-chart"><canvas id="ad-chart-28" aria-label="최근 28일 일별 세션 선 그래프" role="img"></canvas></div>' +
        '<p class="ad-foot">앞 28일 ' + num(g.prev_sessions) + ' → 최근 28일 ' + num(g.sessions) + ' <b>(' + (chg == null ? '—' : (chg >= 0 ? '+' : '') + Math.round(chg * 100) + '%') + ')</b> · 내부 트래픽 제외(GA 필터)</p>');
    }
    var cs = candidates().slice(0, 5);
    html += sec('지금 고칠 것', cs.length ? '<ol class="ad-todo">' + cs.map(function (x) {
      return '<li><b class="ad-todo-t">' + esc(x.title) + '</b><span class="ad-todo-b">' + esc(x.basis) + '</span>' +
        '<button type="button" class="btn-text btn-text--sm" data-go="' + x.tab + '">' + { ux: 'UX 지표에서 보기', ops: '운영 탭에서 보기', chg: '변경 전후에서 보기' }[x.tab] + '</button></li>';
    }).join('') + '</ol>' : '<p class="ad-note">' + (A ? '규칙에 걸린 후보가 없어요' : 'VM 집계가 들어오면 후보를 뽑아요') + '</p>', '운영·데이터 규칙 7개로 뽑은 할 일, 영향 큰 순 5개');
    var hs = db && db.hotels, showN = hs ? (hs.active || 0) + (hs.watch || 0) : (cnt.active || 0) + (cnt.watch || 0);
    var affR = ratio(cnt.affiliate_detail, cnt.detail);
    html += sec('사이트 현황', '<div class="ad-grid">' +
      kpi({ label: '사이트 노출 호텔', value: num(showN), sub: hs ? '운영 ' + num(hs.active) + ' · 리뷰 적음 ' + num(hs.watch) + ' · 대기 ' + num((hs.new || 0) + (hs.pending || 0)) : '빌드 기준' }) +
      kpi({ label: '상세 페이지', value: num(cnt.detail), sub: '실망 확률 노출 ' + num(cnt.scored) + '곳' }) +
      kpi({ label: '제휴 링크', value: num(cnt.affiliate_detail) + '곳', sub: '상세의 ' + pct(affR), spark: '<div class="ad-kpi-bar">' + bar(affR) + '</div>' }) +
      kpi({ label: '사이트 평가 리뷰', value: db ? num(db.reviews_site) : '—', sub: db && db.analyzed_v5 != null ? 'v5 분석 ' + num(db.analyzed_v5) + '건' : 'VM 집계 없음' }) +
      '</div>', '', { raw: 1 });
    $('ad-home').innerHTML = html;
    drawChart();
  }
  function drawChart() {
    var el = $('ad-chart-28');
    if (!el || !window.Chart || !A || !A.ga.daily) return;
    var d = A.ga.daily.slice(-28), pri = tok('--primary'), ink3 = tok('--ink-3'), line = tok('--line');
    if (drawn.c28) drawn.c28.destroy();
    drawn.c28 = new Chart(el, {
      type: 'line',
      data: { labels: d.map(function (x) { return x.day.slice(5); }), datasets: [
        { label: '전체 세션', data: d.map(function (x) { return x.sessions; }), borderColor: pri, backgroundColor: pri, borderWidth: 2.5, pointRadius: 0, pointHoverRadius: 4, tension: .3 },
        { label: '상세 세션', data: d.map(function (x) { return x.detail_sessions; }), borderColor: ink3, backgroundColor: ink3, borderWidth: 1.5, borderDash: [4, 3], pointRadius: 0, pointHoverRadius: 3, tension: .3 }] },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false }, ticks: { color: ink3, maxTicksLimit: 7, font: { size: 13 } } },
          y: { beginAtZero: true, grid: { color: line }, border: { display: false }, ticks: { color: ink3, precision: 0, maxTicksLimit: 5, font: { size: 13 } } } } }
    });
  }

  // ───────────── UX 지표 ─────────────
  var hotelSort = { k: 'views', d: -1 }, hotelOnlyNoLink = false, claritySort = { k: 'sessions', d: -1 }, openEv = {}, more = {};
  function renderUx() {
    var g = gaWin(WIN), html = '', end = A && A.ga && A.ga.end;
    html += '<div class="ad-chips" role="group" aria-label="기간">' + ['7', '28', '90'].map(function (w) {
      return '<button type="button" class="chip-view' + (w === WIN ? ' is-on' : '') + '" data-win="' + w + '" aria-pressed="' + (w === WIN) + '">최근 ' + w + '일</button>';
    }).join('') + '</div>';
    if (!g) { $('ad-ux').innerHTML = html + card('<p class="ad-note">VM 집계(GA4)가 없어 이 탭을 그릴 수 없어요. ' + esc(A_ERR) + '</p>'); return; }
    var ins = insights(g, WIN);
    html += sec('인사이트', '<div class="ad-grid ad-grid-1 ad-g2">' + ins.map(insCard).join('') + '</div>',
      '최근 ' + WIN + '일' + (end ? '(' + esc(end.slice(5)) + '까지)' : '') + ' 데이터에서 규칙으로 뽑은 결론 · 문제 → 살펴보기 → 좋아요 순', { raw: 1 });
    html += sec('핵심 지표', '<div class="ad-grid ad-g3">' + coreKpis(g, WIN, true) + '</div>', '앞 ' + WIN + '일과 비교 · 점 = 판단할 만큼 표본·변화가 클 때만', { raw: 1 });
    html += renderJourney(g);
    html += '<div class="ad-cols">' + renderChannels(g) + renderLanding(g) + '</div>';
    html += '<div class="ad-cols">' + renderFeatures(g) + renderSearch(g) + '</div>';
    html += renderHotels(g);
    html += renderClarity();
    $('ad-ux').innerHTML = html;
  }
  function renderJourney(g) {
    var f = g.funnel || {}, pv = f.prev || {}, D = f.detail_sessions, P = pv.detail_sessions;
    if (!D) return '';
    var steps = [['상세 페이지 도착', 'detail_sessions'], ['끝까지 읽음 (90% 스크롤)', 'scroll90'], ['탭으로 이동', 'tab_click'], ['가격 버튼 클릭', 'cta_click']];
    function per(k) { return Math.round(ratio(f[k], D) * 100); }
    var lead = '상세를 본 100명 중 <b>' + per('scroll90') + '명</b>이 끝까지 읽고, <b>' + per('tab_click') + '명</b>이 탭을 누르고, <b>' + per('cta_click') + '명</b>이 가격 버튼을 눌러요.';
    var rows = steps.map(function (s, i) {
      var r = ratio(f[s[1]], D), none = i && !pv[s[1]], rp = none ? null : ratio(pv[s[1]], P);   // 앞 기간 0건 = 그때는 이벤트가 없었음(11-04 이후 추가분) → 비교 안 함
      var sub = !i ? '<span>앞 ' + WIN + '일 ' + num(P) + '</span>' : none ? '<span>앞 ' + WIN + '일 기록 없음 — 이벤트를 나중에 달아서 비교 안 함</span>'
        : delta(r, rp, 'pp', true, Math.min(D, P || 0)) + '<span>앞 ' + WIN + '일 ' + pct(rp, 1) + '</span>';
      return hrow(esc(s[0]), num(f[s[1]]) + (i ? ' · ' + pct(r, 1) : ''), r, sub, 'ad-fill-chart', i ? rp : null);
    });
    return sec('상세 페이지 여정', '<p class="ad-lead">' + lead + '</p>' +
      '<div class="ad-legend"><span><i class="ad-leg-box ad-s1-chart"></i>최근 ' + WIN + '일</span><span><i class="ad-leg-tick"></i>앞 ' + WIN + '일</span></div>' +
      '<ul class="ad-hb">' + rows.join('') + '</ul>' +
      '<p class="ad-foot">가격 버튼 도착지 — 아고다 <b>' + num(f.cta_agoda) + '</b> · 구글 <b>' + num(f.cta_google) + '</b> (세션)</p>',
      '막대 = 상세를 본 세션 중 그 행동이 있었던 비율 · 세로선 = 앞 ' + WIN + '일');
  }
  function renderChannels(g) {
    var tot = g.sessions || 0, ch = (g.channel || []).slice().sort(function (a, b) { return b.sessions - a.sessions; });
    if (!tot || !ch.length) return '';
    return sec('어디서 왔나', '<div class="ad-stack" role="img" aria-label="유입 채널 비중">' + ch.map(function (c) {
      return '<i class="' + (CH_CLS[c.name] || 'ad-s5-chart') + '" style="flex:' + c.sessions + ' 0 0"></i>';
    }).join('') + '</div><ul class="ad-leg">' + ch.map(function (c) {
      return '<li><span class="ad-leg-dot ' + (CH_CLS[c.name] || 'ad-s5-chart') + '"></span><span class="ad-leg-n">' + esc(CH_NAME[c.name] || c.name) + '</span>' +
        '<span class="ad-leg-v">' + pct(ratio(c.sessions, tot)) + '</span><span class="ad-leg-s">' + num(c.sessions) + '</span></li>';
    }).join('') + '</ul>', '유입 채널별 세션 비중');
  }
  function renderLanding(g) {
    var tot = g.sessions || 0;
    return sec('첫 페이지별 반응', '<ul class="ad-hb">' + (g.landing || []).map(function (l) {
      var tone = l.engaged_rate >= 0.6 ? 'safe' : l.engaged_rate >= 0.4 ? 'warning' : 'danger';
      return hrow(esc(l.group), '머묾 ' + pct(l.engaged_rate), l.engaged_rate,
        dot(tone) + '<span>' + num(l.sessions) + '세션 (' + pct(ratio(l.sessions, tot)) + ') · 평균 ' + num(l.avg_sec) + '초</span>', 'is-' + tone);
    }).join('') + '</ul>', '처음 들어온 페이지별 머문 세션 비율(참여율) · 60% 이상 양호, 40% 미만 문제');
  }
  function renderFeatures(g) {
    var tot = g.sessions || 0, fs = features(g), max = fs.length ? fs[0].s : 1, rest = fs.slice(8);
    var body = fs.length ? '<ul class="ad-hb">' + fs.slice(0, 8).map(function (x) {
      return hrow(esc(x.name), pct(ratio(x.s, tot), 1), x.s / max, '<span>' + (x.approx ? '약 ' : '') + num(x.s) + '세션</span>');
    }).join('') + '</ul>' + (rest.length ? '<p class="ad-foot">그 밖: ' + rest.map(function (x) { return esc(x.name) + ' ' + num(x.s); }).join(' · ') + '세션</p>' : '')
      : '<p class="ad-note">이벤트 기록이 없어요</p>';
    var open = more.ev;
    body += moreBtn('ev', '이벤트 원본 표 보기', open);
    if (open) body += table([{ t: '이벤트' }, { t: '건수', num: 1 }, { t: '세션', num: 1 }, { t: '세션 대비', num: 1 }],
      g.events.filter(function (e) { return e.count > 0; }).map(function (e) {
        var dims = Object.keys(e.by || {}), op = openEv[e.name];
        var row = '<tr>' + td(dims.length ? '<button type="button" class="ad-exp" data-ev="' + esc(e.name) + '" aria-expanded="' + !!op + '">' + esc(e.name) + '</button>' : esc(e.name)) +
          td(num(e.count), 1) + td(num(e.sessions), 1) + td(pct(ratio(e.sessions, tot), 1), 1) + '</tr>';
        if (op) dims.forEach(function (dm) {
          Object.keys(e.by[dm]).sort(function (a, b) { return e.by[dm][b] - e.by[dm][a]; }).slice(0, 12).forEach(function (v) {
            row += '<tr class="ad-sub">' + td(esc(dm) + ' · ' + esc(v)) + td(num(e.by[dm][v]), 1) + td('', 1) + td('', 1) + '</tr>';
          });
        });
        return row;
      }), 'ad-t-ev');
    return sec('무엇을 쓰나', body, '기능별 사용 세션 비율(전체 세션 대비) · 막대는 가장 많이 쓴 기능 기준');
  }
  function renderSearch(g) {
    var se = ev(g, 'search'), nr = ev(g, 'search_no_result'), terms = g.search_noresult || [];
    var rr = se ? clamp01(ratio(nr ? nr.sessions : 0, se.sessions)) : null;
    var links = terms.filter(function (t) { return /^https?:/.test(t.term); }), names = terms.filter(function (t) { return !/^https?:/.test(t.term); });
    var body = se ? '<div class="ad-hb-r"><span class="ad-hb-l">결과 없음을 본 검색 세션</span><span class="ad-hb-v">' + pct(rr) + '</span></div>' +
      bar(rr, rr >= 0.3 ? 'is-danger' : 'is-warning') + '<div class="ad-hb-s"><span>검색 ' + num(se.sessions) + '세션 중 ' + num(nr ? nr.sessions : 0) + '세션</span></div>' : '<p class="ad-note">검색 기록이 없어요</p>';
    if (names.length) body += '<h3 class="ad-h3">찾던 이름 ' + names.length + '개</h3><ul class="ad-terms">' + names.map(function (t) {
      return '<li>' + esc(t.term) + (t.n > 1 ? ' <b>' + num(t.n) + '회</b>' : '') + '</li>'; }).join('') + '</ul>';
    if (links.length) body += '<h3 class="ad-h3">붙여넣은 구글 지도 링크 ' + links.length + '개</h3><p class="ad-note">이름 대신 지도 링크를 넣는 사람이 있어요 — 링크에서 장소 이름을 읽으면 찾을 수 있어요.</p>';
    return sec('찾다 실패한 검색', body, '최근 ' + WIN + '일 결과 없음 검색어 상위 20 · 있는 호텔이면 token_dict.py 별칭 추가');
  }
  function renderHotels(g) {
    if (!S) return '';
    var all = (g.hotels || []).filter(function (h) { return hotelOf(h.pid); });
    var top = all.filter(function (h) { return h.views > 0; }).sort(function (a, b) { return b.views - a.views; }).slice(0, 10);
    var max = top.length ? top[0].views : 1;
    var body = top.length ? '<ul class="ad-hb">' + top.map(function (h) {
      var x = hotelOf(h.pid);
      return hrow('<a href="/hotels/' + esc(x[1]) + '" target="_blank" rel="noopener">' + esc(x[0]) + '</a>' + (x[2] ? '' : '<span class="tag">' + dot('warning') + '링크 없음</span>'),
        '조회 ' + num(h.views), h.views / max, '<span>사용자 ' + num(h.users) + ' · 가격 버튼 ' + num(h.cta) + '</span>');
    }).join('') + '</ul>' : '<p class="ad-note">조회 기록이 없어요</p>';
    var open = more.hotels;
    body += moreBtn('hotels', '호텔 ' + num(all.length) + '곳 표로 보기', open);
    if (open) {
      var k = hotelSort.k, d = hotelSort.d;
      var rows = all.filter(function (h) { return !hotelOnlyNoLink || !hotelOf(h.pid)[2]; }).sort(function (a, b) { return (a[k] - b[k]) * d || b.views - a.views; });
      body += '<div class="ad-chips"><button type="button" class="chip-filter chip-filter--sm' + (hotelOnlyNoLink ? ' is-on' : '') + '" data-nolink aria-pressed="' + hotelOnlyNoLink + '">링크 없는 곳만</button></div>' +
        table([{ t: '호텔' }, { t: '조회', num: 1, sort: 'h:views' }, { t: '사용자', num: 1, sort: 'h:users' }, { t: '가격 버튼', num: 1, sort: 'h:cta' }],
          rows.map(function (h) {
            var x = hotelOf(h.pid);
            return '<tr>' + td('<a href="/hotels/' + esc(x[1]) + '" target="_blank" rel="noopener">' + esc(x[0]) + '</a>' + (x[2] ? '' : ' <span class="tag">링크 없음</span>')) +
              td(num(h.views), 1) + td(num(h.users), 1) + td(num(h.cta), 1) + '</tr>';
          }), 'ad-t-hotels');
    }
    return sec('많이 본 호텔', body, '최근 ' + WIN + '일 상세 조회 상위 10곳 · 링크 없음 = 제휴 링크가 없어 구글로 나가는 곳');
  }
  function renderClarity() {
    var c = A && A.clarity;
    if (!c) return sec('불편 신호', '<p class="ad-note">Clarity 집계가 없어요</p>');
    var urls = c.urls.filter(function (u) { return !u.rest; });
    var top = urls.slice().sort(function (a, b) { return b.sessions - a.sessions; }).slice(0, 6);
    var body = (c.n_days < 3 ? '<p class="ad-note ad-note-gap">수집 ' + c.n_days + '일째라 표본이 작아요 — 7일이 쌓이면 믿을 만해져요.</p>' : '') +
      '<ul class="ad-hb">' + top.map(function (u) {
        var sc = u.scroll == null ? null : u.scroll / 100, qb = ratio(u.quickback_sessions, u.sessions), dr = ratio(u.dead, u.sessions);
        var tone = sc == null ? '' : sc >= 0.5 ? 'safe' : sc >= 0.3 ? 'warning' : 'danger';
        var flags = [];
        if (qb >= 0.3) flags.push(dot('danger') + '<span>퀵백 ' + pct(qb) + '</span>');
        if (dr >= 0.3) flags.push(dot('danger') + '<span>데드 클릭 ' + num(u.dead) + '회</span>');
        return hrow('<span title="' + esc(u.url) + '">' + esc(urlLabel(u.url)) + '</span>', '스크롤 ' + (sc == null ? '—' : Math.round(u.scroll) + '%'), sc,
          '<span>세션 ' + num(u.sessions) + ' · 활동 ' + (u.engage_sec == null ? '—' : num(u.engage_sec) + '초') + '</span>' + flags.join(''), tone ? 'is-' + tone : '');
      }).join('') + '</ul>';
    var open = more.clarity;
    body += moreBtn('clarity', '페이지 ' + num(urls.length) + '개 표로 보기', open);
    if (open) {
      var k = claritySort.k, d = claritySort.d;
      var rows = urls.slice().sort(function (a, b) {
        var x = k === 'quickback' ? ratio(a.quickback_sessions, a.sessions) : a[k], y = k === 'quickback' ? ratio(b.quickback_sessions, b.sessions) : b[k];
        return ((x == null ? -1 : x) - (y == null ? -1 : y)) * d;
      }).concat(c.urls.filter(function (u) { return u.rest; }));
      body += table([{ t: '페이지' }, { t: '세션', num: 1, sort: 'c:sessions' }, { t: '데드 클릭', num: 1, sort: 'c:dead' },
        { t: '레이지', num: 1, sort: 'c:rage' }, { t: '퀵백', num: 1, sort: 'c:quickback' }, { t: '스크롤', num: 1, sort: 'c:scroll' }, { t: '활동', num: 1, sort: 'c:engage_sec' }],
        rows.map(function (u) {
          return '<tr>' + td('<span title="' + esc(u.url) + '">' + esc(urlLabel(u.url)) + '</span>') + td(num(u.sessions), 1) + td(num(u.dead), 1) + td(num(u.rage), 1) +
            td(pct(ratio(u.quickback_sessions, u.sessions)), 1) + td(u.scroll == null ? '—' : Math.round(u.scroll) + '%', 1) + td(u.engage_sec == null ? '—' : num(u.engage_sec) + '초', 1) + '</tr>';
        }), 'ad-t-wide');
    }
    return sec('불편 신호 (Clarity)', body, '최근 7일 많이 본 페이지의 평균 스크롤 깊이 · 퀵백(바로 뒤로)·데드 클릭(눌러도 반응 없음)이 30% 넘으면 표시 · 기간 칩과 상관없음');
  }

  // ───────────── 변경 전후 ─────────────
  var VD = { up: ['safe', '개선'], down: ['danger', '악화'], same: ['', '차이 없음'], hold: ['', '아직 모름(표본 적음)'] };
  function baList() {
    var ba = {}; ((A && A.changes && A.changes.before_after) || []).forEach(function (x) { ba[x.commit] = x; });
    return ((S && S.changes) || []).map(function (c) { return { c: c, ba: ba[c.commit] || null }; });
  }
  function renderChg() {
    var list = baList(), html = '';
    var cnt = { up: 0, down: 0, wait: 0 };
    list.forEach(function (x) { var v = x.ba && x.ba.verdict; if (v === 'up') cnt.up++; else if (v === 'down') cnt.down++; else cnt.wait++; });
    var last = list.length ? list.map(function (x) { return x.c.date; }).sort().pop() : null;
    html += sec('요약', '<div class="ad-grid">' +
      kpi({ label: '기록된 변경', value: num(list.length) + '건', sub: '대기 중 ' + num(((S && S.pending) || []).length) + '건' }) +
      kpi({ label: '개선', value: num(cnt.up) + '건', sub: '14일 비교로 확정' }) +
      kpi({ label: '악화', value: num(cnt.down) + '건', sub: cnt.down ? '되돌리기 검토' : '없음' }) +
      kpi({ label: '다음 측정일', value: last ? esc(addDays(last, 14).slice(5)) : '—', sub: last ? '가장 최근 변경 ' + esc(last.slice(5)) + ' + 14일' : '' }) + '</div>', '', { raw: 1 });
    html += sec('변경 ' + list.length + '건', list.length ? '<ol class="ad-chg">' + list.map(function (x) {
      var c = x.c, b = x.ba, v = VD[(b && b.verdict) || 'hold'];
      var head = '<div class="ad-chg-meta">' + esc(c.date) + ' · <a href="' + GH + esc(c.commit) + '" target="_blank" rel="noopener">' + esc(c.commit) + '</a>' + (c.doc ? ' · ' + esc(c.doc) : '') + '</div>' +
        '<h3 class="ad-chg-h">' + esc(c.title) + '</h3>' + (c.what ? '<p class="ad-chg-what">' + esc(c.what) + '</p>' : '');
      var state = !b ? 'VM 집계가 들어오면 계산해요' : !b.after ? '배포 다음 날부터 계산해요 (' + esc(addDays(c.date, 14)) + ' 확정)'
        : b.final ? '전 ' + esc(b.before[0].slice(5)) + '~' + esc(b.before[1].slice(5)) + ' / 후 ' + esc(b.after[0].slice(5)) + '~' + esc(b.after[1].slice(5))
          : b.days_after + '일째, ' + esc(addDays(c.date, 14)) + ' 확정 — 지금은 비율만 비교';
      var rows = (c.watch || []).map(function (k) {
        var m = b && b.metrics && b.metrics[k];
        if (!m) return '<tr>' + td(esc(k)) + td('—', 1) + td('—', 1) + td('—') + '</tr>';
        var diff = m.before != null && m.after != null ? (m.after - m.before) * 100 : null, mv = VD[m.verdict] || VD.hold;
        var kn = function (k2, n2) { return '<span class="ad-n ad-n-block">' + num(k2) + '/' + num(n2) + '</span>'; };
        return '<tr>' + td(esc(m.label || k)) + td(pct(m.before, 1) + kn(m.k_before, m.n_before), 1) +
          td(m.after == null ? '—' : pct(m.after, 1) + kn(m.k_after, m.n_after), 1) +
          td(tag(mv[0], m.verdict === 'hold' ? '보류' : mv[1]) + (diff == null ? '' : '<span class="ad-n ad-n-block">' + (diff >= 0 ? '+' : '') + diff.toFixed(1) + '%p</span>')) + '</tr>';
      });
      return '<li>' + head + '<div class="ad-chg-vd">' + tag(v[0], v[1]) + '<span>' + state + '</span></div>' +
        table([{ t: '지표' }, { t: '14일 전', num: 1 }, { t: '14일 후', num: 1 }, { t: '판정·변화' }], rows, 'ad-t-chg') + '</li>';
    }).join('') + '</ol>' : card('<p class="ad-note">scripts/changes.json에 기록된 변경이 없어요</p>'),
      '배포일 전 14일(배포일 제외)과 다음 날부터 14일을 비교해요. 한쪽이라도 분모 100 미만이면 보류, 차이 3%p 이상이고 표준오차 합보다 크면 개선·악화', { raw: 1 });
    var pend = (S && S.pending) || [];
    html += sec('대기 중 ' + pend.length + '건', pend.length ? '<ul class="ad-todo">' + pend.map(function (p) {
      return '<li><b class="ad-todo-t">' + esc(p.title) + '</b>' + (p.why ? '<span class="ad-todo-w">' + esc(p.why) + '</span>' : '') +
        '<span class="ad-todo-b">' + esc(p.from || '') + (p.needs ? ' · 확인: ' + esc(p.needs) : '') + '</span></li>';
    }).join('') + '</ul>' : '<p class="ad-note">대기 항목이 없어요</p>', '설계서에서 옮긴 아직 안 한 일 — scripts/changes.json pending');
    $('ad-chg').innerHTML = html;
  }

  // ───────────── 운영 ─────────────
  var JOB_ST = { ok: ['safe', '정상'], partial: ['warning', '일부 실패'], failed: ['danger', '실패'], running: ['warning', '진행 중'] };
  var DOW = ['일', '월', '화', '수', '목', '금', '토'];
  function cronField(f, lo, hi) {   // '*' · '*/n' · 'a-b' · 'a,b' → 허용 값 집합
    var set = {};
    f.split(',').forEach(function (part) {
      var step = 1, m = /^(.*)\/(\d+)$/.exec(part); if (m) { part = m[1]; step = +m[2]; }
      var a = lo, b = hi;
      if (part !== '*') { var r = part.split('-'); a = +r[0]; b = r.length > 1 ? +r[1] : (m ? hi : a); }
      for (var i = a; i <= b; i += step) set[i === 7 && hi === 6 ? 0 : i] = 1;
    });
    return set;
  }
  function cronNext(fields) {   // CRON_TZ=Asia/Seoul — KST 분 단위로 최대 45일 앞까지
    var mi = cronField(fields[0], 0, 59), hr = cronField(fields[1], 0, 23), dm = cronField(fields[2], 1, 31), mo = cronField(fields[3], 1, 12), dw = cronField(fields[4], 0, 6);
    var domAny = fields[2] === '*', dowAny = fields[4] === '*';
    var t = new Date(Math.ceil((Date.now() + 9 * 3600e3 + 1) / 6e4) * 6e4);
    for (var i = 0; i < 45 * 1440; i++, t = new Date(t.getTime() + 6e4)) {
      if (!mo[t.getUTCMonth() + 1]) continue;
      var dOk = domAny && dowAny ? true : domAny ? !!dw[t.getUTCDay()] : dowAny ? !!dm[t.getUTCDate()] : (dm[t.getUTCDate()] || dw[t.getUTCDay()]);
      if (!dOk || !hr[t.getUTCHours()] || !mi[t.getUTCMinutes()]) continue;
      return p2(t.getUTCMonth() + 1) + '-' + p2(t.getUTCDate()) + ' (' + DOW[t.getUTCDay()] + ') ' + p2(t.getUTCHours()) + ':' + p2(t.getUTCMinutes());
    }
    return '—';
  }
  function cronHuman(f) {
    var m = /^\*\/(\d+)$/.exec(f[0]);
    if (m && f[1] === '*') return m[1] + '분마다';
    var hm = f[1].split(',').map(function (h) { return p2(+h) + ':' + p2(+f[0]); }).join(' · ');
    if (f[2] !== '*') return '매월 ' + f[2] + '일 ' + hm;
    if (f[4] !== '*') return '매주 ' + f[4].split(',').map(function (d) { return DOW[+d % 7] || d; }).join('·') + ' ' + hm;
    return '매일 ' + hm;
  }
  function cronCmd(cmd) {
    var s = /([\w-]+\.(?:py|sh))/.exec(cmd);
    return s ? s[1] : cmd.slice(0, 60);
  }
  function renderOps() {
    var o = A && A.ops, html = '';
    if (!o) {
      html += sec('VM 집계 없음', '<p class="ad-note">' + esc(A_ERR || 'admin.json이 아직 없어요') + ' — 빌드 정보만 보여요. VM cron(09:20 admin_export.py)·R2 바인딩 ADMIN_BUCKET을 확인해요.</p>');
    } else {
      html += sec('상태', '<div class="ad-grid">' + stCard('주간 배치', batchState()) + stCard('DB 백업', backupState()) +
        stCard('운영 감시', healthState()) + stCard('Clarity 수집', { tone: clarityLate() ? 'danger' : 'safe', v: clarityLate() ? '2일 넘게 비었음' : '정상',
          s: '마지막 ' + esc((A.clarity && A.clarity.last_day) || '없음') + ' · 오늘 ' + num(A.clarity && A.clarity.pulls_today) + '/10회' }) + '</div>', '', { raw: 1 });
      html += sec('배치 이력', table([{ t: '유형' }, { t: '시작' }, { t: '끝' }, { t: '상태' }, { t: '요약' }], (o.sync_jobs || []).map(function (j) {
        var st = JOB_ST[j.status] || ['', j.status || '—'], x = j.stats || {}, dur = j.completed_at ? Math.round((new Date(j.completed_at) - new Date(j.started_at)) / 6e4) : null;
        var sum = [x.new_reviews != null ? '신규 리뷰 ' + num(x.new_reviews) : '', x.new_hotels ? '신규 호텔 ' + num(x.new_hotels) : '',
          x.analysis_cost != null ? '분석 $' + x.analysis_cost : '', (x.failed_steps || []).length ? '실패: ' + x.failed_steps.join(', ') : '', j.error ? '오류: ' + j.error.slice(0, 80) : ''].filter(Boolean).join(' · ');
        return '<tr>' + td(esc(j.job_type || '—')) + td(md(j.started_at)) + td(j.completed_at ? md(j.completed_at) + (dur != null ? '<span class="ad-n">' + dur + '분</span>' : '') : '—') +
          td(dot(st[0]) + ' ' + esc(st[1])) + td(esc(sum) || '—') + '</tr>';
      }), 'ad-t-wide'), 'sync_jobs 최근 10건');
      var desc = '', cr = [];
      (o.crontab || []).forEach(function (l) {
        if (/^\s*#/.test(l)) { desc = l.replace(/^\s*#\s*/, ''); return; }
        if (/^\s*[A-Z_]+=/.test(l)) return;
        var f = l.trim().split(/\s+/);
        if (f.length < 6) return;
        cr.push('<tr>' + td(esc(cronHuman(f))) + td(esc(cronNext(f))) + td('<b class="ad-mono">' + esc(cronCmd(f.slice(5).join(' '))) + '</b>' + (desc ? '<span class="ad-n ad-n-block">' + esc(desc.slice(0, 90)) + '</span>' : '')) + '</tr>');
        desc = '';
      });
      html += sec('cron', table([{ t: '일정(KST)' }, { t: '다음 실행' }, { t: '작업' }], cr, 'ad-t-wide'), '출처 ' + esc(o.crontab_src || '') + ' · 다음 실행은 이 화면을 연 시각 기준');
      var h = o.health || {}, iss = h.issues || [];
      var c = A.clarity || {}, ps = o.price_sample || {}, b = o.backup || {};
      html += sec('감시', '<dl class="ad-kv">' +
        '<dt>운영 감시 5항목</dt><dd>' + (iss.length ? dot('danger') + ' ' + iss.map(esc).join('<br>') : dot('safe') + ' 이상 없음') + '<span class="ad-n ad-n-block">점검 ' + md(h.checked_at) + ' · 동기화·running·열린 트랜잭션·잠금 대기·백업</span></dd>' +
        '<dt>Clarity 수집</dt><dd>' + dot(clarityLate() ? 'danger' : 'safe') + ' 마지막 ' + esc(c.last_day || '없음') + '<span class="ad-n ad-n-block">최근 ' + num(c.days) + '일 중 ' + num(c.n_days) + '일 수집 · 오늘 호출 ' + num(c.pulls_today) + ' / 10회</span></dd>' +
        '<dt>DB 백업</dt><dd>' + esc(b.latest_key || '없음') + '<span class="ad-n ad-n-block">' + (b.size_mb != null ? b.size_mb + 'MB · ' : '') + md(b.at) + ' · 보관 ' + num(b.count) + '개</span></dd>' +
        '<dt>가격 표본</dt><dd>' + (ps.last_run ? '마지막 ' + md(ps.last_run) : '기록 없음(매월 7일 05:00)') + '</dd></dl>' +
        ((ps.tail || []).length ? '<ol class="ad-log" aria-label="price_sample.log 마지막 10줄">' + ps.tail.map(function (l) { return '<li>' + esc(l) + '</li>'; }).join('') + '</ol>' : ''));
    }
    var dep = (S && S.deploys) || [];
    html += sec('빌드·배포', '<dl class="ad-kv"><dt>기준일(asof)</dt><dd>' + esc((S && S.asof) || '—') + '</dd>' +
      '<dt>빌드</dt><dd>' + md(S && S.built_at) + ' · 커밋 ' + esc((S && S.commit) || '—') + '</dd>' +
      '<dt>VM 집계</dt><dd>' + (A ? md(A.made_at) + ' · DB 기준 ' + esc(A.asof_db || '—') : '없음') + '</dd></dl>' +
      table([{ t: '커밋' }, { t: '날짜' }, { t: '내용' }], dep.map(function (d) {
        return '<tr>' + td('<a href="' + GH + esc(d.commit) + '" target="_blank" rel="noopener">' + esc(d.commit) + '</a>') + td(md(d.date, false)) + td(esc(d.subject)) + '</tr>';
      }), 'ad-t-wide'), '빌드 때 심은 최근 커밋 5건');
    var q = (A && A.ga && A.ga.quota) || {};
    html += sec('외부 쿼터', '<dl class="ad-kv">' +
      '<dt>Clarity Data Export</dt><dd>오늘 ' + num(A && A.clarity && A.clarity.pulls_today) + ' / 10회<span class="ad-n ad-n-block">1~3일치만, 프로젝트당 하루 10회</span></dd>' +
      '<dt>GA4 Data API</dt><dd>' + (q.tokens_day_remaining != null ? '이번 집계 ' + num(q.tokens_day_consumed) + '토큰 · 오늘 남음 ' + num(q.tokens_day_remaining) : '—') + '</dd>' +
      '<dt>Apify · Gemini</dt><dd><a href="https://console.apify.com/billing" target="_blank" rel="noopener">Apify 결제</a> · <a href="https://aistudio.google.com/" target="_blank" rel="noopener">Google AI Studio</a><span class="ad-n ad-n-block">사용량 API가 없어 링크만</span></dd></dl>');
    $('ad-ops').innerHTML = html;
  }

  // ───────────── 탭·이벤트 ─────────────
  var RENDER = { home: renderHome, ux: renderUx, chg: renderChg, ops: renderOps };
  function show(k, push) {
    if (!RENDER[k]) k = 'home';
    document.querySelectorAll('.ad-tabs [data-tab]').forEach(function (b) {
      var on = b.getAttribute('data-tab') === k; b.classList.toggle('is-on', on); b.setAttribute('aria-selected', on);
    });
    document.querySelectorAll('.ad-pane').forEach(function (p) { p.hidden = p.id !== 'ad-' + k; });
    if (S || A) RENDER[k]();
    if (push) try { history.replaceState(null, '', '#' + k); } catch (e) {}
  }
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-tab],[data-go],[data-win],[data-sort],[data-ev],[data-nolink],[data-more]');
    if (!t) return;
    if (t.hasAttribute('data-tab') || t.hasAttribute('data-go')) {   // 탭을 바꾸면 새 탭 맨 위(탭 줄 바로 아래)부터
      var tabs = document.querySelector('.ad-tabs'), y0 = window.scrollY;
      show(t.getAttribute('data-tab') || t.getAttribute('data-go'), true);
      var top = tabs.parentNode.querySelector('.ad-made').getBoundingClientRect().bottom + window.scrollY - (parseFloat(tok('--sticky-top')) || 56);
      if (y0 > top) window.scrollTo(0, top);
      return;
    }
    if (t.hasAttribute('data-win')) { WIN = t.getAttribute('data-win'); return renderUx(); }
    if (t.hasAttribute('data-more')) { var m = t.getAttribute('data-more'); more[m] = !more[m]; return renderUx(); }
    if (t.hasAttribute('data-ev')) { var n = t.getAttribute('data-ev'); openEv[n] = !openEv[n]; return renderUx(); }
    if (t.hasAttribute('data-nolink')) { hotelOnlyNoLink = !hotelOnlyNoLink; return renderUx(); }
    var s = t.getAttribute('data-sort').split(':'), st = s[0] === 'c' ? claritySort : hotelSort;
    st.d = st.k === s[1] ? -st.d : -1; st.k = s[1];
    renderUx();
  });

  function getJSON(u) {
    return fetch(u, { credentials: 'same-origin', cache: 'no-store' }).then(function (r) {
      if (!r.ok) return r.text().then(function (t) { var m = ''; try { m = JSON.parse(t).error; } catch (x) {} throw new Error(r.status + (m ? ' ' + m : '')); });
      return r.json();
    });
  }
  function loadAdmin() {
    var day = /[?&]day=(\d{8})/.exec(location.search);
    return getJSON('/admin/api/data' + (day ? '?day=' + day[1] : '')).catch(function (e) {
      if (LOCAL) return getJSON('/admin/sample.json').catch(function () { throw e; });
      throw e;
    });
  }
  Promise.all([
    getJSON('/admin/site.json').catch(function () { return null; }),
    loadAdmin().catch(function (e) { A_ERR = 'VM 집계를 못 받았어요(' + e.message + ')'; return null; })
  ]).then(function (r) {
    S = r[0]; A = r[1];
    $('ad-made').innerHTML = (A ? 'VM 집계 ' + md(A.made_at) + (A.mode === 'dry-run' ? ' (GA만)' : '') : esc(A_ERR || 'VM 집계 없음')) +
      ' · 빌드 ' + (S ? md(S.built_at) + ' · ' + esc(S.commit || '') : '정보 없음') +
      (A && A.errors && A.errors.length ? ' · 집계 일부 실패 ' + A.errors.length + '건' : '');
    show((location.hash || '#home').slice(1), false);
  });
})();

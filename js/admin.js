/* 관리자 페이지 /admin/ (ADMIN-DESIGN §1, 2026-11-05) — 순수 JS(jQuery 없음), chart.js 4.4.1(상세와 같은 CDN) 선 그래프 1종.
   데이터 2개:
     /admin/site.json  — 빌드 시점 사실(generate.admin_site_json): 호텔 표(pid → [이름, 슬러그, 제휴, 점수 노출, 상태])·상세 수·제휴 링크 수·
                         asof·빌드 시각·커밋·최근 커밋 5건·changes.json 사본(changes·pending)
     /admin/api/data   — VM 집계(pipeline/admin_export.py → R2 → functions/admin/api/data.js). 없으면(503) site.json만으로 일부를 그린다.
                         로컬 프리뷰(localhost)는 /admin/sample.json(scripts/check_admin.py가 만든 실제 값, 커밋 안 함)으로 대신한다.
   탭 4개: 현황 · UX 지표 · 변경 전후 · 운영. 개선 후보 규칙 7개(§4-4)는 두 데이터를 다 봐야 해서 여기서 계산한다.
   색은 토큰만(tok) — hex 금지(R-jshex). 글자·간격은 css/ds.css §v3 끝 .ad-* 부품. */
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
  function sec(title, body, desc, id) {
    return '<div class="ad-sec"' + (id ? ' id="' + id + '"' : '') + '><h2 class="ad-h2">' + esc(title) + '</h2>' +
      (desc ? '<p class="ad-desc">' + desc + '</p>' : '') + body + '</div>';
  }
  function table(head, rows, cls) {
    return '<div class="ad-tw"><table class="ad-table' + (cls ? ' ' + cls : '') + '"><thead><tr>' + head.map(function (h) {
      return '<th scope="col"' + (h.num ? ' class="num"' : '') + '>' + (h.sort ? '<button type="button" class="ad-sort" data-sort="' + h.sort + '">' + esc(h.t) + '</button>' : esc(h.t)) + '</th>';
    }).join('') + '</tr></thead><tbody>' + (rows.join('') || '<tr><td colspan="' + head.length + '" class="ad-empty">아직 기록이 없어요</td></tr>') + '</tbody></table></div>';
  }
  function td(v, isNum, extra) { return '<td' + (isNum ? ' class="num"' : '') + (extra || '') + '>' + v + '</td>'; }
  function hotelOf(pid) { return (S && S.hotels && S.hotels[pid]) || null; }
  function slugMap() {
    if (slugMap.m) return slugMap.m;
    var m = {}; Object.keys((S && S.hotels) || {}).forEach(function (p) { m[S.hotels[p][1]] = p; });
    return (slugMap.m = m);
  }
  function urlLabel(u) {
    var mm = /^\/hotels\/([^/?#]+)/.exec(u || '');
    if (mm) { var p = slugMap()[mm[1]] || (mm[1].indexOf('ChIJ') === 0 ? mm[1] : null), h = p && hotelOf(p); if (h) return h[0]; }
    return u;
  }
  function win() { return (A && A.ga && A.ga.days && A.ga.days[WIN]) || null; }

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
    return { tone: late ? 'danger' : 'safe', v: md(b.at) + (late ? ' · 36시간 넘음' : ''), s: (b.size_mb != null ? b.size_mb + 'MB · ' : '') + 'R2 ' + num(b.count) + '개' };
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
    return { tone: old ? 'warning' : 'safe', v: '기준 ' + (S.asof || '—'), s: '빌드 ' + md(S.built_at) + ' · ' + esc(S.commit || '') };
  }
  function clarityLate() {
    var c = A && A.clarity; if (!c || !c.last_day) return !!A;
    return (Date.now() - new Date(c.last_day + 'T09:00:00+09:00').getTime()) / 864e5 >= 2;
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
    var g90 = A && A.ga && A.ga.days && A.ga.days['90'];
    if (g90 && S) {
      var miss = g90.hotels.slice(0, 40).filter(function (h) { var x = hotelOf(h.pid); return x && !x[2] && h.views > 0; });
      if (miss.length) add(miss.reduce(function (s, h) { return s + h.views; }, 0) * 0.5, '조회 많은 호텔에 제휴 링크가 없어요 (' + miss.length + '곳)',
        '세시간전 링크 만들기: ' + miss.slice(0, 6).map(function (h) { return hotelOf(h.pid)[0]; }).join(' · ') + (miss.length > 6 ? ' 외' : ''), 'ux');
    }
    var g28 = A && A.ga && A.ga.days && A.ga.days['28'];
    if (g28) {
      var f = g28.funnel, pv = f.prev || {};
      [['scroll90', '90% 스크롤'], ['tab_click', '탭 클릭'], ['cta_click', '가격 버튼 클릭']].forEach(function (st) {
        var a = ratio(f[st[0]], f.detail_sessions), b = ratio(pv[st[0]], pv.detail_sessions);
        if (a != null && b != null && b - a >= 0.03 && pv.detail_sessions >= 100)
          add(f.detail_sessions * (b - a) * 10, '상세 깔때기 ' + st[1] + ' 단계가 줄었어요', '28일 ' + pct(a, 1) + ' ← 앞 28일 ' + pct(b, 1), 'ux');
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

  // ───────────── 현황 ─────────────
  function cell(label, st) {
    return '<div class="is-cell"><span class="sl">' + esc(label) + '</span><b class="sv">' + dot(st.tone) + esc(st.v) + '</b>' +
      (st.s ? '<span class="ss">' + st.s + '</span>' : '') + '</div>';
  }
  function ncell(label, v, sub) { return '<div class="is-cell"><span class="sl">' + esc(label) + '</span><b class="sv">' + v + '</b>' + (sub ? '<span class="ss">' + sub + '</span>' : '') + '</div>'; }
  function renderHome() {
    var cnt = (S && S.counts) || {}, db = A && A.db, g = A && A.ga && A.ga.days && A.ga.days['28'];
    var html = '';
    html += sec('상태', '<div class="ad-cells">' + cell('주간 배치', batchState()) + cell('DB 백업', backupState()) +
      cell('운영 감시', healthState()) + cell('사이트 빌드', buildState()) + '</div>');
    var hs = db && db.hotels, showN = hs ? (hs.active || 0) + (hs.watch || 0) : (cnt.active || 0) + (cnt.watch || 0);
    var hsub = hs ? ['active', 'watch', 'new', 'pending', 'hidden', 'closed'].map(function (k) { return k + ' ' + num(hs[k] || 0); }).join(' · ')
      : 'active ' + num(cnt.active) + ' · watch ' + num(cnt.watch) + ' (빌드 기준)';
    var cta = null, agoda = 0;
    if (g) (g.events || []).forEach(function (e) { if (e.name === 'check_price_click') { cta = e.count; agoda = (e.by.partner && e.by.partner.agoda) || 0; } });
    html += sec('숫자', '<div class="ad-cells ad-nums">' +
      ncell('사이트 노출 호텔', num(showN), hsub) +
      ncell('상세 페이지', num(cnt.detail), '실망 확률 노출 ' + num(cnt.scored)) +
      ncell('제휴 링크', num(cnt.affiliate_detail) + '곳', '상세의 ' + pct(ratio(cnt.affiliate_detail, cnt.detail))) +
      ncell('사이트 평가 리뷰', db ? num(db.reviews_site) : '—', db && db.analyzed_v5 != null ? 'v5 분석 ' + num(db.analyzed_v5) : 'VM 집계 없음') +
      ncell('28일 세션', g ? num(g.sessions) : '—', g ? '사용자 ' + num(g.users) : 'VM 집계 없음') +
      ncell('28일 가격 버튼 클릭', cta == null ? '—' : num(cta), cta == null ? 'VM 집계 없음' : '아고다 ' + num(agoda) + ' · 구글 ' + num(cta - agoda)) + '</div>');
    if (g) {
      var ch = ratio(g.sessions - g.prev_sessions, g.prev_sessions);
      html += sec('28일 세션', '<div class="ad-chart"><canvas id="ad-chart-28" aria-label="최근 28일 일별 세션 선 그래프" role="img"></canvas></div>' +
        '<p class="ad-foot">지난 28일 ' + num(g.prev_sessions) + ' 대비 <b>' + (ch == null ? '—' : (ch >= 0 ? '+' : '') + Math.round(ch * 100) + '%</b>') + ' · 내부 트래픽 제외(GA 필터)</p>',
        '선 = 사이트 세션, 점선 = 상세 페이지 세션');
    }
    var cs = candidates().slice(0, 5);
    html += sec('지금 고칠 것', cs.length ? '<ol class="ad-todo">' + cs.map(function (x) {
      return '<li><b class="ad-todo-t">' + esc(x.title) + '</b><span class="ad-todo-b">' + esc(x.basis) + '</span>' +
        '<button type="button" class="btn-text btn-text--sm" data-go="' + x.tab + '">' + { ux: 'UX 지표에서 보기', ops: '운영 탭에서 보기', chg: '변경 전후에서 보기' }[x.tab] + '</button></li>';
    }).join('') + '</ol>' : '<p class="ad-note">' + (A ? '규칙에 걸린 후보가 없어요' : 'VM 집계가 들어오면 후보를 뽑아요') + '</p>', '데이터에서 규칙 7개로 뽑은 후보, 영향 큰 순 5개');
    $('ad-home').innerHTML = html;
    drawChart();
  }
  function drawChart() {
    var el = $('ad-chart-28');
    if (!el || !window.Chart || !A || !A.ga.daily) return;
    var d = A.ga.daily.slice(-28), ink = tok('--ink'), ink3 = tok('--ink-3'), line = tok('--line');
    if (drawn.c28) drawn.c28.destroy();
    drawn.c28 = new Chart(el, {
      type: 'line',
      data: { labels: d.map(function (x) { return x.day.slice(5); }), datasets: [
        { label: '세션', data: d.map(function (x) { return x.sessions; }), borderColor: ink, backgroundColor: ink, borderWidth: 2, pointRadius: 0, tension: .25 },
        { label: '상세 세션', data: d.map(function (x) { return x.detail_sessions; }), borderColor: ink3, backgroundColor: ink3, borderWidth: 1.5, borderDash: [4, 3], pointRadius: 0, tension: .25 }] },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false }, ticks: { color: ink3, maxTicksLimit: 7, font: { size: 13 } } },
          y: { beginAtZero: true, grid: { color: line }, ticks: { color: ink3, precision: 0, font: { size: 13 } } } } }
    });
  }

  // ───────────── UX 지표 ─────────────
  var CH_NAME = { naver: '네이버', direct: '직접(북마크·앱)', organic: '검색(구글 등)', social: '소셜(유튜브 등)', other: '기타 링크' };
  var hotelSort = { k: 'views', d: -1 }, hotelOnlyNoLink = false, hotelAll = false, claritySort = { k: 'sessions', d: -1 }, openEv = {};
  function renderUx() {
    var g = win(), html = '';
    html += '<div class="ad-chips" role="group" aria-label="기간">' + ['7', '28', '90'].map(function (w) {
      return '<button type="button" class="chip-view' + (w === WIN ? ' is-on' : '') + '" data-win="' + w + '" aria-pressed="' + (w === WIN) + '">' + w + '일</button>';
    }).join('') + '</div>';
    if (!g) { $('ad-ux').innerHTML = html + '<p class="ad-note">VM 집계(GA4)가 없어 이 탭을 그릴 수 없어요. ' + esc(A_ERR) + '</p>'; return; }
    var tot = g.sessions || 0;
    html += sec('유입 — 첫 페이지', table([{ t: '착지' }, { t: '세션', num: 1 }, { t: '참여율', num: 1 }, { t: '평균 시간', num: 1 }],
      g.landing.map(function (r) { return '<tr>' + td(esc(r.group)) + td(num(r.sessions), 1) + td(pct(r.engaged_rate), 1) + td(num(r.avg_sec) + '초', 1) + '</tr>'; })),
      '세션 ' + num(tot) + ' · 사용자 ' + num(g.users) + ' · 앞 ' + WIN + '일 ' + num(g.prev_sessions));
    html += sec('유입 채널', table([{ t: '채널' }, { t: '세션', num: 1 }, { t: '비중', num: 1 }],
      g.channel.map(function (r) { return '<tr>' + td(esc(CH_NAME[r.name] || r.name)) + td(num(r.sessions), 1) + td(pct(ratio(r.sessions, tot)), 1) + '</tr>'; })));
    var f = g.funnel, pv = f.prev || {};
    var steps = [['상세 세션', 'detail_sessions'], ['90% 스크롤', 'scroll90'], ['탭 클릭', 'tab_click'], ['가격 버튼 클릭', 'cta_click']];
    html += sec('상세 깔때기', '<ol class="ad-funnel">' + steps.map(function (s) {
      var r = ratio(f[s[1]], f.detail_sessions), rp = ratio(pv[s[1]], pv.detail_sessions);
      return '<li><div class="ad-fl"><b>' + esc(s[0]) + '</b><span>' + num(f[s[1]]) + '세션 · ' + pct(r) + '</span></div>' +
        '<div class="ad-bar"><i style="width:' + Math.max(0, Math.min(100, (r || 0) * 100)).toFixed(1) + '%"></i></div>' +
        '<span class="ad-fp">앞 ' + WIN + '일 ' + num(pv[s[1]]) + '세션 · ' + pct(rp) + '</span></li>';
    }).join('') + '</ol><p class="ad-foot">가격 버튼 도착지: 아고다 ' + num(f.cta_agoda) + '세션 · 구글 ' + num(f.cta_google) + '세션</p>',
      '상세 페이지를 본 세션 중 각 행동이 있었던 비율');
    html += sec('이벤트', table([{ t: '이벤트' }, { t: '건수', num: 1 }, { t: '세션', num: 1 }, { t: '세션 대비', num: 1 }],
      g.events.filter(function (e) { return e.count > 0; }).map(function (e) {
        var dims = Object.keys(e.by || {}), open = openEv[e.name];
        var row = '<tr' + (dims.length ? ' class="ad-has-sub"' : '') + '>' + td(dims.length ? '<button type="button" class="ad-exp" data-ev="' + esc(e.name) + '" aria-expanded="' + !!open + '">' + esc(e.name) + '</button>' : esc(e.name)) +
          td(num(e.count), 1) + td(num(e.sessions), 1) + td(pct(ratio(e.sessions, tot), 1), 1) + '</tr>';
        if (open) dims.forEach(function (dm) {
          Object.keys(e.by[dm]).sort(function (a, b) { return e.by[dm][b] - e.by[dm][a]; }).slice(0, 12).forEach(function (v) {
            row += '<tr class="ad-sub">' + td(esc(dm) + ' · ' + esc(v)) + td(num(e.by[dm][v]), 1) + td('', 1) + td('', 1) + '</tr>';
          });
        });
        return row;
      })), '이벤트 이름을 누르면 맞춤 측정기준(placement·partner·tab·block·group·method)으로 나눠 봐요. 11-05 등록이라 그 전은 집계 안 돼요');
    html += renderClarity();
    html += renderHotels(g);
    html += sec('결과 없는 검색어', table([{ t: '검색어' }, { t: '횟수', num: 1 }],
      (g.search_noresult || []).map(function (t) { return '<tr>' + td(esc(t.term)) + td(num(t.n), 1) + '</tr>'; })), '최근 ' + WIN + '일 상위 20 — 있는 호텔이면 token_dict.py에 별칭 추가');
    $('ad-ux').innerHTML = html;
  }
  function renderClarity() {
    var c = A && A.clarity;
    if (!c) return sec('Clarity (URL별)', '<p class="ad-note">Clarity 집계가 없어요</p>');
    var k = claritySort.k, d = claritySort.d;
    var rows = c.urls.filter(function (u) { return !u.rest; }).slice().sort(function (a, b) {
      var x = k === 'quickback' ? ratio(a.quickback_sessions, a.sessions) : a[k], y = k === 'quickback' ? ratio(b.quickback_sessions, b.sessions) : b[k];
      return ((x == null ? -1 : x) - (y == null ? -1 : y)) * d;
    }).concat(c.urls.filter(function (u) { return u.rest; }));
    return sec('Clarity (URL별, ' + c.days + '일 합)', table([{ t: '페이지' }, { t: '세션', num: 1, sort: 'c:sessions' }, { t: '데드 클릭', num: 1, sort: 'c:dead' },
      { t: '레이지', num: 1, sort: 'c:rage' }, { t: '퀵백', num: 1, sort: 'c:quickback' }, { t: '스크롤', num: 1, sort: 'c:scroll' }, { t: '활동', num: 1, sort: 'c:engage_sec' }],
      rows.map(function (u) {
        return '<tr>' + td('<span title="' + esc(u.url) + '">' + esc(urlLabel(u.url)) + '</span>') + td(num(u.sessions), 1) + td(num(u.dead), 1) + td(num(u.rage), 1) +
          td(pct(ratio(u.quickback_sessions, u.sessions)), 1) + td(u.scroll == null ? '—' : Math.round(u.scroll) + '%', 1) + td(u.engage_sec == null ? '—' : num(u.engage_sec) + '초', 1) + '</tr>';
      }), 'ad-t-wide'), '수집 ' + c.n_days + '일 · 마지막 ' + esc(c.last_day || '—') + ' · 열 머리를 누르면 정렬, 퀵백 = 퀵백 있었던 세션 비율. 기간 칩과 상관없이 최근 7일');
  }
  function renderHotels(g) {
    if (!S) return '';
    var k = hotelSort.k, d = hotelSort.d;
    var rows = g.hotels.filter(function (h) { var x = hotelOf(h.pid); return x && (!hotelOnlyNoLink || !x[2]); })
      .sort(function (a, b) { return (a[k] - b[k]) * d || b.views - a.views; });
    var n = rows.length, show = hotelAll ? rows : rows.slice(0, 30);
    return sec('호텔별 접속 (' + WIN + '일)', '<div class="ad-chips"><button type="button" class="chip-filter chip-filter--sm' + (hotelOnlyNoLink ? ' is-on' : '') + '" data-nolink aria-pressed="' + hotelOnlyNoLink + '">링크 없는 곳만</button></div>' +
      table([{ t: '호텔' }, { t: '조회', num: 1, sort: 'h:views' }, { t: '사용자', num: 1, sort: 'h:users' }, { t: '가격 버튼', num: 1, sort: 'h:cta' }],
        show.map(function (h) {
          var x = hotelOf(h.pid);
          return '<tr>' + td('<a href="/hotels/' + esc(x[1]) + '" target="_blank" rel="noopener">' + esc(x[0]) + '</a>' + (x[2] ? '' : ' <span class="tag">링크 없음</span>')) +
            td(num(h.views), 1) + td(num(h.users), 1) + td(num(h.cta), 1) + '</tr>';
        }), 'ad-t-hotels') +
      (n > show.length ? '<button type="button" class="btn-gray btn-block ad-more" data-hall>호텔 ' + num(n) + '곳 모두 보기</button>' : ''),
      '상세 ' + num(n) + '곳 · 기본 조회순, 열 머리를 누르면 정렬');
  }

  // ───────────── 변경 전후 ─────────────
  var VD = { up: ['safe', '개선'], down: ['danger', '악화'], same: ['', '차이 없음'], hold: ['', '아직 모름(표본 적음)'] };
  function baList() {
    var ba = {}; ((A && A.changes && A.changes.before_after) || []).forEach(function (x) { ba[x.commit] = x; });
    return ((S && S.changes) || []).map(function (c) { return { c: c, ba: ba[c.commit] || null }; });
  }
  function renderChg() {
    var list = baList(), html = '';
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
    }).join('') + '</ol>' : '<p class="ad-note">scripts/changes.json에 기록된 변경이 없어요</p>',
      '배포일 전 14일(배포일 제외)과 다음 날부터 14일을 비교해요. 한쪽이라도 분모 100 미만이면 보류, 차이 3%p 이상이고 표준오차 합보다 크면 개선·악화');
    var pend = (S && S.pending) || [];
    html += sec('대기 중 ' + pend.length + '건', pend.length ? '<ul class="ad-todo">' + pend.map(function (p) {
      return '<li><b class="ad-todo-t">' + esc(p.title) + '</b>' + (p.why ? '<span class="ad-todo-w">' + esc(p.why) + '</span>' : '') +
        '<span class="ad-todo-b">' + esc(p.from || '') + (p.needs ? ' · 확인: ' + esc(p.needs) : '') + '</span></li>';
    }).join('') + '</ul>' : '<p class="ad-note">대기 항목이 없어요</p>', '설계서에서 옮긴 아직 안 한 일 — scripts/changes.json pending');
    var last = list.length ? list.map(function (x) { return x.c.date; }).sort().pop() : null;
    html += sec('다음 측정일', '<p class="ad-big">' + (last ? esc(addDays(last, 14)) : '—') + '</p>', last ? '가장 최근 변경(' + esc(last) + ') + 14일' : '');
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
    var t = e.target.closest('[data-tab],[data-go],[data-win],[data-sort],[data-ev],[data-nolink],[data-hall]');
    if (!t) return;
    if (t.hasAttribute('data-tab') || t.hasAttribute('data-go')) {   // 탭을 바꾸면 새 탭 맨 위(탭 줄 바로 아래)부터
      var tabs = document.querySelector('.ad-tabs'), y0 = window.scrollY;
      show(t.getAttribute('data-tab') || t.getAttribute('data-go'), true);
      var top = tabs.parentNode.querySelector('.ad-made').getBoundingClientRect().bottom + window.scrollY - (parseFloat(tok('--sticky-top')) || 56);
      if (y0 > top) window.scrollTo(0, top);
      return;
    }
    if (t.hasAttribute('data-win')) { WIN = t.getAttribute('data-win'); hotelAll = false; return renderUx(); }
    if (t.hasAttribute('data-ev')) { var n = t.getAttribute('data-ev'); openEv[n] = !openEv[n]; return renderUx(); }
    if (t.hasAttribute('data-nolink')) { hotelOnlyNoLink = !hotelOnlyNoLink; return renderUx(); }
    if (t.hasAttribute('data-hall')) { hotelAll = true; return renderUx(); }
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

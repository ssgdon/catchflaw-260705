/* 캐치플로 검색 자동완성 (홈 #hero-q + search.html #q 공용) — §7-c
   의존: jQuery, data/search_index.js(window.CF_IDX) — 소리 키 매칭은 이 파일 안(search-key.js 불필요, 2026-11-04)
   window.CF_AREAS(인기 지역), window.CF_SB(Supabase INSERT)
   각 검색창은 data-ac-href 로 상세 링크 접두사(홈="./hotels/", search="./hotels/") 지정.
   상세 주소 = 접두사 + 슬러그(u, SEO-CRAWL §2 — CF_IDX·HOTELS 항목의 u). u가 없으면 pid(옛 주소, 301로 이어짐). */
(function () {
  'use strict';

  // 등급 색은 토큰 변수로(--safe·--warning·--danger), 없으면 메타 회색

  function toast(msg) { CF.toast(msg); }   // 토스트 1벌(js/backnav.js)

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* ── 소리 키 퍼지 매칭 (SEARCH-2611, 2026-11-04) ──
     예전엔 빌드가 호텔마다 표기 조합(하카타/하까다/hakata…)을 미리 만들어 두고 그중 하나와 맞아야 찾았다 — 상한 40개에서 73곳이 잘렸고,
     만들지 않은 표기(리졸↔리솔·치구시↔치쿠시·에키↔역·2↔Ⅱ)는 늘 실패했다. 이제는 호텔 200곳 이름을 검색할 때마다 직접 비교한다.
     ① 정규화: NFKC 소문자, 한글↔로마자·숫자 경계에서 띄우기, 같은 뜻 묶기(에키·스테이션→역, 에키마에→역앞, ii→2), 불용어(호텔·후쿠오카·더·숙소) 빼기
     ② 소리 키: 한글은 자모로 풀고 예사·된·거센소리(ㄱㄲㅋ·ㄷㄸㅌ·ㅂㅃㅍ·ㅈㅉㅊ·ㅅㅆ)와 ㅐ/ㅔ·ㅒ/ㅖ/ㅔ·ㅙ/ㅚ/ㅞ를 한 소리로, 로마자는 tsu/tu·shi/si·chi/ti·장음을 한 소리로
     ③ 토큰마다: 같음 3 · 앞부분 일치 2 · 오타(길이의 1/4까지 편집거리, 4자모는 낱말 전체만) 1.5 · 안에 포함 1, 드문 말일수록 무겁게(idf) — 쿼리 토큰 전부가 맞으면 '찾음', 절반 이상이면 '혹시'
     ④ 붙여 쓴 쿼리는 이름 전체(공백 없는 소리 키)에 들어 있으면 찾음, 이름과 똑같으면 가산. 초성(ㄷㅁㅇ)은 이름 초성에 들어 있으면 찾음
     호텔 토큰 = 이름(t)·영문(en) + 파이프라인 토큰(tok, pipeline/token_dict) + 사람이 확인한 별칭(al, scripts/search_aliases.json).
     회귀 검사: node scripts/check_search.js (실검색 실패어 scripts/search_cases.json). 콘솔: CFAutocomplete.selfTest() */
  var CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ', JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ';
  var JONG = ['', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ', 'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'];
  var FOLD = { 'ㄲ': 'ㄱ', 'ㅋ': 'ㄱ', 'ㄸ': 'ㄷ', 'ㅌ': 'ㄷ', 'ㅃ': 'ㅂ', 'ㅍ': 'ㅂ', 'ㅉ': 'ㅈ', 'ㅊ': 'ㅈ', 'ㅆ': 'ㅅ',
               'ㅐ': 'ㅔ', 'ㅒ': 'ㅔ', 'ㅖ': 'ㅔ', 'ㅙ': 'ㅞ', 'ㅚ': 'ㅞ' };
  var SYN = { 'eki': '역', 'station': '역', 'ekimae': '역앞', 'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', '駅': '역', '駅前': '역앞' };
  var STOPW = ['호텔', 'hotel', 'hotels', 'ホテル', '후쿠오카', 'fukuoka', '福岡', '더', 'the', '숙소', 'by', '바이', 'and', '앤'];
  var SEP = /[\s\-·・.,'"&()~!?\/|:;\[\]_+]+/;

  function fold(s) {   // 한글 음절 → 자모 소리 키, 낱자모·로마자도 같은 규칙으로
    var o = '', i, c, t, ch;
    for (i = 0; i < s.length; i++) {
      c = s.charCodeAt(i); ch = s.charAt(i);
      if (c >= 0xAC00 && c <= 0xD7A3) {
        t = c - 0xAC00;
        var a = CHO.charAt(Math.floor(t / 588)), b = JUNG.charAt(Math.floor((t % 588) / 28)), z = JONG[t % 28];
        o += (FOLD[a] || a) + (FOLD[b] || b) + (z ? (FOLD[z] || z) : '');
      } else o += FOLD[ch] || ch;
    }
    if (/[a-z]/.test(o)) o = o.replace(/tsu/g, 'tu').replace(/shi/g, 'si').replace(/chi/g, 'ti').replace(/ou/g, 'o').replace(/oo/g, 'o').replace(/uu/g, 'u').replace(/nn/g, 'n');
    return o;
  }
  function cho(s) {    // 이름의 초성 줄(ㄷㅁㅇ 검색용)
    var o = '';
    for (var i = 0; i < s.length; i++) { var c = s.charCodeAt(i); if (c >= 0xAC00 && c <= 0xD7A3) o += CHO.charAt(Math.floor((c - 0xAC00) / 588)); }
    return o;
  }
  var STOP = null;
  function words(s) {   // 글 → 정규화한 낱말(접기 전). 한글 덩어리 안의 '호텔·후쿠오카'와 같은 뜻 말도 여기서 정리
    s = String(s || '').normalize('NFKC').toLowerCase().replace(/\(.*?\)/g, ' ');
    s = s.replace(/에키마에|역마에|역 앞/g, ' 역앞 ').replace(/스테이션/g, ' 역 ').replace(/에키(?!마)/g, ' 역 ');
    s = s.replace(/([가-힣]+)/g, ' $1 ').replace(/([0-9]+)/g, ' $1 ');           // 한글 ↔ 로마자·숫자·가나 경계
    s = s.replace(/([가-힣]{2,})(호텔스|호텔|후쿠오카)/g, '$1 ').replace(/(호텔스|호텔|후쿠오카)([가-힣]{2,})/g, ' $2');
    return s.split(SEP).filter(Boolean).map(function (w) { return SYN[w] || w; });
  }
  function toks(s) {
    if (!STOP) { STOP = {}; STOPW.forEach(function (w) { STOP[fold(w)] = 1; }); }
    return words(s).map(fold).filter(function (t) { return t && !STOP[t]; });
  }

  var PREP = null, DICT = null, DICT_MAX = 0;
  function prep() {   // CF_IDX를 처음 쓸 때 한 번: 호텔마다 소리 키 토큰·이름 전체 키·초성
    var idx = window.CF_IDX || [];
    if (PREP && PREP.n === idx.length) return PREP.list;
    DICT = {}; DICT_MAX = 0;
    var list = idx.map(function (it) {
      var set = {}, full = [], add = function (t) { if (t && !set[t]) { set[t] = 1; DICT[t] = 1; if (t.length > DICT_MAX) DICT_MAX = t.length; } };
      var main = toks(it.t);
      main.forEach(add);
      [it.en].concat(it.al || []).forEach(function (n) { var tk = toks(n); tk.forEach(add); if (tk.length) full.push(tk.join('')); });
      (it.tok || []).forEach(function (t) { var f = fold(String(t).toLowerCase()); if (!STOP[f]) add(f); });
      full.unshift(main.join(''));
      return { it: it, tk: Object.keys(set), main: main, full: full, cho: cho(it.t.replace(/호텔스|호텔|후쿠오카|숙소/g, '')) };
    });
    PREP = { n: idx.length, list: list };
    return list;
  }
  function segment(k) {   // 붙여 쓴 덩어리 → 호텔 토큰 사전 최장일치 조각(없는 부분은 이어 붙여 한 조각)
    var out = [], buf = '', i = 0;
    while (i < k.length) {
      var hit = 0;
      for (var j = Math.min(k.length, i + DICT_MAX); j > i + 2; j--) { if (DICT[k.slice(i, j)]) { hit = j; break; } }
      if (hit) { if (buf) { out.push(buf); buf = ''; } out.push(k.slice(i, hit)); i = hit; }
      else { buf += k.charAt(i); i++; }
    }
    if (buf) out.push(buf);
    return out.filter(function (t) { return !STOP[t]; });
  }
  function qTokens(q) {
    prep();
    var out = [];
    toks(q).forEach(function (t) { (t.length >= 9 && !DICT[t] ? segment(t) : [t]).forEach(function (x) { out.push(x); }); });
    return out;
  }
  function lev(a, b, max) {   // 편집거리(max 넘으면 max+1)
    if (Math.abs(a.length - b.length) > max) return max + 1;
    var p = [], c, i, j;
    for (j = 0; j <= b.length; j++) p[j] = j;
    for (i = 1; i <= a.length; i++) {
      c = [i]; var lo = i;
      for (j = 1; j <= b.length; j++) { c[j] = Math.min(p[j] + 1, c[j - 1] + 1, p[j - 1] + (a.charAt(i - 1) === b.charAt(j - 1) ? 0 : 1)); if (c[j] < lo) lo = c[j]; }
      if (lo > max) return max + 1;
      p = c;
    }
    return p[b.length];
  }
  function tokScore(qt, tk) {   // 쿼리 토큰 1개의 최고 점수: 같음 3 · 앞부분 2 · 오타 1.5 · 포함 1 · 없음 0
    var best = 0, L = qt.length, lim = Math.floor(L / 4);
    for (var i = 0; i < tk.length; i++) {
      var t = tk[i];
      if (t === qt) return 3;
      if (L >= 2 && t.indexOf(qt) === 0) { best = 2; continue; }
      if (best < 1.5 && L >= 4 && lim && (lev(qt, t, lim) <= lim || (L >= 5 && t.length > L && lev(qt, t.slice(0, L), lim) <= lim))) { best = 1.5; continue; }   // 4자모(니코↔닛코)는 낱말 전체만, 5자모부터 앞부분도(메이가 마이스테이스에 붙지 않게)
      if (best < 1 && L >= 4 && t.indexOf(qt) > 0) best = 1;
    }
    return best;
  }
  function scoreAll(q) {
    if (!q || !(window.CF_IDX || []).length) return [];
    var list = prep(), qt = qTokens(q), qc = qt.join(''), res = [], i, c;
    var qcho = /^[ㄱ-ㅎ\s]+$/.test(q) ? q.replace(/\s+/g, '') : '';
    if (!qt.length && !qcho) return [];
    // 토큰마다 맞는 호텔 수(df) → 드문 말(브랜드)일수록 무겁게: '라이브맥스 에키마에'에서 '역앞'보다 '라이브맥스'
    var sc = list.map(function (h) { return qt.map(function (t) { return tokScore(t, h.tk); }); }), df = qt.map(function () { return 0; });
    sc.forEach(function (row) { row.forEach(function (v, k) { if (v) df[k]++; }); });
    var idf = df.map(function (d) { return Math.log(1 + list.length / Math.max(d, 1)); });
    for (i = 0; i < list.length; i++) {
      var h = list[i], s = 0, hit = 0, fs = 0, ch = false, v;
      for (c = 0; c < qt.length; c++) { v = sc[i][c]; if (v) { hit++; s += v * idf[c]; } }
      for (c = 0; c < h.full.length; c++) { if (h.full[c] === qc && qc.length >= 2) { fs = 10; break; } if (qc.length >= 4 && h.full[c].indexOf(qc) >= 0) fs = Math.max(fs, 4); }
      if (qcho.length >= 2 && h.cho.indexOf(qcho) >= 0) ch = true;
      var r = qt.length ? hit / qt.length : 0;
      if (!r && !fs && !ch) continue;
      var cov = 0;   // 호텔 이름 토큰 중 쿼리가 덮은 비율 — '아파호텔 하카타 에키마에'가 '…3초메'보다 앞에 오게
      if (h.main.length) { for (c = 0; c < h.main.length; c++) { for (var d = 0; d < qt.length; d++) { if (tokScore(qt[d], [h.main[c]]) >= 1.5) { cov++; break; } } } cov /= h.main.length; }
      res.push({ it: h.it, strong: r === 1 || fs > 0 || ch, r: r, s: s + fs + (ch ? 3 : 0) + cov + Math.min(h.it.pop || 0, 20) * 0.1 });
    }
    res.sort(function (x, y) { return (y.strong - x.strong) || (y.r - x.r) || (y.s - x.s); });
    return res;
  }
  // 찾음(쿼리 토큰 전부 일치·이름 전체에 포함·초성) 상위 N
  function match(q, limit) {
    return scoreAll(q).filter(function (r) { return r.strong; }).slice(0, limit || 8).map(function (r) { return r.it; });
  }
  // 목록 필터용: 매칭된 id 집합 (search.html run에서 사용)
  function matchIds(q) {
    return match(q, 9999).map(function (it) { return it.id; });
  }
  // 찾음 0건일 때 '혹시 이 호텔인가요?' — 쿼리 토큰 절반 이상 일치, 없으면 소리 키 바이그램 유사도 ≥0.45, 최대 3
  function bigrams(s) { var o = {}, n = 0; for (var i = 0; i < s.length - 1; i++) { var g = s.substr(i, 2); o[g] = (o[g] || 0) + 1; n++; } return { g: o, n: n }; }
  function dice(a, b) {
    if (!a.n || !b.n) return 0;
    var inter = 0; for (var g in a.g) if (b.g[g]) inter += Math.min(a.g[g], b.g[g]);
    return 2 * inter / (a.n + b.n);
  }
  function suggest(q, limit) {
    if (!q) return [];
    var qt = qTokens(q);
    var part = scoreAll(q).filter(function (r) { return !r.strong && r.r >= 0.5 && qt.length >= 2; });
    if (part.length) return part.slice(0, limit || 3).map(function (r) { return r.it; });
    var bq = bigrams(qt.join('')), out = [];
    if (!bq.n) return [];
    prep().forEach(function (h) {
      var best = 0;
      h.full.forEach(function (f) { var d = dice(bq, bigrams(f)); if (d > best) best = d; });
      if (best >= 0.45) out.push({ it: h.it, s: best });
    });
    out.sort(function (x, y) { return y.s - x.s || (y.it.pop || 0) - (x.it.pop || 0); });
    return out.slice(0, limit || 3).map(function (r) { return r.it; });
  }
  // 콘솔 자가검증: window.CFAutocomplete.selfTest() — 전체 회귀는 node scripts/check_search.js
  function selfTest() {
    var cases = [
      ['톈진오리엔탈호텔', /오리엔탈 익스프레스.*텐진/],
      ['하카타 도미인', /도미 ?인/],
      ['니시테츠그랜드', /니시테츠 그랜드/],
      ['솔라리아', /솔라리아/],
      ['ㄷㅁㅇ', /도미 ?인/],
      ['Hyatt', /하얏트/],
      ['리졸 트리니티 하카타', /리솔 트리니티/],
      ['더크로스라이프하카타텐진', /크로스라이프 하카타 텐진/]
    ];
    var ok = true;
    cases.forEach(function (c) {
      var top = match(c[0], 1)[0], pass = !!(top && c[1].test(top.t));
      if (!pass) ok = false;
      // eslint-disable-next-line no-console
      console.log((pass ? '[OK]  ' : '[FAIL]') + ' ' + c[0] + ' → ' + (top ? top.t : '(없음)'));
    });
    // eslint-disable-next-line no-console
    console.log(ok ? 'search-ac selfTest: ALL PASS' : 'search-ac selfTest: FAILED');
    return ok;
  }

  // 미매칭 → 분석 요청 (Supabase analysis_requests · anon INSERT RLS — engage.js 피드백과 동일 패턴). 검색 결과 없음 화면의 '분석 요청하기'도 이 함수
  function requestAnalysis(q, quiet, place) {   // quiet = 부른 쪽이 완료 화면을 따로 그림(검색 결과 없음 화면) → 토스트 생략. place = 구글 장소(우리 목록에 없는 호텔) → 이름·장소 ID를 같이. 보냈으면 true
    if (window.CF_SB && window.CF_SB.url && window.CF_SB.key) {
      fetch(window.CF_SB.url + '/rest/v1/analysis_requests', {
        method: 'POST',
        headers: { 'apikey': window.CF_SB.key, 'Authorization': 'Bearer ' + window.CF_SB.key,
          'Content-Type': 'application/json', 'Prefer': 'return=minimal' },
        body: JSON.stringify({ hotel_name: place ? place.name + ' · 검색어 ' + q + ' · ' + place.id : q, source: 'search_miss' })
      }).catch(function () {});
      if (!quiet) toast('요청했어요. 분석되면 사이트에 올라와요');
      return true;
    }
    toast('분석 요청은 준비 중이에요');
    return false;
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
    for (var i = 0; i < H.length; i++) if (H[i].id === id) return { id: H[i].id, t: H[i].name, u: H[i].u };
    return null;
  }
  function resolveUrl(v) {
    var s = String(v || '').trim(), m, h;
    if (/maps\.app\.goo\.gl|goo\.gl\/maps|[?&]cid=\d/i.test(s)) return { kind: 'short' };
    if ((m = s.match(/(ChIJ[A-Za-z0-9_-]{10,})/)) && (h = byId(m[1]))) return { hit: h };
    if ((m = s.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/)) && (h = nearest(+m[1], +m[2], 80))) return { hit: { id: h.id, t: h.name, u: h.u } };
    var name = null;
    if ((m = s.match(/\/place\/([^\/@?#]+)/))) name = m[1];
    else if ((m = s.match(/[?&](?:q|query)=([^&#]+)/)) && !/^-?\d+\.\d+,-?\d+\.\d+$/.test(decodeURIComponent(m[1]))) name = m[1];
    if (name) {
      try { name = decodeURIComponent(name.replace(/\+/g, ' ')); } catch (e) { name = name.replace(/\+/g, ' '); }
      var top = match(name, 1)[0];
      if (top) return { hit: { id: top.id, t: top.t, u: top.u } };
    }
    if ((m = s.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/)) && (h = nearest(+m[1], +m[2], 40))) return { hit: { id: h.id, t: h.name, u: h.u } };
    return { kind: 'none' };
  }

  /* ── 구글 장소 검색으로 한 번 더 (SEARCH-2611) — functions/api/find.js ──
     사이트 안에서 못 찾았을 때만 부른다(검색 결과 없음 화면 · 공유 짧은 링크). 우리 호텔 ID = 구글 장소 ID라 id로 바로 맞추고,
     ID가 다르면(장소 ID 갱신) 25m 안의 우리 호텔. 그래도 아니면 '아직 분석 전' 호텔(other). 실패·키 없음 = null → 화면은 그대로. */
  function remote(q) {
    if (!window.fetch) return Promise.resolve(null);
    var ctl = window.AbortController ? new AbortController() : null, tm = ctl ? setTimeout(function () { ctl.abort(); }, 6000) : 0;
    return fetch('/api/find?q=' + encodeURIComponent(q), ctl ? { signal: ctl.signal } : {})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        clearTimeout(tm);
        if (!j) return null;
        if (j.url) return { url: j.url, ours: [], other: [] };
        var ours = [], other = [], seen = {}, ps = j.places || [];
        // 이름이 검색어와 닮았거나(소리 키 바이그램 0.3 이상) 구글이 딱 1곳만 준 경우만 믿는다 — '방음 좋은 숙소' 같은 말에 아무 호텔이나 붙지 않게
        var bq = bigrams(qTokens(q).join(''));
        ps = ps.filter(function (p) { return ps.length === 1 || dice(bq, bigrams(toks(p.name).join(''))) >= 0.3; });
        ps.forEach(function (p) {
          var h = byId(p.id), n;
          if (!h && p.lat != null && (n = nearest(+p.lat, +p.lng, 25))) h = { id: n.id, t: n.name, u: n.u };
          if (h) { if (!seen[h.id]) { seen[h.id] = 1; ours.push(h); } } else other.push(p);
        });
        return { ours: ours, other: other };
      })
      .catch(function () { clearTimeout(tm); return null; });
  }
  // 링크 → 호텔: 긴 링크는 바로 읽고, 공유 짧은 링크(maps.app.goo.gl·cid)는 /api/find가 리다이렉트를 따라가 준 주소로 다시 읽는다
  function resolveLink(v) {
    var r = resolveUrl(v);
    if (r.kind !== 'short') return Promise.resolve(r);
    return remote(String(v).trim()).then(function (res) { return res && res.url ? resolveUrl(res.url) : { kind: 'short' }; });
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
      return '<a class="ac-item" role="option" data-i="' + i + '" href="' + hrefPrefix + (h.u || h.id) + '">'
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
      if (r.kind === 'short') {   // 공유 짧은 링크: 확인 중 안내 → /api/find로 풀어서 다시 그림
        $box.prop('hidden', false).html('<div class="ac-none">링크를 확인하고 있어요</div>');
        resolveLink(v).then(function (r2) { if ($input.val().trim() !== v) return; paintUrl(r2); });
        return;
      }
      paintUrl(r);
    }
    function paintUrl(r) {
      if (r.hit) {
        var it = (window.CF_IDX || []).filter(function (x) { return x.id === r.hit.id; })[0];   // 동네·실망 확률은 인덱스에서(없을 때만 '분석 준비 중')
        $box.prop('hidden', false).html('<div class="ac-section">링크의 호텔</div>' + hotelRow(it || { id: r.hit.id, u: r.hit.u, t: r.hit.t, p: null, band: null }, 0));
        sel = 0; highlight();
      } else {
        $box.prop('hidden', false).html('<div class="ac-none">' + (r.kind === 'short'
          ? '공유 링크를 읽지 못했어요. 호텔 이름으로 검색해 주세요'
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

  /* ── 조건 검색어 (2026-11-07, changes.json pending '의도 검색어 라우팅') ──
     '방음 좋은 숙소'·'벌레 없는 호텔'·'텐진 가성비'처럼 호텔 이름이 아니라 조건을 찾는 말 → 검색 필터·정렬.
     호텔 이름이 하나도 안 맞을 때만 쓴다(search.html run()). 조건·지역·군말을 다 빼고 조사만 남아야 조건으로 본다 —
     모르는 말이 남으면 null(이름 검색으로 계속). cat = 검색 '불만 적은 항목'(CAT_KEYS 한글 이름), no = '한 번도 없어야'(NO_KEYS) */
  var INTENTS = [
    { re: /방음|조용|소음|시끄|정숙|층간/g, cat: '소음' },
    { re: /깨끗|청결|깔끔|위생|청소/g, cat: '청결' },
    { re: /냄새|담배|금연|흡연|곰팡내/g, cat: '냄새' },
    { re: /넓은 ?방|넓은|넓고|큰 ?방|침대|객실/g, cat: '객실' },
    { re: /친절|직원|응대|서비스/g, cat: '직원' },
    { re: /역세권|역 ?가까운?|역 ?근처|역에서 ?가까운?|교통|접근성|위치/g, cat: '위치' },
    { re: /바퀴 ?벌레|바퀴|벌레/g, no: 'roach' },
    { re: /빈대/g, no: 'bedbug' },
    { re: /안전|치안|보안/g, no: 'safe' },
    { re: /가성비|저렴|싼|싸게|싸고|최저가|값싼/g, sort: 'price' }
  ];
  var INTENT_AREAS = [[/하카타 ?역|하카타/g, 'hakata'], [/텐진|덴진/g, 'tenjin'], [/나카스|캐널 ?시티/g, 'nakasu'], [/기온|오호리/g, 'gion']];
  var INTENT_FILL = /잘 ?되는|좋은|좋고|좋다|괜찮은|있는|없는|없고|적은|적고|많은|되는|하고|하는|숙소|호텔|료칸|후쿠오카|추천|근처|주변|위주|곳|데|중에/g;
  function intent(q) {
    var s = String(q || '').normalize('NFKC').toLowerCase(), r = { cats: [], no: [], sort: '', area: '' }, hit = false;
    if (/https?:/.test(s)) return null;
    // 지역을 먼저 뺀다 — '하카타역 근처'의 '역 근처'가 위치 조건으로 잡히지 않게
    INTENT_AREAS.forEach(function (a) { a[0].lastIndex = 0; if (a[0].test(s)) { a[0].lastIndex = 0; s = s.replace(a[0], ' '); if (!r.area) r.area = a[1]; } });
    var pos = {};
    INTENTS.forEach(function (it) {
      it.re.lastIndex = 0;
      var at = s.search(it.re);
      if (at < 0) return;
      it.re.lastIndex = 0; s = s.replace(it.re, function (m) { return new Array(m.length + 1).join(' '); }); hit = true;   // 같은 길이 공백 — 뒤 조건의 위치가 안 밀리게
      if (it.cat && r.cats.indexOf(it.cat) < 0) { r.cats.push(it.cat); pos[it.cat] = at; }
      if (it.no && r.no.indexOf(it.no) < 0) r.no.push(it.no);
      if (it.sort) r.sort = it.sort;
    });
    if (!hit) return null;   // 지역만 있는 말은 이름 검색·지역 칩이 맡는다
    r.cats.sort(function (a, b) { return pos[a] - pos[b]; });   // 먼저 쓴 조건이 정렬 기준
    s = s.replace(INTENT_FILL, ' ').replace(/[\s\d.,!?~·\-]+/g, '');
    return /^[한은는이가을를의에도인된운요해]*$/.test(s) ? r : null;   // 조사·어미만 남아야 조건
  }

  // 소리가 거의 같은 말(벳퓨↔벳푸)인지 — 미지원 도시 판정용. 낱말마다 소리 키 편집거리 1 이하(4자모 이상만)
  function soundLike(q, list) {
    var qs = words(q).map(fold).filter(function (t) { return t.length >= 4; });
    return qs.length > 0 && list.some(function (k) {
      var kf = fold(String(k).toLowerCase().replace(/\s+/g, ''));
      return kf.length >= 4 && qs.some(function (t) { return lev(t, kf, 1) <= 1; });
    });
  }

  window.CFAutocomplete = { attach: attach, match: match, matchIds: matchIds, suggest: suggest, selfTest: selfTest, requestAnalysis: requestAnalysis,
                            isMapsUrl: isMapsUrl, resolveUrl: resolveUrl, resolveLink: resolveLink, remote: remote, intent: intent, soundLike: soundLike };
})();

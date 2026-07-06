/* 캐치플로 검색 정규화 (pipeline/search_key.py의 JS 미러 — 바이트 동일 키가 생명)
   NFKC lower + 구두점 제거 + 결합자모→호환자모 폴딩 + 한글 자모분해 + 초성.
   로직 변경 시 search_key.py와 동시 수정. 참조: DETAIL-UI-REVAMP-DESIGN §7-b. */
(function (global) {
  'use strict';

  var CHO = ['ㄱ','ㄲ','ㄴ','ㄷ','ㄸ','ㄹ','ㅁ','ㅂ','ㅃ','ㅅ','ㅆ','ㅇ','ㅈ','ㅉ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ'];
  var JUNG = ['ㅏ','ㅐ','ㅑ','ㅒ','ㅓ','ㅔ','ㅕ','ㅖ','ㅗ','ㅘ','ㅙ','ㅚ','ㅛ','ㅜ','ㅝ','ㅞ','ㅟ','ㅠ','ㅡ','ㅢ','ㅣ'];
  var JONG = ['','ㄱ','ㄲ','ㄳ','ㄴ','ㄵ','ㄶ','ㄷ','ㄹ','ㄺ','ㄻ','ㄼ','ㄽ','ㄾ','ㄿ','ㅀ','ㅁ','ㅂ','ㅄ','ㅅ','ㅆ','ㅇ','ㅈ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ'];

  // 결합자모(conjoining) → 호환자모(compat) 폴딩 맵 (search_key.py _JAMO_FOLD와 동일)
  var FOLD = {};
  for (var i = 0; i < CHO.length; i++) FOLD[String.fromCharCode(0x1100 + i)] = CHO[i];       // 초성 19
  for (var j = 0; j < JUNG.length; j++) FOLD[String.fromCharCode(0x1161 + j)] = JUNG[j];      // 중성 21
  for (var k = 0; k < JONG.length; k++) { if (JONG[k]) FOLD[String.fromCharCode(0x11A7 + k)] = JONG[k]; } // 종성 27

  // 구두점 제거 정규식 (search_key.py _PUNCT와 동일 문자셋)
  var PUNCT = /[\s\-·.,'"&()~!?/|:;\[\]]+/g;

  function foldJamo(s) {
    var out = '';
    for (var m = 0; m < s.length; m++) {
      var ch = s.charAt(m);
      out += (FOLD[ch] !== undefined) ? FOLD[ch] : ch;
    }
    return out;
  }

  function base(raw) {
    var s = (raw || '').normalize('NFKC').toLowerCase();
    s = s.replace(PUNCT, '');
    return foldJamo(s);
  }

  function decompose(s) {
    var out = '';
    for (var i = 0; i < s.length; i++) {
      var c = s.charCodeAt(i);
      if (c >= 0xAC00 && c <= 0xD7A3) {
        var t = c - 0xAC00;
        out += CHO[Math.floor(t / 588)] + JUNG[Math.floor((t % 588) / 28)] + JONG[t % 28];
      } else {
        out += s.charAt(i);
      }
    }
    return out;
  }

  function choseong(s) {
    var out = '';
    for (var i = 0; i < s.length; i++) {
      var c = s.charCodeAt(i);
      out += (c >= 0xAC00 && c <= 0xD7A3) ? CHO[Math.floor((c - 0xAC00) / 588)] : s.charAt(i);
    }
    return out;
  }

  // (자모키, 초성키) 반환 — Python to_key와 동일
  function toKey(raw) {
    var b = base(raw);
    return { full: decompose(b), cho: choseong(b) };
  }

  // 콘솔 자가검증 (Python 파리티 케이스). window.CF_SEARCH_KEY_SELFTEST() 로 호출.
  function selfTest() {
    var cases = [
      ['블러썸', 'ㅂㅡㄹㄹㅓㅆㅓㅁ', 'ㅂㄹㅆ'],
      ['Hyatt 호텔', 'hyattㅎㅗㅌㅔㄹ', 'hyattㅎㅌ'],
      ['도미인', 'ㄷㅗㅁㅣㅇㅣㄴ', 'ㄷㅁㅇ'],
      ['ㄷㅁㅇ', 'ㄷㅁㅇ', 'ㄷㅁㅇ'],
      ['블라섬', 'ㅂㅡㄹㄹㅏㅅㅓㅁ', 'ㅂㄹㅅ']
    ];
    var ok = true;
    cases.forEach(function (c) {
      var r = toKey(c[0]);
      var pass = (r.full === c[1] && r.cho === c[2]);
      if (!pass) ok = false;
      // eslint-disable-next-line no-console
      console.log((pass ? '[OK]  ' : '[FAIL]') + ' ' + c[0] + ' → full=' + r.full + ' cho=' + r.cho +
        (pass ? '' : '  (기대 full=' + c[1] + ' cho=' + c[2] + ')'));
    });
    // eslint-disable-next-line no-console
    console.log(ok ? 'search-key selfTest: ALL PASS' : 'search-key selfTest: FAILED');
    return ok;
  }

  global.CFSearchKey = { toKey: toKey, base: base, selfTest: selfTest };
  global.CF_SEARCH_KEY_SELFTEST = selfTest;
})(window);

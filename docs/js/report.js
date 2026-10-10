/* 캐치플로 리뷰 오분류 신고 (report.js) — REPORT-RECLASSIFY-DESIGN §2 · FEEDBACK-2610 §13
   버튼: .rep-btn[data-fid][data-cat][data-sub][data-grade] (리뷰 시트 카드·위험도 인용 카드. 실전정보 근거 제외)
   전송: Supabase classification_reports (anon INSERT, RLS status='new') → VM report_review.py가 AI 재판정·디스코드 승인
   중복 방지: localStorage cf_rep = 신고한 fid 배열 → 버튼 '신고함' 비활성
   GA4: report_open / report_submit {reason, cat, sub}
   의존: backnav.js(CF.sheet·CF.toast), window.CF_HOTEL.pid, window.CF_SB, window.CAT_KO */
(function () {
  'use strict';
  var REASONS = [
    { code: 'not_complaint', label: '불만이 아니에요', desc: '칭찬이나 중립적인 문장이에요' },
    { code: 'wrong_category', label: '다른 항목이에요', desc: '맞는 항목을 고를 수 있어요(선택)' },
    { code: 'wrong_grade', label: '심각도가 과해요·부족해요', desc: '심각·주의 판정이 맞지 않아요' },
    { code: 'other', label: '기타', desc: '' }
  ];
  var CATS7 = ['청결', '냄새', '소음', '객실', '직원', '위치', '안전'];
  var KEY = 'cf_rep';
  var modal = null, cur = null;

  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function done() { try { var a = JSON.parse(localStorage.getItem(KEY) || '[]'); return Array.isArray(a) ? a : []; } catch (e) { return []; } }
  function markDone(fid) {
    try { var a = done(); if (a.indexOf(fid) < 0) a.push(fid); localStorage.setItem(KEY, JSON.stringify(a.slice(-500))); } catch (e) {}
  }
  function catKo(c) { return (window.CAT_KO && window.CAT_KO[c]) || c; }
  function gtagSafe(name, p) { if (typeof gtag === 'function') gtag('event', name, p || {}); }
  function toast(msg) { CF.toast(msg); }   // 토스트 1벌(js/backnav.js)
  // 남용 집계용 익명 ID: localStorage 랜덤값의 SHA-256 앞 16자 (개인정보 아님)
  function clientHash() {
    var id = '';
    try { id = localStorage.getItem('cf_rid') || ''; } catch (e) {}
    if (!id) {
      id = Math.random().toString(36).slice(2) + Date.now().toString(36) + Math.random().toString(36).slice(2);
      try { localStorage.setItem('cf_rid', id); } catch (e) {}
    }
    if (window.crypto && crypto.subtle && window.TextEncoder) {
      return crypto.subtle.digest('SHA-256', new TextEncoder().encode(id)).then(function (buf) {
        return Array.prototype.map.call(new Uint8Array(buf), function (b) { return ('0' + b.toString(16)).slice(-2); }).join('').slice(0, 16);
      }).catch(function () { return id.slice(0, 16); });
    }
    return Promise.resolve(id.slice(0, 16));
  }

  // 화면에 그려진 신고 버튼의 '신고함' 상태 반영 (시트는 다시 그려지므로 열 때·그릴 때마다 호출)
  function refresh(root) {
    var d = done();
    (root || document).querySelectorAll('.rep-btn[data-fid]').forEach(function (b) {
      var on = d.indexOf(String(b.getAttribute('data-fid'))) >= 0;
      b.disabled = on; b.classList.toggle('is-done', on); b.textContent = on ? '신고함' : '분류가 이상해요';
    });
  }

  // A 페이지 시트 · H2 큰 제목 · F3(잉크 '신고하기' + 비활성일 때 위 안내). 리뷰 근거 시트 위에서 열리면 '시트 위 시트'
  function build() {
    var m = CF.sheet.make({
      id: 'cf-report', type: 'sheet', w: 'md', head: 'large', tag: 'form', title: '어떤 점이 이상한가요?', sub: ' ',
      body: '<div class="ov-sec"><div class="ov-opts rp-reasons" role="radiogroup" aria-label="신고 이유">' + REASONS.map(function (r) {
          return '<label class="ov-opt rp-reason"><span class="ov-opt-t"><b>' + r.label + '</b>' + (r.desc ? '<span>' + r.desc + '</span>' : '') + '</span>'
            + '<input type="radio" class="ov-radio" name="rp-reason" value="' + r.code + '"></label>'
            + (r.code === 'wrong_category' ? '<div class="rp-cats ov-chips" hidden>' + CATS7.map(function (c) {
              return '<button type="button" class="chip-filter rp-cat" data-cat="' + c + '" aria-pressed="false">' + esc(catKo(c)) + '</button>';
            }).join('') + '</div>' : '');
        }).join('') + '</div></div>'
        + '<div class="ov-sec"><label class="ov-sec-t" for="rp-comment">덧붙일 말 <span class="ov-opt-q">(선택, 200자)</span></label>'
        + '<textarea id="rp-comment" class="ov-input rp-comment" maxlength="200" placeholder="어떤 점이 이상한지 알려 주세요"></textarea>'
        + '<p class="ov-note">검토 후 반영돼요 · 신고만으로 분류가 바로 바뀌지는 않아요</p></div>'
        + '<input type="text" class="rp-hp" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">',
      footType: 'f3',
      foot: '<p class="ov-foot-note rp-hint">이유를 하나 골라 주세요</p><button type="submit" class="btn-ink rp-submit" disabled>신고하기</button>'
    });
    m.addEventListener('change', function (e) {
      if (e.target.name !== 'rp-reason') return;
      m.querySelector('.rp-cats').hidden = e.target.value !== 'wrong_category';
      setReady(true);
      CF.sheet.update(m);
    });
    m.addEventListener('click', function (e) {
      var b = e.target.closest('.rp-cat'); if (!b) return;
      var on = !b.classList.contains('on');
      m.querySelectorAll('.rp-cat').forEach(function (x) { x.classList.remove('on'); x.setAttribute('aria-pressed', 'false'); });
      if (on) { b.classList.add('on'); b.setAttribute('aria-pressed', 'true'); }
    });
    m.querySelector('form').addEventListener('submit', function (e) { e.preventDefault(); submit(); });
    return m;
  }
  function setReady(on) {
    var sb = modal.querySelector('.rp-submit');
    sb.disabled = !on; sb.textContent = '신고하기';
    modal.querySelector('.rp-hint').hidden = on;
  }

  function open(btn) {
    cur = {
      fid: String(btn.getAttribute('data-fid')), cat: btn.getAttribute('data-cat') || '',
      sub: btn.getAttribute('data-sub') || '', grade: btn.getAttribute('data-grade') || ''
    };
    if (!modal) modal = build();
    var f = modal.querySelector('form'); f.reset();
    modal.querySelector('.rp-cats').hidden = true;
    modal.querySelectorAll('.rp-cat').forEach(function (x) { x.classList.remove('on'); x.setAttribute('aria-pressed', 'false'); });
    var sub = (window.QSUBKO && window.QSUBKO[cur.sub]) || cur.sub;
    modal.querySelector('.ov-sub').textContent = '지금 분류 · ' + [catKo(cur.cat), sub].filter(Boolean).join(' > ') + (cur.grade ? ' · ' + cur.grade : '');
    setReady(false);
    modal.querySelector('.ov-body').scrollTop = 0;
    CF.sheet.open(modal, { opener: btn });   // 리뷰 근거 시트 위면 아래 시트는 scale .96 + 딤 하나, 닫으면 스크롤 잠금 유지
    gtagSafe('report_open', { cat: cur.cat, sub: cur.sub });
  }

  function submit() {
    if (!cur || !modal) return;
    var r = modal.querySelector('input[name="rp-reason"]:checked'); if (!r) return;
    var sc = modal.querySelector('.rp-cat.on');
    var comment = modal.querySelector('.rp-comment').value.trim().slice(0, 200);
    var hp = modal.querySelector('.rp-hp').value;
    var H = window.CF_HOTEL || {}, SB = window.CF_SB || {};
    var sb = modal.querySelector('.rp-submit'); sb.disabled = true; sb.textContent = '보내는 중…';
    var finish = function (ok) {
      if (ok) {
        markDone(cur.fid); refresh();
        gtagSafe('report_submit', { reason: r.value, cat: cur.cat, sub: cur.sub });
        CF.sheet.close(modal);
        toast('신고가 접수됐어요 · 검토 후 반영돼요');
      } else {
        sb.disabled = false; sb.textContent = '신고하기';
        toast('보내지 못했어요 · 잠시 후 다시 시도해 주세요');
      }
    };
    if (hp) { finish(true); return; }                     // 허니팟(봇) — 보낸 척만
    if (!SB.url || !SB.key || !H.pid) { finish(false); return; }
    clientHash().then(function (hash) {
      var body = {
        place_id: H.pid, fid: parseInt(cur.fid, 10), cur_cat: cur.cat || null, cur_sub: cur.sub || null, cur_grade: cur.grade || null,
        reason: r.value, suggest_cat: (r.value === 'wrong_category' && sc) ? sc.getAttribute('data-cat') : null,
        comment: comment || null, client_hash: hash
      };
      return fetch(SB.url + '/rest/v1/classification_reports', {
        method: 'POST',
        headers: { 'apikey': SB.key, 'Authorization': 'Bearer ' + SB.key, 'Content-Type': 'application/json', 'Prefer': 'return=minimal' },
        body: JSON.stringify(body)
      });
    }).then(function (res) { finish(!!(res && res.ok)); }).catch(function () { finish(false); });
  }

  function ready(fn) { if (document.readyState !== 'loading') fn(); else document.addEventListener('DOMContentLoaded', fn); }
  ready(function () {
    document.addEventListener('click', function (e) {
      var b = e.target.closest('.rep-btn'); if (!b || b.disabled) return;
      e.preventDefault(); e.stopPropagation();
      open(b);
    }, true);
    refresh();
    // 리뷰 시트는 열릴 때마다 카드를 다시 그린다 → 새로 생긴 버튼에도 '신고함' 반영
    var list = document.getElementById('sheet-list');
    if (list && window.MutationObserver) new MutationObserver(function () { refresh(list); }).observe(list, { childList: true });
  });
  window.CFReport = { refresh: refresh };
})();

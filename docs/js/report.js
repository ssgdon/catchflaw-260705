/* 캐치플로 리뷰 오분류 신고 (report.js) — REPORT-RECLASSIFY-DESIGN §2 · FEEDBACK-2610 §13
   버튼: .rep-btn[data-fid][data-cat][data-sub][data-grade] (리뷰 시트 카드·위험도 인용 카드. 실전정보 근거 제외)
   전송: Supabase classification_reports (anon INSERT, RLS status='new') → VM report_review.py가 AI 재판정·디스코드 승인
   중복 방지: localStorage cf_rep = 신고한 fid 배열 → 버튼 '신고함' 비활성
   GA4: report_open / report_submit {reason, cat, sub}
   의존: backnav.js(CFNav), window.CF_HOTEL.pid, window.CF_SB, window.CAT_KO */
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
  function toast(msg) {
    var el = document.createElement('div'); el.className = 'cf-toast'; el.textContent = msg;
    document.body.appendChild(el);
    requestAnimationFrame(function () { el.classList.add('show'); });
    setTimeout(function () { el.classList.remove('show'); setTimeout(function () { el.remove(); }, 300); }, 2200);
  }
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

  function build() {
    var m = document.createElement('div');
    m.className = 'cf-modal'; m.id = 'cf-report';
    m.innerHTML =
      '<div class="cf-modal-dim"></div>' +
      '<form class="cf-modal-card rp-card" novalidate>' +
        '<div class="rp-head"><div class="rp-tit">이 리뷰 분류가 맞지 않나요?</div>' +
        '<button type="button" class="rp-close" aria-label="닫기">✕</button></div>' +
        '<div class="rp-now"><span class="rp-label">지금 분류</span><span class="rp-cur-chip"></span></div>' +
        '<div class="rp-label">이유를 골라 주세요</div>' +
        '<div class="rp-reasons">' + REASONS.map(function (r) {
          return '<label class="rp-reason"><input type="radio" name="rp-reason" value="' + r.code + '">' +
            '<span class="rp-r-t"><b>' + r.label + '</b>' + (r.desc ? '<span>' + r.desc + '</span>' : '') + '</span></label>' +
            (r.code === 'wrong_category' ? '<div class="rp-cats" hidden>' + CATS7.map(function (c) {
              return '<button type="button" class="rp-cat" data-cat="' + c + '">' + esc(catKo(c)) + '</button>';
            }).join('') + '</div>' : '');
        }).join('') + '</div>' +
        '<label class="rp-label" for="rp-comment">덧붙일 말 <span class="rp-opt">(선택, 200자)</span></label>' +
        '<textarea id="rp-comment" class="rp-comment" maxlength="200" placeholder="어떤 점이 이상한지 알려 주세요"></textarea>' +
        '<input type="text" class="rp-hp" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">' +
        '<div class="rp-note">검토 후 반영돼요 · 신고만으로 점수가 바로 바뀌지는 않아요</div>' +
        '<button type="submit" class="cf-btn cf-btn-primary rp-submit" disabled>신고하기</button>' +
      '</form>';
    document.body.appendChild(m);
    m.querySelector('.cf-modal-dim').addEventListener('click', function () { CFNav.pop(); });
    m.querySelector('.rp-close').addEventListener('click', function () { CFNav.pop(); });
    m.addEventListener('change', function (e) {
      if (e.target.name !== 'rp-reason') return;
      m.querySelector('.rp-cats').hidden = e.target.value !== 'wrong_category';
      m.querySelector('.rp-submit').disabled = false;
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

  function open(btn) {
    cur = {
      fid: String(btn.getAttribute('data-fid')), cat: btn.getAttribute('data-cat') || '',
      sub: btn.getAttribute('data-sub') || '', grade: btn.getAttribute('data-grade') || ''
    };
    if (!modal) modal = build();
    var f = modal.querySelector('form'); f.reset();
    modal.querySelector('.rp-cats').hidden = true;
    modal.querySelectorAll('.rp-cat').forEach(function (x) { x.classList.remove('on'); });
    var sub = (window.QSUBKO && window.QSUBKO[cur.sub]) || cur.sub;
    modal.querySelector('.rp-cur-chip').textContent = [catKo(cur.cat), sub].filter(Boolean).join(' > ') + (cur.grade ? ' · ' + cur.grade : '');
    var sb = modal.querySelector('.rp-submit'); sb.disabled = true; sb.textContent = '신고하기';
    modal.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    CFNav.push(function () { modal.classList.remove('is-open'); if (!document.querySelector('.review-sheet.is-open')) document.body.style.overflow = ''; });   // 리뷰 시트 위에서 열렸으면 스크롤 잠금 유지
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
        CFNav.pop();
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

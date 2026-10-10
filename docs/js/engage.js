/* 캐치플로 공유 + 이탈 전 피드백 (engage.js)
   window.CF_HOTEL = {pid, name, gmap} 가 있을 때만 동작 (상세 페이지)
   window.CF_SB = {url, key} 로 Supabase(mvp_feedbacks, INSERT 전용) 저장
   의존: jQuery, backnav.js(CF.sheet·CF.toast) */
(function () {
  function ready(fn) { if (document.readyState !== 'loading') fn(); else document.addEventListener('DOMContentLoaded', fn); }
  ready(function () {
    var H = window.CF_HOTEL;
    if (!H) return;

    // ───────── 최근 본 호텔 기록 (F40) ─────────
    // localStorage 'cf_recent' = 최신순 pid 배열(중복 제거, 최대 20) + 'cf_recent_ts' = {pid: 본 시각} — recent 페이지(build_recent)가 동일 키로 읽음
    try {
      var rec = JSON.parse(localStorage.getItem('cf_recent') || '[]');
      if (!Array.isArray(rec)) rec = [];
      rec = rec.filter(function (p) { return p !== H.pid; });
      rec.unshift(H.pid);
      rec = rec.slice(0, 20);
      localStorage.setItem('cf_recent', JSON.stringify(rec));
      // 본 시각 {pid: ms} — recent 페이지의 '오늘/어제/이번 주/그 전' 묶음용. 목록에서 빠진 호텔의 시각은 같이 지운다
      var ts = JSON.parse(localStorage.getItem('cf_recent_ts') || '{}'), keep = {};
      ts[H.pid] = Date.now();
      rec.forEach(function (p) { if (ts[p]) keep[p] = ts[p]; });
      localStorage.setItem('cf_recent_ts', JSON.stringify(keep));
    } catch (e) {}

    // 카카오톡 인앱 브라우저 감지
    var isKakaoInApp = /KAKAOTALK/i.test(navigator.userAgent);

    // ───────── 공유 (B 바텀 시트 · H3 정보형 — navigator.share가 없을 때만) ─────────
    var shareSheet = null;
    var ICO_LINK = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1.2 1.2M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1.2-1.2" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/></svg>';
    var ICO_OUT = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    function esc(t) { return String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }
    function buildShareSheet() {
      var img = (window.CF_IMGS || [])[0];
      var m = CF.sheet.make({
        id: 'cf-share-sheet', type: 'bottom', w: 'md', head: 'info', title: '공유하기',
        body: '<div class="sh-hotel">' + (img ? '<img class="sh-thumb" src="' + esc(img) + '" alt="">' : '') + '<span class="sh-name">' + esc(H.name) + '</span></div>'
          + '<div class="sh-opts">'
          + '<button type="button" class="sh-opt" data-act="copy">' + ICO_LINK + '링크 복사</button>'
          // 카카오 인앱 → 외부 브라우저로 현재 URL 열기 (거기서 OS 공유 사용 가능)
          + (isKakaoInApp ? '<button type="button" class="sh-opt" data-act="external">' + ICO_OUT + '브라우저로 열기</button>' : '')
          + '</div>'
      });
      m.querySelector('[data-act="copy"]').addEventListener('click', function () { copyLink(); CF.sheet.close(m); });
      var ext = m.querySelector('[data-act="external"]');
      if (ext) ext.addEventListener('click', function () {
        location.href = 'kakaotalk://web/openExternal?url=' + encodeURIComponent(location.href);
      });
      return m;
    }
    function copyLink() {
      if (navigator.clipboard) navigator.clipboard.writeText(location.href).then(showToast, fallbackCopy);
      else fallbackCopy();
    }
    function fallbackCopy() {
      var t = document.createElement('textarea'); t.value = location.href;
      document.body.appendChild(t); t.select();
      try { document.execCommand('copy'); showToast(); } catch (e) {}
      document.body.removeChild(t);
    }
    function showToast() { CF.toast('링크를 복사했어요'); }   // 토스트 1벌(js/backnav.js)
    function openShare(opener) {
      if (!shareSheet) shareSheet = buildShareSheet();
      CF.sheet.open(shareSheet, { opener: opener });
    }

    $('.btn-share').off('click').on('click', function (e) {
      e.preventDefault();
      var data = { title: document.title, text: H.name + ' — 캐치플로 분석', url: location.href };
      // OS 네이티브 공유(카카오톡 등 앱 목록) 우선
      if (navigator.share) { navigator.share(data).catch(function () {}); }
      else { openShare(this); }  // 미지원(카카오 인앱 등) → 자체 공유 시트
    });

    // ───────── 이탈 전 피드백 ─────────
    var fbModal = null, pendingUrl = null;
    var FB_KEY = 'cf_fb_shown';
    function alreadyShown() { try { return sessionStorage.getItem(FB_KEY) === '1'; } catch (e) { return false; } }
    function markShown() { try { sessionStorage.setItem(FB_KEY, '1'); } catch (e) {} }

    // B 바텀 시트 · H2 큰 제목 · F1('그냥 이동할게요' 링크 + 잉크 '보내고 이동')
    function buildFbModal() {
      var m = CF.sheet.make({
        id: 'cf-feedback-modal', type: 'bottom', w: 'md', head: 'large', title: '이동 전에 잠깐만요',
        sub: '<span class="seg">어떤 기능이 있으면 좋을까요?</span> <span class="seg">불편한 점도 좋아요.</span>', footType: 'f1',
        body: '<div class="fb-body">'
          + '<textarea id="fb-text" class="ov-input" placeholder="예) 객실 사진이 더 많았으면 좋겠어요" aria-label="의견"></textarea>'
          + '<input type="tel" id="fb-phone" class="ov-input" placeholder="휴대폰 번호 (선택)" inputmode="numeric" aria-label="휴대폰 번호(선택)">'
          + '<p class="ov-note"><span class="seg">새 기능이 나오면 먼저 알려드릴게요 ·</span> <span class="seg">번호는 안내 용도로만 써요</span></p>'
          + '</div>'
          + '<div class="fb-done" hidden><p class="fb-done-msg">소중한 의견 고마워요</p></div>',
        foot: '<button type="button" class="btn-text" data-act="skip">그냥 이동할게요</button>'
          + '<button type="button" class="btn-ink" data-act="send">보내고 이동</button>'
      });
      m.querySelector('.ov-sub').classList.add('is-text');
      m.querySelector('[data-act="skip"]').addEventListener('click', function () { go(); });
      m.querySelector('[data-act="send"]').addEventListener('click', function () {
        var text = (m.querySelector('#fb-text').value || '').trim();
        var phone = (m.querySelector('#fb-phone').value || '').trim();
        if (!text && !phone) { go(); return; }  // 빈 값이면 그냥 이동
        submit(text, phone);
        // 저장 성공 여부와 무관하게 UX는 즉시 진행
        m.querySelector('.fb-body').setAttribute('hidden', '');
        m.querySelector('.ov-hero').setAttribute('hidden', '');
        m.querySelector('.ov-foot').setAttribute('hidden', '');
        m.querySelector('.fb-done').removeAttribute('hidden');
        setTimeout(go, 900);
      });
      return m;
    }
    function submit(text, phone) {
      if (!window.CF_SB) return;
      try {
        fetch(window.CF_SB.url + '/rest/v1/mvp_feedbacks', {
          method: 'POST',
          headers: {
            'apikey': window.CF_SB.key,
            'Authorization': 'Bearer ' + window.CF_SB.key,
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal'
          },
          body: JSON.stringify({ place_id: H.pid, hotel_name: H.name, feedback: text || null, phone: phone || null, source: 'detail_exit' })
        }).catch(function () {});
      } catch (e) {}
    }
    function go() {
      markShown();
      var url = pendingUrl || H.gmap;
      if (fbModal) CF.sheet.close(fbModal);
      window.open(url, '_blank', 'noopener');
    }
    function openFb(url, opener) {
      pendingUrl = url;
      if (!fbModal) fbModal = buildFbModal();
      ['.fb-body', '.ov-hero', '.ov-foot'].forEach(function (q) { fbModal.querySelector(q).removeAttribute('hidden'); });
      fbModal.querySelector('.fb-done').setAttribute('hidden', '');
      CF.sheet.open(fbModal, { opener: opener });
    }

    // 구글맵으로 나가는 링크 가로채기 (세션당 1회만 피드백)
    // 훅은 클래스가 아니라 속성에 건다(DESIGN-SYSTEM-V3 §6-1): data-out="cta|google|map" — 버튼 클래스가 바뀌어도 GA4가 끊기지 않게
    var OUT_PLACEMENT = { cta: 'floating_cta', google: 'google_rating', map: 'map_link' };
    $(document).on('click', 'a[data-out]', function (e) {
      var url = this.getAttribute('href');
      var kind = this.getAttribute('data-out');
      // GA4 전환 측정 — 피드백 모달 노출 여부와 무관하게 매 클릭 카운트
      if (typeof gtag === 'function') {
        var h = window.CF_HOTEL || {};
        gtag('event', kind === 'cta' ? 'check_price_click' : 'outbound_google', {
          hotel_name: h.name || '',
          hotel_id: h.pid || '',
          link_url: url || '',
          placement: OUT_PLACEMENT[kind] || 'map_link'
        });
      }
      if (alreadyShown()) return;  // 이미 봤으면 정상 이동
      e.preventDefault();
      openFb(url, this);
    });
  });
})();

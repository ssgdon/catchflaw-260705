/* 캐치플로 공유 + 이탈 전 피드백 (engage.js)
   window.CF_HOTEL = {pid, name, gmap, cta} 가 있을 때만 동작 (상세 페이지)
   window.CF_SB = {url, key} 로 Supabase(mvp_feedbacks, INSERT 전용) 저장
   의존: jQuery, backnav.js(CF.sheet·CF.toast) */
(function () {
  function ready(fn) { if (document.readyState !== 'loading') fn(); else document.addEventListener('DOMContentLoaded', fn); }
  ready(function () {
    var H = window.CF_HOTEL;
    if (!H) return;
    // Meta 픽셀(2026-11-11, generate.py GA4의 cfPx) — 상세 조회. 이름과 분류만 보낸다
    if (window.cfPx) window.cfPx('ViewContent', { content_name: H.name || '', content_category: 'hotel' });

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
    // 공유 주소 = canonical + utm(source=share, medium=os|copy) — 받은 사람이 들어오면 GA4에 'share' 유입으로 잡힌다(2026-11-05).
    // #rv=·?q= 같은 화면 상태는 빼고 보낸다. canonical 태그가 있어 검색엔진엔 중복 주소가 아니다.
    function shareUrl(medium) {
      var u = H.url || location.href.split('#')[0].split('?')[0];
      return u + (u.indexOf('?') < 0 ? '?' : '&') + 'utm_source=share&utm_medium=' + medium + '&utm_campaign=hotel';
    }
    function copyLink() {
      var u = shareUrl('copy');
      if (navigator.clipboard) navigator.clipboard.writeText(u).then(showToast, function () { fallbackCopy(u); });
      else fallbackCopy(u);
    }
    function fallbackCopy(u) {
      var t = document.createElement('textarea'); t.value = u;
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
      // 문구에 실망 확률·도시 평균·판정을 넣는다(H.share, generate.py) — 미리보기 카드가 안 뜨는 앱에서도 숫자가 보이게
      var data = { title: H.name, text: H.share || (H.name + ' — 캐치플로 리뷰 분석'), url: shareUrl('os') };
      // OS 네이티브 공유(카카오톡 등 앱 목록) 우선
      if (typeof gtag === 'function') gtag('event', 'share', { method: navigator.share ? 'os' : 'sheet', hotel_id: H.pid || '',
        placement: this.getAttribute('data-share-at') || 'header' });   // UX-2611 A: 공유 측정 · 어느 버튼인지(header|who|pc_side)
      if (navigator.share) { navigator.share(data).catch(function () {}); }
      else { openShare(this); }  // 미지원(카카오 인앱 등) → 자체 공유 시트
    });

    // ───────── 피드백 시트 (UX-2611 B: CTA를 가로채지 않는다) ─────────
    // 예전엔 세션 첫 a[data-out] 클릭을 preventDefault로 막고 '이동 전에 잠깐만요'를 띄웠다 — 유일한 전환 클릭(세션 3.6%)에 질문지가 먼저 끼고,
    // X·뒤로가기면 이동도 안 됐다. 지금은 ① 아고다·구글에서 탭이 돌아왔을 때 토스트 한 번 ② 상세 맨 아래 '의견 남기기'에서만 연다.
    var fbModal = null;
    var FB_KEY = 'cf_fb_shown', OUT_KEY = 'cf_out_ts';
    function alreadyShown() { try { return sessionStorage.getItem(FB_KEY) === '1'; } catch (e) { return false; } }
    function markShown() { try { sessionStorage.setItem(FB_KEY, '1'); } catch (e) {} }

    // B 바텀 시트 · H2 큰 제목 · F1('그냥 이동할게요' 링크 + 잉크 '보내고 이동')
    function buildFbModal() {
      var m = CF.sheet.make({
        id: 'cf-feedback-modal', type: 'bottom', w: 'md', head: 'large', title: '의견을 남겨 주세요',
        sub: '<span class="seg">어떤 기능이 있으면 좋을까요?</span> <span class="seg">불편한 점도 좋아요.</span>', footType: 'f1',
        body: '<div class="fb-body">'
          + '<textarea id="fb-text" class="ov-input" placeholder="예) 객실 사진이 더 많았으면 좋겠어요" aria-label="의견"></textarea>'
          + '<input type="tel" id="fb-phone" class="ov-input" placeholder="휴대폰 번호 (선택)" inputmode="numeric" aria-label="휴대폰 번호(선택)">'
          + '<p class="ov-note"><span class="seg">새 기능이 나오면 먼저 알려드릴게요 ·</span> <span class="seg">번호는 안내 용도로만 써요</span></p>'
          + '</div>'
          + '<div class="fb-done" hidden>' + (CF.mascot ? CF.mascot('jump') : '') + '<p class="fb-done-msg">소중한 의견 고마워요</p></div>',
        foot: '<button type="button" class="btn-text" data-act="skip">다음에 할게요</button>'
          + '<button type="button" class="btn-ink" data-act="send">보내기</button>'
      });
      m.querySelector('.ov-sub').classList.add('is-text');
      m.querySelector('[data-act="skip"]').addEventListener('click', function () { fbEnd('fb_skip', { empty: 0 }); CF.sheet.close(m); });
      m.querySelector('[data-act="send"]').addEventListener('click', function () {
        var text = (m.querySelector('#fb-text').value || '').trim();
        var phone = (m.querySelector('#fb-phone').value || '').trim();
        if (!text && !phone) { fbEnd('fb_skip', { empty: 1 }); CF.sheet.close(m); return; }  // 빈 값이면 그냥 닫기
        fbEnd('fb_submit', { has_text: text ? 1 : 0, has_phone: phone ? 1 : 0, text_len: text.length });  // 내용·번호는 GA로 보내지 않는다
        submit(text, phone);
        // 저장 성공 여부와 무관하게 완료 화면 1.2초 → 닫기
        m.querySelector('.fb-body').setAttribute('hidden', '');
        m.querySelector('.ov-hero').setAttribute('hidden', '');
        m.querySelector('.ov-foot').setAttribute('hidden', '');
        m.querySelector('.fb-done').removeAttribute('hidden');
        setTimeout(function () { if (fbModal) CF.sheet.close(fbModal); }, 1200);
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
          body: JSON.stringify({ place_id: H.pid, hotel_name: H.name, feedback: text || null, phone: phone || null, source: 'detail_' + (fbCtx.placement || 'link') })
        }).catch(function () {});
      } catch (e) {}
    }
    // 2026-11-04 피드백 창 GA 기록: fb_shown(뜸) → fb_submit(보냄)·fb_skip('다음에 할게요', empty=1은 빈 채로 '보내기')
    // ·fb_dismiss(X·뒤로가기로 닫음). placement = return_toast(돌아왔을 때 토스트) | footer_link(상세 맨 아래) — 응답 0건이 '저장 실패'인지 '아무도 안 씀'인지 가르기 위함.
    var fbCtx = {}, fbDone = false;
    function fbEv(name, p) {
      if (typeof gtag !== 'function') return;
      var o = { hotel_id: H.pid || '', placement: fbCtx.placement || '' };
      for (var k in p) o[k] = p[k];
      gtag('event', name, o);
    }
    function fbEnd(name, p) { if (fbDone) return; fbDone = true; fbEv(name, p || {}); }
    function openFb(opener, placement) {
      fbCtx = { placement: placement }; fbDone = false;
      if (!fbModal) fbModal = buildFbModal();
      ['.fb-body', '.ov-hero', '.ov-foot'].forEach(function (q) { fbModal.querySelector(q).removeAttribute('hidden'); });
      fbModal.querySelector('.fb-done').setAttribute('hidden', '');
      CF.sheet.open(fbModal, { opener: opener, onClose: function () { fbEnd('fb_dismiss'); } });
      fbEv('fb_shown', {});
    }

    // 상세 맨 아래 '의견 남기기'(generate.py .det-end) — 언제든 연다
    $(document).on('click', '[data-act="feedback"]', function () { openFb(this, 'footer_link'); });

    // 나가는 링크: 측정만 하고 막지 않는다(새 탭은 브라우저 기본 동작 = 팝업 차단 없음)
    // 훅은 클래스가 아니라 속성에 건다(DESIGN-SYSTEM-V3 §6-1): data-out="cta|google|map" + data-out-to="agoda|google"(도착지) — 버튼 클래스가 바뀌어도 GA4가 끊기지 않게
    var OUT_PLACEMENT = { cta: 'floating_cta', google: 'google_rating', map: 'map_link' };
    $(document).on('click', 'a[data-out]', function () {
      var url = this.getAttribute('href');
      var kind = this.getAttribute('data-out');
      if (typeof gtag === 'function') {
        var h = window.CF_HOTEL || {};
        gtag('event', kind === 'cta' ? 'check_price_click' : 'outbound_google', {
          hotel_name: h.name || '',
          hotel_id: h.pid || '',
          link_url: url || '',
          partner: this.getAttribute('data-out-to') || 'google',
          placement: OUT_PLACEMENT[kind] || 'map_link'
        });
      }
      // Meta 픽셀 — 가격 버튼 누름(GA check_price_click와 같은 순간). 광고 세트의 전환 이벤트 '결제 시작'이 이것
      if (kind === 'cta' && window.cfPx) {
        window.cfPx('InitiateCheckout', { content_name: (window.CF_HOTEL || {}).name || '', content_category: this.getAttribute('data-out-to') || 'google' });
      }
      try { sessionStorage.setItem(OUT_KEY, String(Date.now())); } catch (e) {}
    });

    // 아고다·구글 탭에서 돌아왔을 때(세션 1회): 작은 토스트 → 누르면 피드백 시트. 3초 안에 돌아온 건 '보기 전 복귀'라 안 띄운다
    function onReturn() {
      if (document.visibilityState !== 'visible' || alreadyShown()) return;
      var ts = 0;
      try { ts = +sessionStorage.getItem(OUT_KEY) || 0; } catch (e) {}
      if (!ts || Date.now() - ts < 3000) return;
      markShown();
      fbCtx = { placement: 'return_toast' };
      fbEv('fb_toast', {});
      CF.toast('찾던 정보가 있었나요?', { ms: 6000, action: { label: '의견 남기기', fn: function () { openFb(null, 'return_toast'); } } });
    }
    document.addEventListener('visibilitychange', onReturn);
    window.addEventListener('pageshow', onReturn);
  });
})();

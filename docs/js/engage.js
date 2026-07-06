/* 캐치플로 공유 + 이탈 전 피드백 (engage.js)
   window.CF_HOTEL = {pid, name, gmap} 가 있을 때만 동작 (상세 페이지)
   window.CF_SB = {url, key} 로 Supabase(mvp_feedbacks, INSERT 전용) 저장
   의존: jQuery, backnav.js(CFNav) */
(function () {
  function ready(fn) { if (document.readyState !== 'loading') fn(); else document.addEventListener('DOMContentLoaded', fn); }
  ready(function () {
    var H = window.CF_HOTEL;
    if (!H) return;

    // 카카오톡 인앱 브라우저 감지
    var isKakaoInApp = /KAKAOTALK/i.test(navigator.userAgent);

    // ───────── 공유 ─────────
    var shareSheet = null;
    function buildShareSheet() {
      var m = document.createElement('div');
      m.className = 'cf-modal'; m.id = 'cf-share-sheet';
      var kakaoBrowserBtn = isKakaoInApp
        ? '<button type="button" class="sh-item kakao" data-act="external">기본 브라우저로 열어 공유하기</button>'
        : '';
      m.innerHTML =
        '<div class="cf-modal-dim"></div>' +
        '<div class="cf-modal-card">' +
          '<div class="sh-tit">공유하기</div>' +
          '<div class="sh-list">' +
            kakaoBrowserBtn +
            '<button type="button" class="sh-item" data-act="copy">링크 복사하기</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(m);
      m.querySelector('.cf-modal-dim').addEventListener('click', function () { CFNav.pop(); });
      m.querySelector('[data-act="copy"]').addEventListener('click', function () {
        copyLink(); CFNav.pop();
      });
      var ext = m.querySelector('[data-act="external"]');
      if (ext) ext.addEventListener('click', function () {
        // 카카오 인앱 → 외부 브라우저로 현재 URL 열기 (거기서 OS 공유 사용 가능)
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
    function showToast() {
      var el = document.createElement('div'); el.className = 'cf-toast'; el.textContent = '링크가 복사되었어요!';
      document.body.appendChild(el);
      requestAnimationFrame(function () { el.classList.add('show'); });
      setTimeout(function () { el.classList.remove('show'); setTimeout(function () { el.remove(); }, 300); }, 1600);
    }
    function openShare() {
      if (!shareSheet) shareSheet = buildShareSheet();
      shareSheet.classList.add('is-open');
      document.body.style.overflow = 'hidden';
      CFNav.push(function () { shareSheet.classList.remove('is-open'); document.body.style.overflow = ''; });
    }

    $('.btn-share').off('click').on('click', function (e) {
      e.preventDefault();
      var data = { title: document.title, text: H.name + ' — 캐치플로 분석', url: location.href };
      // OS 네이티브 공유(카카오톡 등 앱 목록) 우선
      if (navigator.share) { navigator.share(data).catch(function () {}); }
      else { openShare(); }  // 미지원(카카오 인앱 등) → 자체 공유 시트
    });

    // ───────── 이탈 전 피드백 ─────────
    var fbModal = null, pendingUrl = null;
    var FB_KEY = 'cf_fb_shown';
    function alreadyShown() { try { return sessionStorage.getItem(FB_KEY) === '1'; } catch (e) { return false; } }
    function markShown() { try { sessionStorage.setItem(FB_KEY, '1'); } catch (e) {} }

    function buildFbModal() {
      var m = document.createElement('div');
      m.className = 'cf-modal'; m.id = 'cf-feedback-modal';
      m.innerHTML =
        '<div class="cf-modal-dim"></div>' +
        '<div class="cf-modal-card">' +
          '<div class="fb-body">' +
            '<div class="fb-head">' +
              '<span class="fb-tit">이동 전에 딱 1초만!</span>' +
              '<button type="button" class="fb-close" data-act="close">✕</button></div>' +
            '<div class="fb-txt">캐치플로에 어떤 기능이 있으면 좋을까요? 불편한 점도 좋아요. 여러분 의견으로 서비스를 만들어가요!</div>' +
            '<textarea id="fb-text" placeholder="예) 지하철역까지 도보 시간도 알려주세요"></textarea>' +
            '<input type="tel" id="fb-phone" placeholder="휴대폰 번호 (선택)" inputmode="numeric">' +
            '<div class="fb-phone-note">정식 오픈하면 제일 먼저 알려드릴게요 · 번호는 안내 용도로만 써요</div>' +
            '<div class="cf-modal-btns">' +
              '<button type="button" class="cf-btn cf-btn-primary" data-act="send">의견 보내고 이동하기</button>' +
              '<button type="button" class="cf-btn fb-skip" data-act="skip">그냥 이동할게요</button>' +
            '</div>' +
          '</div>' +
          '<div class="fb-done" hidden><div class="msg">소중한 의견 고마워요!</div></div>' +
        '</div>';
      document.body.appendChild(m);
      m.querySelector('[data-act="close"]').addEventListener('click', function () { CFNav.pop(); });
      m.querySelector('.cf-modal-dim').addEventListener('click', function () { CFNav.pop(); });
      m.querySelector('[data-act="skip"]').addEventListener('click', function () { go(); });
      m.querySelector('[data-act="send"]').addEventListener('click', function () {
        var text = (m.querySelector('#fb-text').value || '').trim();
        var phone = (m.querySelector('#fb-phone').value || '').trim();
        if (!text && !phone) { go(); return; }  // 빈 값이면 그냥 이동
        submit(text, phone);
        // 저장 성공 여부와 무관하게 UX는 즉시 진행
        m.querySelector('.fb-body').setAttribute('hidden', '');
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
      if (fbModal) { fbModal.querySelector('.fb-body').removeAttribute('hidden'); fbModal.querySelector('.fb-done').setAttribute('hidden', ''); }
      if (CFNav.isOpen()) CFNav.pop();
      window.open(url, '_blank', 'noopener');
    }
    function openFb(url) {
      pendingUrl = url;
      if (!fbModal) fbModal = buildFbModal();
      fbModal.classList.add('is-open');
      document.body.style.overflow = 'hidden';
      CFNav.push(function () { fbModal.classList.remove('is-open'); document.body.style.overflow = ''; });
    }

    // 구글맵으로 나가는 3개 링크 가로채기 (세션당 1회만 피드백)
    $(document).on('click', 'a.btn-google, a.btn-reservate, a.map-link', function (e) {
      var url = this.getAttribute('href');
      if (alreadyShown()) return;  // 이미 봤으면 정상 이동
      e.preventDefault();
      openFb(url);
    });
  });
})();

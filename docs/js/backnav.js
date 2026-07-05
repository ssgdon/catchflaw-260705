/* 캐치플로 공통 뒤로가기 관리 (backnav.js)
   - 오버레이(리뷰시트/필터시트/공유시트/피드백모달)가 열려 있으면
     아이폰 스와이프백 · 갤럭시 뒤로가기가 페이지를 나가지 않고 오버레이만 닫음
   - 외부에서 처음 들어온 페이지에서 뒤로가기로 사이트를 나가려 하면 종료 확인 모달 표시
   의존: 없음 (순수 JS, jQuery 불필요) */
(function () {
  var closers = [];        // 열린 오버레이의 '시각적 닫기' 함수 스택
  var suppressPop = false; // 버튼 닫기로 history.back() 할 때 popstate 중복 처리 방지
  var exitArmed = false;   // 외부 유입 페이지에서만 종료 확인 활성화
  var leaving = false;

  // 외부(다른 사이트/앱)에서 들어왔는지 판별
  function isExternalEntry() {
    if (!document.referrer) return true;
    try { return new URL(document.referrer).origin !== location.origin; }
    catch (e) { return true; }
  }

  // ── 종료 확인 모달 (DOM 동적 주입) ──
  var exitModal = null;
  function buildExitModal() {
    var m = document.createElement('div');
    m.className = 'cf-modal';
    m.id = 'cf-exit-modal';
    m.innerHTML =
      '<div class="cf-modal-dim"></div>' +
      '<div class="cf-modal-card">' +
        '<div class="cf-modal-emoji">😢</div>' +
        '<div class="cf-modal-tit">정말 나가시겠어요?</div>' +
        '<div class="cf-modal-txt">보던 호텔 분석은 저장되지 않아요.<br>후쿠오카 호텔이 아직 많이 남아 있어요!</div>' +
        '<div class="cf-modal-btns">' +
          '<button type="button" class="cf-btn cf-btn-ghost" data-act="leave">나가기</button>' +
          '<button type="button" class="cf-btn cf-btn-primary" data-act="stay">계속 볼래요</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(m);
    m.querySelector('[data-act="stay"]').addEventListener('click', hideExit);
    m.querySelector('.cf-modal-dim').addEventListener('click', hideExit);
    m.querySelector('[data-act="leave"]').addEventListener('click', function () {
      leaving = true;
      exitArmed = false;
      // 버퍼 + 실제 페이지를 건너뛰어 이전 사이트로. 히스토리가 짧으면 back 1회.
      if (history.length > 2) history.go(-2); else history.back();
    });
    return m;
  }
  function showExit() {
    if (!exitModal) exitModal = buildExitModal();
    exitModal.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  }
  function hideExit() {
    if (exitModal) exitModal.classList.remove('is-open');
    document.body.style.overflow = '';
  }

  // ── 공개 API ──
  window.CFNav = {
    // 오버레이를 '시각적으로' 연 직후 호출: 닫기함수 등록 + 히스토리 버퍼 push
    push: function (closeFn) {
      closers.push(closeFn);
      try { history.pushState({ cfOverlay: 1 }, ''); } catch (e) {}
    },
    // 버튼(X/딤/ESC)으로 닫을 때 호출: 시각적 닫기 실행 + 버퍼 소비
    pop: function () {
      if (!closers.length) return;
      var fn = closers.pop();
      try { fn(); } catch (e) {}
      suppressPop = true;
      history.back();
    },
    isOpen: function () { return closers.length > 0; }
  };

  window.addEventListener('popstate', function () {
    if (leaving) return;
    if (suppressPop) { suppressPop = false; return; }
    // 오버레이가 열려 있으면 최상단만 닫음 (푸시된 버퍼는 이 popstate가 소비)
    if (closers.length) {
      var fn = closers.pop();
      try { fn(); } catch (e) {}
      return;
    }
    // 오버레이 없음 → 사이트 이탈 시도. 외부 유입이면 종료 확인.
    if (exitArmed) {
      try { history.pushState({ cfExit: 1 }, ''); } catch (e) {}
      showExit();
    }
  });

  // 외부 유입 페이지에서만 버퍼 1개 push → 첫 뒤로가기를 가로챔
  if (isExternalEntry()) {
    exitArmed = true;
    try { history.pushState({ cfExit: 1 }, ''); } catch (e) {}
  }
})();

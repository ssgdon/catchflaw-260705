/* 캐치플로 사진 확대 보기 (상세 페이지) — FEEDBACK-2610 후속
   window.CF_IMGS(전체 사진 URL 배열)를 PC 1+4 그리드(.pc-gallery .pg-cell / .pg-count)·모바일 히어로 Swiper(.hotel-gallery .swiper-slide)에서
   눌렀을 때 전체 화면으로 열고 이전/다음(버튼·키보드·스와이프)·닫기(✕·배경·Esc·뒤로가기). 의존: backnav.js(CFNav, 선택) */
(function () {
  'use strict';
  var imgs = window.CF_IMGS || [];
  if (!imgs.length) return;
  var box = null, cur = 0;

  function build() {
    box = document.createElement('div');
    box.className = 'cf-lightbox';
    box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'true'); box.setAttribute('aria-label', '호텔 사진');
    box.innerHTML =
      '<div class="lb-dim"></div>' +
      '<button type="button" class="lb-close" aria-label="닫기">✕</button>' +
      '<button type="button" class="lb-prev" aria-label="이전 사진">‹</button>' +
      '<button type="button" class="lb-next" aria-label="다음 사진">›</button>' +
      '<div class="lb-stage"><img class="lb-img" alt=""></div>' +
      '<div class="lb-count"></div>';
    document.body.appendChild(box);
    box.querySelector('.lb-dim').addEventListener('click', close);
    box.querySelector('.lb-close').addEventListener('click', close);
    box.querySelector('.lb-prev').addEventListener('click', function () { go(-1); });
    box.querySelector('.lb-next').addEventListener('click', function () { go(1); });
    // 스와이프
    var sx = 0, sy = 0;
    box.addEventListener('touchstart', function (e) { var t = e.touches[0]; sx = t.clientX; sy = t.clientY; }, { passive: true });
    box.addEventListener('touchend', function (e) {
      var t = e.changedTouches[0], dx = t.clientX - sx, dy = t.clientY - sy;
      if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) go(dx < 0 ? 1 : -1);
    }, { passive: true });
  }

  function show(i) {
    cur = (i + imgs.length) % imgs.length;
    var img = box.querySelector('.lb-img');
    img.src = imgs[cur];
    img.alt = '호텔 사진 ' + (cur + 1);
    box.querySelector('.lb-count').textContent = (cur + 1) + ' / ' + imgs.length;
    box.querySelector('.lb-prev').hidden = box.querySelector('.lb-next').hidden = imgs.length < 2;
    // 이웃 미리 받기
    [cur + 1, cur - 1].forEach(function (k) { var p = new Image(); p.src = imgs[(k + imgs.length) % imgs.length]; });
  }
  function go(d) { show(cur + d); }

  function onKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); go(1); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); go(-1); }
  }
  var viaNav = false;
  function closeVisual() {
    if (!box) return;
    box.classList.remove('is-open');
    document.body.style.overflow = '';
    document.removeEventListener('keydown', onKey);
  }
  function close() {
    if (viaNav && window.CFNav) { viaNav = false; CFNav.pop(); }   // CFNav.pop → closeVisual
    else closeVisual();
  }
  function open(i) {
    if (!box) build();
    show(i || 0);
    box.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', onKey);
    box.querySelector('.lb-close').focus();
    if (window.CFNav) { viaNav = true; CFNav.push(function () { viaNav = false; closeVisual(); }); }
    if (typeof gtag === 'function') gtag('event', 'gallery_open', { index: i || 0, total: imgs.length });
  }

  // 진입점: PC 그리드 셀·장수 배지, 모바일 히어로 슬라이드(loop 복제 슬라이드도 data-i를 그대로 가짐)
  document.addEventListener('click', function (e) {
    var cell = e.target.closest('.pc-gallery .pg-cell');
    if (cell) { e.preventDefault(); open(parseInt(cell.getAttribute('data-i') || '0', 10)); return; }
    if (e.target.closest('.pc-gallery .pg-count')) { e.preventDefault(); open(0); return; }
    var slide = e.target.closest('.hotel-gallery .swiper-slide');
    if (slide) { e.preventDefault(); open(parseInt(slide.getAttribute('data-i') || '0', 10)); return; }
    var single = e.target.closest('#detail .visual > img');
    if (single) { e.preventDefault(); open(0); }
  });

  window.CFLightbox = { open: open, close: close };
})();

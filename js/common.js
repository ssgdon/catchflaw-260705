// CATCHFLAW common.js
// 페이지 공통 인터랙션은 각 페이지의 인라인 스크립트에 구현되어 있습니다.
// 이 파일은 전 페이지에서 참조되므로 404 방지 및 향후 공통 로직 확장용으로 유지합니다.

// 떠 있는 버튼(공유·위로·비교·비교함)이 본문을 가리지 않게: 아래로 스크롤하는 동안 html.is-scroll-down → 숨김, 위로 올리면 다시 (2026-10)
(function () {
  var last = window.pageYOffset || 0, acc = 0, hidden = false, root = document.documentElement;
  function set(h) { if (hidden !== h) { hidden = h; root.classList.toggle('is-scroll-down', h); } }
  window.addEventListener('scroll', function () {
    var y = window.pageYOffset || 0, dy = y - last; last = y;
    if (y < 120) { set(false); acc = 0; return; }            // 맨 위 근처에선 항상 보임
    acc = ((dy > 0) === (acc > 0)) ? acc + dy : dy;         // 같은 방향으로 누적, 방향 바뀌면 초기화
    if (acc > 24) set(true); else if (acc < -24) set(false); // 24px 이상 움직였을 때만 (미세 떨림 무시)
  }, { passive: true });
})();

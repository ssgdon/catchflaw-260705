/* jQuery를 defer로 싣기 위한 짝 — head()의 인라인 shim이 jQuery 로드 전에 들어온 $(function…) 호출을 window.__cfq에 모아 두면,
   이 파일이 DOMContentLoaded(모든 defer 스크립트가 실행된 뒤)에 진짜 jQuery.ready로 넘긴다(2026-10-20 속도).
   (jQuery는 defer 실행 중엔 DOM을 '준비됨'으로 보고 setTimeout으로 바로 실행하므로, 그대로 넘기면 swiper.js 같은 뒤쪽 defer보다 먼저 돌 수 있다.)
   규칙: 인라인 스크립트는 파싱 시점에 $(function){…}) 외의 jQuery를 쓰지 않는다(검색 페이지만 예외로 jQuery를 sync로 싣는다). */
(function () {
  var q = window.__cfq || [];
  window.__cfq = null;
  if (!window.jQuery || !q.length) return;
  function run() { for (var i = 0; i < q.length; i++) { try { window.jQuery(q[i]); } catch (e) { if (window.console) console.error(e); } } }
  if (document.readyState === 'loading' || document.readyState === 'interactive') document.addEventListener('DOMContentLoaded', run);
  else run();
})();

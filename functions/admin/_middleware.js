/* /admin/* 공통 문지기(2026-11-05) — 정적 껍데기(index.html·site.json)와 /admin/api/* 모두 여기를 먼저 지난다.
   Cloudflare Access 앱은 catchflaw.com/admin 에만 걸려 있어서, 같은 배포가 서빙되는 catchflaw-260705.pages.dev 와
   브랜치 미리보기(*.catchflaw-260705.pages.dev)는 Access를 거치지 않는다. 거기선 Cf-Access-Jwt-Assertion 헤더를
   아무 값으로나 붙여 보낼 수 있으므로, 관리자 경로는 Access가 앞을 막는 catchflaw.com 호스트에서만 내준다.
   (catchflaw.com 에선 Access가 로그인 안 된 요청을 엣지에서 302로 돌려보내 헤더 위조가 함수까지 오지 못한다.) */
const HOST = 'catchflaw.com';

export async function onRequest({ request, next }) {
  const url = new URL(request.url);
  if (url.hostname !== HOST) {
    return new Response('Not found', {
      status: 404,
      headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow' },
    });
  }
  if (!request.headers.get('Cf-Access-Jwt-Assertion')) {
    return new Response('Unauthorized', {
      status: 401,
      headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow' },
    });
  }
  return next();
}

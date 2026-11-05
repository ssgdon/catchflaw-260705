/* GET /admin/api/data[?day=YYYYMMDD] — 관리자 페이지 데이터(ADMIN-DESIGN §3, 2026-11-05)
   Cloudflare Pages Function. VM cron(pipeline/admin_export.py, 매일 09:20 KST)이 R2 비공개 버킷 catchflaw-admin에 올린 admin.json을 내준다.
   - 로그인: Cloudflare Access가 /admin/* 앞을 막는다(구글 로그인, 코드 없음). Access를 지난 요청에만 Cf-Access-Jwt-Assertion 헤더가 붙으므로
     헤더가 없으면 401(방어 2중 — JWT 서명 검증은 v2: https://<팀>.cloudflareaccess.com/cdn-cgi/access/certs).
     pages.dev·미리보기 주소는 Access 밖이라 functions/admin/_middleware.js가 catchflaw.com 외 호스트를 404로 막는다.
   - R2 바인딩: Pages 프로젝트 → Settings → Functions → R2 bucket bindings, 변수 이름 ADMIN_BUCKET → 버킷 catchflaw-admin.
   - ?day=YYYYMMDD면 그날 판(admin_YYYYMMDD.json, 최근 7판 보관). 없으면 503 {error:'no_data'} → 화면은 site.json만으로 일부를 그린다. */
function json(body, status) {
  return new Response(typeof body === 'string' ? body : JSON.stringify(body), {
    status: status || 200,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'private, no-store',
      'X-Robots-Tag': 'noindex, nofollow',
    },
  });
}

export async function onRequestGet({ request, env }) {
  if (!request.headers.get('Cf-Access-Jwt-Assertion')) return json({ error: 'unauthorized' }, 401);
  if (!env.ADMIN_BUCKET) return json({ error: 'no_binding' }, 503);
  const day = new URL(request.url).searchParams.get('day');
  if (day && !/^\d{8}$/.test(day)) return json({ error: 'bad_day' }, 400);
  const obj = await env.ADMIN_BUCKET.get(day ? `admin_${day}.json` : 'admin.json');
  if (!obj) return json({ error: 'no_data' }, 503);
  return json(await obj.text());
}

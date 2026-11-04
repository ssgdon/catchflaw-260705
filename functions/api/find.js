/* GET /api/find?q=… — 사이트 안 검색이 못 찾은 검색어를 구글 장소 검색으로 호텔에 연결 (SEARCH-2611, 2026-11-04)
   Cloudflare Pages Function. 우리 호텔 ID = 구글 장소 ID라 돌려준 id를 페이지가 HOTELS와 바로 맞춘다(js/search-ac.js remote()).
   - 키: Pages 프로젝트 설정 → Variables and Secrets(Production)의 PLACES_API_KEY(비밀). 없으면 503 no_key → 페이지는 예전처럼 동작.
   - 범위: 후쿠오카 사각형 안의 숙소(lodging)만. 밖이면 빈 목록.
   - 공유 짧은 링크(maps.app.goo.gl·goo.gl/maps·?cid=): 리다이렉트를 따라가 최종 주소만 돌려준다(장소 검색 호출 없음, 비용 0).
   - 남용 막기: 우리 사이트에서 부른 것만(Referer/Origin), 검색어 80자, 결과 7일 캐시. 하루 상한은 GCP 콘솔 할당량에서 건다.
   - 비용: Text Search(Pro 필드 — displayName·formattedAddress·location). 무료 사용량·단가는 GCP 요금표 기준. */
const BOX = { low: { latitude: 33.40, longitude: 130.15 }, high: { latitude: 33.80, longitude: 130.60 } };
const OK_ORIGIN = /^https:\/\/(www\.)?catchflaw\.com$|^https:\/\/([a-z0-9-]+\.)?catchflaw-260705\.pages\.dev$|^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/;
const SHORT = /^https?:\/\/(maps\.app\.goo\.gl|goo\.gl\/maps)\/|[?&]cid=\d/i;
const FOLLOW_HOST = /^(maps\.app\.goo\.gl|goo\.gl|maps\.google\.[a-z.]+|www\.google\.[a-z.]+|google\.[a-z.]+)$/i;

function json(body, status, maxAge) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': maxAge ? `public, max-age=${maxAge}` : 'no-store' },
  });
}

async function expand(u) {   // 짧은 링크 → 최종 구글 지도 주소 (최대 5번, 구글 도메인만 따라감)
  let cur = u;
  for (let i = 0; i < 5; i++) {
    const host = new URL(cur).hostname;
    if (!FOLLOW_HOST.test(host)) break;
    const r = await fetch(cur, { redirect: 'manual', headers: { 'User-Agent': 'Mozilla/5.0 (catchflaw link resolver)' } });
    const loc = r.headers.get('location');
    if (!loc) break;
    cur = new URL(loc, cur).href;
    if (/google\.[a-z.]+\/maps\/(place|search)\//.test(cur) || /!3d-?\d/.test(cur)) break;
  }
  return cur;
}

export async function onRequestGet({ request, env, waitUntil }) {
  const url = new URL(request.url);
  const q = (url.searchParams.get('q') || '').trim().slice(0, 300);
  if (!q) return json({ error: 'empty' }, 400);
  const from = request.headers.get('origin') || (request.headers.get('referer') || '').replace(/^(https?:\/\/[^/]+).*$/, '$1');
  if (!OK_ORIGIN.test(from)) return json({ error: 'origin' }, 403);

  if (SHORT.test(q)) {
    try { return json({ url: await expand(q) }, 200, 86400); } catch (e) { return json({ error: 'link' }, 502); }
  }
  if (q.length > 80) return json({ error: 'long' }, 400);
  if (!env.PLACES_API_KEY) return json({ error: 'no_key' }, 503);

  const cache = caches.default;
  const ck = new Request('https://catchflaw.com/api/find?c=' + encodeURIComponent(q.toLowerCase().replace(/\s+/g, ' ')));
  const hit = await cache.match(ck);
  if (hit) return hit;

  const r = await fetch('https://places.googleapis.com/v1/places:searchText', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Goog-Api-Key': env.PLACES_API_KEY,
      'X-Goog-FieldMask': 'places.id,places.displayName,places.formattedAddress,places.location',
    },
    body: JSON.stringify({
      textQuery: q, languageCode: 'ko', regionCode: 'KR', pageSize: 5,
      includedType: 'lodging', strictTypeFiltering: true,
      locationRestriction: { rectangle: BOX },
    }),
  });
  if (!r.ok) return json({ error: 'upstream', status: r.status }, 502);
  const j = await r.json();
  const places = (j.places || []).map((p) => ({
    id: p.id, name: (p.displayName || {}).text || '', addr: p.formattedAddress || '',
    lat: (p.location || {}).latitude, lng: (p.location || {}).longitude,
  }));
  const res = json({ places }, 200, 604800);
  waitUntil(cache.put(ck, res.clone()));
  return res;
}

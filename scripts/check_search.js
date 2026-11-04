/* 검색 회귀 검사 (SEARCH-2611, 2026-11-04) — 빌드 뒤 `node scripts/check_search.js` (check_links.py 다음)
   js/search-ac.js 를 그대로 node vm 에서 돌려 docs/data/search_index.js(CF_IDX)로 검사한다.
   ① scripts/search_cases.json 의 실검색 사례(top·has·sug·none)
   ② 자기 이름 검사: 모든 호텔의 한글 이름·영문 이름이 자기 자신을 1위로 찾는가
   실패가 있으면 exit 1. --idx <경로> 로 다른 인덱스 파일을 검사할 수 있다. */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const ROOT = path.resolve(__dirname, '..');
const arg = (k) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : null; };
const idxPath = arg('--idx') || path.join(ROOT, 'docs', 'data', 'search_index.js');

const ctx = { console };
ctx.window = ctx;
ctx.$ = () => ({ on() {} });
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(idxPath, 'utf8'), ctx);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'js', 'search-ac.js'), 'utf8'), ctx);
const A = ctx.CFAutocomplete, IDX = ctx.CF_IDX || [];
if (!A || !IDX.length) { console.error('검색 인덱스나 search-ac.js를 읽지 못했어요:', idxPath); process.exit(1); }

const { cases } = JSON.parse(fs.readFileSync(path.join(ROOT, 'scripts', 'search_cases.json'), 'utf8'));
const fails = [];
for (const c of cases) {
  const strong = A.match(c.q, 3).map((x) => x.u);
  const sug = strong.length ? strong : A.suggest(c.q, 3).map((x) => x.u);
  let ok;
  if (c.none) ok = strong.length === 0;
  else if (c.top) ok = strong[0] === c.top;
  else if (c.has) ok = strong.includes(c.has);
  else if (c.sug) ok = sug.includes(c.sug);
  if (!ok) fails.push(`사례 '${c.q}' → 찾음 [${strong.join(', ')}]${strong.length ? '' : ' 혹시 [' + sug.join(', ') + ']'} · 기대 ${c.none ? '없음' : (c.top || c.has || c.sug)}`);
}
let selfN = 0;
for (const h of IDX) {
  for (const nm of [h.t, h.en]) {
    if (!nm) continue;
    selfN++;
    const top = A.match(nm, 1)[0];
    if (!top || top.id !== h.id) fails.push(`자기 이름 '${nm}' → ${top ? top.t : '없음'}`);
  }
}
console.log(`check_search: 사례 ${cases.length} · 자기 이름 ${selfN} · 실패 ${fails.length}`);
if (fails.length) { console.log(fails.map((f) => '  ✗ ' + f).join('\n')); process.exit(1); }

/* 상세 페이지 공용 스크립트 — 2026-10-10 generate.py 인라인 블록(호텔마다 동일 31KB)에서 분리.
   페이지별 값은 상세 HTML의 window.QDATA_URL·QTOTAL·QSUBS·CF_HOTEL 등 인라인 변수로 받는다.
   (generate.py f-string이 아니므로 중괄호를 두 번 쓰지 않는다)
   2026-10-10 v3 디자인 시스템 병합: 리뷰 근거 시트(CF.sheet, #ov-review)·리뷰 항목(.rv) 마크업은 v3 기준 */
$(function(){
    $('.hotel-gallery').each(function(i, el){
        var cnt = el.querySelector('.gallery-count'), total = el.querySelectorAll('.swiper-slide').length;
        new Swiper(el, {slidesPerView:1, spaceBetween:0, loop:true,
            pagination:{el: el.querySelector('.swiper-pagination'), clickable:true},
            observer:true, observeParents:true,
            on:{slideChange:function(){ if(cnt) cnt.textContent=(this.realIndex+1)+' / '+total; }}
        });
    });
    $('.review-slider, #detail .hotel-slider, .yt-slider').each(function(i, el){
        new Swiper(el, {slidesPerView:'auto', spaceBetween:12, observer:true, observeParents:true});
    });

    // F36 메뉴(바텀 시트) JS는 site_header() 공통 컴포넌트에 포함

    // 공유(.btn-share)는 js/engage.js 에서 처리 (OS 공유시트 + 카카오 인앱 폴백)

    // F16+F21+F31: 산출 기준(basis) ? 토글 — 가드 없는 블록에서 바인딩(항상 실행). 모바일 탭 확실성 위해 preventDefault
    $('#detail').on('click', '.basis-toggle', function(e){
        e.preventDefault();
        $('.disappear .basis-fold').toggleClass('is-open');
    });

    // F27: 상대시간 뱃지 — 클라이언트 계산(로드 시점 기준, 빌드 고정 아님). <7일 N일 전 / <35일 N주 전 / <12개월 N개월 전 / 그 외 N년 전
    window.CF_rel = function(iso){
        if (!iso) return '';
        var t = Date.parse(iso.length > 10 ? iso : iso + 'T00:00:00');
        if (isNaN(t)) return '';
        var days = Math.floor((Date.now() - t) / 86400000);
        if (days < 0) days = 0;
        if (days < 7) return (days || 0) + '일 전';
        if (days < 35) return Math.floor(days / 7) + '주 전';
        var mon = Math.floor(days / 30);
        if (mon < 12) return mon + '개월 전';
        return Math.floor(days / 365) + '년 전';
    };
    // 서버 렌더된 FAQ 미리보기 뱃지 채우기 (동적 시트 카드는 렌더 시 inline 처리)
    $('.rel-badge[data-d]').each(function(){ var s = window.CF_rel($(this).data('d')); if (s) $(this).text(s); });

    // ───── 리뷰 근거 시트 (v3 §5-8 ①: A 페이지 시트 · H1 '청결 리뷰 11건' · PC 1032 2단, ←/→ 항목 이동) ─────
    //   모드 3개: is-cat(항목·소분류 칩) · is-dis(실망 리뷰 모아보기, PC 780) · is-faq(실전정보 근거, H3 질문 2줄, PC 780)
    //   열기·닫기·뒤로가기·ESC·포커스는 CF.sheet(js/backnav.js). 정렬 데이터 = 심각도 > 최신순
    if (!window.QDATA && !window.QDATA_URL) return;
    var $sheet = $("#ov-review"), curCat = null, curSub = null, krOnly = false, mode = 'cat';
    var qfull = false, qloading = false;   // R2 전체 인용문 로드 상태 (REVIEW-LAZYLOAD §C)

    function toast(msg){ CF.toast(msg); }   // 토스트 1벌(js/backnav.js)
    // 첫 '모두 보기'/한국인필터 시 호텔 전체 인용문 JSON을 R2에서 1회 fetch → QDATA 교체(이후 탭 전환 즉시)
    function loadFull(cb){
        if (qfull || !window.QFULL) { cb && cb(); return; }
        if (qloading) return;
        qloading = true; render();
        fetch(window.QFULL, {cache: 'force-cache'})
            .then(function(r){ return r.ok ? r.json() : Promise.reject(r.status); })
            .then(function(j){
                if (window.QCUT) Object.keys(j).forEach(function(c){ j[c] = (j[c] || []).filter(function(q){ return (q.d || '') >= window.QCUT; }); });
                window.QDATA = j; qfull = true; qloading = false; cb && cb(); })
            .catch(function(){ qloading = false; render(); toast('전체 리뷰를 불러오지 못했어요'); });
    }
    // 임베드 인용문(카테고리당 40건)은 같은 사이트의 정적 JSON(data/q/{pid}.json) — 상세 HTML을 가볍게 하려고(구글 크롤 비용)
    // 2026-10-10 분리. 페이지가 뜬 뒤 미리 받아 두고, 받기 전에 팝업을 열면 '불러오는 중'을 보였다가 그린다.
    var qembed = null;
    function loadEmbed(){
        if (window.QDATA) return Promise.resolve();
        if (!qembed) qembed = fetch(window.QDATA_URL, {cache: 'force-cache'})
            .then(function(r){ return r.ok ? r.json() : Promise.reject(r.status); })
            .then(function(j){ if (!window.QDATA) window.QDATA = j; })
            .catch(function(){ qembed = null; if (!window.QDATA) window.QDATA = {}; });   // 실패해도 '리뷰 전체 보기'(R2)는 동작
        return qembed;
    }
    if (!window.QDATA) setTimeout(loadEmbed, 1200);

    function esc(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
    function subKo(s){ return (window.QSUBKO && window.QSUBKO[s]) || s; }   // '동네 분위기' → '밤길·동네 분위기' 등 화면 표기
    function catKo(c){ return (window.CAT_KO && window.CAT_KO[c]) || c; }    // 표시만 순화, curCat은 내부키 유지
    function emph(s){ return esc(s).replace(/\*\*(.+?)\*\*/g, '<mark>$1</mark>').replace(/\*\*/g, ''); }   // 키워드 = 형광펜(--hl) + 잉크
    function langLabel(l){
        if (!l) return '';
        var M = {ko:'한국어', ja:'일본어', en:'영어'};
        if (M[l]) return M[l];
        if (l.indexOf('zh') === 0) return '중국어';
        return l.toUpperCase();
    }
    function fmtDate(d){ d = String(d||'').slice(0,10); return d ? d.replace(/-/g,'. ') : ''; }   // 'YYYY. MM. DD'(UI-STANDARDS §7) — FAQ 근거도 같은 표기
    // 리뷰 항목(§6-5): 작성자 16/600 + 심각도 태그 → 메타 14(별점·출처·언어) → 본문 16/1.5 → 날짜·소분류·상대시간 14 → 텍스트 링크 줄. 상자 없이 여백 32
    function item(o){
        var star = o.st ? '<span class="rv-star" role="img" aria-label="별점 ' + o.st + '점"><i style="width:' + (o.st*20) + '%"></i></span>' : '';
        var lang = langLabel(o.l);
        return '<li class="rv">'
            + '<div class="rv-top"><span class="rv-name">' + esc(o.n) + '</span>' + (o.g ? '<span class="rv-tag is-' + (o.g === '심각' ? 'danger' : 'warning') + '">' + o.g + '</span>' : '') + '</div>'
            + '<div class="rv-meta">' + star + '<span>' + esc(o.o) + '</span>' + (lang ? '<span>' + lang + ' 리뷰</span>' : '') + '</div>'
            + '<p class="rv-text clamp">' + o.text + '</p>'
            + '<div class="rv-date">' + esc(fmtDate(o.d)) + (o.s ? ' · ' + esc(subKo(o.s)) : '') + relSpan(o.d) + '</div>'
            + '<div class="rv-foot">' + origLink(o.u) + (o.rep || '') + (o.full ? '<button type="button" class="rv-act rv-more" aria-expanded="false">전체 리뷰</button>' : '') + '</div>'
            + (o.full ? '<div class="rv-full" hidden>' + o.full + '</div>' : '')
            + '</li>';
    }
    function card(q){
        var full = '';
        if (q.tf) full += '<p class="rv-full-t">전체 리뷰 (번역)</p><p class="rv-full-x">' + esc(q.tf) + '</p>';
        if (q.of && q.of !== q.tf) full += '<p class="rv-full-t">원문</p><p class="rv-full-x">' + esc(q.of) + '</p>';
        return item({n: q.n, g: q.g, st: q.st, o: q.o, l: q.l, text: emph(q.q), d: q.d, s: q.s, u: q.u, rep: q.f ? repBtn(q) : '', full: full});
    }
    // 오분류 신고 버튼 (FEEDBACK-2610 §13, js/report.js) — 대분류는 소분류에서(실망 모아보기는 여러 항목이 섞임)
    function repBtn(q){
        var c = (window.QSUBCAT && window.QSUBCAT[q.s]) || (curCat !== '__dis__' ? curCat : '');
        return '<button type="button" class="rv-act rep-btn" data-fid="' + esc(q.f) + '" data-cat="' + esc(c) + '" data-sub="' + esc(q.s) + '" data-grade="' + esc(q.g) + '">분류가 이상해요</button>';
    }
    // F32+F39: 원문 링크 — 라벨 통일 "리뷰 원문 보기", 목적지는 저장 URL 그대로. URL 빈값이면 미출력
    function origLink(u){
        if (!u) return '';
        return '<a class="rv-act" href="' + esc(u) + '" target="_blank" rel="noopener">리뷰 원문 보기 ↗</a>';
    }
    // F27: 날짜 옆 상대 시간 (동적 렌더 — 로드시점 계산)
    function relSpan(d){ var s = window.CF_rel ? window.CF_rel(String(d||'').slice(0,10)) : ''; return s ? ' · ' + s : ''; }

    // 실망 리뷰만(근거 줄): 전 카테고리 카드 중 심각 또는 재방문·추천 거부(rf) 리뷰를 리뷰 단위(r)로 묶는다 — 근거 줄 M건과 같은 집합
    function disList(){
        var seen = {}, out = [];
        Object.keys(window.QDATA || {}).forEach(function(c){
            (window.QDATA[c] || []).forEach(function(q){
                if (!(q.g === '심각' || q.rf)) return;
                var k = q.r || (q.n + '|' + q.d + '|' + q.o);
                if (seen[k]) { if (q.g === '심각' && seen[k].g !== '심각') { out[out.indexOf(seen[k])] = q; seen[k] = q; } return; }
                seen[k] = q; out.push(q);
            });
        });
        out.sort(function(a, b){ return ((b.g === '심각') - (a.g === '심각')) || (b.d > a.d ? 1 : b.d < a.d ? -1 : 0); });
        return out;
    }
    function setMode(m){
        mode = m;
        $sheet.removeClass('is-cat is-dis is-faq').addClass('is-' + m).attr('aria-labelledby', m === 'faq' ? 'rs-ft' : 'rs-t');
    }
    function renderDis(){
        var list = disList();
        if (krOnly) list = list.filter(function(q){ return q.l === 'ko'; });
        var M = (window.QDIS && window.QDIS.n) || 0;
        $('#sheet-cat').text('실망');
        $('#sheet-cnt').text(qloading ? '불러오는 중…' : (!krOnly && qfull && M && M !== list.length) ? M + '건 중 ' + list.length + '건' : list.length + '건');
        $('#sheet-list').html(list.map(card).join('') || '<li class="rs-empty">' + (qloading ? '리뷰를 불러오는 중…' : '실망 리뷰가 없어요') + '</li>');
        $('#sheet-chips').html('<p class="rs-note">심각한 문제를 겪었거나, 불만과 함께 다시 안 가겠다고 한 리뷰예요</p>');
        $('#sheet-kr').toggleClass('on', krOnly).attr('aria-pressed', krOnly ? 'true' : 'false');
        after();
    }
    function render(){
        if (!window.QDATA) { $('#sheet-list').html('<li class="rs-loading">리뷰를 불러오는 중…</li>'); after(); return; }
        if (curCat === '__dis__') return renderDis();
        var T = (window.QTOTAL && window.QTOTAL[curCat]) || null;
        var base = (window.QDATA[curCat] || []);
        var list = krOnly ? base.filter(function(q){ return q.l === 'ko'; }) : base;
        var filtered = curSub ? list.filter(function(q){ return q.s === curSub; }) : list;
        // 건수: 전체언어 & 미로드 상태면 실제 총건수(QTOTAL), 그 외(로드완료·한국인필터)는 현재 리스트 기준
        var useReal = (!qfull && !krOnly && T);
        function cnt(sub){
            if (useReal) return sub ? (T.s[sub] || 0) : T.t;
            return (sub ? list.filter(function(q){ return q.s === sub; }) : list).length;
        }
        $('#sheet-cat').text(catKo(curCat));
        $('#sheet-cnt').text(cnt(curSub) + '건');
        $('#rs-h').text(catKo(curCat) + ' 리뷰 ' + cnt(curSub) + '건');
        var cards = filtered.map(card).join('');
        // 모두 보기: 아직 전체 로드 전이고 임베드가 실제 총건보다 적으면 목록 끝에 회색 버튼 '청결 리뷰 11건 모두 보기'
        var more = '';
        if (!qfull && T && base.length < T.t) {
            more = '<li class="rs-more"><button type="button" class="btn-gray rs-more-btn"' + (qloading ? ' disabled' : '') + '>'
                 + (qloading ? '불러오는 중…' : esc(curSub ? subKo(curSub) : catKo(curCat)) + ' 리뷰 ' + cnt(curSub) + '건 모두 보기') + '</button></li>';
        }
        $('#sheet-list').html((cards ||
            '<li class="rs-empty">' + (krOnly ? '이 항목엔 한국어 리뷰가 없어요' : '이 불만을 언급한 리뷰가 없어요') + '</li>') + more);
        var subs = window.QSUBS[curCat] || [];
        var chips = ['<button type="button" class="chip-view rs-chip' + (!curSub ? ' on' : '') + '" data-sub="" aria-pressed="' + !curSub + '">전체 ' + cnt(null) + '</button>'];
        subs.forEach(function(s){
            var n = cnt(s);
            if (!n) return;
            chips.push('<button type="button" class="chip-view rs-chip' + (curSub === s ? ' on' : '') + '" data-sub="' + esc(s) + '" aria-pressed="' + (curSub === s) + '">' + esc(subKo(s)) + ' ' + n + '</button>');
        });
        $('#sheet-chips').html(chips.join(''));
        $('#sheet-kr').toggleClass('on', krOnly).attr('aria-pressed', krOnly ? 'true' : 'false');
        after();
    }
    function after(){ renderTabs(); renderSide(); $sheet.find('.rs-body').scrollTop(0); CF.sheet.update($sheet[0]); }
    function catN(c){ var T = window.QTOTAL && window.QTOTAL[c]; return T ? T.t : ((window.QDATA && window.QDATA[c]) || []).length; }
    // 모바일 항목 전환 = 밑줄 탭 줄(옛 ‹ › 원형 버튼 대체). 리뷰가 있는 항목만
    function renderTabs(){
        if (mode !== 'cat') { $('#rs-tabs').empty(); return; }
        $('#rs-tabs').html(Object.keys(window.QSUBS).filter(function(c){ return c === curCat || catN(c); }).map(function(c){
            var on = c === curCat;
            return '<button type="button" class="rs-tab' + (on ? ' on' : '') + '" role="tab" aria-selected="' + on + '" data-cat="' + esc(c) + '">' + esc(catKo(c)) + '</button>';
        }).join(''));
        var t = $('#rs-tabs .rs-tab.on')[0];
        if (t) t.parentNode.scrollLeft = Math.max(0, t.offsetLeft - 24);
    }
    // PC 왼쪽 열: 호텔명 + 항목 6행(점 + 이름 + 결론 + 건수) — 누르면 그 항목 리뷰로 (Airbnb 리뷰 팝업 패턴)
    function renderSide(){
        if (mode !== 'cat') return;
        var Q = window.QCAT || {};
        function vlab(v){ return v < 25 ? '거의 없음' : v < 45 ? '적은 편' : v < 55 ? '평균 수준' : v < 70 ? '많은 편' : '많음'; }   // cat_verdict와 같은 구간
        var rows = Object.keys(window.QSUBS).map(function(c){
            var n = catN(c);
            var sc = Q[c] || [0, 'safe'];
            var chip = window.QCHIP && window.QCHIP[c];          // 칩 전용 대분류(안전): 점수 대신 심각 건수 문구
            if (chip) sc = [0, chip[1] === 'alert' ? 'danger' : 'safe'];
            return '<button type="button" class="ss-cat' + (c === curCat ? ' is-on' : '') + '" data-cat="' + esc(c) + '"' + (n ? '' : ' disabled') + ' aria-pressed="' + (c === curCat) + '">'
                + '<span class="ss-dot is-' + sc[1] + '"></span>'
                + '<span class="ss-name">' + esc(catKo(c)) + '</span>'
                + '<span class="ss-score">' + (chip ? esc(chip[0]) : '불만 ' + vlab(sc[0])) + '</span>'
                + '<span class="ss-cnt">' + n + '건</span></button>';
        }).join('');
        var hn = (window.CF_HOTEL && window.CF_HOTEL.name) || '';
        $('#sheet-side').html((hn ? '<p class="ss-hotel">' + esc(hn) + '</p>' : '')
            + '<p class="ss-sub">항목을 고르면 ' + esc(window.QPER || '최근 1년') + ' 리뷰 중 그 불만이 언급된 리뷰만 보여드려요</p>'
            + '<div class="ss-list">' + rows + '</div>'
            + '<p class="ss-note">불만 정도는 후쿠오카 호텔 평균과 비교한 결과예요 · 인용문은 리뷰 원문 발췌이며 작성자 이름은 가렸어요</p>');
    }
    function show(opener){
        CF.sheet.open($sheet[0], {opener: opener, focus: mode === 'faq' ? '#rs-ft' : '#rs-t',
            keys: function(d){ if (mode === 'cat') shift(d); }});   // PC ←/→ 항목 이동(UI-STANDARDS §13)
    }
    // F28: FAQ 근거 = 리뷰 항목과 같은 모양(이름·별점·출처·언어·인용·날짜+상대시간·원문링크·번역 펼치기). 심각도는 해당 없음
    function faqCard(e){
        return item({n: e.n || '투숙객', st: parseInt(e.st, 10) || 0, o: e.o || 'Google', l: e.l, text: e.qh || emph(e.q), d: e.d, u: e.u,
                     full: e.tf ? '<p class="rv-full-t">전체 리뷰 (번역)</p><p class="rv-full-x">' + esc(e.tf) + '</p>' : ''});   // qh = 서버 하이라이트 HTML(F23)
    }
    // FAQ-LAZYLOAD: 근거 시트 소스 = R2 faq_reviews/{pid}.json (토픽별 최근1년 매칭 전체, 토픽당 최대 60건).
    // 전체 JSON 1회 fetch 후 캐싱(토픽 전환 시 재요청 없음). 실패/CORS 시 인라인 FAQEVID 폴백 — 빈 시트 금지.
    var faqFull = null, faqFetchP = null, faqSeq = 0;
    function maskName(s){
        s = String(s || '').trim();
        return s ? Array.from(s)[0] + '**' : '투숙객';
    }
    // R2 카드(rn 원명) → faqCard 입력형 변환. rn은 반드시 마스킹(LEGAL §3). qh 없음 → faqCard가 emph(q)로 렌더.
    function faqNorm(r){
        return {n: maskName(r.rn), st: r.st, o: r.o || 'Google', u: r.u || '',
                l: r.l || '', q: r.q || '', d: r.d || '', tf: r.tf || ''};
    }
    function faqFetch(){
        if (faqFetchP) return faqFetchP;
        if (!window.CF_FAQR) return Promise.reject();
        faqFetchP = fetch(window.CF_FAQR, {cache: 'force-cache'})
            .then(function(r){ return r.ok ? r.json() : Promise.reject(r.status); })
            .then(function(j){ faqFull = j; return j; })
            .catch(function(e){ faqFetchP = null; return Promise.reject(e); });
        return faqFetchP;
    }
    // H3 정보형 머리: 질문(최대 2줄) + '리뷰 12건 · 최근 1년 투숙객 리뷰'
    function faqList(topic, q, cnt, cards){
        $('#rs-ft').text(q || '');
        $('#rs-fs').text(cnt ? '리뷰 ' + cnt + '건 · 최근 1년 투숙객 리뷰' : '');
        $('#sheet-list').html(cards || '<li class="rs-empty">리뷰 근거가 없어요</li>');
        $sheet.find('.rs-body').scrollTop(0);
        CF.sheet.update($sheet[0]);
    }
    function faqRender(topic, q){
        var t = faqFull && faqFull[topic];
        if (t && t.r && t.r.length) {
            faqList(topic, q, t.n || t.r.length, t.r.map(faqNorm).map(faqCard).join(''));
        } else {
            if (!window.FAQEVID && window.FAQEVID_URL) {   // 폴백 근거 8개도 같은 사이트 정적 JSON — R2 실패 때만 받는다(2026-10-10)
                fetch(window.FAQEVID_URL).then(function(r){ return r.ok ? r.json() : {}; })
                    .catch(function(){ return {}; })
                    .then(function(j){ window.FAQEVID = j || {}; faqRender(topic, q); });
                return;
            }
            var list = (window.FAQEVID && window.FAQEVID[topic]) || [];   // 폴백: 근거 8개
            faqList(topic, q, list.length, list.map(faqCard).join(''));
        }
    }
    function faqOpen(topic, q, opener){
        setMode('faq');
        $('#sheet-chips').empty(); $('#rs-tabs').empty();
        var seq = ++faqSeq;   // 로딩 중 토픽 전환/재오픈 시 낡은 응답 렌더 방지
        if (faqFull) faqRender(topic, q);
        else {
            faqList(topic, q, 0, '<li class="rs-loading">리뷰를 불러오는 중…</li>');
            faqFetch()
                .then(function(){ if (seq === faqSeq) faqRender(topic, q); })
                .catch(function(){ if (seq === faqSeq) faqRender(topic, q); });
        }
        show(opener);
    }
    $(document).on('click', '[data-act="faq-more"]', function(){ faqOpen($(this).data('topic'), $(this).data('q'), this); });
    function open(cat, sub, opener){
        setMode('cat');
        curCat = cat; curSub = sub || null; krOnly = false;
        render();
        if (!window.QDATA) loadEmbed().then(render);
        show(opener);
    }
    function openDis(opener){
        setMode('dis');
        curCat = '__dis__'; curSub = null; krOnly = false;
        if (!qfull) loadFull(render); else render();   // 임베드는 카테고리당 40건 상한 → 전체 파일 먼저
        show(opener);
    }
    $(document).on('click', '.ev-row[data-dis]', function(){ openDis(this); });
    $(document).on('click', '.stat-count.has-reviews', function(){
        open($(this).data('cat'), $(this).data('sub'), this);
    });
    $(document).on('click', '[data-act="rv-more"]', function(){ open($(this).data('cat'), null, this); });
    $sheet.on('click', '.rs-more-btn', function(){ loadFull(render); });
    $sheet.on('click', '.rs-chip', function(){ curSub = $(this).data('sub') || null; render(); });
    // 한국인 리뷰만: 정확한 한국어 총건 위해 미로드 상태면 전체 먼저 로드
    $sheet.on('click', '#sheet-kr', function(){
        krOnly = !krOnly;
        if (krOnly && !qfull) loadFull(render); else render();
    });
    var CATLIST = Object.keys(window.QSUBS);
    function shift(dir){
        var i = (CATLIST.indexOf(curCat) + dir + CATLIST.length) % CATLIST.length;
        curCat = CATLIST[i]; curSub = null; render();
    }
    $sheet.on('click', '.ss-cat, .rs-tab', function(){ curCat = $(this).data('cat'); curSub = null; render(); });
    $sheet.on('click', '.rv-more', function(){
        var $b = $(this), $li = $b.closest('.rv'), $full = $li.find('.rv-full');
        var opened = !$full.prop('hidden');
        $full.prop('hidden', opened);
        $b.toggleClass('is-open', !opened).attr('aria-expanded', !opened);
        $li.find('.rv-text').toggleClass('clamp', opened);
    });
});

// ───── 소셜 후기 (SOCIAL): 네이버 블로그 시트 + 유튜브 lite-embed ─────
$(function(){
    // 블로그: 카드 탭 → 페이지 시트 iframe (원본 그대로, X·딤·뒤로가기로 즉시 복귀 — CF.sheet)
    var bs = document.getElementById("ov-blog");
    $(document).on('click', '.nb-card', function(){
        if (!bs) return;
        var u = $(this).data('url'), t = $(this).data('title');
        if (typeof gtag === 'function') {
            var hh = window.CF_HOTEL || {};
            gtag('event', 'blog_open', {hotel_name: hh.name || '', hotel_id: hh.pid || '', blog_url: u});
        }
        $('#bs-link').attr('href', u);
        CF.sheet.open(bs, {opener: this, onClose: function(){ setTimeout(function(){ $('#bs-frame').attr('src', 'about:blank'); }, 250); }});
        $('#bs-frame').attr({src: u, title: t || '네이버 블로그 후기'});   // 시트를 연 뒤에(열 때 body 끝으로 옮기면 iframe이 다시 읽힘)
    });
    // 블로그 더보기: 숨긴 카드 전체 펼침 (기본 3 → 최대 9)
    $(document).on('click', '[data-act="nb-more"]', function(){
        $('.nb-card.nb-hidden').removeClass('nb-hidden');
        $(this).remove();
    });

    // 유튜브: 썸네일 탭 → 그 자리에서 플레이어 교체(자동재생, 이탈 없음)
    $(document).on('click', '.yt-card', function(){
        var $c = $(this);
        if ($c.hasClass('is-playing')) return;
        var vid = $c.data('vid');
        if (typeof gtag === 'function') {
            var hh2 = window.CF_HOTEL || {};
            gtag('event', 'video_play', {hotel_name: hh2.name || '', hotel_id: hh2.pid || '', video_id: vid, video_title: $c.data('title') || ''});
        }
        $c.addClass('is-playing');
        $c.find('.yt-thumb').html('<iframe src="https://www.youtube-nocookie.com/embed/' + vid
            + '?autoplay=1&playsinline=1&rel=0" title="YouTube" frameborder="0" '
            + 'allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>');
    });
});

// ───── 리스크 아코디언 + 레이더 칩 + 한국인 필터 (§2-e·§3-b·§4·§5) ─────
$(function(){
    var $sect = $('#risk-detail');
    if (!$sect.length) return;

    // ── 월별 불만 리뷰 비율 라인차트 공통 생성 헬퍼 (카테고리·전체 공용) ──
    function makeTrendChart(canvasId, d){
        var el = document.getElementById(canvasId); if (!el || !window.Chart || !d) return;
        Chart.defaults.font.size = 14;
        var ctx = el.getContext('2d');
        var gW = ctx.createLinearGradient(0,0,0,130); gW.addColorStop(0,CF.rgba('--warning',.22)); gW.addColorStop(1,CF.rgba('--warning',.02));
        var gC = ctx.createLinearGradient(0,0,0,130); gC.addColorStop(0,CF.rgba('--danger',.22)); gC.addColorStop(1,CF.rgba('--danger',.02));
        var n = d.m.length, pr = Array(n).fill(0); pr[n-1] = 3;
        new Chart(ctx, {type:'line', data:{labels:d.m, datasets:[
            {label:'심각', data:d.c, borderColor:CF.tok('--danger'), backgroundColor:gC, fill:'origin', tension:.35, borderWidth:2, pointRadius:pr, pointBackgroundColor:CF.tok('--danger'), stack:'risk'},
            {label:'주의', data:d.w, borderColor:CF.tok('--warning'), backgroundColor:gW, fill:'-1', tension:.35, borderWidth:2, pointRadius:pr, pointBackgroundColor:CF.tok('--warning'), stack:'risk'},
            {label:'후쿠오카 평균', data:d.a, borderColor:CF.tok('--ink-4'), borderDash:[4,4], borderWidth:1.5, pointRadius:0, fill:false, tension:.35, stack:'avg'}]},
          options:{responsive:true, maintainAspectRatio:false, interaction:{mode:'index', intersect:false},
            plugins:{legend:{display:false}, tooltip:{displayColors:false, backgroundColor:CF.tok('--surface-card'), titleColor:CF.tok('--ink'), bodyColor:CF.tok('--ink-3'),
                borderColor:CF.tok('--line-strong'), borderWidth:1, cornerRadius:10, padding:10, footerColor:CF.tok('--ink'), footerFont:{weight:'bold'},
                callbacks:{label:function(t){return t.dataset.label+' '+t.parsed.y.toFixed(1)+'%';},
                    footer:function(items){var s=0; items.forEach(function(it){if(it.dataset.stack==='risk') s+=it.parsed.y;}); return '합계 '+s.toFixed(1)+'%';}}}},
            scales:{x:{grid:{display:false}, ticks:{font:{size:13}, color:CF.tok('--ink-3'), maxRotation:0, autoSkip:true, maxTicksLimit:7}},
                    y:{beginAtZero:true, stacked:true, grid:{color:CF.tok('--line')}, border:{display:false},
                       ticks:{font:{size:13}, color:CF.tok('--ink-3'), maxTicksLimit:4, callback:function(v){return v+'%';}}}}}});
    }


    // F7+F24: 월별 트렌드 폴드(전체·카테고리 공용) — 기본 접힘, 펼칠 때 1회 지연 렌더(0폭 canvas 함정 회피)
    var allTrendInited = false;
    var trendInited = {};
    $('#detail').on('click', '.trend-fold-btn', function(){
        var $fold = $(this).closest('.trend-fold');
        $fold.toggleClass('is-open');
        if (!$fold.hasClass('is-open') || !window.TRENDC || !window.Chart) return;
        if ($fold.find('#cat-trend-all').length) {
            if (!allTrendInited && TRENDC['all']) { allTrendInited = true; makeTrendChart('cat-trend-all', TRENDC['all']); }
            return;
        }
        var ci = $fold.data('ci');
        if (ci !== undefined && !trendInited[ci] && TRENDC[ci]) {
            trendInited[ci] = 1; makeTrendChart('cat-trend-'+ci, TRENDC[ci]);
        }
    });

    // 아코디언 재오픈 시: 이미 펼쳐둔 폴드가 있는데 차트 미생성이면 보완 초기화 (F24 가드)
    function initCatTrend($item){
        var $fold = $item.find('.trend-fold.is-open'); if (!$fold.length) return;
        var ci = $fold.data('ci'); if (ci === undefined || trendInited[ci] || !window.TRENDC || !window.Chart || !TRENDC[ci]) return;
        trendInited[ci] = 1;
        makeTrendChart('cat-trend-'+ci, TRENDC[ci]);
    }

    // 아코디언 토글 (헤더 클릭). sticky 스택은 CSS가 담당.
    $sect.on('click', '.risk-acc-head', function(){
        var $item = $(this).closest('.risk-acc-item');
        $item.toggleClass('is-open');
        if ($item.hasClass('is-open')) { initCatTrend($item); if (window.CF_qmore) CF_qmore($item[0]); }   // 펼칠 때만 init
    });

    // F12 FAQ 필터 탭: 그룹별 카드 표시 토글 (전체=data-g 빈값)
    $('#hotel-faq').on('click', '.faq-tab', function(){
        var g = String($(this).data('g') || '');
        $('#hotel-faq .faq-tab').removeClass('is-on');
        $(this).addClass('is-on');
        $('#hotel-faq .faq-card').each(function(){
            $(this).toggle(!g || $(this).data('group') === g);
        });
    });
    // F18 FAQ 카드 접힘/펼침 — Q줄 클릭은 토글(펼침 상태에서 접기 가능)
    $('#hotel-faq').on('click', '.faq-q', function(e){
        $(this).closest('.faq-card').toggleClass('is-open');
        e.stopPropagation();   // 카드 레벨 핸들러 중복 방지
    });
    // F29 접힘 상태 = 카드 박스 전체가 클릭 영역. 펼친 상태에선 내부 인터랙션(더보기·링크) 보존
    $('#hotel-faq').on('click', '.faq-card', function(){
        if (!$(this).hasClass('is-open')) $(this).addClass('is-open');
    });

    // 특정 카테고리 열고 그 위치로 스크롤 (칩·캔버스 공용)
    function openAndScroll(id){
        var $item = $('#' + id);
        if (!$item.length) return;
        $item.addClass('is-open');
        initCatTrend($item); if (window.CF_qmore) CF_qmore($item[0]);
        // 이동 오프셋(탭 48 + 헤더 숨김/보임)은 상세 공용 CF_jump가 계산(DETAIL_TABS_JS)
        window.CF_jump($item[0], 8);
    }
    $('.radar-cats').on('click', '.radar-cat', function(){
        openAndScroll($(this).data('target'));
    });
    // 실망 확률 근거 줄('심각 리뷰 벌레 3건' 등) → 해당 카테고리 아코디언을 열고 그 소분류 행으로 스크롤·잠시 강조
    $('#detail').on('click', '.ev-row[data-target]', function(e){
        e.preventDefault();
        var t = String($(this).data('target') || ''), sub = String($(this).data('sub') || '');
        var $item = $('#' + t); if (!$item.length) return;
        $item.addClass('is-open'); initCatTrend($item); if (window.CF_qmore) CF_qmore($item[0]);
        var $row = sub ? $item.find('.stat-row').filter(function(){ return $(this).attr('data-sub') === sub; }).first() : $();
        var $to = $row.length ? $row : $item;
        setTimeout(function(){   // 본문(display:none → block)이 그려진 뒤에 위치를 재야 행 좌표가 맞는다
            window.CF_jump($to[0], 8);
            if ($row.length) { $row.addClass('is-flash'); setTimeout(function(){ $row.removeClass('is-flash'); }, 2200); }
        }, 60);
    });
    // 레이더 캔버스 클릭 → nearest 카테고리 아코디언 열기
    var chartEl = document.getElementById('radar');
    if (chartEl && window.Chart) {
        chartEl.addEventListener('click', function(e){
            var ch = (Chart.getChart && Chart.getChart(chartEl)) || null;
            if (!ch) return;
            var pts = ch.getElementsAtEventForMode(e, 'nearest', {intersect:false}, true);
            if (!pts || !pts.length) return;
            var idx = pts[0].index;                 // CATS 원본 인덱스와 동일 순서
            openAndScroll('risk-' + idx);
        });
    }

    // 초기 열림(1위) 카테고리 차트 즉시 init
    initCatTrend($sect.find('.risk-acc-item.is-open'));
});


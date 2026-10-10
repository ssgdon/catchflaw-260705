/* 상세 페이지 공용 스크립트 — 2026-10-10 generate.py 인라인 블록(호텔마다 동일 31KB)에서 분리.
   페이지별 값은 상세 HTML의 window.QDATA_URL·QTOTAL·QSUBS·CF_HOTEL 등 인라인 변수로 받는다.
   (generate.py f-string이 아니므로 중괄호를 두 번 쓰지 않는다) */
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
                new Swiper(el, {slidesPerView:'auto', spaceBetween:10, observer:true, observeParents:true});
            });

            // F36 드로어 JS는 site_header() 공통 컴포넌트에 포함 (상세·recent 공유)

            // ───── 플로팅: 공유 / 맨 위로 ─────
            $(window).on('scroll', function(){
                $('#float').toggleClass('is-active', $(window).scrollTop() > 50);
            });
            $('.btn-top').on('click', function(e){
                e.preventDefault();
                $('html, body').stop().animate({scrollTop: 0}, 400);
            });
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

            // ───── 리뷰 바텀시트 (심각도>최신순 정렬 데이터, 소분류 칩 필터) ─────
            if (!window.QDATA && !window.QDATA_URL) return;
            var $sheet = $('#review-sheet'), curCat = null, curSub = null, krOnly = false;
            var qfull = false, qloading = false;   // R2 전체 인용문 로드 상태 (REVIEW-LAZYLOAD §C)

            function toast(msg){
                var t = document.createElement('div'); t.className = 'cf-toast'; t.textContent = msg;
                document.body.appendChild(t);
                requestAnimationFrame(function(){ t.classList.add('show'); });
                setTimeout(function(){ t.classList.remove('show'); setTimeout(function(){ t.remove(); }, 300); }, 1800);
            }
            // 첫 '더보기'/한국인필터 시 호텔 전체 인용문 JSON을 R2에서 1회 fetch → QDATA 교체(이후 탭 전환 즉시)
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
            function emph(s){ return esc(s).replace(/\*\*(.+?)\*\*/g, '<span>$1</span>').replace(/\*\*/g, ''); }
            function langLabel(l){
                if (!l) return '';
                var M = {ko:'한국어', ja:'일본어', en:'영어'};
                if (M[l]) return M[l];
                if (l.indexOf('zh') === 0) return '중국어';
                return l.toUpperCase();
            }

            function card(q){
                var star = q.st ? '<div class="star"><i style="width:' + (q.st*20) + '%"></i></div>' : '';
                var band = q.g === '심각' ? 'danger' : 'warning';
                var hasFull = !!(q.tf || q.of);
                var full = '';
                if (hasFull) {
                    full = '<div class="full" hidden>'
                        + (q.tf ? '<div class="full-tit">전체 리뷰 (번역)</div><div class="full-txt">' + esc(q.tf) + '</div>' : '')
                        + (q.of && q.of !== q.tf ? '<div class="full-tit">원문</div><div class="full-txt">' + esc(q.of) + '</div>' : '')
                        + '</div>';
                }
                var foot = '<div class="item-foot">'
                    + origLink(q.o, q.u)
                    + (q.f ? repBtn(q) : '')
                    + (hasFull ? '<button type="button" class="expand-btn">전체 리뷰 <i>▾</i></button>' : '')
                    + '</div>';
                return '<li><div class="item">'
                    + '<div class="item-top"><div class="name">' + esc(q.n) + '</div>'
                    + '<div class="status"><div class="status-item ' + band + '">' + q.g + '</div></div></div>'
                    + '<div class="item-info">' + star + '<div class="web">' + esc(q.o) + '</div>' + (langLabel(q.l) ? '<span class="q-lang">' + langLabel(q.l) + '</span>' : '') + '</div>'
                    + '<div class="item-bottom"><div class="text clamp">' + emph(q.q) + '</div>'
                    + '<div class="date">' + esc((q.d||'').replace(/-/g,'. ')) + (q.s ? ' · ' + esc(subKo(q.s)) : '') + relSpan(q.d) + '</div></div>'
                    + foot + full
                    + '</div></li>';
            }
            // 오분류 신고 버튼 (FEEDBACK-2610 §13, js/report.js) — 대분류는 소분류에서(실망 모아보기는 여러 항목이 섞임)
            function repBtn(q){
                var c = (window.QSUBCAT && window.QSUBCAT[q.s]) || (curCat !== '__dis__' ? curCat : '');
                return '<button type="button" class="rep-btn" data-fid="' + esc(q.f) + '" data-cat="' + esc(c) + '" data-sub="' + esc(q.s) + '" data-grade="' + esc(q.g) + '">분류가 이상해요</button>';
            }
            // F32+F39: 원문 링크 — 라벨 통일 "리뷰 원문 보기", 목적지는 저장 URL 그대로. URL 빈값이면 미출력
            function origLink(o, u){
                if (!u) return '<span></span>';
                return '<a class="orig-link" href="' + esc(u) + '" target="_blank" rel="noopener">리뷰 원문 보기 ↗</a>';
            }
            // F27: 시트 카드 날짜 옆 상대 뱃지 (동적 렌더 — 로드시점 계산)
            function relSpan(d){ var s = window.CF_rel ? window.CF_rel(String(d||'').slice(0,10)) : ''; return s ? '<span class="rel-badge">' + s + '</span>' : ''; }

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
            function renderDis(){
                var list = disList();
                if (krOnly) list = list.filter(function(q){ return q.l === 'ko'; });
                var M = (window.QDIS && window.QDIS.n) || 0;
                $('#sheet-cat').text('실망');
                $('#sheet-cnt').text(qloading ? '불러오는 중…' : (!krOnly && qfull && M && M !== list.length) ? M + '건 중 ' + list.length + '건' : list.length + '건');
                $('#sheet-list').html(list.map(card).join('') || '<li class="sheet-empty">' + (qloading ? '리뷰를 불러오는 중…' : '실망 리뷰가 없어요') + '</li>');
                $('#sheet-chips').html('<div class="sheet-note">심각한 문제를 겪었거나, 불만과 함께 다시 안 가겠다고 한 리뷰예요</div>');
                $('#sheet-list').scrollTop(0);
                $('#sheet-kr').toggleClass('is-on', krOnly);
                renderSide();
            }
            function render(){
                if (!window.QDATA) { $('#sheet-list').html('<li class="sheet-loading">리뷰를 불러오는 중…</li>'); return; }
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
                $('#sheet-cat').text((window.CAT_KO && window.CAT_KO[curCat]) || curCat);   // 표시만 순화, curCat은 내부키 유지
                $('#sheet-cnt').text(cnt(curSub) + '건');
                var cards = filtered.map(card).join('');
                // 더보기: 아직 전체 로드 전이고 임베드가 실제 총건보다 적으면 리스트 하단에 노출
                var more = '';
                if (!qfull && T && base.length < T.t) {
                    var remain = cnt(curSub) - filtered.length;
                    more = '<li class="sheet-more"><button type="button" class="sheet-more-btn"' + (qloading ? ' disabled' : '') + '>'
                         + (qloading ? '불러오는 중…' : '리뷰 전체 보기' + (remain > 0 ? ' (+' + remain + '건)' : '')) + '</button></li>';
                }
                $('#sheet-list').html((cards ||
                    '<li class="sheet-empty">' + (krOnly ? '이 카테고리엔 한국어 리뷰가 없어요' : '이 소분류의 인용 리뷰가 없어요') + '</li>') + more);
                var subs = window.QSUBS[curCat] || [];
                var chips = ['<button type="button" class="sheet-chip' + (!curSub ? ' on' : '') + '" data-sub="">전체 ' + cnt(null) + '</button>'];
                subs.forEach(function(s){
                    var n = cnt(s);
                    if (!n) return;
                    chips.push('<button type="button" class="sheet-chip' + (curSub === s ? ' on' : '') + '" data-sub="' + esc(s) + '">' + esc(subKo(s)) + ' ' + n + '</button>');
                });
                $('#sheet-chips').html(chips.join(''));
                $('#sheet-list').scrollTop(0);
                $('#sheet-kr').toggleClass('is-on', krOnly);
                renderSide();
            }
            // PC 팝업 왼쪽: 6개 카테고리(위험도·리뷰 수) — 누르면 그 카테고리 근거 리뷰로 전환 (Airbnb 리뷰 팝업 패턴)
            function renderSide(){
                var Q = window.QCAT || {};
                function vlab(v){ return v < 25 ? '거의 없음' : v < 45 ? '적은 편' : v < 55 ? '평균 수준' : v < 70 ? '많은 편' : '많음'; }   // cat_verdict와 같은 구간
                var rows = Object.keys(window.QSUBS).map(function(c){
                    var T = window.QTOTAL && window.QTOTAL[c], n = T ? T.t : ((window.QDATA && window.QDATA[c]) || []).length;
                    var sc = Q[c] || [0, 'safe'];
                    var chip = window.QCHIP && window.QCHIP[c];          // 칩 전용 대분류(안전): 점수 대신 심각 건수 문구
                    if (chip) sc = [0, chip[1] === 'alert' ? 'danger' : 'safe'];
                    return '<button type="button" class="ss-cat' + (c === curCat ? ' is-on' : '') + '" data-cat="' + esc(c) + '"' + (n ? '' : ' disabled') + '>'
                        + '<span class="ss-dot is-' + sc[1] + '"></span>'
                        + '<span class="ss-name">' + esc((window.CAT_KO && window.CAT_KO[c]) || c) + '</span>'
                        + '<span class="ss-score is-' + sc[1] + '">' + (chip ? esc(chip[0]) : '불만 ' + vlab(sc[0])) + '</span>'
                        + '<span class="ss-cnt">' + n + '건</span></button>';
                }).join('');
                var hn = (window.CF_HOTEL && window.CF_HOTEL.name) || '';
                $('#sheet-side').html('<div class="ss-tit">리뷰 근거</div>' + (hn ? '<div class="ss-hotel">' + esc(hn) + '</div>' : '')
                    + '<div class="ss-sub">항목을 고르면 ' + esc(window.QPER || '최근 1년') + ' 리뷰 중 그 불만이 언급된 리뷰만 보여드려요</div>'
                    + '<div class="ss-list">' + rows + '</div>'
                    + '<div class="ss-note">불만 정도는 후쿠오카 호텔 평균과 비교한 결과예요 · 인용문은 리뷰 원문 발췌이며 작성자 이름은 가렸어요</div>');
            }

            function closeVisual(){
                $sheet.removeClass('is-open faq-mode');
                $('body').css('overflow', '');
                setTimeout(function(){ $sheet.prop('hidden', true); }, 300);
            }
            // F28: FAQ 시트 카드 = 리스크 시트 카드 동형(이름·별점·출처·언어칩·인용·날짜+상대뱃지·원문링크·tf 토글). grade만 미해당→생략.
            function faqCard(e){
                var stw = parseInt(e.st, 10) || 0;
                var star = stw ? '<div class="star"><i style="width:' + (stw*20) + '%"></i></div>' : '';
                var d = String(e.d||'').slice(2,10).replace(/-/g,'.');   // YY.MM.DD
                var hasFull = !!e.tf;
                var full = hasFull ? '<div class="full" hidden><div class="full-tit">전체 리뷰 (번역)</div><div class="full-txt">' + esc(e.tf) + '</div></div>' : '';
                var foot = '<div class="item-foot">' + origLink(e.o, e.u)
                    + (hasFull ? '<button type="button" class="expand-btn">전체 리뷰 <i>▾</i></button>' : '') + '</div>';
                return '<li><div class="item">'
                    + '<div class="item-top"><div class="name">' + esc(e.n || '투숙객') + '</div></div>'
                    + '<div class="item-info">' + star + '<div class="web">' + esc(e.o || 'Google') + '</div>' + (langLabel(e.l) ? '<span class="q-lang">' + langLabel(e.l) + '</span>' : '') + '</div>'
                    + '<div class="item-bottom"><div class="text clamp">' + (e.qh || emph(e.q)) + '</div>'   // qh = 서버 하이라이트 HTML(F23)
                    + '<div class="date">' + esc(d) + relSpan(e.d) + '</div></div>'
                    + foot + full
                    + '</div></li>';
            }
            // FAQ-LAZYLOAD: 더보기 시트 소스 = R2 faq_reviews/{pid}.json (토픽별 최근1년 매칭 전체, 토픽당 최대 60건).
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
            function faqList(topic, q, cnt, cards){
                $('#sheet-cat').text(q || '');
                $('#sheet-cnt').text(cnt ? cnt + '건' : '');
                $('#sheet-list').html(cards || '<li class="sheet-empty">리뷰 근거가 없어요</li>');
                $('#sheet-list').scrollTop(0);
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
            function faqOpen(topic, q){
                $sheet.addClass('faq-mode');
                $('#sheet-chips').empty();
                $sheet.prop('hidden', false);
                requestAnimationFrame(function(){ $sheet.addClass('is-open'); });
                $('body').css('overflow', 'hidden');
                if (window.CFNav) CFNav.push(closeVisual);
                var seq = ++faqSeq;   // 로딩 중 토픽 전환/재오픈 시 낡은 응답 렌더 방지
                if (faqFull) { faqRender(topic, q); return; }
                faqList(topic, q, 0, '<li class="sheet-loading">리뷰를 불러오는 중…</li>');
                faqFetch()
                    .then(function(){ if (seq === faqSeq) faqRender(topic, q); })
                    .catch(function(){ if (seq === faqSeq) faqRender(topic, q); });
            }
            $(document).on('click', '.faq-more-btn', function(){ faqOpen($(this).data('topic'), $(this).data('q')); });
            function open(cat, sub){
                curCat = cat; curSub = sub || null; krOnly = false;
                render();
                if (!window.QDATA) loadEmbed().then(render);
                $sheet.prop('hidden', false);
                void $sheet[0].offsetHeight;          // hidden 해제를 전환에 반영(백그라운드 탭에선 rAF가 안 불림)
                $sheet.addClass('is-open');
                $sheet.find('.sheet-close').trigger('focus');
                $('body').css('overflow', 'hidden');
                if (window.CFNav) CFNav.push(closeVisual);  // 뒤로가기로 시트만 닫힘
            }
            function openDis(){
                curCat = '__dis__'; curSub = null; krOnly = false;
                if (!qfull) loadFull(render); else render();   // 임베드는 카테고리당 40건 상한 → 전체 파일 먼저
                $sheet.prop('hidden', false);
                void $sheet[0].offsetHeight;
                $sheet.addClass('is-open');
                $sheet.find('.sheet-close').trigger('focus');
                $('body').css('overflow', 'hidden');
                if (window.CFNav) CFNav.push(closeVisual);
            }
            $(document).on('click', '.ev-row[data-dis]', function(){ openDis(); });
            function close(){ if (window.CFNav) CFNav.pop(); else closeVisual(); }

            $(document).on('click', '.stat-count.has-reviews', function(){
                open($(this).data('cat'), $(this).data('sub'));
            });
            $(document).on('click', '.more-btn', function(){ open($(this).data('cat')); });
            $sheet.on('click', '.sheet-more-btn', function(){ loadFull(render); });
            $(document).on('click', '.sheet-chip', function(){
                curSub = $(this).data('sub') || null; render();
            });
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
            $('#sheet-prev').on('click', function(){ shift(-1); });
            $('#sheet-next').on('click', function(){ shift(1); });
            $sheet.on('click', '.ss-cat', function(){ curCat = $(this).data('cat'); curSub = null; render(); });
            $(document).on('keydown', function(e){   // 팝업이 열려 있을 때 ←/→ 로 카테고리 이동(FAQ 모드 제외)
                if (!$sheet.hasClass('is-open') || $sheet.hasClass('faq-mode')) return;
                if (e.key === 'ArrowLeft') shift(-1); else if (e.key === 'ArrowRight') shift(1);
            });
            $sheet.on('click', '.expand-btn', function(){
                var $b = $(this), $full = $b.closest('.item').find('.full');
                var opened = !$full.prop('hidden');
                $full.prop('hidden', opened);
                $b.toggleClass('is-open', !opened);
                $b.closest('.item').find('.text').toggleClass('clamp', opened);
            });
            $sheet.on('click', '.sheet-close, .sheet-dim', close);
            $(document).on('keydown', function(e){ if (e.key === 'Escape') close(); });
        });

        // ───── 소셜 후기 (SOCIAL): 네이버 블로그 바텀시트 + 유튜브 lite-embed ─────
        $(function(){
            // 블로그: 카드 탭 → 바텀시트 iframe (원본 그대로, X·딤·뒤로가기로 즉시 복귀)
            var $bs = $('#blog-sheet');
            function bsCloseVisual(){
                $bs.removeClass('is-open');
                $('body').css('overflow', '');
                setTimeout(function(){ $bs.prop('hidden', true); $('#bs-frame').attr('src', 'about:blank'); }, 300);
            }
            $(document).on('click', '.nb-card', function(){
                if (!$bs.length) return;
                var u = $(this).data('url'), t = $(this).data('title');
                if (typeof gtag === 'function') {
                    var hh = window.CF_HOTEL || {};
                    gtag('event', 'blog_open', {hotel_name: hh.name || '', hotel_id: hh.pid || '', blog_url: u});
                }
                $('#bs-tit').text(t);
                $('#bs-link').attr('href', u);
                $('#bs-frame').attr('src', u);
                $bs.prop('hidden', false);
                void $bs[0].offsetHeight;               // 강제 reflow — hidden 해제가 transition에 반영되도록 (rAF는 백그라운드 탭에서 안 불림)
                $bs.addClass('is-open');
                $('body').css('overflow', 'hidden');
                if (window.CFNav) CFNav.push(bsCloseVisual);
            });
            $bs.on('click', '.sheet-close, .sheet-dim', function(){
                if (window.CFNav) CFNav.pop(); else bsCloseVisual();
            });
            // 블로그 더보기: 숨긴 카드 전체 펼침 (기본 3 → 최대 9)
            $(document).on('click', '.nb-more', function(){
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
                var ctx = el.getContext('2d');
                var gW = ctx.createLinearGradient(0,0,0,130); gW.addColorStop(0,'rgba(240,160,40,.22)'); gW.addColorStop(1,'rgba(240,160,40,.02)');
                var gC = ctx.createLinearGradient(0,0,0,130); gC.addColorStop(0,'rgba(250,82,82,.22)'); gC.addColorStop(1,'rgba(250,82,82,.02)');
                var n = d.m.length, pr = Array(n).fill(0); pr[n-1] = 3;
                new Chart(ctx, {type:'line', data:{labels:d.m, datasets:[
                    {label:'심각', data:d.c, borderColor:'#FA5252', backgroundColor:gC, fill:'origin', tension:.35, borderWidth:2, pointRadius:pr, pointBackgroundColor:'#FA5252', stack:'risk'},
                    {label:'주의', data:d.w, borderColor:'#F0A028', backgroundColor:gW, fill:'-1', tension:.35, borderWidth:2, pointRadius:pr, pointBackgroundColor:'#F0A028', stack:'risk'},
                    {label:'후쿠오카 평균', data:d.a, borderColor:'#B0B8C1', borderDash:[4,4], borderWidth:1.5, pointRadius:0, fill:false, tension:.35, stack:'avg'}]},
                  options:{responsive:true, maintainAspectRatio:false, interaction:{mode:'index', intersect:false},
                    plugins:{legend:{display:false}, tooltip:{displayColors:false, backgroundColor:'#fff', titleColor:'#191F28', bodyColor:'#4E5968',
                        borderColor:'#E5E8EB', borderWidth:1, cornerRadius:10, padding:10, footerColor:'#191F28', footerFont:{weight:'bold'},
                        callbacks:{label:function(t){return t.dataset.label+' '+t.parsed.y.toFixed(1)+'%';},
                            footer:function(items){var s=0; items.forEach(function(it){if(it.dataset.stack==='risk') s+=it.parsed.y;}); return '합계 '+s.toFixed(1)+'%';}}}},
                    scales:{x:{grid:{display:false}, ticks:{font:{size:12}, color:'#8B95A1', maxRotation:0, autoSkip:true, maxTicksLimit:7}},
                            y:{beginAtZero:true, stacked:true, grid:{color:'#F2F4F6'}, border:{display:false},
                               ticks:{font:{size:12}, color:'#8B95A1', maxTicksLimit:4, callback:function(v){return v+'%';}}}}}});
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
                if ($item.hasClass('is-open')) initCatTrend($item);   // 펼칠 때만 init
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
                initCatTrend($item);
                // 스택 헤더 높이만큼 보정해서 헤더가 바로 보이도록
                var top = $item.offset().top - 8;
                $('html, body').stop().animate({scrollTop: top}, 350);
            }
            $('.radar-cats').on('click', '.radar-cat', function(){
                openAndScroll($(this).data('target'));
            });
            // 실망 확률 근거 줄('심각 리뷰 벌레 3건' 등) → 해당 카테고리 아코디언을 열고 그 소분류 행으로 스크롤·잠시 강조
            $('#detail').on('click', '.ev-row[data-target]', function(e){
                e.preventDefault();
                var t = String($(this).data('target') || ''), sub = String($(this).data('sub') || '');
                var $item = $('#' + t); if (!$item.length) return;
                $item.addClass('is-open'); initCatTrend($item);
                var $row = sub ? $item.find('.stat-row').filter(function(){ return $(this).attr('data-sub') === sub; }).first() : $();
                var $to = $row.length ? $row : $item;
                setTimeout(function(){   // 본문(display:none → block)이 그려진 뒤에 위치를 재야 행 좌표가 맞는다
                    // html{scroll-behavior:smooth}와 jQuery animate(scrollTop)가 충돌해 제자리에 머무는 일이 있어 브라우저 기본 스크롤 사용
                    window.scrollTo({top: Math.max(0, $to.offset().top - ($row.length ? 72 : 8)), behavior: 'smooth'});
                    if ($row.length) { $row.addClass('is-flash'); setTimeout(function(){ $row.removeClass('is-flash'); }, 2200); }
                }, 60);
            });
            // 점프 칩(진입점·위치 섹션 공용): risk-* → 아코디언 오픈, faq-* → 해당 카드로 스크롤, hotel-faq → 섹션 앵커
            $('#detail').on('click', '.fj-btn', function(){
                var t = String($(this).data('target') || '');
                if (t.indexOf('risk-') === 0) { openAndScroll(t); return; }
                if (t.indexOf('faq-') === 0) $('#hotel-faq .faq-tab[data-g=""]').trigger('click');  // 전체 탭으로 카드 노출 보장
                var $el = $('#' + t); if (!$el.length) return;
                if ($el.hasClass('faq-card')) $el.addClass('is-open');   // F18: 점프 진입 시 답변까지 펼침
                $('html, body').stop().animate({scrollTop: $el.offset().top - 8}, 350);
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
    

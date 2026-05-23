/* ZFK · 轮盘后台交互
   - 计算扇形 path
   - 飞入合并动效
   - hover 焦点
   - 点击扇形 → 展开为面板（fetch partial HTML）
   - 面板内导航/表单提交保持在面板里，不离开轮盘
*/
(function() {
    'use strict';

    var svg     = document.getElementById('wheelSvg');
    var stage   = document.getElementById('wheelStage');
    var rotor   = document.getElementById('wheelRotor');
    var overlay = document.getElementById('panelOverlay');
    var panelStage = document.getElementById('panelStage');
    var panelBody  = document.getElementById('panelBody');
    var panelClose = document.getElementById('panelClose');
    var panelHeaderText = document.getElementById('panelHeaderText');

    if (!svg || !stage) return;

    var ADMIN_PREFIX = stage.dataset.adminPrefix || '/admin';
    var slices = Array.prototype.slice.call(stage.querySelectorAll('.wheel-slice'));
    var N = slices.length;
    var R_OUTER = 150;
    var R_INNER = 46;

    /* ---------- 计算扇形 path ---------- */
    function polar(cx, cy, r, angDeg) {
        var a = (angDeg - 90) * Math.PI / 180;
        return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
    }

    function buildSlicePath(idx, total) {
        var step = 360 / total;
        var pad  = 1.2;            // 扇形之间的小缝隙
        var a0   = idx * step + pad;
        var a1   = (idx + 1) * step - pad;
        var p0 = polar(0, 0, R_OUTER, a0);
        var p1 = polar(0, 0, R_OUTER, a1);
        var p2 = polar(0, 0, R_INNER, a1);
        var p3 = polar(0, 0, R_INNER, a0);
        var large = (a1 - a0) > 180 ? 1 : 0;
        return [
            'M', p0[0], p0[1],
            'A', R_OUTER, R_OUTER, 0, large, 1, p1[0], p1[1],
            'L', p2[0], p2[1],
            'A', R_INNER, R_INNER, 0, large, 0, p3[0], p3[1],
            'Z'
        ].join(' ');
    }

    function labelPos(idx, total) {
        var step = 360 / total;
        var mid  = idx * step + step / 2;
        var r    = (R_OUTER + R_INNER) / 2;
        return polar(0, 0, r, mid);
    }

    slices.forEach(function(g, i) {
        var path = g.querySelector('.wheel-slice-path');
        var text = g.querySelector('.wheel-slice-label');
        path.setAttribute('d', buildSlicePath(i, N));
        var lp = labelPos(i, N);
        text.setAttribute('x', lp[0]);
        text.setAttribute('y', lp[1]);
    });

    /* ---------- 飞入动画 ---------- */
    function fly() {
        slices.forEach(function(g, i) {
            // 起始：从屏幕外随机一角飞入
            var ang = (i / N) * Math.PI * 2 + Math.PI / 7;
            var dist = 900;
            var dx = Math.cos(ang) * dist;
            var dy = Math.sin(ang) * dist;
            g.style.transition = 'none';
            g.style.transform = 'translate(' + dx + 'px,' + dy + 'px) scale(.4) rotate(' + (i * 60) + 'deg)';
            g.style.opacity = '0';
        });
        // 强制重排
        // eslint-disable-next-line no-unused-expressions
        svg.getBoundingClientRect();

        stage.classList.add('is-flying');
        slices.forEach(function(g, i) {
            setTimeout(function() {
                g.style.transition = 'transform .8s cubic-bezier(.34,1.25,.64,1), opacity .5s ease';
                g.style.transform = 'translate(0,0) scale(1) rotate(0)';
                g.style.opacity = '1';
            }, 80 + i * 60);
        });

        setTimeout(function() {
            stage.classList.remove('is-flying');
            stage.classList.add('is-ready');
            // 清理内联 transform 让 hover/CSS 接管
            slices.forEach(function(g) {
                g.style.transition = '';
                g.style.transform = '';
            });
        }, 80 + N * 60 + 900);
    }

    /* ---------- 面板：打开 / 关闭 / 注入内容 ---------- */
    var currentURL = null;
    var closeTimer = null;

    function setOriginFromSlice(g) {
        if (!g) {
            panelStage.style.setProperty('--panel-origin-x', '50%');
            panelStage.style.setProperty('--panel-origin-y', '50%');
            return;
        }
        var rect = g.getBoundingClientRect();
        var cx = rect.left + rect.width / 2;
        var cy = rect.top + rect.height / 2;
        var vw = window.innerWidth, vh = window.innerHeight;
        panelStage.style.setProperty('--panel-origin-x', (cx / vw * 100).toFixed(1) + '%');
        panelStage.style.setProperty('--panel-origin-y', (cy / vh * 100).toFixed(1) + '%');
    }

    function showLoading() {
        panelBody.innerHTML = '<div class="panel-loading"><div class="spinner"></div><div>加载中…</div></div>';
    }

    function injectHTML(html) {
        // 解析 partial 返回的内容片段
        var tpl = document.createElement('template');
        tpl.innerHTML = html;
        panelBody.innerHTML = '';
        panelBody.appendChild(tpl.content);
        // 执行其中的 <script>
        Array.prototype.forEach.call(panelBody.querySelectorAll('script'), function(old) {
            var s = document.createElement('script');
            if (old.src) s.src = old.src; else s.textContent = old.textContent;
            old.parentNode.replaceChild(s, old);
        });
        syncPanelTitle();
        bindPanelLinks();
        bindPanelForms();
        panelBody.scrollTop = 0;
    }

    function syncPanelTitle() {
        if (!panelHeaderText) return;
        var h1 = panelBody.querySelector('.page-header h1');
        if (h1) {
            // 去掉 h1 内部的小圆点装饰，只取文字
            var clone = h1.cloneNode(true);
            var dot = clone.querySelector('.h1-dot');
            if (dot) dot.remove();
            var txt = (clone.textContent || '').trim();
            if (txt) {
                panelHeaderText.textContent = txt;
                // 隐藏 partial 内重复的 page-header（只保留按钮组）
                var ph = panelBody.querySelector('.page-header');
                if (ph) ph.classList.add('page-header--in-panel');
            }
        }
    }

    function withPartial(url) {
        try {
            var u = new URL(url, window.location.origin);
            u.searchParams.set('partial', '1');
            return u.pathname + u.search + u.hash;
        } catch (e) {
            return url + (url.indexOf('?') === -1 ? '?' : '&') + 'partial=1';
        }
    }

    function loadInto(url, opts) {
        opts = opts || {};
        currentURL = url;
        showLoading();
        return fetch(withPartial(url), {
            headers: { 'X-Partial': '1', 'X-Requested-With': 'fetch' },
            credentials: 'same-origin',
            redirect: 'follow'
        }).then(function(res) {
            if (res.redirected) currentURL = res.url;
            return res.text().then(function(html) {
                return { ok: res.ok, status: res.status, html: html, url: res.url };
            });
        }).then(function(r) {
            if (!r.ok && r.status === 401) {
                window.location.href = ADMIN_PREFIX + '/login';
                return;
            }
            injectHTML(r.html);
        }).catch(function() {
            panelBody.innerHTML = '<div class="alert alert-error">加载失败，请检查网络</div>';
        });
    }

    function openPanel(url, sliceEl) {
        if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
        setOriginFromSlice(sliceEl);
        if (panelHeaderText && sliceEl) {
            var lbl = sliceEl.querySelector('.wheel-slice-label');
            if (lbl) panelHeaderText.textContent = lbl.textContent.trim();
        }
        overlay.classList.add('is-open');
        overlay.classList.remove('is-closing');
        stage.classList.add('is-paused');
        document.body.style.overflow = 'hidden';
        loadInto(url);
    }

    function closePanel() {
        if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
        overlay.classList.add('is-closing');
        overlay.classList.remove('is-open');
        closeTimer = setTimeout(function() {
            closeTimer = null;
            overlay.classList.remove('is-closing');
            panelBody.innerHTML = '';
            stage.classList.remove('is-paused');
            document.body.style.overflow = '';
            currentURL = null;
        }, 450);
    }

    panelClose.addEventListener('click', closePanel);
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) closePanel();
    });
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && overlay.classList.contains('is-open')) closePanel();
    });

    /* ---------- slice click ---------- */
    slices.forEach(function(g) {
        g.addEventListener('mouseenter', function() { stage.classList.add('is-paused'); });
        g.addEventListener('mouseleave', function() {
            if (!overlay.classList.contains('is-open')) stage.classList.remove('is-paused');
        });
        g.addEventListener('click', function() {
            var href = g.dataset.href;
            if (g.dataset.external === '1') {
                window.open(href, '_blank');
                return;
            }
            openPanel(href, g);
        });
    });

    /* ---------- 面板内导航劫持 ---------- */
    function isAdminURL(url) {
        try {
            var u = new URL(url, window.location.origin);
            if (u.origin !== window.location.origin) return false;
            return u.pathname === ADMIN_PREFIX || u.pathname.indexOf(ADMIN_PREFIX + '/') === 0;
        } catch (e) { return false; }
    }

    function bindPanelLinks() {
        Array.prototype.forEach.call(panelBody.querySelectorAll('a[href]'), function(a) {
            var href = a.getAttribute('href');
            if (!href || href.charAt(0) === '#') return;
            if (a.target === '_blank') return;
            if (a.dataset.wheelBound === '1') return;
            a.dataset.wheelBound = '1';
            if (!isAdminURL(href)) return;
            a.addEventListener('click', function(e) {
                e.preventDefault();
                loadInto(href);
            });
        });
    }

    function bindPanelForms() {
        Array.prototype.forEach.call(panelBody.querySelectorAll('form'), function(f) {
            if (f.dataset.wheelBound === '1') return;
            f.dataset.wheelBound = '1';
            var action = f.getAttribute('action') || (currentURL || '');
            if (!isAdminURL(action)) return;
            // 退出登录表单：让浏览器原生处理
            if (action.indexOf('/logout') !== -1) return;
            f.addEventListener('submit', function(e) {
                e.preventDefault();
                var fd = new FormData(f);
                var method = (f.method || 'post').toUpperCase();
                showLoading();
                fetch(withPartial(action), {
                    method: method,
                    body: method === 'GET' ? null : fd,
                    headers: { 'X-Partial': '1', 'X-Requested-With': 'fetch' },
                    credentials: 'same-origin',
                    redirect: 'follow'
                }).then(function(res) {
                    if (!res.ok && res.status === 401) {
                        window.location.href = ADMIN_PREFIX + '/login';
                        return null;
                    }
                    if (res.redirected) currentURL = res.url;
                    return res.text();
                }).then(function(html) {
                    if (html != null) injectHTML(html);
                }).catch(function() {
                    panelBody.innerHTML = '<div class="alert alert-error">提交失败</div>';
                });
            });
        });
    }

    /* ---------- 初始化：飞入 → 旋转 ---------- */
    fly();

    /* 若服务端把用户直接送到子页面（非根 admin），把 initial content 放进面板 */
    var initialTpl = document.getElementById('initialPanelContent');
    var initialURL = window.__INITIAL_PANEL_URL__;
    if (initialTpl && initialURL) {
        setTimeout(function() {
            var match = slices.find(function(g) {
                var h = g.dataset.href;
                return h === initialURL || initialURL.indexOf(h) === 0;
            }) || slices[0];
            setOriginFromSlice(match);
            overlay.classList.add('is-open');
            stage.classList.add('is-paused');
            document.body.style.overflow = 'hidden';
            currentURL = initialURL;
            injectHTML(initialTpl.innerHTML);
            try { history.replaceState(null, '', ADMIN_PREFIX + '/'); } catch (e) {}
        }, 600);
    }

})();

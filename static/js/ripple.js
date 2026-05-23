/* ZFK · 真实水面波纹
   - 高度场（height-field）波动方程：cur = (邻居和)/2 - prev，乘衰减
   - 鼠标移动 / 点击在指定点抬升水面，自然向四周传播 + 互相干涉反射
   - 渲染：用高度梯度做光照阴影，模拟阳光打在水面上的反光
*/
(function() {
    'use strict';

    var canvas = document.getElementById('rippleCanvas');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');

    /* 模拟在低分辨率网格上跑（每格 SCALE 像素），渲染时再放大到全屏 */
    var SCALE = 4;

    var W = 0, H = 0, cols = 0, rows = 0;
    var cur, prev;
    var off, offCtx, offImg;

    function resize() {
        W = window.innerWidth;
        H = window.innerHeight;
        canvas.width = W;
        canvas.height = H;
        canvas.style.width = W + 'px';
        canvas.style.height = H + 'px';

        cols = Math.max(8, Math.ceil(W / SCALE));
        rows = Math.max(8, Math.ceil(H / SCALE));
        cur = new Float32Array(cols * rows);
        prev = new Float32Array(cols * rows);

        off = document.createElement('canvas');
        off.width = cols;
        off.height = rows;
        offCtx = off.getContext('2d');
        offImg = offCtx.createImageData(cols, rows);
    }
    resize();
    window.addEventListener('resize', resize);

    /* 在 (x, y) 像素位置抬升一片水面（高斯衰减，旋转对称） */
    function disturb(px, py, strength, radius) {
        var cx = px / SCALE;
        var cy = py / SCALE;
        var r  = Math.max(1, radius / SCALE);
        var r2 = r * r;
        var sigma2 = r2 * 0.35;
        var iMin = Math.max(1, Math.floor(cx - r));
        var iMax = Math.min(cols - 2, Math.ceil(cx + r));
        var jMin = Math.max(1, Math.floor(cy - r));
        var jMax = Math.min(rows - 2, Math.ceil(cy + r));
        for (var y = jMin; y <= jMax; y++) {
            for (var x = iMin; x <= iMax; x++) {
                var dx = x - cx, dy = y - cy;
                var d2 = dx * dx + dy * dy;
                if (d2 > r2) continue;
                // 高斯：中心强、外圈柔，旋转对称
                prev[y * cols + x] += strength * Math.exp(-d2 / sigma2);
            }
        }
    }

    /* 鼠标移动：拖出小波纹 */
    var lastX = -1, lastY = -1, lastMove = 0;
    document.addEventListener('mousemove', function(e) {
        var now = performance.now();
        if (now - lastMove < 16) return;
        if (lastX >= 0) {
            var dx = e.clientX - lastX, dy = e.clientY - lastY;
            if (dx * dx + dy * dy < 9) return;
        }
        lastMove = now;
        lastX = e.clientX; lastY = e.clientY;
        disturb(e.clientX, e.clientY, 0.6, 6);
    }, { passive: true });

    /* 点击：原地砸出一颗"石子"，强度大很多 */
    document.addEventListener('click', function(e) {
        disturb(e.clientX, e.clientY, 8, 14);
    }, { passive: true });

    /* 一次模拟步：9 点离散波动方程（轴 + 对角加权），波速更接近各向同性 */
    function step() {
        var p = prev, c = cur;
        var damping = 0.985;
        // 邻居权重：轴向 4 个 ×0.2，对角 4 个 ×0.05，加起来正好 1
        var wA = 0.2, wD = 0.05;
        for (var y = 1; y < rows - 1; y++) {
            var base = y * cols;
            for (var x = 1; x < cols - 1; x++) {
                var i = base + x;
                var sum =
                    (p[i - 1] + p[i + 1] + p[i - cols] + p[i + cols]) * wA +
                    (p[i - 1 - cols] + p[i + 1 - cols] + p[i - 1 + cols] + p[i + 1 + cols]) * wD;
                // 等效原本的 (邻居均值)*2 - prev_self；wA*4+wD*4=1，所以 sum*2 - c[i]
                var v = sum * 2 - c[i];
                c[i] = v * damping;
            }
        }
        var t = prev; prev = cur; cur = t;
    }

    /* 渲染：用梯度模长（旋转对称）做高光，用高度本身做色调
       —— 这样涟漪是真正同心的圆环，没有偏向某一侧 */
    function render() {
        var data = offImg.data;
        var h = prev;
        for (var y = 1; y < rows - 1; y++) {
            var base = y * cols;
            for (var x = 1; x < cols - 1; x++) {
                var i = base + x;
                var gx = h[i - 1] - h[i + 1];
                var gy = h[i - cols] - h[i + cols];
                var gradMag = Math.sqrt(gx * gx + gy * gy);
                var hv = h[i];

                var idx = i * 4;

                // 基础水面色：偏冷的浅蓝
                var r = 205, g = 225, b = 245;

                // 波峰（hv > 0）受光偏白；波谷（hv < 0）背光偏深蓝
                if (hv > 0) {
                    var t = hv * 0.45;
                    if (t > 1) t = 1;
                    r += t * 45;
                    g += t * 30;
                    b += t * 10;
                } else {
                    var u = -hv * 0.45;
                    if (u > 1) u = 1;
                    r -= u * 70;
                    g -= u * 55;
                    b -= u * 30;
                }

                data[idx]     = r;
                data[idx + 1] = g;
                data[idx + 2] = b;

                // alpha 由梯度模长决定 —— 圆环本身是旋转对称的
                var a = gradMag * 340 + Math.abs(hv) * 6;
                if (a > 210) a = 210;
                data[idx + 3] = a;
            }
        }
        offCtx.putImageData(offImg, 0, 0);
        ctx.clearRect(0, 0, W, H);
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(off, 0, 0, W, H);
    }

    function frame() {
        step();
        render();
        requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
})();

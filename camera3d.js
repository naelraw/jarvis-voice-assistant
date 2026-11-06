/* Fenêtre « Caméra » de JARVIS (v3) : la webcam, un suivi des mains lissé (MediaPipe servi en local + filtre 1€) et l'ATELIER 3D :
   des formes dessinées dans l'air avec les doigts (rond = sphère, carré = cube, triangle = pyramide…), saisies, déplacées, lancées,
   agrandies avec une ou deux mains. Ouverte par la voix ou par l'onglet Caméra ; le serveur envoie l'état dans le message « uix »
   (champ cam) et index.html le passe à CAM3D.state(). Sans caméra, la souris sert de main (clic = pincer). */
(() => {
  'use strict';
  const TOK = () => encodeURIComponent(window.JTOKEN || '');
  const CYAN = '0,210,255';
  let win, video, cv, ctx, hudEl, barEl;
  let media = null, landmarker = null, raf = 0, open = false, mode = 'atelier', lastN = -1, lastCmd = 0, loadingMsg = '';
  let streaming = false, streamTimer = 0, tsLast = 0, big = false, full = true;   // plein écran par défaut
  function setFull(on) {
    full = on; win.classList.toggle('full', on); win.classList.toggle('big', !on && big);
    const b = win.querySelector('#cambig'); b.textContent = on ? '⤡' : '⤢'; b.title = on ? 'Réduire en fenêtre' : 'Plein écran';
    if (!on) { win.style.left = '50%'; win.style.top = '50%'; win.style.transform = 'translate(-50%, -50%)'; }
    resize(); setTimeout(resize, 60); setTimeout(resize, 250);
  }
  let W = 640, H = 360, fps = 0, fpsT = performance.now(), fpsN = 0, uid = 1;
  const shapes = [], strokes = [], hints = [];
  const slots = [null, null];                    // mains suivies (gauche / droite), lissées
  const mouse = { x: 0, y: 0, down: false, active: false };
  const grabs = new Map();                       // id de main -> { o, dx, dy, s0, ps0, rz0, roll0, t0, hist[] }
  const draw = new Map();                        // id de main -> { pts[] } (dessin dans le vide)

  // ------------------------------------------------------------------ filtre « 1 euro » (lissage sans retard)
  class OneEuro {
    constructor(minC = 1.2, beta = 9, dC = 1.0) { this.minC = minC; this.beta = beta; this.dC = dC; this.t = null; this.x = 0; this.dx = 0; }
    f(x, t) {
      if (this.t === null) { this.t = t; this.x = x; this.dx = 0; return x; }
      const dt = Math.max(1e-3, (t - this.t) / 1000); this.t = t;
      const al = (c) => { const r = 2 * Math.PI * c * dt; return r / (r + 1); };
      this.dx += al(this.dC) * ((x - this.x) / dt - this.dx);
      this.x += al(this.minC + this.beta * Math.abs(this.dx)) * (x - this.x);
      return this.x;
    }
    reset() { this.t = null; }
  }
  const newSlot = () => ({ fx: Array.from({ length: 21 }, () => new OneEuro()), fy: Array.from({ length: 21 }, () => new OneEuro()),
                           P: null, seen: 0, pinch: false, pinchN: 0, rpinch: false, rN: 0, pose: 'autre', ratio: 1, ratioM: 1,
                           cur: new OneEuro(2.2, 25), cury: new OneEuro(2.2, 25) });

  // ------------------------------------------------------------------ formes (listes de lignes 3D, coordonnées -1..1)
  const circle = (n, f) => Array.from({ length: n + 1 }, (_, i) => f((i / n) * Math.PI * 2));
  const GEOM = {
    cube: (() => { const v = [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]];
      return [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]].map(([a, b]) => [v[a], v[b]]); })(),
    pyramide: (() => { const a = [0, -1.1, 0], b = [[-1, 0.9, -1], [1, 0.9, -1], [1, 0.9, 1], [-1, 0.9, 1]];
      return [[b[0], b[1], b[2], b[3], b[0]], [a, b[0]], [a, b[1]], [a, b[2]], [a, b[3]]]; })(),
    octaèdre: (() => { const v = [[1.15, 0, 0], [-1.15, 0, 0], [0, 1.15, 0], [0, -1.15, 0], [0, 0, 1.15], [0, 0, -1.15]];
      const e = []; for (let i = 0; i < 6; i++) for (let j = i + 1; j < 6; j++) if (!(i >> 1 === j >> 1)) e.push([v[i], v[j]]); return e; })(),
    sphère: [...[-0.6, 0, 0.6].map(y => circle(36, t => { const r = Math.sqrt(1 - y * y); return [Math.cos(t) * r, y, Math.sin(t) * r]; })),
      ...[0, 1, 2, 3].map(k => circle(36, t => { const a = (k * Math.PI) / 4; return [Math.cos(t) * Math.cos(a), Math.sin(t), Math.cos(t) * Math.sin(a)]; }))],
    anneau: [...Array.from({ length: 16 }, (_, k) => circle(14, t => { const a = (k / 16) * Math.PI * 2, R = 0.78 + 0.3 * Math.cos(t);
        return [Math.cos(a) * R, 0.3 * Math.sin(t), Math.sin(a) * R]; })), ...[0.48, 0.78, 1.08].map(R => circle(48, t => [Math.cos(t) * R, 0, Math.sin(t) * R]))],
    cylindre: [circle(30, t => [Math.cos(t) * 0.8, -1, Math.sin(t) * 0.8]), circle(30, t => [Math.cos(t) * 0.8, 1, Math.sin(t) * 0.8]),
      ...Array.from({ length: 8 }, (_, k) => { const a = (k / 8) * Math.PI * 2; return [[Math.cos(a) * 0.8, -1, Math.sin(a) * 0.8], [Math.cos(a) * 0.8, 1, Math.sin(a) * 0.8]]; })],
  };
  const KINDS = ['cube', 'pyramide', 'sphère', 'anneau', 'cylindre', 'octaèdre'];
  const TINT = { cube: '0,210,255', pyramide: '110,235,255', 'sphère': '30,140,255', anneau: '150,170,255', cylindre: '0,190,230', 'octaèdre': '190,235,255' };

  function addShape(kind, x, y, size) {
    if (!GEOM[kind]) kind = 'cube';
    const n = shapes.length;
    shapes.push({ id: uid++, kind, x: x ?? W * (0.3 + 0.4 * ((n * 0.37) % 1)), y: y ?? H * (0.45 + 0.1 * ((n % 3) - 1)), s: 1, anim: 0.25,
                  size: size ?? Math.min(W, H) * 0.14, rx: 0.5, ry: 0.6, rz: 0, spin: 0.35, vx: 0, vy: 0, born: performance.now(), dying: 0 });
  }

  // ------------------------------------------------------------------ reconnaissance d'un tracé dans l'air
  const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  function resample(pts, n) {
    let L = 0; for (let i = 1; i < pts.length; i++) L += dist(pts[i], pts[i - 1]);
    const step = L / n, out = [pts[0]]; let acc = 0;
    for (let i = 1; i < pts.length; i++) {
      let a = pts[i - 1]; const b = pts[i]; let d = dist(a, b);
      while (d > 0 && acc + d >= step) { const t = (step - acc) / d, q = { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t }; out.push(q); a = q; d = dist(a, b); acc = 0; }
      acc += d;
    }
    while (out.length < n) out.push(pts[pts.length - 1]);
    return out.slice(0, n);
  }
  function recognize(raw) {
    if (!raw || raw.length < 8) return null;
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9, len = 0;
    for (let i = 0; i < raw.length; i++) { const p = raw[i]; x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y); if (i) len += dist(p, raw[i - 1]); }
    const w = x1 - x0, h = y1 - y0, m = Math.max(w, h);
    if (m < 35 || len < 100) return null;
    if (dist(raw[0], raw[raw.length - 1]) > 0.55 * m && len < 1.6 * m * 2) return null;                  // tracé resté ouvert
    const N = 64; let P = resample(raw, N);
    for (let pass = 0; pass < 2; pass++) P = P.map((p, i) => { const a = P[(i + N - 1) % N], b = P[(i + 1) % N]; return { x: (a.x + 2 * p.x + b.x) / 4, y: (a.y + 2 * p.y + b.y) / 4 }; });   // lissage (la main tremble)
    // angle de virage à chaque point (fenêtre de ±5 points) et enroulement total
    const k = 5, turn = P.map((p, i) => { const a = P[(i + N - k) % N], b = P[(i + k) % N];
      let d = Math.atan2(b.y - p.y, b.x - p.x) - Math.atan2(p.y - a.y, p.x - a.x); while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI; return d * 180 / Math.PI; });
    let wind = 0; { const gx = raw.reduce((q, p) => q + p.x, 0) / raw.length, gy = raw.reduce((q, p) => q + p.y, 0) / raw.length;      // balayage angulaire autour du centre : insensible au tremblement
      for (let i = 1; i < raw.length; i++) { let d = Math.atan2(raw[i].y - gy, raw[i].x - gx) - Math.atan2(raw[i - 1].y - gy, raw[i - 1].x - gx); while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI; wind += d; } }
    const turns = Math.abs(wind) / (2 * Math.PI);
    const sg = Math.sign(turn.reduce((s, v) => s + v, 0)) || 1, tn = turn.map(v => v * sg);
    const peaks = []; for (let i = 0; i < N; i++) { if (tn[i] < 52) continue; let top = true; for (let j = -k; j <= k; j++) if (tn[(i + j + N) % N] > tn[i]) top = false; if (top) peaks.push(i); }
    let cs = peaks.filter((c, i) => i === 0 || (c - peaks[i - 1]) > 6);
    if (cs.length > 1 && (cs[0] + N - cs[cs.length - 1]) <= 6) cs.pop();
    for (let again = true; again && cs.length > 3;) {      // un « coin » presque à plat sur un côté (angle > 150°) n'en est pas un
      again = false;
      for (let i = 0; i < cs.length; i++) { const a = P[cs[(i + cs.length - 1) % cs.length]], b = P[cs[i]], c = P[cs[(i + 1) % cs.length]];
        let d = Math.abs(Math.atan2(a.y - b.y, a.x - b.x) - Math.atan2(c.y - b.y, c.x - b.x)); if (d > Math.PI) d = 2 * Math.PI - d;
        if (d * 180 / Math.PI > 150) { cs.splice(i, 1); again = true; break; } }
    }
    const corners = cs.length;
    let area = 0, per = 0; for (let i = 0; i < N; i++) { const a = P[i], b = P[(i + 1) % N]; area += a.x * b.y - b.x * a.y; per += dist(a, b); }
    area = Math.abs(area / 2);
    const circ = 4 * Math.PI * area / (per * per), fill = area / Math.max(1, w * h), asp = Math.max(w, h) / Math.max(1, Math.min(w, h));
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, size = Math.max(40, Math.min(150, m * 0.4));
    let kind;
    if (turns > 1.75) kind = 'anneau';
    else if (corners === 3 && fill < 0.7) kind = 'pyramide';
    else if (corners === 3 || corners === 4 || (corners === 5 && circ < 0.8)) kind = fill < 0.66 ? 'octaèdre' : asp > 1.45 ? 'cylindre' : 'cube';
    else kind = circ > 0.74 ? 'sphère' : (fill > 0.88 ? (asp > 1.45 ? 'cylindre' : 'cube') : 'sphère');
    return { kind, x: cx, y: cy, size, corners, circ, fill };
  }

  // ------------------------------------------------------------------ interface (fenêtre)
  function build() {
    const css = document.createElement('style');
    css.textContent = `
      #camwin { position: fixed; z-index: 9; left: 50%; top: 50%; transform: translate(-50%, -50%); width: min(94vw, 760px);
        background: linear-gradient(180deg, rgba(4,18,30,.94), rgba(2,10,18,.92)); border: 1px solid rgba(${CYAN},.32);
        box-shadow: 0 0 60px rgba(0,120,200,.18) inset, 0 16px 60px rgba(0,0,0,.6); backdrop-filter: blur(10px); display: none;
        font-family: "Bahnschrift", "Segoe UI", sans-serif; color: #d6ecf5; }
      #camwin.on { display: block; } #camwin.big { width: min(96vw, 1180px); }
      #camwin.full { left: 0 !important; top: 0 !important; transform: none !important; width: 100vw !important; height: 100vh; border: 0; z-index: 50; display: none; flex-direction: column; background: #01060c; }
      #camwin.full.on { display: flex; } #camwin.full .cs { flex: 1; height: auto !important; min-height: 0; } #camwin.full .ch { cursor: default; }
      #camwin .ch { display: flex; align-items: center; gap: 8px; padding: 8px 10px 8px 14px; cursor: grab; user-select: none; touch-action: none;
        border-bottom: 1px solid rgba(${CYAN},.2); background: linear-gradient(90deg, rgba(${CYAN},.14), transparent 70%); }
      #camwin .ct { flex: 1; color: #fff; font-weight: 600; font-size: 13px; letter-spacing: 3px; text-shadow: 0 0 10px rgba(${CYAN},.5); }
      #camwin .ct i { color: rgba(${CYAN},.8); font-style: normal; font-weight: 400; font-size: 10px; letter-spacing: 2px; margin-left: 10px; }
      #camwin .cb { height: 28px; padding: 0 12px; border: 1px solid rgba(${CYAN},.28); background: rgba(3,14,24,.8); color: rgba(${CYAN},.9);
        font: 600 10px "Cascadia Mono", Consolas, monospace; letter-spacing: 1.5px; cursor: pointer; }
      #camwin .cb:hover { color: #fff; border-color: rgba(${CYAN},.85); box-shadow: 0 0 10px rgba(${CYAN},.4); }
      #camwin .cb.on { color: #fff; background: rgba(${CYAN},.2); border-color: rgb(${CYAN}); }
      #camwin .cx { width: 30px; padding: 0; }
      #camwin .cs { position: relative; width: 100%; background: #000; overflow: hidden; touch-action: none; }
      #camwin video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; transform: scaleX(-1); opacity: .62; }
      @media (display-mode: fullscreen) { #camwin .ch { padding-top: 10px; } }
      #camwin canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
      #camwin .cf { padding: 6px 12px; font: 10.5px "Cascadia Mono", Consolas, monospace; letter-spacing: 1.5px; color: rgba(${CYAN},.75);
        display: flex; justify-content: space-between; text-transform: uppercase; gap: 12px; }
      @media (max-width: 1100px), (max-height: 700px) { #camwin { width: min(70vw, 560px); } #camwin.big { width: min(94vw, 900px); }
        #camwin .ch { padding: 5px 8px 5px 10px; } #camwin .cb { height: 34px; } }`;
    document.head.appendChild(css);
    win = document.createElement('div');
    win.id = 'camwin';
    win.innerHTML = `<div class="ch"><span class="ct">CAMÉRA<i id="camsub"></i></span>
        <button class="cb cx" id="cambig" title="Agrandir">⤢</button><button class="cb cx" id="camx" title="Fermer">✕</button></div>
      <div class="cs" id="camstage"><video id="camvid" playsinline muted autoplay></video><canvas id="camcv"></canvas></div>
      <div class="cf"><span id="camhud"></span><span id="cambar"></span></div>`;
    document.body.appendChild(win);
    video = win.querySelector('#camvid'); cv = win.querySelector('#camcv'); ctx = cv.getContext('2d');
    hudEl = win.querySelector('#camhud'); barEl = win.querySelector('#cambar');
    win.querySelector('#camx').onclick = () => close(true);
    win.querySelector('#cambig').onclick = () => setFull(!full);
    const head = win.querySelector('.ch');
    head.addEventListener('pointerdown', (e) => {
      if (e.target.closest('button')) return;
      const r = win.getBoundingClientRect();
      win.style.left = r.left + 'px'; win.style.top = r.top + 'px'; win.style.transform = 'none';
      const dx = e.clientX - r.left, dy = e.clientY - r.top;
      head.setPointerCapture(e.pointerId);
      const mv = (ev) => { win.style.left = Math.max(0, Math.min(innerWidth - 80, ev.clientX - dx)) + 'px'; win.style.top = Math.max(0, Math.min(innerHeight - 40, ev.clientY - dy)) + 'px'; };
      const up = () => { head.removeEventListener('pointermove', mv); head.removeEventListener('pointerup', up); };
      head.addEventListener('pointermove', mv); head.addEventListener('pointerup', up);
    });
    const stage = win.querySelector('#camstage');
    const pos = (e) => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) * (W / r.width), (e.clientY - r.top) * (H / r.height)]; };
    stage.addEventListener('pointerdown', (e) => { [mouse.x, mouse.y] = pos(e); mouse.down = true; mouse.active = true; stage.setPointerCapture(e.pointerId); });
    stage.addEventListener('pointermove', (e) => { [mouse.x, mouse.y] = pos(e); mouse.active = true; });
    stage.addEventListener('pointerup', () => { mouse.down = false; });
    stage.addEventListener('pointerleave', () => { if (!mouse.down) mouse.active = false; });
    stage.addEventListener('wheel', (e) => { e.preventDefault(); const o = pickObj(mouse.x, mouse.y, 1); if (o) o.s = Math.max(0.35, Math.min(3, o.s * (e.deltaY < 0 ? 1.08 : 0.92))); }, { passive: false });
    new ResizeObserver(() => resize()).observe(stage);
    addEventListener('keydown', (e) => { if (e.key === 'Escape' && open) { close(true); } });
  }
  function resize() {
    const st = win && win.querySelector('#camstage');
    if (!st) return;
    const ar = (video && video.videoWidth) ? video.videoWidth / video.videoHeight : 16 / 9;
    if (!full) st.style.height = Math.round(st.clientWidth / ar) + 'px'; else st.style.height = '';
    const d = Math.min(2, devicePixelRatio || 1);
    W = st.clientWidth; H = st.clientHeight;
    cv.width = Math.round(W * d); cv.height = Math.round(H * d); ctx.setTransform(d, 0, 0, d, 0, 0);
  }

  // ------------------------------------------------------------------ caméra + suivi des mains (détection à la cadence de la caméra)
  async function start() {
    resize();
    loadingMsg = 'Ouverture de la caméra…';
    if (!raf) raf = requestAnimationFrame(loop);
    try {
      media = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 960 }, height: { ideal: 540 }, frameRate: { ideal: 30 } }, audio: false });
      video.srcObject = media; await video.play().catch(() => {});
      await new Promise(r => { if (video.videoWidth) r(); else video.onloadedmetadata = () => r(); });
      resize();
    } catch (e) { loadingMsg = 'Caméra indisponible : ' + (e.message || e.name) + ' (la souris peut servir de main)'; media = null; }
    if (media && !landmarker) {
      loadingMsg = 'Chargement du suivi des mains…';
      try {
        const v = await import('/vendor/mediapipe/vision_bundle.mjs');
        const fs = await v.FilesetResolver.forVisionTasks('/vendor/mediapipe');
        const mk = (delegate) => v.HandLandmarker.createFromOptions(fs, { baseOptions: { modelAssetPath: '/vendor/mediapipe/hand_landmarker.task', delegate },
          runningMode: 'VIDEO', numHands: 2, minHandDetectionConfidence: 0.55, minHandPresenceConfidence: 0.5, minTrackingConfidence: 0.5 });
        try { landmarker = await mk('GPU'); } catch (e) { landmarker = await mk('CPU'); }
        loadingMsg = '';
      } catch (e) { loadingMsg = 'Suivi des mains indisponible : ' + (e.message || e); landmarker = null; }
    } else if (media) loadingMsg = '';
    if (media && open) videoLoop();
  }
  function videoLoop() {   // une détection par image de la caméra (pas par image affichée) : moins de retard, moins de charge
    const tick = () => {
      if (!open || !media) return;
      if (landmarker && video.readyState >= 2) {
        try { const ts = Math.max(tsLast + 1, performance.now()); tsLast = ts; ingest(landmarker.detectForVideo(video, ts), ts); } catch (e) { /* image pas prête */ }
      }
      if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(tick); else setTimeout(tick, 33);
    };
    if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(tick); else setTimeout(tick, 33);
  }
  function stop() {
    cancelAnimationFrame(raf); raf = 0;
    if (media) { media.getTracks().forEach(t => t.stop()); media = null; }
    video.srcObject = null;
    setStreaming(false);
  }
  function close(notify) {
    if (!open) return;
    open = false; win.classList.remove('on'); stop();
    slots[0] = slots[1] = null; grabs.clear(); draw.clear();
    if (notify) fetch('/api/cam/closed', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: window.JTOKEN }) }).catch(() => {});
  }
  function setMode() {
    mode = 'atelier';
    win.querySelector('#camsub').textContent = 'ATELIER 3D';
    if (!shapes.length) addShape('cube');
    grabs.clear(); draw.clear();
  }

  // ------------------------------------------------------------------ flux vers Gemini (1 image / s)
  function setStreaming(on) {
    if (on === streaming) return;
    streaming = on; clearInterval(streamTimer);
    if (!on) return;
    streamTimer = setInterval(() => {
      if (!media && !mouse.active) return;
      const c = document.createElement('canvas'), w = 768, h = Math.round(w * H / W);
      c.width = w; c.height = h; const g = c.getContext('2d');
      if (video.videoWidth) { g.save(); g.translate(w, 0); g.scale(-1, 1); g.drawImage(video, 0, 0, w, h); g.restore(); } else { g.fillStyle = '#02060c'; g.fillRect(0, 0, w, h); }
      g.drawImage(cv, 0, 0, w, h);
      c.toBlob(b => { if (b) fetch('/api/cam/frame?token=' + TOK(), { method: 'POST', body: b }).catch(() => {}); }, 'image/jpeg', 0.7);
    }, 1000);
  }

  // ------------------------------------------------------------------ main : lissage, pincement, poses
  const dpx = (P, a, b) => Math.hypot((P[a].x - P[b].x) * W, (P[a].y - P[b].y) * H);
  function ingest(res, t) {
    const lms = (res && res.landmarks) || [], hn = (res && res.handednesses) || [];
    const used = new Set();
    lms.forEach((lm, i) => {
      let k = (hn[i] && hn[i][0] && hn[i][0].categoryName === 'Left') ? 0 : 1;
      if (!hn[i]) k = i;
      if (used.has(k)) k = 1 - k;
      used.add(k);
      const s = slots[k] || (slots[k] = newSlot());
      if (!s.P || t - s.seen > 300) { s.fx.forEach(f => f.reset()); s.fy.forEach(f => f.reset()); s.cur.reset(); s.cury.reset(); s.pinch = false; s.pinchN = 0; s.rpinch = false; }
      s.seen = t;
      const vw = video.videoWidth, vh = video.videoHeight, sc = vw ? Math.max(W / vw, H / vh) : 1, kx = vw ? vw * sc / W : 1, ky = vh ? vh * sc / H : 1;   // vidéo recadrée (cover) : on recale
      s.P = lm.map((l, j) => ({ x: s.fx[j].f(0.5 + (0.5 - l.x) * kx, t), y: s.fy[j].f(0.5 + (l.y - 0.5) * ky, t) }));     // x miroir
      analyze(s);
    });
  }
  function analyze(s) {
    const P = s.P, pw = dpx(P, 5, 17) || 1, wr = (a) => dpx(P, a, 0);
    s.pw = pw; s.ratio = dpx(P, 4, 8) / pw; s.ratioM = dpx(P, 4, 12) / pw;
    const flip = (cur, want, key) => { if (want === cur) { s[key] = 0; return cur; } s[key] = (s[key] || 0) + 1; if (s[key] >= 2) { s[key] = 0; return want; } return cur; };
    const idxOut = wr(8) > wr(6) * 0.9;      // l'index reste tendu vers le pouce (un poing fermé n'est pas un pincement)
    s.pinch = flip(s.pinch, s.pinch ? !(s.ratio > 0.68) : (s.ratio < 0.4 && idxOut), 'pinchN');
    const midOut = wr(12) > wr(9) * 0.9;     // le majeur vient vers le pouce (pas replié contre la paume : sinon le poing ferait un clic droit)
    s.rpinch = !s.pinch && flip(s.rpinch, s.rpinch ? !(s.ratioM > 0.68) : (s.ratioM < 0.38 && s.ratio > 0.7 && midOut), 'rN');
    const ext = (tip, pip) => wr(tip) > wr(pip) * 1.12;
    const e = [ext(8, 6), ext(12, 10), ext(16, 14), ext(20, 18)];
    const thumbOut = dpx(P, 4, 5) / pw > 0.85;
    let pose = 'autre';
    if (s.pinch || s.rpinch) pose = 'pince';
    else if (e[0] && e[1] && e[2] && e[3] && thumbOut) pose = 'paume';
    else if (!e[0] && !e[1] && !e[2] && !e[3]) pose = 'poing';
    else if (e[0] && e[1] && !e[2] && !e[3]) pose = 'deux';
    else if (e[0] && !e[1] && !e[2] && !e[3]) pose = 'index';
    const now = performance.now();
    if (pose !== s.rawPose) { s.rawPose = pose; s.rawT = now; }
    if (now - (s.rawT || 0) > 90 && s.pose !== s.rawPose) s.pose = s.rawPose;      // la pose doit tenir ~3 images
    const tip = P[8], mid = { x: (P[4].x + P[8].x) / 2, y: (P[4].y + P[8].y) / 2 };
    const w = Math.max(0, Math.min(1, (0.95 - s.ratio) / 0.6));                     // fondu index → milieu du pincement
    s.pt = { x: (tip.x + (mid.x - tip.x) * w) * W, y: (tip.y + (mid.y - tip.y) * w) * H };
    s.roll = Math.atan2((P[9].y - P[0].y) * H, (P[9].x - P[0].x) * W);
    s.ps = pw / W;
  }
  const present = (s, t) => s && s.P && t - s.seen < 220;

  // ------------------------------------------------------------------ géométrie et dessin des formes
  function project(o, p) {
    const [x, y, z] = p;
    const cy = Math.cos(o.ry), sy = Math.sin(o.ry), cx = Math.cos(o.rx), sx = Math.sin(o.rx), cz = Math.cos(o.rz), sz = Math.sin(o.rz);
    const x1 = x * cy + z * sy, z1 = -x * sy + z * cy, y1 = y * cx - z1 * sx, z2 = y * sx + z1 * cx;
    const x2 = x1 * cz - y1 * sz, y2 = x1 * sz + y1 * cz;
    const k = o.size * o.s * o.anim / (1 - z2 * 0.22);
    return [o.x + x2 * k, o.y + y2 * k, z2];
  }
  function drawShape(o, state) {         // state : 0 normal, 1 survol, 2 tenu
    const tint = TINT[o.kind] || CYAN, near = new Path2D(), far = new Path2D(), dots = [];
    for (const line of GEOM[o.kind]) {
      let zs = 0; const pr = line.map(p => { const q = project(o, p); zs += q[2]; return q; });
      const path = zs / line.length > 0 ? near : far;
      pr.forEach((q, i) => i ? path.lineTo(q[0], q[1]) : path.moveTo(q[0], q[1]));
      if (GEOM[o.kind].length <= 12) dots.push(pr[0], pr[pr.length - 1]);
    }
    ctx.save();
    ctx.globalAlpha = o.dying ? Math.max(0, 1 - (performance.now() - o.dying) / 350) : 1;
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.shadowColor = `rgba(${tint},.9)`; ctx.shadowBlur = state === 2 ? 18 : state === 1 ? 12 : 8;
    const col = state === 2 ? '235,250,255' : tint, lw = state === 2 ? 2.4 : state === 1 ? 2 : 1.6;
    ctx.strokeStyle = `rgba(${col},.4)`; ctx.lineWidth = lw * 0.8; ctx.stroke(far);
    ctx.strokeStyle = `rgba(${col},.95)`; ctx.lineWidth = lw; ctx.stroke(near);
    ctx.shadowBlur = 0; ctx.fillStyle = state === 2 ? '#fff' : `rgba(${tint},.95)`;
    for (const q of dots) { ctx.beginPath(); ctx.arc(q[0], q[1], 2.4, 0, 6.283); ctx.fill(); }
    ctx.restore();
  }
  function roundRect(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  function pickObj(x, y, grow = 1.15) {
    let best = null, bd = 1e9;
    for (const o of shapes) { if (o.dying) continue; const d = Math.hypot(x - o.x, y - o.y), r = o.size * o.s * grow; if (d < r && d < bd) { bd = d; best = o; } }
    return best;
  }
  const trash = () => ({ x: W - 118, y: H - 66, w: 104, h: 52 });
  const inTrash = (x, y) => { const t = trash(); return x > t.x && x < t.x + t.w && y > t.y && y < t.y + t.h; };
  function toolbar() {
    const labels = [...KINDS.map(k => ({ k, t: k.toUpperCase() })), { k: '__clear', t: 'EFFACER' }];
    const bw = Math.min(88, (W - 20) / labels.length - 5), bh = 24, tot = labels.length * (bw + 5) - 5;
    return labels.map((l, i) => ({ ...l, x: W / 2 - tot / 2 + i * (bw + 5), y: 8, w: bw, h: bh }));
  }
  function press(b) { if (b.k === '__clear') shapes.forEach(o => { o.dying = performance.now(); }); else addShape(b.k); }
  const dwell = { btn: null, t0: 0, done: 0 };

  // ------------------------------------------------------------------ onglet ATELIER 3D
  function stepAtelier(now, dt) {
    const hs = [];
    for (const k of [0, 1]) { const s = slots[k]; if (present(s, now)) hs.push({ id: k, x: s.pt.x, y: s.pt.y, pinch: s.pinch, ps: s.ps, roll: s.roll, pose: s.pose, tip: { x: s.P[8].x * W, y: s.P[8].y * H } }); }
    if (mouse.active) hs.push({ id: 2, x: mouse.x, y: mouse.y, pinch: mouse.down, ps: 0.2, roll: 0, pose: mouse.down ? 'pince' : 'index', tip: { x: mouse.x, y: mouse.y } });
    for (const h of hs) {      // un pincement qui saute une image ne lâche pas la forme (tolérance 150 ms)
      if (h.pinch) lastPinch.set(h.id, now);
      else if (wasPinch.get(h.id) && now - (lastPinch.get(h.id) || 0) < 150 && h.pose !== 'paume') h.pinch = true;
    }
    const tb = toolbar();
    let hover = null;
    for (const h of hs) {
      let g = grabs.get(h.id);
      const ob = pickObj(h.x, h.y, 1.3);
      if (!h.pinch) hover = hover || ob;
      const was = wasPinch.get(h.id);
      if (h.pinch && !was && !g && !draw.has(h.id)) {
        const b = tb.find(b => h.x > b.x && h.x < b.x + b.w && h.y > b.y && h.y < b.y + b.h);
        if (b) press(b);
        else if (ob) { g = { o: ob, dx: ob.x - h.x, dy: ob.y - h.y, s0: ob.s, ps0: h.ps, rz0: ob.rz, roll0: h.roll, t0: now, hist: [] }; grabs.set(h.id, g); ob.vx = ob.vy = 0;
          shapes.push(shapes.splice(shapes.indexOf(ob), 1)[0]); }
        else if (h.y > 40) draw.set(h.id, { pts: [{ x: h.x, y: h.y }] });
      }
      if (h.pinch && g) {
        const o = g.o, tx = h.x + g.dx, ty = h.y + g.dy;
        g.hist.push({ x: tx, y: ty, t: now }); while (g.hist.length > 6) g.hist.shift();
        o.x += (tx - o.x) * 0.7; o.y += (ty - o.y) * 0.7;
        const other = [...grabs].find(([id, gg]) => id !== h.id && gg.o === o);
        if (!other) { o.s += (Math.max(0.35, Math.min(3, g.s0 * Math.pow(h.ps / g.ps0, 1.5))) - o.s) * 0.35; o.rz += ((g.rz0 + (h.roll - g.roll0) * 0.8) - o.rz) * 0.4; }
      }
      const dr = draw.get(h.id);
      if (h.pinch && dr) { const l = dr.pts[dr.pts.length - 1]; if (Math.hypot(h.x - l.x, h.y - l.y) > 4) dr.pts.push({ x: h.x, y: h.y }); }
      if (!h.pinch) {
        if (g) {                                   // relâché : lancer (inertie) ou corbeille
          const o = g.o, a = g.hist[0], b = g.hist[g.hist.length - 1];
          if (inTrash(o.x, o.y)) o.dying = now;
          else if (a && b && b.t > a.t) { o.vx = (b.x - a.x) / (b.t - a.t) * 1000; o.vy = (b.y - a.y) / (b.t - a.t) * 1000; }
          grabs.delete(h.id);
        }
        if (dr) { draw.delete(h.id); const r = recognize(dr.pts);
          if (r) { addShape(r.kind, r.x, r.y, r.size); hints.push({ t: r.kind.toUpperCase(), x: r.x, y: r.y - r.size - 14, t0: now }); strokes.push({ pts: dr.pts, t0: now, ok: true }); }
          else if (dr.pts.length > 8) { strokes.push({ pts: dr.pts, t0: now, ok: false }); hints.push({ t: 'FORME NON RECONNUE', x: dr.pts[0].x, y: dr.pts[0].y, t0: now }); } }
      }
      wasPinch.set(h.id, h.pinch);
    }
    // deux mains sur la même forme : écartement = taille, angle = rotation
    const gs = [...grabs];
    if (gs.length === 2 && gs[0][1].o === gs[1][1].o) {
      const A = hs.find(x => x.id === gs[0][0]), B = hs.find(x => x.id === gs[1][0]), o = gs[0][1].o;
      if (A && B) { const d = Math.hypot(A.x - B.x, A.y - B.y), ang = Math.atan2(B.y - A.y, B.x - A.x);
        if (!o._two) o._two = { d0: d, s0: o.s, a0: ang, rz0: o.rz };
        o.s += (Math.max(0.35, Math.min(3, o._two.s0 * d / o._two.d0)) - o.s) * 0.4; o.rz = o._two.rz0 + (ang - o._two.a0); }
    } else shapes.forEach(o => { o._two = null; });
    // 2e main qui pince dans le vide pendant que la 1re tient une forme : elle prend la même forme
    for (const h of hs) if (h.pinch && !grabs.has(h.id) && !draw.has(h.id)) { const other = [...grabs].find(([id]) => id !== h.id);
      if (other) grabs.set(h.id, { o: other[1].o, dx: 0, dy: 0, s0: other[1].o.s, ps0: h.ps, rz0: other[1].o.rz, roll0: h.roll, t0: now, hist: [] }); }
    // pointer du doigt un bouton 0,7 s
    let prog = null, any = false;
    for (const h of hs) if (h.pose === 'index') { const b = tb.find(b => h.tip.x > b.x && h.tip.x < b.x + b.w && h.tip.y > b.y && h.tip.y < b.y + b.h);
      if (b) { any = true; if (dwell.btn !== b.k) { dwell.btn = b.k; dwell.t0 = now; } const v = Math.min(1, (now - dwell.t0) / 700); prog = { btn: b.k, v };
        if (v >= 1 && now - dwell.done > 1200) { dwell.done = now; dwell.t0 = now; press(b); } } }
    if (!any) dwell.btn = null;
    // physique douce : inertie, rebonds, rotation lente, disparition
    const held = new Set([...grabs.values()].map(g => g.o));
    for (const o of shapes) {
      const age = (now - o.born) / 400; o.anim = Math.min(1, 0.25 + 0.75 * (1 - Math.pow(1 - Math.min(1, age), 3)));
      if (held.has(o)) continue;
      o.ry += o.spin * dt;
      if (o.vx || o.vy) { o.x += o.vx * dt; o.y += o.vy * dt; const f = Math.pow(0.9, dt * 60); o.vx *= f; o.vy *= f; if (Math.hypot(o.vx, o.vy) < 8) o.vx = o.vy = 0;
        if (o.x < 20 || o.x > W - 20) { o.vx *= -0.6; o.x = Math.max(20, Math.min(W - 20, o.x)); } if (o.y < 20 || o.y > H - 20) { o.vy *= -0.6; o.y = Math.max(20, Math.min(H - 20, o.y)); } }
    }
    for (let i = shapes.length - 1; i >= 0; i--) if (shapes[i].dying && now - shapes[i].dying > 350) shapes.splice(i, 1);
    // dessin
    for (const o of shapes) drawShape(o, held.has(o) ? 2 : (o === hover ? 1 : 0));
    for (const [, d] of draw) strokeLine(d.pts, 1, true);
    for (let i = strokes.length - 1; i >= 0; i--) { const a = 1 - (now - strokes[i].t0) / 700; if (a <= 0) strokes.splice(i, 1); else strokeLine(strokes[i].pts, a, strokes[i].ok); }
    for (let i = hints.length - 1; i >= 0; i--) { const a = 1 - (now - hints[i].t0) / 1400; if (a <= 0) { hints.splice(i, 1); continue; }
      ctx.save(); ctx.globalAlpha = a; ctx.fillStyle = '#e8f8ff'; ctx.font = '600 11px "Cascadia Mono", Consolas, monospace'; ctx.textAlign = 'center'; ctx.shadowColor = `rgba(${CYAN},.9)`; ctx.shadowBlur = 8;
      ctx.fillText(hints[i].t, hints[i].x, hints[i].y - (1 - a) * 14); ctx.restore(); }
    if (held.size) { const t = trash(), over = [...held].some(o => inTrash(o.x, o.y)); roundRect(t.x, t.y, t.w, t.h, 8);
      ctx.fillStyle = over ? 'rgba(255,90,90,.28)' : 'rgba(3,14,24,.7)'; ctx.fill(); ctx.strokeStyle = over ? 'rgba(255,120,120,.95)' : `rgba(${CYAN},.5)`; ctx.lineWidth = 1.4; ctx.stroke();
      ctx.fillStyle = over ? '#ffd0d0' : 'rgba(214,236,245,.85)'; ctx.font = '600 10px "Cascadia Mono", Consolas, monospace'; ctx.textAlign = 'center'; ctx.fillText('SUPPRIMER', t.x + t.w / 2, t.y + t.h / 2 + 3); ctx.textAlign = 'left'; }
    drawToolbar(tb, prog);
    if (!shapes.length && !draw.size) { ctx.fillStyle = 'rgba(214,236,245,.55)'; ctx.font = '12px "Cascadia Mono", Consolas, monospace'; ctx.textAlign = 'center';
      ctx.fillText('Pince le pouce et l’index dans le vide et dessine : ○ sphère · □ cube · △ pyramide · ◇ octaèdre · ▭ cylindre · ◎ anneau (2 tours)', W / 2, H * 0.72); ctx.textAlign = 'left'; }
  }
  const wasPinch = new Map(), lastPinch = new Map();
  function strokeLine(pts, a, ok) {
    if (pts.length < 2) return;
    ctx.save(); ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.globalAlpha = a;
    ctx.strokeStyle = ok ? 'rgba(160,240,255,.95)' : 'rgba(255,140,140,.9)'; ctx.shadowColor = ok ? `rgba(${CYAN},1)` : 'rgba(255,90,90,1)'; ctx.shadowBlur = 12; ctx.lineWidth = 3;
    ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)); ctx.stroke(); ctx.restore();
  }
  function drawToolbar(tb, prog) {
    ctx.save(); ctx.font = '600 9px "Cascadia Mono", Consolas, monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (const b of tb) {
      roundRect(b.x, b.y, b.w, b.h, 4); ctx.fillStyle = 'rgba(3,14,24,.75)'; ctx.fill();
      ctx.strokeStyle = `rgba(${CYAN},${prog && prog.btn === b.k ? .95 : .4})`; ctx.lineWidth = 1; ctx.stroke();
      if (prog && prog.btn === b.k) { ctx.fillStyle = `rgba(${CYAN},.35)`; ctx.fillRect(b.x, b.y + b.h - 3, b.w * prog.v, 3); }
      ctx.fillStyle = '#d6ecf5'; ctx.fillText(b.t, b.x + b.w / 2, b.y + b.h / 2 + 1);
    }
    ctx.restore();
  }
  function drawHand(s, color) {
    const P = s.P.map(p => ({ x: p.x * W, y: p.y * H })), links = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12], [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17]];
    ctx.save(); ctx.lineWidth = 1.3; ctx.strokeStyle = `rgba(${color},.7)`; ctx.shadowColor = `rgba(${color},.8)`; ctx.shadowBlur = 6;
    ctx.beginPath(); for (const [a, b] of links) { ctx.moveTo(P[a].x, P[a].y); ctx.lineTo(P[b].x, P[b].y); } ctx.stroke();
    ctx.fillStyle = '#e8f8ff'; for (const p of P) { ctx.beginPath(); ctx.arc(p.x, p.y, 2, 0, 6.283); ctx.fill(); }
    if (s.pinch || s.rpinch) { ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(s.pt.x, s.pt.y, 11, 0, 6.283); ctx.stroke(); }
    else if (s.ratio < 0.7) { ctx.strokeStyle = `rgba(${color},.7)`; ctx.lineWidth = 1.4; ctx.beginPath(); ctx.arc(s.pt.x, s.pt.y, 7 + 10 * (s.ratio - 0.4) / 0.3, 0, 6.283); ctx.stroke(); }
    ctx.restore();
  }

  // ------------------------------------------------------------------ boucle d'affichage (60 images/s)
  let lastT = performance.now();
  function loop() { raf = requestAnimationFrame(loop); frame(); }
  function frame() {
    if (!open) return;
    if (typeof gaming !== 'undefined' && gaming) { close(true); return; }   // un jeu démarre : la caméra se coupe
    const now = performance.now(), dt = Math.min(0.1, (now - lastT) / 1000); lastT = now;
    fpsN++; if (now - fpsT > 1000) { fps = fpsN; fpsN = 0; fpsT = now; }
    if (window.CAM3D && window.CAM3D._fake) ingest({ landmarks: window.CAM3D._fake(), handednesses: [] }, now);   // tests : mains simulées
    ctx.clearRect(0, 0, W, H);
    if (!video.videoWidth) { ctx.fillStyle = '#02060c'; ctx.fillRect(0, 0, W, H); }
    stepAtelier(now, dt);
    let n = 0;
    for (const k of [0, 1]) if (present(slots[k], now)) { n++; drawHand(slots[k], CYAN); }
    hudEl.textContent = loadingMsg || `${n} main(s) · ${shapes.length} forme(s)`;
    barEl.textContent = streaming ? '● JARVIS TE VOIT EN DIRECT' : `${fps} img/s`;
    barEl.style.color = streaming ? '#ff7a7a' : '';
    if (mouse.active) { ctx.save(); ctx.strokeStyle = mouse.down ? '#fff' : `rgba(${CYAN},.8)`; ctx.lineWidth = 1.6; ctx.beginPath(); ctx.arc(mouse.x, mouse.y, mouse.down ? 9 : 14, 0, 6.283); ctx.stroke(); ctx.restore(); }
  }

  // ------------------------------------------------------------------ commandes du serveur
  function state(d) {
    if (!d || d.n === lastN) return;
    lastN = d.n;
    if (!win) build();
    if (d.on === false) { close(false); return; }
    if (d.on) {
      if (!open) { open = true; win.classList.add('on'); setFull(full); start(); setMode(d.mode || mode); }
    }
    if (typeof d.stream === 'boolean') setStreaming(d.stream);
    if (d.cmd && d.cmd.id !== lastCmd) {
      lastCmd = d.cmd.id;
      if (d.cmd.op === 'clear') shapes.forEach(o => { o.dying = performance.now(); });
      if (d.cmd.op === 'add') { addShape(d.cmd.type); }
    }
  }
  window.CAM3D = { isOpen: () => open, state, close: () => close(true), shapes, setMode, addShape, tick: frame, _slots: slots, recognize };
})();

/* Visionneuse 3D / plateau de JARVIS (fenêtre à droite du panneau) : un ou PLUSIEURS modèles STL / OBJ en hologramme sur le
   plateau de l'Ender 3 (220 × 220 mm), à déplacer à la souris ou au doigt directement sur le plateau, tourner, agrandir,
   dupliquer ; options d'impression communes (supports, remplissage, qualité, accroche) ; découpe et impression (2 clics)
   de tout le plateau d'un coup, aux positions choisies (assemblé par JARVIS : /api/print/plate).
   WebGL sans bibliothèque. Ouverte par la voix (outil voir_modele_3d -> UIX « m3d ») ou « Voir en 3D » (page Imprimante). */
(() => {
  'use strict';
  const tokq = () => 'token=' + encodeURIComponent(window.JTOKEN || '');
  const post = (p, b) => fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(Object.assign({ token: window.JTOKEN }, b)) }).then(r => r.json());
  const BED = { x: 220, y: 220, z: 250 }, HALF = 110, GAP = 3;
  let ov, cv, gl, progM, progL, bed = null, raf = 0, lastN = -1;
  let objs = [], sel = -1, uid = 1;            // objets : {uid, id, name, g:{bp,bn,n}, sx, sy, sz, tris, x, z, rot, scale}
  const cache = new Map();                     // id du fichier -> géométrie déjà chargée
  let opts = { supports: false, infill: 20, pattern: 'auto', quality: 'normal', brim: false };
  let yaw = 0.7, pitch = 0.62, zoom = 1, lastTouch = 0, t0 = performance.now(), vpCur = null, drag = null;

  // ------------------------------------------------------------------ matrices 4×4 (colonnes)
  const M = {
    mul(a, b) { const o = new Float32Array(16); for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) { let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + j] * b[i * 4 + k]; o[i * 4 + j] = s; } return o; },
    persp(f, a, n, fa) { const t = 1 / Math.tan(f / 2), o = new Float32Array(16); o[0] = t / a; o[5] = t; o[10] = (fa + n) / (n - fa); o[11] = -1; o[14] = 2 * fa * n / (n - fa); return o; },
    id() { const o = new Float32Array(16); o[0] = o[5] = o[10] = o[15] = 1; return o; },
    tr(x, y, z) { const o = M.id(); o[12] = x; o[13] = y; o[14] = z; return o; },
    rx(a) { const o = M.id(), c = Math.cos(a), s = Math.sin(a); o[5] = c; o[6] = s; o[9] = -s; o[10] = c; return o; },
    ry(a) { const o = M.id(), c = Math.cos(a), s = Math.sin(a); o[0] = c; o[2] = -s; o[8] = s; o[10] = c; return o; },
    sc(k) { const o = M.id(); o[0] = o[5] = o[10] = k; return o; },
    inv(a) {  // inverse générale 4×4
      const o = new Float32Array(16);
      const b00 = a[0] * a[5] - a[1] * a[4], b01 = a[0] * a[6] - a[2] * a[4], b02 = a[0] * a[7] - a[3] * a[4], b03 = a[1] * a[6] - a[2] * a[5];
      const b04 = a[1] * a[7] - a[3] * a[5], b05 = a[2] * a[7] - a[3] * a[6], b06 = a[8] * a[13] - a[9] * a[12], b07 = a[8] * a[14] - a[10] * a[12];
      const b08 = a[8] * a[15] - a[11] * a[12], b09 = a[9] * a[14] - a[10] * a[13], b10 = a[9] * a[15] - a[11] * a[13], b11 = a[10] * a[15] - a[11] * a[14];
      let d = b00 * b11 - b01 * b10 + b02 * b09 + b03 * b08 - b04 * b07 + b05 * b06; if (!d) return null; d = 1 / d;
      o[0] = (a[5] * b11 - a[6] * b10 + a[7] * b09) * d; o[1] = (a[2] * b10 - a[1] * b11 - a[3] * b09) * d; o[2] = (a[13] * b05 - a[14] * b04 + a[15] * b03) * d; o[3] = (a[10] * b04 - a[9] * b05 - a[11] * b03) * d;
      o[4] = (a[6] * b08 - a[4] * b11 - a[7] * b07) * d; o[5] = (a[0] * b11 - a[2] * b08 + a[3] * b07) * d; o[6] = (a[14] * b02 - a[12] * b05 - a[15] * b01) * d; o[7] = (a[8] * b05 - a[10] * b02 + a[11] * b01) * d;
      o[8] = (a[4] * b10 - a[5] * b08 + a[7] * b06) * d; o[9] = (a[1] * b08 - a[0] * b10 - a[3] * b06) * d; o[10] = (a[12] * b04 - a[13] * b02 + a[15] * b00) * d; o[11] = (a[9] * b02 - a[8] * b04 - a[11] * b00) * d;
      o[12] = (a[5] * b07 - a[4] * b09 - a[6] * b06) * d; o[13] = (a[0] * b09 - a[1] * b07 + a[2] * b06) * d; o[14] = (a[13] * b01 - a[12] * b03 - a[14] * b00) * d; o[15] = (a[8] * b03 - a[9] * b01 + a[10] * b00) * d;
      return o;
    },
    tx(m, v) { const o = [0, 0, 0, 0]; for (let j = 0; j < 4; j++) for (let k = 0; k < 4; k++) o[j] += m[k * 4 + j] * v[k]; return o; },
  };

  // ------------------------------------------------------------------ lecture des fichiers
  function parseSTL(b) {
    const dv = new DataView(b), n = b.byteLength >= 84 ? dv.getUint32(80, true) : 0, out = [];
    if (n && 84 + n * 50 === b.byteLength) {
      for (let i = 0; i < n; i++) { const o = 84 + i * 50 + 12; for (let v = 0; v < 3; v++) out.push(dv.getFloat32(o + v * 12, true), dv.getFloat32(o + v * 12 + 4, true), dv.getFloat32(o + v * 12 + 8, true)); }
      return new Float32Array(out);
    }
    const txt = new TextDecoder().decode(b), re = /vertex\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)/g;
    let m; while ((m = re.exec(txt))) out.push(+m[1], +m[2], +m[3]);
    return new Float32Array(out);
  }
  function parseOBJ(txt) {
    const v = [], out = [];
    for (const line of txt.split('\n')) {
      const p = line.trim().split(/\s+/);
      if (p[0] === 'v') v.push([+p[1], +p[2], +p[3]]);
      else if (p[0] === 'f') { const ix = p.slice(1).map(s => { const k = parseInt(s, 10); return k < 0 ? v.length + k : k - 1; });
        for (let i = 1; i + 1 < ix.length; i++) for (const k of [ix[0], ix[i], ix[i + 1]]) { const q = v[k] || [0, 0, 0]; out.push(q[0], q[1], q[2]); } }
    }
    return new Float32Array(out);
  }

  // ------------------------------------------------------------------ WebGL
  const VS = `attribute vec3 p; attribute vec3 n; uniform mat4 mvp; uniform mat4 mv; varying vec3 vn; varying float vy;
    void main(){ vn = (mv * vec4(n,0.)).xyz; vy = p.y; gl_Position = mvp * vec4(p,1.); }`;
  const FS = `precision mediump float; varying vec3 vn; varying float vy; uniform float t; uniform float hmax; uniform float sel; uniform float warn;
    void main(){ vec3 N = normalize(vn); float f = pow(1. - abs(N.z), 2.2); float d = max(dot(N, normalize(vec3(.4,.8,.6))), 0.);
      vec3 rim = mix(vec3(0.,.82,1.), vec3(1.,.55,.2), warn);
      vec3 c = mix(vec3(.03,.22,.36), vec3(.05,.32,.5), sel) * (.45 + .75*d) + rim * f * (1.15 + .6*sel);
      float scan = smoothstep(.0,.02, abs(fract(vy/ max(hmax,1.) * 24. - t*.35) - .5) - .45);
      c += vec3(.0,.5,.7) * (1.-scan) * (.25 + .25*sel);
      gl_FragColor = vec4(c, .93); }`;
  const VL = `attribute vec3 p; uniform mat4 mvp; void main(){ gl_Position = mvp * vec4(p,1.); }`;
  const FL = `precision mediump float; uniform vec4 col; void main(){ gl_FragColor = col; }`;
  function sh(type, src) { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; }
  function prog(vs, fs) { const p = gl.createProgram(); gl.attachShader(p, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(p); return p; }
  const buf = (a) => { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, a instanceof Float32Array ? a : new Float32Array(a), gl.STATIC_DRAW); return b; };
  function initGL() {
    gl = cv.getContext('webgl', { antialias: true, premultipliedAlpha: false });
    if (!gl) return false;
    progM = prog(VS, FS); progL = prog(VL, FL);
    const L = [], L5 = [], hx = BED.x / 2, hz = BED.y / 2;
    for (let i = -hx; i <= hx + 0.01; i += 10) (Math.round(i) % 50 === 0 ? L5 : L).push(i, 0, -hz, i, 0, hz);
    for (let i = -hz; i <= hz + 0.01; i += 10) (Math.round(i) % 50 === 0 ? L5 : L).push(-hx, 0, i, hx, 0, i);
    const rect = (m) => [-hx - m, 0, -hz - m, hx + m, 0, -hz - m, hx + m, 0, -hz - m, hx + m, 0, hz + m, hx + m, 0, hz + m, -hx - m, 0, hz + m, -hx - m, 0, hz + m, -hx - m, 0, -hz - m];
    const E = [...rect(0), ...rect(1.2), ...rect(2.4)];
    const F = [-hx, -0.3, -hz, hx, -0.3, -hz, hx, -0.3, hz, -hx, -0.3, -hz, hx, -0.3, hz, -hx, -0.3, hz];
    bed = { bl: buf(L), nl: L.length / 3, bl5: buf(L5), nl5: L5.length / 3, be: buf(E), ne: E.length / 3, bf: buf(F) };
    return true;
  }
  function geometry(pos) {
    // Z vers le haut -> Y vers le haut ; centré en X/Y, posé à Y = 0 ; normales de faces
    let x0 = 1e9, y0 = 1e9, z0 = 1e9, x1 = -1e9, y1 = -1e9, z1 = -1e9;
    for (let i = 0; i < pos.length; i += 3) { x0 = Math.min(x0, pos[i]); x1 = Math.max(x1, pos[i]); y0 = Math.min(y0, pos[i + 1]); y1 = Math.max(y1, pos[i + 1]); z0 = Math.min(z0, pos[i + 2]); z1 = Math.max(z1, pos[i + 2]); }
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, P = new Float32Array(pos.length), N = new Float32Array(pos.length);
    for (let i = 0; i < pos.length; i += 3) { P[i] = pos[i] - cx; P[i + 1] = pos[i + 2] - z0; P[i + 2] = -(pos[i + 1] - cy); }
    for (let i = 0; i < P.length; i += 9) {
      const ax = P[i + 3] - P[i], ay = P[i + 4] - P[i + 1], az = P[i + 5] - P[i + 2], bx = P[i + 6] - P[i], by = P[i + 7] - P[i + 1], bz = P[i + 8] - P[i + 2];
      let nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx; const l = Math.hypot(nx, ny, nz) || 1; nx /= l; ny /= l; nz /= l;
      for (let k = 0; k < 9; k += 3) { N[i + k] = nx; N[i + k + 1] = ny; N[i + k + 2] = nz; }
    }
    return { g: { bp: buf(P), bn: buf(N), n: P.length / 3 }, sx: x1 - x0, sy: y1 - y0, sz: z1 - z0, tris: P.length / 9 };
  }


  // ---- repères du plateau (étiquettes HTML placées en projetant des points 3D) : partagés par les deux vues
  const LABELS = [['AVANT', 0, 0, 122, ''], ['ARRIÈRE', 0, 0, -122, ''], ['GAUCHE', -126, 0, 0, ''],
                  ['DROITE', 126, 0, 0, ''], ['DÉPART DE LA BUSE', -110, 0, 110, 'o']];
  function makeLabels(parent) {
    const box = document.createElement('div'); box.style.cssText = 'position:absolute;inset:0;pointer-events:none;overflow:hidden';
    for (const [t, , , , k] of LABELS) { const d = document.createElement('div'); d.textContent = t;
      d.style.cssText = 'position:absolute;transform:translate(-50%,-50%);white-space:nowrap;font:600 11px Cascadia Mono,Consolas,monospace;letter-spacing:2px;'
        + (k === 'f' ? 'color:#fff;background:rgba(0,150,200,.55);padding:3px 8px;border:1px solid rgba(0,210,255,.9);'
          : k === 'o' ? 'color:#ffc078;font-size:10px;' : 'color:rgba(150,225,255,.75);');
      box.appendChild(d); }
    parent.appendChild(box); return box;
  }
  function placeLabels(box, vp, w, h) {
    if (!box) return;
    [...box.children].forEach((d, i) => { const [, x, y, z] = LABELS[i], p = M.tx(vp, [x, y, z, 1]);
      if (p[3] <= 0) { d.style.display = 'none'; return; }
      d.style.display = ''; d.style.left = ((p[0] / p[3] + 1) / 2 * w) + 'px'; d.style.top = ((1 - p[1] / p[3]) / 2 * h) + 'px'; });
  }
  // axes au coin de départ : X (rouge, vers la droite) et Y (vert, vers l'arrière)
  const AXES = new Float32Array([-110, 0.2, 110, -70, 0.2, 110, -110, 0.2, 110, -110, 0.2, 70]);

  let lbls = null, axesBuf = null;
  // ------------------------------------------------------------------ place occupée, chevauchements, débordements
  function half(o) { const k = o.scale / 100, w = o.sx * k / 2, d = o.sy * k / 2, c = Math.abs(Math.cos(o.rot)), s = Math.abs(Math.sin(o.rot));
    return [c * w + s * d, s * w + c * d]; }
  function outOf(o) { const [hw, hd] = half(o); return Math.abs(o.x) + hw > HALF + 0.01 || Math.abs(o.z) + hd > HALF + 0.01 || o.sz * o.scale / 100 > BED.z; }
  function hits(a, b) { const [aw, ad] = half(a), [bw, bd] = half(b); return Math.abs(a.x - b.x) < aw + bw + GAP && Math.abs(a.z - b.z) < ad + bd + GAP; }
  const problems = () => objs.map((o, i) => ({ out: outOf(o), hit: objs.some((b, j) => j !== i && hits(o, b)) }));
  function freeSpot(o) {   // une place libre sur le plateau (spirale depuis le centre)
    for (let r = 0; r <= HALF; r += 5) for (let a = 0; a < (r ? 24 : 1); a++) {
      o.x = Math.round(r * Math.cos(a / 24 * 2 * Math.PI)); o.z = Math.round(r * Math.sin(a / 24 * 2 * Math.PI));
      if (!outOf(o) && !objs.some(b => b !== o && hits(o, b))) return true;
    }
    o.x = o.z = 0; return false;
  }

  // ------------------------------------------------------------------ dessin
  function draw() {
    raf = requestAnimationFrame(draw);
    if (!gl) return;
    const w = cv.clientWidth, h = cv.clientHeight, d = Math.min(2, devicePixelRatio || 1);
    if (cv.width !== Math.round(w * d) || cv.height !== Math.round(h * d)) { cv.width = Math.round(w * d); cv.height = Math.round(h * d); }
    gl.viewport(0, 0, cv.width, cv.height);
    gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    const now = performance.now();
    if (now - lastTouch > 6000 && !drag) yaw += 0.003;   // tourne doucement tout seul quand on n'y touche pas
    const H = Math.max(10, ...objs.map(o => o.sz * o.scale / 100)), span = Math.max(BED.x, H * 1.6);
    const proj = M.persp(0.75, w / Math.max(1, h), 1, 5000);
    const view = M.mul(M.tr(0, -Math.min(H, BED.z) * 0.3 + span * 0.06, -span * 1.85 / zoom), M.mul(M.rx(pitch), M.ry(yaw)));
    vpCur = M.mul(proj, view);
    gl.enable(gl.DEPTH_TEST); gl.enable(gl.BLEND);
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);   // sinon l'opacité se multiplie (plateau invisible)
    for (let i = 0; i < 4; i++) gl.disableVertexAttribArray(i);
    // plateau
    gl.useProgram(progL);
    const pl = gl.getAttribLocation(progL, 'p');
    gl.uniformMatrix4fv(gl.getUniformLocation(progL, 'mvp'), false, vpCur);
    gl.enableVertexAttribArray(pl);
    const lines = (b, n, mode, r, g, bb, a) => { gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.vertexAttribPointer(pl, 3, gl.FLOAT, false, 0, 0);
      gl.uniform4f(gl.getUniformLocation(progL, 'col'), r, g, bb, a); gl.drawArrays(mode, 0, n); };
    gl.depthMask(false);
    lines(bed.bf, 6, gl.TRIANGLES, 0.0, 0.32, 0.48, 0.42);
    lines(bed.bl, bed.nl, gl.LINES, 0.2, 0.85, 1.0, 0.34);
    lines(bed.bl5, bed.nl5, gl.LINES, 0.35, 0.92, 1.0, 0.7);
    lines(bed.be, bed.ne, gl.LINES, 0.55, 0.95, 1.0, 1.0);
    if (!axesBuf) axesBuf = buf(AXES);
    lines(axesBuf, 2, gl.LINES, 1.0, 0.35, 0.3, 1.0); gl.bindBuffer(gl.ARRAY_BUFFER, axesBuf);
    gl.vertexAttribPointer(pl, 3, gl.FLOAT, false, 12, 24); gl.uniform4f(gl.getUniformLocation(progL, 'col'), 0.35, 1.0, 0.45, 1.0); gl.drawArrays(gl.LINES, 0, 2);
    gl.depthMask(true);
    placeLabels(lbls, vpCur, w, h);
    gl.disableVertexAttribArray(pl);
    // objets
    gl.useProgram(progM);
    const ap = gl.getAttribLocation(progM, 'p'), an = gl.getAttribLocation(progM, 'n');
    gl.uniform1f(gl.getUniformLocation(progM, 't'), (now - t0) / 1000);
    gl.enableVertexAttribArray(ap); gl.enableVertexAttribArray(an);
    const pb = problems();
    objs.forEach((o, i) => {
      const model = M.mul(M.tr(o.x, 0, o.z), M.mul(M.ry(o.rot), M.sc(o.scale / 100))), mv = M.mul(view, model);
      gl.uniformMatrix4fv(gl.getUniformLocation(progM, 'mvp'), false, M.mul(proj, mv));
      gl.uniformMatrix4fv(gl.getUniformLocation(progM, 'mv'), false, mv);
      gl.uniform1f(gl.getUniformLocation(progM, 'hmax'), o.sz);
      gl.uniform1f(gl.getUniformLocation(progM, 'sel'), i === sel ? 1 : 0);
      gl.uniform1f(gl.getUniformLocation(progM, 'warn'), pb[i].out || pb[i].hit ? 1 : 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, o.g.bp); gl.vertexAttribPointer(ap, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, o.g.bn); gl.vertexAttribPointer(an, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.TRIANGLES, 0, o.g.n);
    });
    gl.disableVertexAttribArray(an); gl.disableVertexAttribArray(ap);
  }
  // point du plateau (hauteur 0) sous la souris
  function bedPoint(cx, cy) {
    if (!vpCur) return null;
    const r = cv.getBoundingClientRect(), nx = (cx - r.left) / r.width * 2 - 1, ny = 1 - (cy - r.top) / r.height * 2, iv = M.inv(vpCur);
    if (!iv) return null;
    const a = M.tx(iv, [nx, ny, -1, 1]), b = M.tx(iv, [nx, ny, 1, 1]);
    const p0 = [a[0] / a[3], a[1] / a[3], a[2] / a[3]], p1 = [b[0] / b[3], b[1] / b[3], b[2] / b[3]];
    const dy = p1[1] - p0[1]; if (Math.abs(dy) < 1e-6) return null;
    const t = -p0[1] / dy; if (t < 0) return null;
    return [p0[0] + (p1[0] - p0[0]) * t, p0[2] + (p1[2] - p0[2]) * t];
  }
  function pick(cx, cy) {
    const p = bedPoint(cx, cy); if (!p) return -1;
    let best = -1, bd = 1e9;
    objs.forEach((o, i) => { const [hw, hd] = half(o); const dx = Math.abs(p[0] - o.x), dz = Math.abs(p[1] - o.z);
      if (dx <= hw + 2 && dz <= hd + 2) { const dd = Math.hypot(dx, dz); if (dd < bd) { bd = dd; best = i; } } });
    return best;
  }

  // ------------------------------------------------------------------ fenêtre
  function build() {
    const css = document.createElement('style');
    css.textContent = `
      #m3d { position: fixed; left: calc(var(--sidew, 0px) + 30px); right: 12px; bottom: 12px; top: 40px; z-index: 9; border: 1px solid rgba(0,210,255,.28); transition: left .2s ease; display: none; background:
        radial-gradient(ellipse at 40% 55%, #06283a, #02060c 70%); font-family: "Bahnschrift","Segoe UI",sans-serif; color: #d6ecf5; }
      #m3d.on { display: flex; }
      #m3d .stage { position: relative; flex: 1; min-width: 0; }
      #m3d canvas { position: absolute; inset: 0; width: 100%; height: 100%; cursor: grab; touch-action: none; }
      #m3d canvas.over { cursor: move; }
      #m3d .ttl { position: absolute; left: 22px; top: 16px; pointer-events: none; }
      #m3d .ttl b { display: block; font: 600 18px "Bahnschrift"; letter-spacing: 3px; color: #fff; text-shadow: 0 0 12px rgba(0,210,255,.6); }
      #m3d .ttl span { display: block; margin-top: 4px; font: 12px "Cascadia Mono", Consolas, monospace; letter-spacing: 1.5px; color: rgba(0,210,255,.85); }
      #m3d .ttl span.bad { color: #ffb36b; }
      #m3d .hint { position: absolute; left: 22px; bottom: 14px; font: 11px "Cascadia Mono", Consolas, monospace; color: rgba(214,236,245,.45); pointer-events: none; }
      #m3d .side { width: 340px; flex: none; border-left: 1px solid rgba(0,210,255,.25); background: linear-gradient(180deg, rgba(4,18,30,.92), rgba(2,10,18,.9));
        padding: 10px 14px; box-sizing: border-box; display: flex; flex-direction: column; gap: 5px; overflow: hidden; }
      #m3d .grp { display: flex; flex-direction: column; gap: 4px; }
      #m3d .fill { flex: 1; min-height: 4px; }
      #m3d .side h4 { margin: 2px 0 0; font: 600 11px "Cascadia Mono", Consolas, monospace; letter-spacing: 3px; color: rgba(0,210,255,.8); }
      #m3d .row { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
      #m3d .opt, #m3d .sm { display: flex; align-items: center; justify-content: center; flex: 1; min-width: 56px; height: 28px; border: 1px solid rgba(0,210,255,.3); background: rgba(3,14,24,.8); color: #bfeaff; cursor: pointer; font: 600 11px "Bahnschrift"; letter-spacing: 1px; }
      #m3d .opt.on { background: rgba(0,210,255,.22); color: #fff; border-color: rgb(0,210,255); box-shadow: 0 0 10px rgba(0,210,255,.35); }
      #m3d .sm.del { border-color: rgba(255,120,120,.45); color: #ffb0b0; }
      #m3d input[type=range] { flex: 1; accent-color: #00d2ff; }
      #m3d .val { width: 52px; text-align: right; font: 13px "Cascadia Mono", Consolas, monospace; }
      #m3d .objs { display: flex; flex-direction: column; gap: 3px; overflow-y: auto; flex: 1 1 0; min-height: 118px; }   /* seule la liste défile : le reste tient toujours */
      #m3d .side > *:not(.objs) { flex-shrink: 0; }
      #m3d .ob { display: flex; align-items: center; gap: 8px; padding: 5px 9px; border: 1px solid rgba(0,210,255,.18); background: rgba(0,20,40,.35); cursor: pointer; font-size: 12.5px; }
      #m3d .ob.on { border-color: rgb(0,210,255); background: rgba(0,210,255,.14); }
      #m3d .ob.bad { border-color: #ffb36b; } #m3d .ob i { font-style: normal; margin-left: auto; font: 11px "Cascadia Mono", Consolas, monospace; opacity: .7; }
      #m3d .ob span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      #m3d .ob .rmx { flex: none; width: 22px; height: 22px; border: 1px solid rgba(255,120,120,.4); background: transparent; color: #ffb0b0; cursor: pointer; font-size: 12px; line-height: 1; padding: 0; }
      #m3d .ob .rmx:hover { background: rgba(255,90,90,.25); color: #fff; }
      #m3d .ctx { position: fixed; z-index: 20; display: none; min-width: 170px; border: 1px solid rgba(0,210,255,.5); background: rgba(3,14,24,.97); box-shadow: 0 8px 30px rgba(0,0,0,.6); padding: 4px; }
      #m3d .ctx.on { display: block; }
      #m3d .ctx div { padding: 8px 12px; cursor: pointer; font-size: 13px; } #m3d .ctx div:hover { background: rgba(0,210,255,.18); }
      #m3d .ctx div.del { color: #ffb0b0; } #m3d .ctx div.del:hover { background: rgba(255,90,90,.22); }
      #m3d .lib { display: none; flex-direction: column; gap: 3px; max-height: 190px; overflow-y: auto; border: 1px solid rgba(0,210,255,.25); padding: 4px; }
      #m3d .lib.on { display: flex; } #m3d .lib div { padding: 6px 8px; cursor: pointer; font-size: 12.5px; } #m3d .lib div:hover { background: rgba(0,210,255,.16); }
      #m3d .act { display: flex; align-items: center; justify-content: center; height: 36px; flex: none; border: 1px solid rgba(0,210,255,.5); background: rgba(0,210,255,.12); color: #fff; cursor: pointer; font: 600 13px "Bahnschrift"; letter-spacing: 2px; }
      #m3d .act.main { background: rgb(0,150,200); border-color: rgb(0,210,255); }
      #m3d .act.armed { background: rgba(255,170,40,.25); border-color: #ffb36b; color: #ffe0b0; }
      #m3d .act:disabled { opacity: .4; cursor: default; }
      #m3d .res { min-height: 0; flex: none; font-size: 12.5px !important; font-size: 13px; line-height: 1.45; color: #cfe3ec; }
      #m3d .res.bad { color: #ffb09a; }
      #m3d .x { position: absolute; right: 12px; top: 12px; width: 34px; height: 30px; border: 1px solid rgba(0,210,255,.35); background: rgba(3,14,24,.8); color: #bfeaff; cursor: pointer; z-index: 2; }
      @media (max-height: 680px) { #m3d .side { gap: 3px; } #m3d .side h4 { font-size: 9.5px; letter-spacing: 2px; } #m3d .opt, #m3d .sm { height: 24px; font-size: 10px; } #m3d .act { height: 30px; font-size: 12px; }  #m3d .ob { padding: 3px 8px; } }
      /* choix d'un fichier à ajouter : grande fenêtre par-dessus la vue 3D */
      #m3d .picker { position: absolute; inset: 0; z-index: 5; display: none; flex-direction: column; gap: 10px; padding: 18px 22px;
        background: rgba(2,8,15,.96); }
      #m3d .picker.on { display: flex; }
      #m3d .pk-head { display: flex; gap: 10px; align-items: center; }
      #m3d .pk-head b { font: 600 16px "Bahnschrift"; letter-spacing: 3px; color: #fff; white-space: nowrap; }
      #m3d .pk-head input { flex: 1; min-width: 120px; height: 36px; padding: 0 12px; border: 1px solid rgba(0,210,255,.4); background: rgba(3,14,24,.9); color: #fff; font: 14px "Bahnschrift"; }
      #m3d .pk-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
      #m3d .pk-sec { font: 600 11px "Cascadia Mono", Consolas, monospace; letter-spacing: 3px; color: rgba(0,210,255,.8); margin-top: 6px; }
      #m3d .pk-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 8px; }
      #m3d .pk-it { padding: 12px 14px; border: 1px solid rgba(0,210,255,.25); background: rgba(0,20,40,.5); cursor: pointer; }
      #m3d .pk-it:hover { border-color: rgb(0,210,255); background: rgba(0,210,255,.14); box-shadow: 0 0 12px rgba(0,210,255,.25); }
      #m3d .pk-it b { display: block; font-size: 15px; color: #fff; word-break: break-word; }
      #m3d .pk-it small { display: block; margin-top: 4px; font: 11.5px "Cascadia Mono", Consolas, monospace; color: rgba(214,236,245,.6); }
      #m3d .pk-it.off { opacity: .45; cursor: default; }
      @media (max-width: 900px) { #m3d { flex-direction: column; } #m3d .side { width: auto; max-height: 50%; border-left: 0; border-top: 1px solid rgba(0,210,255,.25); } }`;
    document.head.appendChild(css);
    ov = document.createElement('div'); ov.id = 'm3d';
    ov.innerHTML = `<div class="stage"><canvas></canvas><div class="ttl"><b>PLATEAU</b><span class="dims"></span><span class="warn bad"></span></div>
        <div class="hint">glisser un objet : le déplacer · glisser le vide : tourner la vue · molette / pincer : zoom · double-clic : recentrer · R : tourner · Suppr : retirer</div>
        <button class="x" title="Fermer (Échap)">✕</button></div>
      <div class="ctx"><div data-c="rot">Tourner de 90°</div><div data-c="dup">Dupliquer</div><div data-c="center">Mettre au centre</div><div class="del" data-c="rm">Supprimer</div></div>
      <div class="picker"><div class="pk-head"><b>AJOUTER AU PLATEAU</b><input type="search" placeholder="Rechercher un fichier…"><button class="sm" data-a="pkx" style="flex:none;width:110px">FERMER</button></div>
        <div class="pk-list"></div></div>
      <div class="side">
        <h4 class="objh">OBJETS SUR LE PLATEAU</h4><div class="objs"></div>
        <button class="sm" data-a="add" style="flex:none">+ AJOUTER UN FICHIER</button>
        <div class="selbox grp"><h4>OBJET SÉLECTIONNÉ · TAILLE</h4>
          <div class="row"><input type="range" min="25" max="300" step="5" data-k="scale"><span class="val" data-v="scale"></span></div>
          <div class="row"><button class="sm" data-a="rot">TOURNER 90°</button><button class="sm" data-a="dup">DUPLIQUER</button><button class="sm del" data-a="rm">RETIRER</button></div></div>
        <h4>SUPPORTS · ACCROCHE AU PLATEAU</h4><div class="row"><button class="opt" data-k="supports" data-v="0" title="Sans supports">Sans sup.</button><button class="opt" data-k="supports" data-v="1" title="Supports automatiques">Supports</button><button class="opt" data-k="brim" data-v="0" title="Jupe autour de la pièce">Jupe</button><button class="opt" data-k="brim" data-v="1" title="Bordure de 5 mm collée à la pièce">Bordure</button></div>
        <h4>REMPLISSAGE</h4><div class="row"><input type="range" min="0" max="100" step="5" data-k="infill"><span class="val" data-v="infill"></span></div>
        <div class="row"><button class="opt" data-k="pattern" data-v="auto" title="Choisi selon la forme de l'objet, pour un maximum de solidité">Auto</button><button class="opt" data-k="pattern" data-v="gyroide" title="Solide dans toutes les directions">Gyroïde</button><button class="opt" data-k="pattern" data-v="cubique" title="Très solide, rapide">Cubique</button><button class="opt" data-k="pattern" data-v="grille" title="Rigide à plat, rapide">Grille</button><button class="opt" data-k="pattern" data-v="nid" title="Très résistant à l'écrasement, plus lent">Nid</button></div>
        <h4>QUALITÉ</h4><div class="row"><button class="opt" data-k="quality" data-v="fine">Fine 0,12</button><button class="opt" data-k="quality" data-v="normal">Normale 0,2</button><button class="opt" data-k="quality" data-v="rapide">Rapide 0,28</button></div>
        <button class="act" data-a="slice">DÉCOUPER</button>
        <button class="act main" data-a="print">IMPRIMER LE PLATEAU</button>
        <div class="res"></div>
      </div>`;
    document.body.appendChild(ov);
    cv = ov.querySelector('canvas');
    lbls = makeLabels(ov.querySelector('.stage'));
    ov.querySelector('.x').onclick = close;
    addEventListener('keydown', (e) => {
      if (!ov.classList.contains('on')) return;
      if (/INPUT|TEXTAREA/.test((document.activeElement || {}).tagName || '') && e.key !== 'Escape') return;
      if (e.key === 'Escape' && ov.querySelector('.ctx.on')) { ov.querySelector('.ctx').classList.remove('on'); return; }
      if (e.key === 'Escape') { const pk = ov.querySelector('.picker'); if (pk.classList.contains('on')) pk.classList.remove('on'); else close(); }
      else if ((e.key === 'Delete' || e.key === 'Backspace') && sel >= 0) removeSel();
      else if ((e.key === 'r' || e.key === 'R') && sel >= 0) { objs[sel].rot += Math.PI / 2; sync(); }
    });
    ov.querySelectorAll('.opt').forEach(b => b.onclick = () => { const k = b.dataset.k, v = b.dataset.v; opts[k] = (k === 'quality' || k === 'pattern') ? v : v === '1'; sync(); });
    ov.querySelector('input[data-k=infill]').oninput = (e) => { opts.infill = +e.target.value; sync(); };
    ov.querySelector('input[data-k=scale]').oninput = (e) => { if (sel >= 0) { objs[sel].scale = +e.target.value; sync(); } };
    ov.querySelector('[data-a=rot]').onclick = () => { if (sel >= 0) { objs[sel].rot += Math.PI / 2; sync(); } };
    ov.querySelector('[data-a=dup]').onclick = () => { if (sel < 0) return; const c = { ...objs[sel], uid: uid++ };
      const fits = freeSpot(c); objs.push(c); sel = objs.length - 1; say(fits ? '' : 'Plus de place libre : la copie est au centre, déplace-la.', !fits); sync(); };
    ov.querySelector('[data-a=rm]').onclick = removeSel;
    const ctx = ov.querySelector('.ctx');
    ctx.querySelectorAll('[data-c]').forEach(d => d.onclick = () => { ctx.classList.remove('on'); act(d.dataset.c); });
    addEventListener('pointerdown', (e) => { if (!e.target.closest || !e.target.closest('.ctx')) ctx.classList.remove('on'); }, true);
    cv.addEventListener('contextmenu', (e) => { e.preventDefault(); const i = pick(e.clientX, e.clientY);
      if (i >= 0) { sel = i; drag = null; sync(); menu(e.clientX, e.clientY); } });
    ov.querySelector('[data-a=add]').onclick = toggleLib;
    ov.querySelector('[data-a=pkx]').onclick = () => ov.querySelector('.picker').classList.remove('on');
    ov.querySelector('.picker input').oninput = renderPicker;
    ov.querySelector('[data-a=slice]').onclick = slice;
    const pb = ov.querySelector('[data-a=print]');
    pb.onclick = () => {
      if (!pb.dataset.armed) { pb.dataset.armed = '1'; pb.classList.add('armed'); pb.textContent = 'PLATEAU DÉGAGÉ ? CONFIRMER';
        clearTimeout(pb._t); pb._t = setTimeout(() => { pb.dataset.armed = ''; pb.classList.remove('armed'); pb.textContent = 'IMPRIMER LE PLATEAU'; }, 5000); return; }
      pb.dataset.armed = ''; pb.classList.remove('armed'); pb.textContent = 'IMPRIMER LE PLATEAU'; clearTimeout(pb._t); print();
    };
    // souris / doigt : un objet sous le pointeur -> on le déplace sur le plateau ; sinon on tourne la vue
    const pts = new Map();
    cv.addEventListener('pointerdown', (e) => {
      if (e.button === 2) return;
      cv.setPointerCapture(e.pointerId); pts.set(e.pointerId, [e.clientX, e.clientY]); lastTouch = performance.now();
      if (pts.size > 1) { drag = null; return; }
      const i = pick(e.clientX, e.clientY);
      if (i >= 0) { sel = i; const p = bedPoint(e.clientX, e.clientY) || [objs[i].x, objs[i].z]; drag = { obj: objs[i], dx: objs[i].x - p[0], dz: objs[i].z - p[1] }; sync(); }
      else drag = { view: true, x: e.clientX, y: e.clientY };
    });
    cv.addEventListener('pointermove', (e) => {
      if (!pts.has(e.pointerId)) { cv.classList.toggle('over', pick(e.clientX, e.clientY) >= 0); return; }
      lastTouch = performance.now();
      if (pts.size === 2) { const [a, b] = [...pts.values()], d0 = Math.hypot(a[0] - b[0], a[1] - b[1]); pts.set(e.pointerId, [e.clientX, e.clientY]);
        const [c, d] = [...pts.values()], d1 = Math.hypot(c[0] - d[0], c[1] - d[1]); if (d0) zoom = Math.max(0.4, Math.min(5, zoom * d1 / d0)); return; }
      pts.set(e.pointerId, [e.clientX, e.clientY]);
      if (!drag) return;
      if (drag.obj) { const p = bedPoint(e.clientX, e.clientY); if (p) { const o = drag.obj, [hw, hd] = half(o);
          o.x = Math.max(-HALF + hw, Math.min(HALF - hw, Math.round((p[0] + drag.dx) * 2) / 2));
          o.z = Math.max(-HALF + hd, Math.min(HALF - hd, Math.round((p[1] + drag.dz) * 2) / 2)); sync(true); } }
      else { yaw += (e.clientX - drag.x) * 0.008; pitch = Math.max(-0.1, Math.min(1.45, pitch + (e.clientY - drag.y) * 0.006)); drag.x = e.clientX; drag.y = e.clientY; }
    });
    const up = (e) => { pts.delete(e.pointerId); if (!pts.size) { if (drag && drag.obj) sync(); drag = null; } };
    cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
    cv.addEventListener('wheel', (e) => { e.preventDefault(); lastTouch = performance.now(); zoom = Math.max(0.4, Math.min(5, zoom * (e.deltaY < 0 ? 1.1 : 0.9))); }, { passive: false });
    cv.addEventListener('dblclick', () => { yaw = 0.7; pitch = 0.62; zoom = 1; });
  }
  function menu(x, y) {
    const m = ov.querySelector('.ctx'); m.classList.add('on');
    m.style.left = Math.min(x, innerWidth - 190) + 'px'; m.style.top = Math.min(y, innerHeight - 170) + 'px';
  }
  function act(c) {
    if (sel < 0) return;
    if (c === 'rm') return removeSel();
    if (c === 'rot') objs[sel].rot += Math.PI / 2;
    if (c === 'center') { objs[sel].x = 0; objs[sel].z = 0; }
    if (c === 'dup') { const cp = { ...objs[sel], uid: uid++ }; const fits = freeSpot(cp); objs.push(cp); sel = objs.length - 1;
      say(fits ? '' : 'Plus de place libre : la copie est au centre, déplace-la.', !fits); }
    sync();
  }
  function removeSel() { if (sel < 0) return; objs.splice(sel, 1); sel = objs.length ? Math.min(sel, objs.length - 1) : -1; sync(); }
  let pkFiles = [];
  async function toggleLib() {
    const pk = ov.querySelector('.picker'), list = pk.querySelector('.pk-list'), q = pk.querySelector('input');
    pk.classList.add('on'); q.value = ''; list.textContent = 'Chargement…';
    const r = await fetch('/api/print/files?dl=1&' + tokq()).then(x => x.json()).catch(() => ({ files: [], downloads: [] }));
    const seen = new Set((r.files || []).map(f => f.name.toLowerCase()));
    pkFiles = [...(r.files || []).map(f => ({ ...f, where: 'Impressions 3D' })),
               ...(r.downloads || []).filter(f => !seen.has(f.name.toLowerCase())).map(f => ({ ...f, where: 'Téléchargements' }))];
    renderPicker(); setTimeout(() => q.focus(), 50);
  }
  function renderPicker() {
    const pk = ov.querySelector('.picker'), list = pk.querySelector('.pk-list'), q = pk.querySelector('input').value.trim().toLowerCase();
    const fs = pkFiles.filter(f => !q || f.name.toLowerCase().includes(q));
    if (!fs.length) { list.textContent = pkFiles.length ? 'Aucun fichier ne correspond.' : 'Aucun modèle 3D dans Impressions 3D ni dans Téléchargements.'; return; }
    const secs = [];
    for (const where of ['Impressions 3D', 'Téléchargements']) {
      const part = fs.filter(f => f.where === where); if (!part.length) continue;
      const grid = document.createElement('div'); grid.className = 'pk-grid';
      for (const f of part) {
        const ok = f.type === 'stl' || f.type === 'obj', it = document.createElement('div'); it.className = 'pk-it' + (ok ? '' : ' off');
        const b = document.createElement('b'); b.textContent = f.name;
        const sm = document.createElement('small'); sm.textContent = `${f.type.toUpperCase()} · ${(f.ko || 0).toLocaleString('fr-FR')} Ko · ${f.date}` + (ok ? '' : ' · pas sur le plateau (STL / OBJ seulement)');
        it.append(b, sm);
        if (ok) it.onclick = () => { pk.classList.remove('on'); add(f.id, f.name); };
        grid.append(it);
      }
      const h = document.createElement('div'); h.className = 'pk-sec'; h.textContent = where.toUpperCase() + ` · ${part.length}`;
      secs.push(h, grid);
    }
    list.replaceChildren(...secs);
  }
  async function load(id, name) {
    if (cache.has(id)) return cache.get(id);
    const r = await fetch('/api/print/model?id=' + encodeURIComponent(id) + '&' + tokq());
    if (!r.ok) throw new Error('fichier introuvable');
    const ext = (name || '').toLowerCase().split('.').pop();
    const pos = ext === 'stl' ? parseSTL(await r.arrayBuffer()) : parseOBJ(await r.text());
    if (!pos.length) throw new Error('modèle vide');
    const g = geometry(pos); cache.set(id, g); return g;
  }
  async function add(id, name) {
    const ext = (name || '').toLowerCase().split('.').pop();
    if (ext !== 'stl' && ext !== 'obj') { say('Le plateau accepte les fichiers STL et OBJ (pas ' + ext.toUpperCase() + ').', true); return; }
    say('Chargement de ' + name + '…');
    try {
      const g = await load(id, name);
      const o = { uid: uid++, id, name, ...g, x: 0, z: 0, rot: 0, scale: 100 };
      const fits = freeSpot(o);
      objs.push(o); sel = objs.length - 1; say(fits ? '' : 'Plus de place libre : l’objet est au centre, déplace-le ou réduis-le.', !fits); sync();
    } catch (e) { say('Lecture de ' + name + ' impossible : ' + (e.message || e), true); }
  }
  function sync(light) {
    const pb = problems(), any = pb.some(p => p.out || p.hit);
    if (!light) {
      ov.querySelectorAll('.opt').forEach(b => { const k = b.dataset.k, v = b.dataset.v; b.classList.toggle('on', (k === 'quality' || k === 'pattern') ? opts[k] === v : (opts[k] ? '1' : '0') === v); });
      ov.querySelector('input[data-k=infill]').value = opts.infill; ov.querySelector('[data-v=infill]').textContent = opts.infill + ' %';
      ov.querySelector('.objs').replaceChildren(...objs.map((o, i) => { const d = document.createElement('div'); d.className = 'ob' + (i === sel ? ' on' : '') + (pb[i].out || pb[i].hit ? ' bad' : '');
        const n = document.createElement('span'); n.textContent = o.name; const k = document.createElement('i'); k.textContent = o.scale + ' %';
        const x = document.createElement('button'); x.className = 'rmx'; x.title = 'Supprimer du plateau'; x.textContent = '✕';
        x.onclick = (e) => { e.stopPropagation(); sel = i; removeSel(); };
        d.append(n, k, x); d.onclick = () => { sel = i; sync(); };
        d.oncontextmenu = (e) => { e.preventDefault(); sel = i; sync(); menu(e.clientX, e.clientY); }; return d; }));
      ov.querySelector('.selbox').style.display = sel >= 0 ? '' : 'none';
      ov.querySelector('.objh').textContent = 'OBJETS SUR LE PLATEAU · ' + objs.length;
    }
    if (sel >= 0) { const o = objs[sel]; ov.querySelector('input[data-k=scale]').value = o.scale; ov.querySelector('[data-v=scale]').textContent = o.scale + ' %'; }
    const o = objs[sel], k = o ? o.scale / 100 : 1;
    ov.querySelector('.dims').textContent = o ? `${o.name} · ${(o.sx * k).toFixed(1)} × ${(o.sy * k).toFixed(1)} × ${(o.sz * k).toFixed(1)} mm · ${objs.length} objet${objs.length > 1 ? 's' : ''}` : (objs.length ? `${objs.length} objets` : 'Plateau vide : ajoute un fichier');
    ov.querySelector('.warn').textContent = pb.some(p => p.out) ? 'UN OBJET DÉPASSE DU PLATEAU' : pb.some(p => p.hit) ? 'DES OBJETS SE TOUCHENT : ÉCARTE-LES' : '';
    ov.querySelector('[data-a=print]').disabled = !objs.length || any;
    ov.querySelector('[data-a=slice]').disabled = !objs.length || any;
  }
  function say(t, bad) { const r = ov.querySelector('.res'); r.textContent = t || ''; r.classList.toggle('bad', !!bad); }
  const plate = () => objs.map(o => ({ id: o.id, x: o.x, z: o.z, rot: o.rot, scale: o.scale }));
  async function slice() {
    const b = ov.querySelector('[data-a=slice]'); b.disabled = true; say('Découpe du plateau en cours…');
    const r = await post('/api/print/plate', { objects: plate(), opts, action: 'slice' }).catch(() => ({ ok: false, why: 'JARVIS ne répond pas.' }));
    sync();
    const fill = r.remplissage ? ` · remplissage ${r.remplissage.motif} ${r.remplissage.densite} %` + (r.remplissage.auto ? ` (auto : ${r.remplissage.auto})` : '') : '';
    say(r.ok ? `Durée estimée : ${r.duree}` + (r.grammes ? ` · ${r.grammes.toFixed(0)} g de PLA` : '') + ` · ${objs.length} objet${objs.length > 1 ? 's' : ''}` + fill : (r.why || 'Découpe impossible'), !r.ok);
  }
  async function print() {
    const b = ov.querySelector('[data-a=print]'); b.disabled = true; say('Découpe puis lancement…');
    const r = await post('/api/print/plate', { objects: plate(), opts, action: 'print', confirm: true }).catch(() => ({ ok: false, why: 'JARVIS ne répond pas.' }));
    sync();
    say(r.ok ? 'Impression lancée : surveille la première couche. Suivi dans la page Imprimante 3D.' : (r.why || 'Lancement impossible'), !r.ok);
  }
  async function open(id, name) {
    if (!ov) build();
    if (!gl && !initGL()) say('WebGL indisponible : aperçu 3D impossible.', true);
    objs = []; sel = -1; opts = { supports: false, infill: 20, pattern: 'auto', quality: 'normal', brim: false };
    yaw = 0.7; pitch = 0.62; zoom = 1; lastTouch = 0;
    ov.classList.add('on'); say(''); sync();
    if (window.updPageOpen) updPageOpen();
    if (!raf) raf = requestAnimationFrame(draw);
    if (id) await add(id, name);
    else toggleLib();
  }
  function close() { if (!ov) return; ov.classList.remove('on'); cancelAnimationFrame(raf); raf = 0; if (window.updPageOpen) updPageOpen(); }
  function state(d) { if (!d || d.n === lastN) return; lastN = d.n;
    if (d.on) { if (d.id && ov && ov.classList.contains('on') && d.add) add(d.id, d.name); else open(d.id || null, d.name || ''); } else close(); }
  window.M3D = { open, add, close, state, _frame: () => { draw(); cancelAnimationFrame(raf); raf = requestAnimationFrame(draw); }, _objs: () => objs };
})();

/* Vue 3D EN DIRECT d'une impression (page Imprimante 3D), ANIMÉE : la buse suit le vrai trajet du G-code à vitesse
   réelle (durée de chaque mouvement calculée par JARVIS : /api/print/toolpath?v=2), recalée en continu sur l'imprimante
   (/api/print/status, chaque seconde ; l'imprimante garde ~20 commandes d'avance en mémoire, on en tient compte).
   Plastique déposé en cyan, couche en cours en blanc, trait en train de se faire qui avance avec la buse, suite en fantôme. */
(() => {
  'use strict';
  const tokq = () => 'token=' + encodeURIComponent(window.JTOKEN || '');
  const C = 115.5, LAG = 20;   // centre de la zone imprimable (mm) ; commandes d'avance gardées par l'imprimante
  const M = {
    mul(a, b) { const o = new Float32Array(16); for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) { let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + j] * b[i * 4 + k]; o[i * 4 + j] = s; } return o; },
    persp(f, a, n, fa) { const t = 1 / Math.tan(f / 2), o = new Float32Array(16); o[0] = t / a; o[5] = t; o[10] = (fa + n) / (n - fa); o[11] = -1; o[14] = 2 * fa * n / (n - fa); return o; },
    id() { const o = new Float32Array(16); o[0] = o[5] = o[10] = o[15] = 1; return o; },
    tr(x, y, z) { const o = M.id(); o[12] = x; o[13] = y; o[14] = z; return o; },
    rx(a) { const o = M.id(), c = Math.cos(a), s = Math.sin(a); o[5] = c; o[6] = s; o[9] = -s; o[10] = c; return o; },
    ry(a) { const o = M.id(), c = Math.cos(a), s = Math.sin(a); o[0] = c; o[2] = -s; o[8] = s; o[10] = c; return o; },
    tx(m, v) { const o = [0, 0, 0, 0]; for (let j = 0; j < 4; j++) for (let k = 0; k < 4; k++) o[j] += m[k * 4 + j] * v[k]; return o; },
  };

  // ---- repères du plateau (étiquettes HTML placées en projetant des points 3D) : partagés par les deux vues
  const LABELS = [['AVANT', 0, 0, 122, ''], ['ARRIÈRE', 0, 0, -122, ''], ['GAUCHE', -126, 0, 0, ''],
                  ['DROITE', 126, 0, 0, ''], ['DÉPART DE LA BUSE', -110, 0, 110, 'o']];
  function makeLabels(parent) {
    const box = document.createElement('div'); box.style.cssText = 'position:absolute;inset:0;pointer-events:none;overflow:hidden';
    for (const [t, , , , k] of LABELS) { const d = document.createElement('div'); d.textContent = t;
      d.style.cssText = 'position:absolute;transform:translate(-50%,-50%);white-space:nowrap;font:600 11px Cascadia Mono,Consolas,monospace;letter-spacing:2px;'
        + (k === 'f' ? 'color:#fff;background:rgba(0,150,200,.55);padding:3px 8px;border:1px solid rgba(0,210,255,.9);'
          : k === 'o' ? 'color:#ffc078;font-size:10px;' : 'color:rgba(150,225,255,.75);');
      box.appendChild(d); }
    parent.appendChild(box); return box;
  }
  function placeLabels(box, vp, w, h) {
    if (!box) return;
    [...box.children].forEach((d, i) => { const [, x, y, z] = LABELS[i], p = M.tx(vp, [x, y, z, 1]);
      if (p[3] <= 0) { d.style.display = 'none'; return; }
      d.style.display = ''; d.style.left = ((p[0] / p[3] + 1) / 2 * w) + 'px'; d.style.top = ((1 - p[1] / p[3]) / 2 * h) + 'px'; });
  }
  // axes au coin de départ : X (rouge, vers la droite) et Y (vert, vers l'arrière)
  const AXES = new Float32Array([-110, 0.2, 110, -70, 0.2, 110, -110, 0.2, 110, -110, 0.2, 70]);
  let host = null, cv, gl, prog, raf = 0, timer = 0, data = null, file = '', info, lbls = null;
  let yaw = 0.6, pitch = 0.6, zoom = 1, lastUser = 0, tp = 0, tTarget = 0, state = 'idle', lastFrame = 0, frozen = false;
  function sh(t, s) { const x = gl.createShader(t); gl.shaderSource(x, s); gl.compileShader(x); return x; }
  function init() {
    gl = cv.getContext('webgl', { antialias: true, premultipliedAlpha: false });
    if (!gl) return false;
    prog = gl.createProgram();
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, 'attribute vec3 p; uniform mat4 mvp; void main(){ gl_Position = mvp * vec4(p,1.); gl_PointSize = 10.; }'));
    gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, 'precision mediump float; uniform vec4 col; void main(){ gl_FragColor = col; }'));
    gl.linkProgram(prog);
    return true;
  }
  const buf = (a) => { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, a, gl.STATIC_DRAW); return b; };
  const bsearch = (arr, v, n) => { let lo = 0, hi = n; while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m] <= v) lo = m + 1; else hi = m; } return lo; };  // nb d'éléments ≤ v
  function load(bytes) {
    const u8 = new Uint8Array(bytes), tp2 = u8[0] === 84 && u8[1] === 80 && u8[2] === 50, dv = new DataView(bytes);
    const off = tp2 ? 4 : 0, n = dv.getUint32(off, true), o = off + 4;
    const raw = new Float32Array(bytes.slice(o, o + n * 24)), idx = new Uint32Array(bytes.slice(o + n * 24, o + n * 28));
    let dur, ext;
    if (tp2) { dur = new Float32Array(bytes.slice(o + n * 28, o + n * 32)); ext = new Uint8Array(bytes.slice(o + n * 32, o + n * 33)); }
    else { dur = new Float32Array(n); ext = new Uint8Array(n).fill(1);   // ancien format : extrusion seule, ~40 mm/s
      for (let i = 0; i < n; i++) dur[i] = Math.hypot(raw[i * 6 + 3] - raw[i * 6], raw[i * 6 + 4] - raw[i * 6 + 1], raw[i * 6 + 5] - raw[i * 6 + 2]) / 40; }
    const cum = new Float64Array(n + 1); for (let i = 0; i < n; i++) cum[i + 1] = cum[i] + dur[i];
    // segments déposés (dans l'ordre) pour le dessin ; extBefore[i] = nb de segments déposés avant le mouvement i
    let ne = 0; for (let i = 0; i < n; i++) ne += ext[i];
    const P = new Float32Array(ne * 6), ez = new Float32Array(ne), extBefore = new Uint32Array(n + 1);
    let k = 0, zmax = 0;
    for (let i = 0; i < n; i++) {
      extBefore[i] = k;
      if (!ext[i]) continue;
      for (let j = 0; j < 6; j += 3) { P[k * 6 + j] = raw[i * 6 + j] - C; P[k * 6 + j + 1] = raw[i * 6 + j + 2]; P[k * 6 + j + 2] = -(raw[i * 6 + j + 1] - C); }
      ez[k] = raw[i * 6 + 5]; zmax = Math.max(zmax, ez[k]); k++;
    }
    extBefore[n] = k;
    const layers = [0]; for (let i = 1; i < ne; i++) if (Math.abs(ez[i] - ez[i - 1]) > 1e-3) layers.push(i);
    // cadrage sur la pièce (sans la ligne d'amorçage : on ignore la 1re couche si la pièce en a d'autres)
    let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9, any = false;
    for (let pass = 0; pass < 2 && !any; pass++) for (let i = 0; i < ne; i++) { if (pass === 0 && ez[i] <= ez[0] + 1e-3) continue;
      any = true; for (const q of [0, 3]) { x0 = Math.min(x0, P[i * 6 + q]); x1 = Math.max(x1, P[i * 6 + q]); y0 = Math.min(y0, P[i * 6 + q + 2]); y1 = Math.max(y1, P[i * 6 + q + 2]); } }
    const hx = 110, L = [];
    for (let v = -hx; v <= hx + 0.01; v += 10) L.push(v, 0, -hx, v, 0, hx, -hx, 0, v, hx, 0, v);
    const E = [-hx, 0, -hx, hx, 0, -hx, hx, 0, -hx, hx, 0, hx, hx, 0, hx, -hx, 0, hx, -hx, 0, hx, -hx, 0, -hx];
    data = { n, raw, idx, dur, ext, cum, total: cum[n], ne, extBefore, layers, ez, zmax, seg: buf(P), P,
             fx: any ? (x0 + x1) / 2 : 0, fz: any ? (y0 + y1) / 2 : 0, ext_: any ? Math.max(x1 - x0, y1 - y0) : 220,
             grid: buf(new Float32Array(L)), ng: L.length / 3, edge: buf(new Float32Array(E)), axes: buf(AXES), dyn: gl.createBuffer() };
    tp = 0; tTarget = 0;
  }
  function targetFrom(sent) {   // temps du trajet correspondant à ce que l'imprimante exécute vraiment (envoyé − mémoire)
    if (!data) return 0;
    if (state === 'done') return data.total;
    const cmd = Math.max(0, sent - LAG), j = bsearch(data.idx, cmd - 1, data.n);   // 1er mouvement de commande ≥ cmd
    return data.cum[Math.min(j, data.n)];
  }
  function draw(now) {
    raf = requestAnimationFrame(draw);
    if (!gl || !data) return;
    const dt = lastFrame ? Math.min(0.25, (now - lastFrame) / 1000) : 0; lastFrame = now;
    // la buse avance à vitesse réelle et se recale doucement sur l'imprimante (plus vite si elle est en retard)
    if (!frozen && state !== 'paused') {
      const gap = tTarget - tp;
      if (Math.abs(gap) > 90) tp = tTarget;                                   // ouvert en cours d'impression : on saute
      else tp += dt * Math.max(0.15, Math.min(4, 1 + gap / 3));
      tp = Math.min(tp, tTarget + 1.5, data.total);
    }
    const w = cv.clientWidth, h = cv.clientHeight, d = Math.min(2, devicePixelRatio || 1);
    if (cv.width !== Math.round(w * d) || cv.height !== Math.round(h * d)) { cv.width = Math.round(w * d); cv.height = Math.round(h * d); }
    gl.viewport(0, 0, cv.width, cv.height); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    if (now - lastUser > 5000) yaw += 0.0015;
    const span = Math.max(50, data.ext_ * 1.9, data.zmax * 1.7);
    const vp = M.mul(M.persp(0.75, w / Math.max(1, h), 1, 5000), M.mul(M.tr(0, -data.zmax * 0.35, -span * 1.7 / zoom),
      M.mul(M.rx(pitch), M.mul(M.ry(yaw), M.tr(-data.fx, 0, -data.fz)))));
    gl.useProgram(prog); gl.enable(gl.BLEND); gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA); gl.disable(gl.DEPTH_TEST);
    for (let i = 0; i < 4; i++) gl.disableVertexAttribArray(i);
    const pl = gl.getAttribLocation(prog, 'p'); gl.enableVertexAttribArray(pl);
    gl.uniformMatrix4fv(gl.getUniformLocation(prog, 'mvp'), false, vp);
    const col = (r, g, b, a) => gl.uniform4f(gl.getUniformLocation(prog, 'col'), r, g, b, a);
    const use = (b) => { gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.vertexAttribPointer(pl, 3, gl.FLOAT, false, 0, 0); };
    use(data.grid); col(0.2, 0.85, 1, 0.22); gl.drawArrays(gl.LINES, 0, data.ng);
    use(data.edge); col(0.55, 0.95, 1, 0.9); gl.drawArrays(gl.LINES, 0, 8);
    use(data.axes); col(1, 0.35, 0.3, 1); gl.drawArrays(gl.LINES, 0, 2); col(0.35, 1, 0.45, 1); gl.drawArrays(gl.LINES, 2, 2);
    placeLabels(lbls, vp, w, h);
    // où en est la buse : mouvement j, fraction f
    let j = Math.min(data.n - 1, Math.max(0, bsearch(data.cum, tp, data.n + 1) - 1));
    const f = data.dur[j] > 0 ? Math.max(0, Math.min(1, (tp - data.cum[j]) / data.dur[j])) : 1, r = data.raw, o = j * 6;
    const nx = r[o] + (r[o + 3] - r[o]) * f - C, nyz = r[o + 2] + (r[o + 5] - r[o + 2]) * f, nz = -(r[o + 1] + (r[o + 4] - r[o + 1]) * f - C);
    const k = data.extBefore[j];   // segments entièrement déposés
    let lo = 0, hi = data.layers.length - 1; while (lo < hi) { const m = (lo + hi + 1) >> 1; if (data.layers[m] <= Math.max(0, k - 1)) lo = m; else hi = m - 1; }
    const ls = Math.min(data.layers[lo], k);
    use(data.seg);
    col(0.25, 0.75, 1, 0.07); gl.drawArrays(gl.LINES, k * 2, (data.ne - k) * 2);   // à venir (fantôme)
    col(0.0, 0.82, 1, 0.78); gl.drawArrays(gl.LINES, 0, ls * 2);                    // déjà déposé
    col(1, 1, 1, 0.95); gl.drawArrays(gl.LINES, ls * 2, (k - ls) * 2);              // couche en cours
    const dyn = [];
    if (data.ext[j] && f > 0) dyn.push(r[o] - C, r[o + 2], -(r[o + 1] - C), nx, nyz, nz);   // trait en train de se faire
    dyn.push(nx, nyz, nz, nx - 5, nyz, nz, nx + 5, nyz, nz, nx, nyz, nz - 5, nx, nyz, nz + 5, nx, nyz, nz, nx, nyz + 14, nz);
    gl.bindBuffer(gl.ARRAY_BUFFER, data.dyn); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(dyn), gl.DYNAMIC_DRAW); gl.vertexAttribPointer(pl, 3, gl.FLOAT, false, 0, 0);
    let s0 = 0;
    if (data.ext[j] && f > 0) { col(1, 1, 1, 1); gl.drawArrays(gl.LINES, 0, 2); s0 = 2; }
    col(1, 0.6, 0.15, 1); gl.drawArrays(gl.POINTS, s0, 1); gl.drawArrays(gl.LINES, s0 + 1, 6);
    gl.disableVertexAttribArray(pl);
    const pct = data.total ? Math.round(100 * tp / data.total) : 0, rest = Math.max(0, data.total - tp);
    info.textContent = state === 'done' || tp >= data.total - 0.5 ? 'Impression terminée'
      : !k && tp < 1 ? 'Chauffe et mise en place de la buse…'
      : `Couche ${lo + 1} / ${data.layers.length} · Z ${nyz.toFixed(2)} mm · ${pct} % · reste ≈ ${rest >= 3600 ? Math.floor(rest / 3600) + ' h ' : ''}${Math.round(rest % 3600 / 60)} min`
        + (state === 'paused' ? ' · EN PAUSE' : '');
  }
  async function poll() {
    try {
      const s = await fetch('/api/print/status?' + tokq()).then(r => r.json());
      state = s.job_state || 'idle';
      if (s.file && s.file !== file) {
        file = s.file;
        let r = await fetch('/api/print/toolpath?v=2&' + tokq());
        if (!r.ok) r = await fetch('/api/print/toolpath?' + tokq());
        if (r.ok) load(await r.arrayBuffer()); else info.textContent = 'Trajet indisponible.';
      }
      tTarget = targetFrom(s.sent || 0);
    } catch (e) { /* JARVIS ne répond pas : on réessaie */ }
  }
  function mount(el) {
    if (host === el && cv && cv.isConnected) return;
    unmount();
    host = el;
    el.innerHTML = '<canvas style="position:absolute;inset:0;width:100%;height:100%;cursor:grab;touch-action:none"></canvas>'
      + '<div style="position:absolute;left:12px;top:10px;font:12px Cascadia Mono,Consolas,monospace;letter-spacing:1px;color:rgba(0,210,255,.9);pointer-events:none"></div>';
    cv = el.querySelector('canvas'); info = el.querySelector('div'); lbls = makeLabels(el);
    if (!init()) { info.textContent = 'WebGL indisponible.'; return; }
    let dr = null;
    cv.addEventListener('pointerdown', (e) => { cv.setPointerCapture(e.pointerId); dr = { x: e.clientX, y: e.clientY }; lastUser = performance.now(); });
    cv.addEventListener('pointermove', (e) => { if (!dr) return; lastUser = performance.now(); yaw += (e.clientX - dr.x) * 0.008;
      pitch = Math.max(0, Math.min(1.45, pitch + (e.clientY - dr.y) * 0.006)); dr = { x: e.clientX, y: e.clientY }; });
    cv.addEventListener('pointerup', () => { dr = null; });
    cv.addEventListener('wheel', (e) => { e.preventDefault(); lastUser = performance.now(); zoom = Math.max(0.5, Math.min(6, zoom * (e.deltaY < 0 ? 1.12 : 0.9))); }, { passive: false });
    file = ''; data = null; lastFrame = 0; info.textContent = 'Chargement du trajet…';
    poll(); timer = setInterval(() => { if (!host || !host.isConnected) return unmount(); poll(); }, 1000);
    raf = requestAnimationFrame(draw);
  }
  function unmount() { clearInterval(timer); cancelAnimationFrame(raf); raf = 0; host = null; data = null; }
  window.LIVE3D = { mount, unmount, _load: (b) => load(b), _stop: () => clearInterval(timer),
    _at: (t) => { frozen = true; tp = t; tTarget = t; }, _target: (s) => { tTarget = targetFrom(s); }, _info: () => data && { n: data.n, ne: data.ne, total: data.total },
    _frame: () => { draw(performance.now()); cancelAnimationFrame(raf); raf = requestAnimationFrame(draw); } };
})();

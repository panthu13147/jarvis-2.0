/* ══════════════════════════════════════════════════════════════════
   JARVIS ORB v2 — Particle-cloud sphere with noise displacement
   Inspired by: cosmic distorted point-cloud orbs
   ══════════════════════════════════════════════════════════════════ */

(function () {
  const canvas = document.getElementById('orbCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const DPR = window.devicePixelRatio || 1;
  let W, H, cx, cy;

  function resize() {
    const rect = canvas.getBoundingClientRect();
    W = rect.width * DPR;
    H = rect.height * DPR;
    canvas.width = W;
    canvas.height = H;
    cx = W / 2;
    cy = H / 2;
  }
  resize();
  window.addEventListener('resize', resize);

  // ── Shared state ───────────────────────────────────────────────
  const state = window.orbState = {
    mode: 'idle',
    energy: 0.5,
    audioLevel: 0,
  };

  // ══════════════════════════════════════════════════════════════
  //  3D Simplex-like noise (fast, good enough for realtime)
  // ══════════════════════════════════════════════════════════════
  const PERM = new Uint8Array(512);
  const GRAD3 = [
    [1,1,0],[-1,1,0],[1,-1,0],[-1,-1,0],
    [1,0,1],[-1,0,1],[1,0,-1],[-1,0,-1],
    [0,1,1],[0,-1,1],[0,1,-1],[0,-1,-1],
  ];
  (function seedPerm() {
    const p = new Uint8Array(256);
    for (let i = 0; i < 256; i++) p[i] = i;
    for (let i = 255; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [p[i], p[j]] = [p[j], p[i]];
    }
    for (let i = 0; i < 512; i++) PERM[i] = p[i & 255];
  })();

  function dot3(g, x, y, z) { return g[0]*x + g[1]*y + g[2]*z; }

  function noise3D(x, y, z) {
    const F3 = 1/3, G3 = 1/6;
    const s = (x+y+z)*F3;
    const i = Math.floor(x+s), j = Math.floor(y+s), k = Math.floor(z+s);
    const t = (i+j+k)*G3;
    const X0 = i-t, Y0 = j-t, Z0 = k-t;
    const x0 = x-X0, y0 = y-Y0, z0 = z-Z0;
    let i1,j1,k1,i2,j2,k2;
    if (x0>=y0) {
      if (y0>=z0) { i1=1;j1=0;k1=0;i2=1;j2=1;k2=0; }
      else if (x0>=z0) { i1=1;j1=0;k1=0;i2=1;j2=0;k2=1; }
      else { i1=0;j1=0;k1=1;i2=1;j2=0;k2=1; }
    } else {
      if (y0<z0) { i1=0;j1=0;k1=1;i2=0;j2=1;k2=1; }
      else if (x0<z0) { i1=0;j1=1;k1=0;i2=0;j2=1;k2=1; }
      else { i1=0;j1=1;k1=0;i2=1;j2=1;k2=0; }
    }
    const x1=x0-i1+G3, y1=y0-j1+G3, z1=z0-k1+G3;
    const x2=x0-i2+2*G3, y2=y0-j2+2*G3, z2=z0-k2+2*G3;
    const x3=x0-1+3*G3, y3=y0-1+3*G3, z3=z0-1+3*G3;
    const ii=i&255, jj=j&255, kk=k&255;
    let n = 0;
    let tt = 0.6-x0*x0-y0*y0-z0*z0;
    if (tt>0) { tt*=tt; const gi=PERM[ii+PERM[jj+PERM[kk]]]%12; n+=tt*tt*dot3(GRAD3[gi],x0,y0,z0); }
    tt = 0.6-x1*x1-y1*y1-z1*z1;
    if (tt>0) { tt*=tt; const gi=PERM[ii+i1+PERM[jj+j1+PERM[kk+k1]]]%12; n+=tt*tt*dot3(GRAD3[gi],x1,y1,z1); }
    tt = 0.6-x2*x2-y2*y2-z2*z2;
    if (tt>0) { tt*=tt; const gi=PERM[ii+i2+PERM[jj+j2+PERM[kk+k2]]]%12; n+=tt*tt*dot3(GRAD3[gi],x2,y2,z2); }
    tt = 0.6-x3*x3-y3*y3-z3*z3;
    if (tt>0) { tt*=tt; const gi=PERM[ii+1+PERM[jj+1+PERM[kk+1]]]%12; n+=tt*tt*dot3(GRAD3[gi],x3,y3,z3); }
    return 32 * n; // range ~ -1 to 1
  }

  // Fractal brownian motion for richer displacement
  function fbm(x, y, z, octaves) {
    let value = 0, amp = 1, freq = 1, max = 0;
    for (let i = 0; i < octaves; i++) {
      value += noise3D(x*freq, y*freq, z*freq) * amp;
      max += amp;
      amp *= 0.5;
      freq *= 2;
    }
    return value / max;
  }

  // ══════════════════════════════════════════════════════════════
  //  Generate sphere points (Fibonacci distribution)
  // ══════════════════════════════════════════════════════════════
  const POINT_COUNT = 3000;
  const PHI = (1 + Math.sqrt(5)) / 2; // golden ratio
  const points = [];

  for (let i = 0; i < POINT_COUNT; i++) {
    const theta = Math.acos(1 - 2 * (i + 0.5) / POINT_COUNT);
    const phi = 2 * Math.PI * i / PHI;
    points.push({
      // Unit sphere coordinates
      theta,
      phi,
      // Base cartesian (unit sphere)
      bx: Math.sin(theta) * Math.cos(phi),
      by: Math.sin(theta) * Math.sin(phi),
      bz: Math.cos(theta),
      // Size variation
      size: 0.6 + Math.random() * 0.8,
    });
  }

  // ══════════════════════════════════════════════════════════════
  //  Rotation matrix helpers
  // ══════════════════════════════════════════════════════════════
  function rotateY(x, y, z, angle) {
    const c = Math.cos(angle), s = Math.sin(angle);
    return [c*x + s*z, y, -s*x + c*z];
  }
  function rotateX(x, y, z, angle) {
    const c = Math.cos(angle), s = Math.sin(angle);
    return [x, c*y - s*z, s*y + c*z];
  }

  // ══════════════════════════════════════════════════════════════
  //  Draw
  // ══════════════════════════════════════════════════════════════
  let smoothAudio = 0;
  let smoothEnergy = 0.3;

  function draw(timestamp) {
    ctx.clearRect(0, 0, W, H);
    const t = timestamp * 0.001;

    // Smooth audio reactivity
    const targetAudio = state.audioLevel;
    smoothAudio += (targetAudio - smoothAudio) * 0.12;

    const isActive = state.mode === 'speaking' || state.mode === 'listening';
    const targetEnergy = isActive ? 0.5 + smoothAudio * 0.5 : 0.15;
    smoothEnergy += (targetEnergy - smoothEnergy) * 0.06;

    // Sphere parameters
    const baseR = Math.min(W, H) * 0.3;
    const noiseSpeed = state.mode === 'speaking' ? 1.2
                     : state.mode === 'listening' ? 0.6
                     : state.mode === 'thinking' ? 0.9
                     : 0.25;
    const noiseAmp = state.mode === 'speaking' ? 0.18 + smoothAudio * 0.22
                   : state.mode === 'listening' ? 0.08 + smoothAudio * 0.12
                   : state.mode === 'thinking' ? 0.12
                   : 0.04;

    // Slow rotation
    const rotY = t * 0.15;
    const rotX = Math.sin(t * 0.08) * 0.2;

    // ── Outer glow ───────────────────────────────────────────
    const glowR = baseR * (1.6 + smoothEnergy * 0.6);
    const glow = ctx.createRadialGradient(cx, cy, baseR * 0.3, cx, cy, glowR);
    glow.addColorStop(0, `rgba(60, 120, 255, ${0.06 + smoothEnergy * 0.08})`);
    glow.addColorStop(0.4, `rgba(100, 80, 255, ${0.03 + smoothEnergy * 0.04})`);
    glow.addColorStop(0.7, `rgba(50, 100, 255, ${0.01 + smoothEnergy * 0.02})`);
    glow.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(cx, cy, glowR, 0, Math.PI * 2);
    ctx.fill();

    // ── Calculate & sort all points ──────────────────────────
    const projected = [];
    const noiseT = t * noiseSpeed;

    for (let i = 0; i < POINT_COUNT; i++) {
      const p = points[i];

      // Noise displacement
      const nx = p.bx * 1.5 + noiseT * 0.4;
      const ny = p.by * 1.5 + noiseT * 0.3;
      const nz = p.bz * 1.5 + noiseT * 0.2;
      const displacement = fbm(nx, ny, nz, 3) * noiseAmp;

      // Displaced radius
      const r = baseR * (1 + displacement);

      // 3D position
      let x = p.bx * r;
      let y = p.by * r;
      let z = p.bz * r;

      // Rotate
      [x, y, z] = rotateY(x, y, z, rotY);
      [x, y, z] = rotateX(x, y, z, rotX);

      // Perspective projection
      const fov = 600;
      const scale = fov / (fov + z);
      const sx = cx + x * scale;
      const sy = cy + y * scale;

      // Depth-based alpha and size
      const depthNorm = (z + baseR) / (2 * baseR); // 0 (back) to 1 (front)
      const alpha = 0.1 + depthNorm * 0.8;
      const dotSize = p.size * scale * DPR * (0.5 + depthNorm * 0.8);

      // Color: map from position — blue at top, cyan at equator, purple at bottom
      const colorT = (p.by + 1) / 2; // 0 to 1 based on Y
      const hue = 220 + colorT * 60;  // 220 (blue) → 280 (purple)
      const sat = 80 + depthNorm * 20;
      const lit = 45 + depthNorm * 35 + smoothEnergy * 15;

      projected.push({ sx, sy, z, alpha, dotSize, hue, sat, lit });
    }

    // Sort back-to-front
    projected.sort((a, b) => a.z - b.z);

    // ── Draw points ──────────────────────────────────────────
    for (const p of projected) {
      // Glow per dot
      if (p.dotSize > 1.2) {
        const glowSize = p.dotSize * 3;
        const dotGlow = ctx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, glowSize);
        dotGlow.addColorStop(0, `hsla(${p.hue}, ${p.sat}%, ${p.lit}%, ${p.alpha * 0.4})`);
        dotGlow.addColorStop(1, `hsla(${p.hue}, ${p.sat}%, ${p.lit}%, 0)`);
        ctx.fillStyle = dotGlow;
        ctx.fillRect(p.sx - glowSize, p.sy - glowSize, glowSize * 2, glowSize * 2);
      }

      // Core dot
      ctx.beginPath();
      ctx.arc(p.sx, p.sy, p.dotSize, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${p.hue}, ${p.sat}%, ${p.lit}%, ${p.alpha})`;
      ctx.fill();
    }

    // ── Edge bloom (rim glow) ────────────────────────────────
    const rimGrad = ctx.createRadialGradient(cx, cy, baseR * 0.85, cx, cy, baseR * 1.15);
    rimGrad.addColorStop(0, 'rgba(80, 140, 255, 0)');
    rimGrad.addColorStop(0.5, `rgba(100, 160, 255, ${0.04 + smoothEnergy * 0.08})`);
    rimGrad.addColorStop(0.8, `rgba(140, 100, 255, ${0.03 + smoothEnergy * 0.06})`);
    rimGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = rimGrad;
    ctx.beginPath();
    ctx.arc(cx, cy, baseR * 1.15, 0, Math.PI * 2);
    ctx.fill();

    requestAnimationFrame(draw);
  }

  requestAnimationFrame(draw);
})();

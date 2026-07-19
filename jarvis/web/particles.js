
const mouse = { x: null, y: null, radius: 150 };
window.addEventListener('mousemove', (e) => {
    mouse.x = e.x;
    mouse.y = e.y;
});
window.addEventListener('mouseout', () => {
    mouse.x = null;
    mouse.y = null;
});

/* ══════════════════════════════════════════════════════════════════
   JARVIS PARTICLES — Full-screen floating particle field
   Creates ambient holographic atmosphere behind the orb
   ══════════════════════════════════════════════════════════════════ */

(function () {
  const canvas = document.getElementById('particleCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const DPR = window.devicePixelRatio || 1;
  let W, H;

  function resize() {
    W = window.innerWidth * DPR;
    H = window.innerHeight * DPR;
    canvas.width = W;
    canvas.height = H;
    canvas.style.width = window.innerWidth + 'px';
    canvas.style.height = window.innerHeight + 'px';
  }
  resize();
  window.addEventListener('resize', resize);

  // ── Particle pool ──────────────────────────────────────────────
  const COUNT = 80;
  const particles = [];

  function createParticle(init) {
    return {
      x: init ? Math.random() * W : -20,
      y: Math.random() * H,
      vx: 0.15 + Math.random() * 0.4,
      vy: (Math.random() - 0.5) * 0.3,
      radius: 0.5 + Math.random() * 1.5,
      alpha: 0.1 + Math.random() * 0.35,
      hue: 200 + Math.random() * 30,   // blue range
      pulse: Math.random() * Math.PI * 2,
      pulseSpeed: 0.01 + Math.random() * 0.02,
    };
  }

  for (let i = 0; i < COUNT; i++) {
    particles.push(createParticle(true));
  }

  // ── Connection lines ───────────────────────────────────────────
  const MAX_DIST = 150 * DPR;

  function drawConnections() {
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < MAX_DIST) {
          const alpha = (1 - dist / MAX_DIST) * 0.08;
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(77, 166, 255, ${alpha})`;
          ctx.lineWidth = 0.5 * DPR;
          ctx.stroke();
        }
      }
    }
  }

  // ── Animate ────────────────────────────────────────────────────
  function animate() {
    ctx.clearRect(0, 0, W, H);

    // Draw connections first (behind particles)
    drawConnections();

    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];

      // Move
      p.x += p.vx * DPR;
      p.y += p.vy * DPR;
      p.pulse += p.pulseSpeed;

      // Recycle if off screen
      if (p.x > W + 20 || p.y < -20 || p.y > H + 20) {
        particles[i] = createParticle(false);
        continue;
      }

      // Pulsing alpha
      const a = p.alpha * (0.6 + 0.4 * Math.sin(p.pulse));

      // Glow
      const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.radius * 4 * DPR);
      grad.addColorStop(0, `hsla(${p.hue}, 80%, 70%, ${a})`);
      grad.addColorStop(0.4, `hsla(${p.hue}, 80%, 60%, ${a * 0.3})`);
      grad.addColorStop(1, `hsla(${p.hue}, 80%, 50%, 0)`);

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius * 4 * DPR, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();

      // Core dot
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius * DPR, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${p.hue}, 90%, 80%, ${a * 1.5})`;
      ctx.fill();
    }

    requestAnimationFrame(animate);
  }

  animate();
})();

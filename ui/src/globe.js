// The particle globe, ported from docs/superpowers/specs/2026-11-15-bonnington-ui-mock.html (v3).
export const MOOD_RGB = {
  neutral: [255, 255, 255], amused: [250, 199, 117], annoyed: [240, 90, 80],
  smug: [175, 169, 236], serious: [133, 183, 235], disappointed: [150, 150, 145],
};

const TARGETS = {
  idle: { spin: 0.05, scale: 1.0 },
  listening: { spin: 0.03, scale: 0.9 },
  waking: { spin: 0.03, scale: 0.9 },
  thinking: { spin: 0.18, scale: 0.95 },
  speaking: { spin: 0.06, scale: 1.03 },
};

export function createGlobe(canvas, getState, count = 9000) {
  const ctx = canvas.getContext("2d");
  let W = 0, H = 0;
  function resize() {
    const d = window.devicePixelRatio || 1;
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = W * d; canvas.height = H * d;
    ctx.setTransform(d, 0, 0, d, 0, 0);
  }
  resize();
  window.addEventListener("resize", resize);
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(resize).observe(canvas);   // the cell resizes with the cards

  const P = [];
  for (let i = 0; i < count; i++) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2;
    P.push([Math.acos(u), th, Math.random()]);
  }

  let spin = 0.05, scale = 1, amp = 0, rot = 0, t = 0, last = performance.now();
  const col = [255, 255, 255];

  function frame(nowMs) {
    const dt = Math.min(0.05, (nowMs - last) / 1000); last = nowMs;
    const k = dt / 0.016;                                   // frame-rate independent easing
    t += dt;
    const s = getState();
    const tg = TARGETS[s.phase] || TARGETS.idle;
    spin += (tg.spin - spin) * 0.02 * k;
    scale += (tg.scale - scale) * 0.02 * k;
    rot += spin * dt;
    const tc = MOOD_RGB[s.mood] || MOOD_RGB.neutral;
    for (let j = 0; j < 3; j++) col[j] += (tc[j] - col[j]) * 0.015 * k;
    const tAmp = s.phase === "speaking" ? 0.03 + 0.09 * Math.min(1, s.amplitude) : s.phase === "listening" ? 0.02 : 0.01;
    amp += (tAmp - amp) * 0.04 * k;

    ctx.fillStyle = "rgba(0,0,0,0.5)"; ctx.fillRect(0, 0, W, H);
    const R = Math.min(W, H) * 0.33 * scale, cx = W / 2, cy = H / 2;
    const c = col.map(Math.round).join(",");
    const g = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 1.5);
    g.addColorStop(0, `rgba(${c},0.06)`); g.addColorStop(1, `rgba(${c},0)`);
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

    // Two quiet rings and four tick marks: the only motion besides the globe itself.
    ctx.lineWidth = 0.6;
    ctx.strokeStyle = `rgba(${c},0.16)`;
    ctx.beginPath(); ctx.arc(cx, cy, R * 1.22, 0, Math.PI * 2); ctx.stroke();
    ctx.setLineDash([2, 7]);
    ctx.beginPath(); ctx.arc(cx, cy, R * 1.34, t * 0.03, t * 0.03 + Math.PI * 2); ctx.stroke();
    ctx.setLineDash([]);
    ctx.strokeStyle = `rgba(${c},0.4)`;
    ctx.beginPath();
    for (let q = 0; q < 4; q++) {
      const a = q * Math.PI / 2 + t * 0.03;
      ctx.moveTo(cx + Math.cos(a) * R * 1.22, cy + Math.sin(a) * R * 1.22);
      ctx.lineTo(cx + Math.cos(a) * R * 1.3, cy + Math.sin(a) * R * 1.3);
    }
    ctx.stroke();

    const ca = Math.cos(rot), sa = Math.sin(rot), tl = 0.35, ct = Math.cos(tl), st = Math.sin(tl), ts = t * 0.25;
    for (const p of P) {
      const ph = p[0], th = p[1];
      const n = Math.sin(ph * 3 + ts * 0.7) * Math.cos(th * 2 - ts * 0.5) + Math.sin(th * 4 + ph * 2 + ts) * 0.4;
      const band = Math.exp(-Math.pow(ph - 2.2 + 0.3 * Math.sin(th * 2 + ts * 0.4), 2) * 6);
      const r = R * (1 + 0.045 * n + amp * Math.sin(th * 3 + ph * 2 + t * 1.6) * (0.4 + band) + (p[2] - 0.5) * 0.05);
      const x = r * Math.sin(ph) * Math.cos(th), y = r * Math.cos(ph), z = r * Math.sin(ph) * Math.sin(th);
      const x2 = x * ca - z * sa, z2 = x * sa + z * ca;
      const y2 = y * ct - z2 * st, z3 = y * st + z2 * ct;
      const d = (z3 / R + 1) / 2;
      const a = Math.min(0.9, (0.1 + 0.45 * d) * (0.3 + band * 1.1));
      const w = band * 0.6 + 0.2;
      ctx.fillStyle = `rgba(${Math.round(255 * (1 - w) + col[0] * w)},${Math.round(255 * (1 - w) + col[1] * w)},${Math.round(255 * (1 - w) + col[2] * w)},${a.toFixed(3)})`;
      ctx.fillRect(cx + x2, cy - y2, 1, 1);
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

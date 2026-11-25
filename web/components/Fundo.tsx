"use client";

import { useEffect, useRef } from "react";

/* O balcão: um campo esparso de glifos quase apagados, com uma poça de luz onde a máquina está. */
export default function Fundo({ focoX }: { focoX: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const foco = useRef(focoX);
  foco.current = focoX;

  useEffect(() => {
    const cv = ref.current!;
    const ctx = cv.getContext("2d")!;
    const reduz = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const familia = getComputedStyle(document.body).fontFamily;
    const CW = 16, CH = 24;
    let w = 0, h = 0, dpr = 1;
    const medir = () => {
      dpr = 1; // fundo de pontos: resolução 1x basta e custa 4x menos que 2x
      w = innerWidth; h = innerHeight;
      cv.width = w * dpr; cv.height = h * dpr;
    };
    medir();
    addEventListener("resize", medir);
    const G = " ..··:+";
    /* atlas: cada caractere em cada nível de alfa desenhado uma vez; o quadro só copia retângulos (drawImage),
       bem mais barato que ~3.300 fillText. Mesmo desenho de antes, pixel a pixel. */
    const NIV = 10, AW = CW, AH = CH;
    const atlas = document.createElement("canvas");
    atlas.width = AW * G.length; atlas.height = AH * NIV;
    const ag = atlas.getContext("2d")!;
    ag.font = `400 11px ${familia}`;
    ag.textAlign = "center"; ag.textBaseline = "middle";
    for (let i = 1; i < G.length; i++) for (let nv = 0; nv < NIV; nv++) {
      ag.fillStyle = `rgba(0,168,104,${(0.05 + (nv / 9) * 0.2).toFixed(3)})`;
      ag.fillText(G[i], i * AW + AW / 2, nv * AH + AH / 2);
    }
    let raf = 0, ultimo = 0;
    const quadro = (t: number) => {
      raf = requestAnimationFrame(quadro);
      if (t - ultimo < 120 && ultimo) return; // ~8 qps: o campo anda devagar
      if (document.hidden) return;
      ultimo = t;
      const s = reduz ? 0 : t / 1000;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const fx = foco.current * w, fy = h * 0.62;
      for (let y = CH / 2; y < h; y += CH) {
        for (let x = CW / 2; x < w; x += CW) {
          const n = Math.sin(x * 0.013 + s * 0.35) * Math.sin(y * 0.017 - s * 0.22) + Math.sin((x + y) * 0.006 + s * 0.15);
          const poca = Math.max(0, 1 - Math.hypot((x - fx) / (w * 0.42), (y - fy) / (h * 0.7)));
          const b = (n + 2) / 4 * 0.55 + poca * 0.45;
          const i = Math.floor(b * (G.length - 1) + 0.15);
          if (i <= 0) continue;
          const nv = Math.min(9, Math.round(b * 9));
          ctx.drawImage(atlas, i * AW, nv * AH, AW, AH, x - AW / 2, y - AH / 2, AW, AH);
        }
      }
    };
    raf = requestAnimationFrame(quadro);
    return () => { cancelAnimationFrame(raf); removeEventListener("resize", medir); };
  }, []);

  return <canvas ref={ref} aria-hidden style={{ position: "fixed", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }} />;
}

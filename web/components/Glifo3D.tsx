"use client";

import { useEffect, useRef, useState } from "react";

/* Embute o motor do afterglyph (MIT, github.com/winchxyz/afterglyph) num iframe da mesma origem,
   esconde a interface dele e dirige tudo pela API window.GB: texto, paleta Stone, 3D e fundo transparente. */

type GB = {
  P: Record<string, unknown>;
  orbit: { yaw: number; zoom: number };
  text: (t: string) => void;
  setSource: (s: Fonte) => void;
  sync: () => void;
  stage: () => void;
  apply: (t: boolean) => void;
  restart: () => void;
  pause: (v: boolean) => void;
};

// fonte de imagem no formato que o afterglyph usa internamente (o mesmo de textSource)
type Fonte = { kind: "image"; key: string; name: string; seed: number; w: number; h: number; animated: false; sway: false; info: string; draw: (g: CanvasRenderingContext2D) => void };

/* O logo oficial da Stone (verde-escuro) vira fonte do afterglyph: a forma vem do alfa do PNG e o brilho é
   remapeado do escuro para o claro, preservando o sombreado interno (o corte diagonal do "o" fica o ponto
   mais claro). Ampliado 3x para o motor ter detalhe; luz suave de cima à esquerda para o relevo 3D. */
const logos = new Map<string, Promise<Fonte>>();
function fonteLogo(url: string): Promise<Fonte> {
  if (!logos.has(url)) logos.set(url, new Promise((ok, falha) => {
    const img = new Image();
    img.onload = () => {
      const k = 3, pad = 40;
      const c = document.createElement("canvas");
      c.width = img.width * k + pad * 2; c.height = img.height * k + pad * 2;
      const g = c.getContext("2d", { willReadFrequently: true })!;
      g.imageSmoothingQuality = "high";
      g.drawImage(img, pad, pad, img.width * k, img.height * k);
      const d = g.getImageData(0, 0, c.width, c.height), px = d.data;
      let lo = 1, hi = 0;
      for (let i = 0; i < px.length; i += 4) if (px[i + 3] > 128) { const l = (px[i] * 0.3 + px[i + 1] * 0.59 + px[i + 2] * 0.11) / 255; lo = Math.min(lo, l); hi = Math.max(hi, l); }
      for (let i = 0; i < px.length; i += 4) {
        if (!px[i + 3]) continue;
        const l = (px[i] * 0.3 + px[i + 1] * 0.59 + px[i + 2] * 0.11) / 255;
        const n = hi > lo ? (l - lo) / (hi - lo) : 0; // 0 = verde do logo, 1 = brilho do corte do "o"
        const x = (i / 4) % c.width, y = Math.floor(i / 4 / c.width);
        const luz = 0.78 + 0.22 * (1 - (x / c.width) * 0.6 - (y / c.height) * 0.4); // luz de cima à esquerda
        const b = Math.min(1, (0.62 + 0.38 * n) * luz);
        px[i] = 40 * b; px[i + 1] = 255 * b; px[i + 2] = 120 * b; // verde claro: a paleta do motor remapeia pelo brilho
      }
      g.putImageData(d, 0, 0);
      ok({ kind: "image", key: "logo", name: "STONE", seed: 7031, w: c.width, h: c.height, animated: false, sway: false, info: "logo", draw: (g2) => g2.drawImage(c, 0, 0) });
    };
    img.onerror = () => falha(new Error("logo"));
    img.src = url;
  }));
  return logos.get(url)!;
}

type Props = {
  texto: string;
  logo?: string; // URL de imagem: quando presente, o glifo desenha o logo em vez do texto
  className?: string;
  densidade?: number;
  tres?: boolean;
  rotulo: string;
  zoom?: number;
  formato?: "16:9" | "1:1" | "4:5";
  balanco?: number;
  intro?: boolean; // false: o texto já nasce inteiro (sem a animação de crescer) // em vez de girar inteiro, balança de leve (rad): número precisa ser lido
  onPronto?: () => void;
  pausado?: boolean; // congela o motor (ex.: atrás do véu do comprovante)
};

const CSS = `
  :root{color-scheme:dark!important}
  html,body{background:transparent!important;overflow:hidden!important;margin:0!important}
  #amb,.top,.panel,.deck,.transport,.editbar,.pinbox,.prog,.drop,#edit,.help,.hint,footer{display:none!important}
  .app,.view{display:block!important;height:100vh!important;width:100vw!important;padding:0!important;background:transparent!important;grid-template-columns:none!important}
  .stage{position:fixed!important;inset:0!important;display:grid!important;place-items:center!important;background:transparent!important;border:0!important;box-shadow:none!important;border-radius:0!important;padding:0!important;max-height:none!important}
  #stage{width:100vw!important;height:100vh!important;max-width:none!important;max-height:none!important;object-fit:contain;border-radius:0!important;box-shadow:none!important;background:transparent!important}
`;

export default function Glifo3D({ texto, logo, className, densidade = 120, tres = true, rotulo, zoom = 1.8, formato = "16:9", balanco, intro = true, onPronto, pausado = false }: Props) {
  const ref = useRef<HTMLIFrameElement>(null);
  const [pronto, setPronto] = useState(false);
  // só aparece depois que a fonte certa (logo ou nota) entrou: antes disso o motor mostra a imagem padrão dele (uma flor)
  const [visivel, setVisivel] = useState(false);
  const gbRef = useRef<GB | null>(null);

  useEffect(() => {
    const fr = ref.current!;
    let vivo = true;
    const iniciar = () => {
      const w = fr.contentWindow as (Window & { GB?: GB }) | null;
      const doc = fr.contentDocument;
      if (!w?.GB || !doc) { if (vivo) setTimeout(iniciar, 120); return; }
      const st = doc.createElement("style"); st.textContent = CSS; doc.head.appendChild(st);
      const gb = w.GB; gbRef.current = gb;
      Object.assign(gb.P, {
        format: formato, res: 1, density: densidade, alpha: true, back: "#020805", hud: false, camera: false,
        palette: "custom", c1: "#0b6b45", c2: "#00a868", c3: "#cffff0", glow: 1.25, sat: 1.25,
        grain: 0, fringe: 0, scan: 0, three: tres, spin: true, intro: true, introStyle: "grow", introLen: 2.4, fpsCap: 30, // 30 qps: metade do custo de reler os pixels a cada quadro, sem diferença visível no ASCII
        // a nota cresce em 2,4 s (o padrão de 8 s atrasaria o rasgo)
        caption: "", outline: true, shimmer: 1, mood: "auto", volume: 0,
      });
      gb.stage();
      if (!logo) { gb.text(texto); gb.sync(); if (tres) gb.apply(true); } // com logo, o efeito abaixo põe a imagem (sem piscar o texto antes)
      // o afterglyph volta o zoom para 1 quando a malha 3D termina de montar; reaplica depois
      for (const ms of [300, 900, 1800]) setTimeout(() => { gb.orbit.zoom = zoom; }, ms);
      setPronto(true); onPronto?.();
    };
    fr.addEventListener("load", iniciar);
    if (fr.contentDocument?.readyState === "complete") iniciar();
    return () => { vivo = false; fr.removeEventListener("load", iniciar); };
    // o texto muda por outro efeito; aqui só a montagem
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const gb = gbRef.current;
    if (!gb || !pronto) return;
    gb.P.spin = balanco == null;
    gb.P.intro = intro;
    gb.orbit.yaw = 0;
    let vivo = true;
    const ids: ReturnType<typeof setTimeout>[] = [];
    const montar = () => {
      gb.sync();
      if (tres) gb.apply(true);
      // dois quadros para o motor desenhar a fonte nova antes de revelar
      requestAnimationFrame(() => requestAnimationFrame(() => { if (vivo) setVisivel(true); }));
      for (const ms of [0, 300, 900, 1800]) ids.push(setTimeout(() => { gb.orbit.zoom = zoom; }, ms));
    };
    if (logo) fonteLogo(logo).then((f) => { if (!vivo) return; gb.setSource(f); montar(); }).catch(() => { if (vivo) { gb.text(texto); montar(); } });
    else { gb.text(texto); montar(); }
    ids.push(setTimeout(() => { gb.orbit.zoom = zoom; }, 2600));
    let raf = 0;
    if (balanco != null) {
      const t0 = performance.now();
      const balanca = () => { gb.orbit.yaw = balanco * Math.sin((performance.now() - t0) / 1000 * 0.7); raf = requestAnimationFrame(balanca); };
      raf = requestAnimationFrame(balanca);
    }
    return () => { vivo = false; ids.forEach(clearTimeout); cancelAnimationFrame(raf); };
  }, [texto, logo, pronto, tres, zoom, balanco, intro]);

  useEffect(() => { if (pronto) gbRef.current?.pause(pausado); }, [pausado, pronto]);

  return (
    <iframe
      ref={ref}
      src="/afterglyph/index.html"
      title={rotulo}
      tabIndex={-1} // decorativo: o Tab não para no glifo
      className={className}
      style={{ border: 0, background: "transparent", colorScheme: "dark", opacity: visivel ? 1 : 0, transition: "opacity 1.2s var(--ease)" }}
    />
  );
}

"use client";

import { useEffect, useRef, type ReactNode } from "react";
import s from "./maquina.module.css";

/* Uma smart POS da Stone, desenhada como objeto sólido: corpo preto fosco, impressora no topo,
   tela touch quase do tamanho da frente e a marca no queixo. Toda a interação mora na tela. */

export const W = 370;
export const H = 770;
export const FENDA_Y = 108; // fenda na emenda entre a cabeça da impressora e o corpo, como na Stone Smart real

type Props = {
  escala: number;
  tela: ReactNode;
  acima?: ReactNode; // o comprovante sai pela fenda e cresce para cima
  ativa?: boolean; // processando: as ondas de aproximação pulsam, como na espera do cartão
};

export default function Maquina({ tela, acima, ativa }: Props) {
  const objeto = useRef<HTMLDivElement>(null);
  const acimaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = objeto.current!;
    const reduz = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const toque = matchMedia("(pointer: coarse)").matches; // no celular a máquina não inclina
    const tilt = { x: 0, y: 0, ax: 0, ay: 0 };
    const mover = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      const sx = (e.clientX - r.left) / r.width, sy = (e.clientY - r.top) / r.height;
      // reflexo da luz segue o cursor sempre
      el.style.setProperty("--lx", `${(sx * 100).toFixed(1)}%`);
      el.style.setProperty("--ly", `${(sy * 100).toFixed(1)}%`);
      // com o cursor em cima da máquina ou do comprovante ela para de inclinar: nada pode fugir do dedo
      const papel = acimaRef.current?.getBoundingClientRect();
      const sobrePapel = !!papel && papel.height > 0 && e.clientX >= papel.left - 12 && e.clientX <= papel.right + 12 && e.clientY >= papel.top - 12 && e.clientY <= papel.bottom;
      if (sobrePapel || (sx > -0.04 && sx < 1.04 && sy > -0.04 && sy < 1.04)) { tilt.ax = tilt.x; tilt.ay = tilt.y; return; }
      tilt.ay = Math.max(-1, Math.min(1, (e.clientX - (r.left + r.width / 2)) / innerWidth)) * 7;
      tilt.ax = Math.max(-1, Math.min(1, (e.clientY - (r.top + r.height * 0.4)) / innerHeight)) * -5;
    };
    addEventListener("pointermove", mover);
    let raf = 0;
    const passo = () => {
      raf = requestAnimationFrame(passo);
      const dx = tilt.ax - tilt.x, dy = tilt.ay - tilt.y;
      if (Math.abs(dx) < 0.01 && Math.abs(dy) < 0.01) return; // parada: não reescreve o transform
      tilt.x += dx * 0.08; tilt.y += dy * 0.08;
      if (!reduz && !toque) el.style.transform = `rotateX(${tilt.x.toFixed(2)}deg) rotateY(${tilt.y.toFixed(2)}deg)`;
    };
    raf = requestAnimationFrame(passo);
    return () => { cancelAnimationFrame(raf); removeEventListener("pointermove", mover); };
  }, []);

  return (
    <div className={s.objeto} ref={objeto} style={{ width: W, height: H }}>
      <div className={s.acima} ref={acimaRef} style={{ bottom: H - FENDA_Y }}>{acima}</div>
      <div className={s.sombra} aria-hidden />
      <div className={s.impressora}>
        {/* área de aproximação: o símbolo de pagamento por aproximação em baixo-relevo, como na peça */}
        <span className={`${s.nfc} ${ativa ? s.nfcAtiva : ""}`} aria-hidden>
          <svg viewBox="0 0 64 40" width="64" height="40">
            <rect x="6" y="9" width="22" height="16" rx="2.5" />
            <path d="M10 14h8" />
            <path d="M36 10c3 3 3 17 0 20" />
            <path d="M42 6c5 5 5 23 0 28" />
            <path d="M48 2c7 7 7 29 0 36" />
          </svg>
        </span>
        <span className={s.fenda} aria-hidden />
      </div>
      <span className={s.tampa} aria-hidden />
      <div className={s.frente}>
        <div className={s.vidro}>
          <span className={s.camera} aria-hidden />
          <div className={s.tela}>{tela}</div>
        </div>
        {/* logo oficial da Stone (stone.com.br, og:image), recortado com fundo transparente, no queixo abaixo da tela */}
        <img className={s.logo} src="/stone-logo.png" alt="Stone" width={184} height={49} />
      </div>
    </div>
  );
}

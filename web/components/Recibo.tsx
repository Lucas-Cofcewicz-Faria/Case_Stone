"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import qrcode from "qrcode-generator";
import s from "./recibo.module.css";

export type Linha =
  | { k: "centro"; t: string; forte?: boolean }
  | { k: "texto"; t: string; forte?: boolean }
  | { k: "rot"; t: string }
  | { k: "par"; a: string; b: string; tom?: "cred" | "deb" | "pend" }
  | { k: "sep"; duplo?: boolean }
  | { k: "total"; nota: number }
  | { k: "ref"; n: number; t: string; sub: string; url: string }
  | { k: "qr"; url: string; t: string }
  | { k: "miudo"; t: string; centro?: boolean }
  | { k: "sub"; t: string; tom?: "pend" | "deb" }; // continuação recuada da linha de cima

type Props = {
  linhas: Linha[];
  fim: boolean; // não chegam mais linhas
  ritmo?: number;
  onTotal?: (nota: number) => void;
  onLinha?: () => void;
  onFim?: () => void;
};

/* matriz 5×7 desenhada à mão para o TOTAL: é o que a cabeça térmica imprimiria */
const DIG: Record<string, string[]> = {
  "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
  "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
  "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
  "3": ["11111", "00010", "00100", "00010", "00001", "10001", "01110"],
  "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
  "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
  "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
  "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
  "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
  "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
};

function Matriz({ texto, passo = 6 }: { texto: string; passo?: number }) {
  const dig = texto.split("");
  const larg = dig.length * 6 * passo - passo;
  return (
    <svg className={s.matriz} width={larg} height={7 * passo} viewBox={`0 0 ${larg} ${7 * passo}`} aria-hidden>
      {dig.map((d, i) => DIG[d]?.flatMap((linha, y) => linha.split("").map((v, x) => v === "1" && (
        <circle key={`${i}-${x}-${y}`} cx={i * 6 * passo + x * passo + passo / 2} cy={y * passo + passo / 2} r={passo * 0.4} />
      ))))}
    </svg>
  );
}

function Qr({ url }: { url: string }) {
  const q = useMemo(() => { const q = qrcode(0, "M"); q.addData(url); q.make(); return q; }, [url]);
  const n = q.getModuleCount();
  const quadros: React.ReactElement[] = [];
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (q.isDark(y, x)) quadros.push(<rect key={`${x}-${y}`} x={x} y={y} width={1.04} height={1.04} />);
  return <svg className={s.qr} viewBox={`-2 -2 ${n + 4} ${n + 4}`} shapeRendering="crispEdges" role="img" aria-label="QR code do post de referência">{quadros}</svg>;
}

function Uma({ l }: { l: Linha }) {
  switch (l.k) {
    case "centro": return <p className={`${s.centro} ${l.forte ? s.forte : ""}`}>{l.t}</p>;
    case "texto": return <p className={`${s.texto} ${l.forte ? s.forte : ""}`}>{l.t}</p>;
    case "rot": return <p className={s.rot}>{l.t}</p>;
    case "sub": return <p className={`${s.sub} ${l.tom ? s[l.tom] : ""}`}>{l.t}</p>;
    case "miudo": return <p className={`${s.miudo} ${l.centro ? s.centro : ""}`}>{l.t}</p>;
    case "sep": return <p className={l.duplo ? s.sepDuplo : s.sep} aria-hidden />;
    case "par": return l.b.length <= 16 && l.a.length > 22 ? (
      <p className={`${s.parQuebra} ${l.tom ? s[l.tom] : ""}`}>
        <span className={s.pa}>{l.a}</span><span className={s.pb}>{l.b}</span>
      </p>
    ) : l.b.length > 16 ? (
      /* valor longo: rótulo numa linha, valor inteiro embaixo, sem cortar palavra */
      <p className={`${s.parLongo} ${l.tom ? s[l.tom] : ""}`}>
        <span className={s.pa}>{l.a}</span><span className={s.pb}>{l.b}</span>
      </p>
    ) : (
      <p className={`${s.par} ${l.tom ? s[l.tom] : ""}`}>
        <span className={s.pa}>{l.a}</span><span className={s.guia} aria-hidden /><span className={s.pb}>{l.b}</span>
      </p>
    );
    case "total": return (
      <div className={s.total} role="text" aria-label={`Total: ${l.nota} de 100`}>
        <span className={s.totalRot}>TOTAL</span>
        <span className={s.totalNum}><Matriz texto={String(l.nota)} /><small>/100</small></span>
      </div>
    );
    case "ref": return (
      <p className={s.ref}>
        <span className={s.refN}>{l.n}</span>
        <a href={l.url} target="_blank" rel="noreferrer">{l.t}</a>
        <span className={s.refSub}>{l.sub}</span>
      </p>
    );
    case "qr": return (
      <a className={s.qrLinha} href={l.url} target="_blank" rel="noreferrer">
        <Qr url={l.url} /><span>{l.t}</span>
      </a>
    );
  }
}

export default function Recibo({ linhas, fim, ritmo = 55, onTotal, onLinha, onFim }: Props) {
  const [n, setN] = useState(0);
  const avisou = useRef(false);
  const reduz = useRef(false);
  // callbacks em ref: o pai re-renderiza a cada décimo de segundo (cronômetro) e não pode zerar o timer
  const cb = useRef({ onTotal, onLinha, onFim });
  cb.current = { onTotal, onLinha, onFim };
  useEffect(() => { reduz.current = matchMedia("(prefers-reduced-motion: reduce)").matches; }, []);

  useEffect(() => {
    if (n >= linhas.length) {
      if (fim && !avisou.current && linhas.length) { avisou.current = true; cb.current.onFim?.(); }
      return;
    }
    const prox = linhas[n];
    const espera = reduz.current ? 8 : prox.k === "total" ? 520 : prox.k === "sep" ? ritmo * 0.6 : ritmo;
    const id = setTimeout(() => {
      setN((v) => v + 1);
      cb.current.onLinha?.();
      if (prox.k === "total") cb.current.onTotal?.(prox.nota);
    }, espera);
    return () => clearTimeout(id);
  }, [n, linhas, fim, ritmo]);

  const impresso = linhas.slice(0, n);
  const terminou = fim && n >= linhas.length;

  return (
    <div className={s.folha}>
      <div className={s.papel}>
      <div className={s.miolo}>
        {impresso.map((l, i) => (
          <div key={i} className={s.linha}><Uma l={l} /></div>
        ))}
        {!terminou && <div className={s.cabeca} aria-hidden><span /></div>}
      </div>
      </div>
    </div>
  );
}

/* O comprovante já rasgado, aberto para leitura: as linhas dobram em colunas (como papel em sanfona)
   até caber na tela sem rolar. No celular fica uma coluna só, rolando dentro do papel. */
// a dobra da coluna nunca separa uma linha da continuação dela, nem um título da primeira linha da seção
function blocos(linhas: Linha[]): Linha[][] {
  const out: Linha[][] = [];
  for (const l of linhas) {
    const ant = out[out.length - 1];
    // continuação fica com a linha de cima; título de seção fica com a linha de baixo
    if (ant && (l.k === "sub" || ant[ant.length - 1].k === "rot")) ant.push(l);
    else out.push([l]);
  }
  return out;
}

export function ReciboAberto({ linhas }: { linhas: Linha[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [cols, setCols] = useState(1);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const medir = () => {
      // mede a altura inteira numa coluna só, sem o limite de altura
      el.style.maxHeight = "none";
      el.style.columnCount = "1";
      el.style.width = "332px";
      const alto = el.scrollHeight;
      el.style.maxHeight = "";
      const cabe = Math.max(1, Math.floor((innerWidth * 0.9 + 28) / (300 + 28)));
      if (cabe === 1) { setCols(1); return; } // celular: uma coluna, rolando
      let n = Math.min(cabe, Math.max(1, Math.ceil(alto / (el.clientHeight || innerHeight * 0.8))));
      // cada coluna tem 300 px; a largura acompanha o número de colunas
      const aplicar = (k: number) => { el.style.columnCount = String(k); el.style.width = `${k * 300 + (k - 1) * 28 + 32}px`; };
      aplicar(n);
      // linhas que não quebram podem empurrar conteúdo para uma coluna extra: acerta até caber
      while (n < cabe && el.scrollWidth > el.clientWidth + 2) { n += 1; aplicar(n); }
      setCols(n);
    };
    medir();
    addEventListener("resize", medir);
    return () => removeEventListener("resize", medir);
  }, [linhas]);
  return (
    <div className={`${s.folha} ${s.aberto}`} style={{ ["--cols" as string]: cols }}>
      <div className={s.papel}>
        <div ref={ref} className={`${s.miolo} ${s.colunas}`}>
          {blocos(linhas).map((b, i) => <div key={i} className={s.linhaAberta}>{b.map((l, j) => <Uma key={j} l={l} />)}</div>)}
        </div>
      </div>
    </div>
  );
}

/* o pedaço serrilhado que fica na fenda depois que o comprovante é destacado */
export function Toco() {
  return <div className={s.toco} aria-hidden />;
}

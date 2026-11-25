"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import dynamic from "next/dynamic";
import s from "./page.module.css";
import Maquina, { FENDA_Y, H, W } from "@/components/Maquina";
import Recibo, { ReciboAberto, Toco, type Linha } from "@/components/Recibo";
import Fundo from "@/components/Fundo";
import {
  apiOnline, avaliar, carregar, rodarAgente, rotulo, NOMES_GRUPO,
  type Avaliacao, type EtapaAgente, type Exemplo,
} from "@/lib/dados";

const Glifo3D = dynamic(() => import("@/components/Glifo3D"), { ssr: false });

type Modo = "avaliar" | "agente";
type Campo = "titulo" | "legenda" | "roteiro";
type Rascunho = { titulo: string; legenda: string; roteiro: string; duracao_s: number };
type Tela =
  | { k: "edita" }
  | { k: "aguarde"; t0: number; fase: string; gravado?: boolean }
  | { k: "imprimindo" }
  | { k: "nota"; nota: number; demo?: boolean }
  | { k: "aviso"; msg: string }
  | { k: "erro"; msg: string };
type Comp = { id: number; linhas: Linha[]; fim: boolean };

const CAMPOS: Campo[] = ["titulo", "legenda", "roteiro"];
const NOME_CAMPO: Record<Campo, string> = { titulo: "título", legenda: "legenda", roteiro: "roteiro" };
const DICA: Record<Campo, string> = {
  titulo: "ex.: Quanto cobrar por um bolo de 2 kg?",
  legenda: "ex.: Comenta QUERO que eu te mando a planilha de custos.",
  roteiro: "ex.: Close nas mãos. Fala: sabe quanto custa esse bolo?",
};
/* cada exemplo tem uma execução gravada (python -m stone.gravar_demo): com o texto intacto, toca em segundos; editou, vai ao vivo */
const PRESETS = [
  { nome: "confeitaria", chave: "confeitaria", pedido: "Post do Impulso para confeiteiras que vendem bolo por encomenda pelo WhatsApp e não sabem quanto cobrar" },
  { nome: "salão", chave: "salao", pedido: "Post do Impulso para donas de salão de beleza pequeno com a agenda vazia na terça e na quarta" },
  { nome: "loja de roupas", chave: "roupas", pedido: "Post do Impulso para donas de loja de roupas de bairro que também querem vender pelo Instagram" },
  { nome: "lavanderia", chave: "lavanderia", pedido: "Post do Impulso para donos de lavanderia de bairro que querem atender os prédios da região" },
  { nome: "artesã MEI", chave: "artesa", pedido: "Post do Impulso para artesãs autônomas, MEI, que fazem lembrancinhas personalizadas e se perdem com a nota fiscal e o DAS" },
  { nome: "ar-condicionado", chave: "arcond", pedido: "Post do Impulso para MEIs de manutenção de ar-condicionado que querem mais orçamentos" },
];
type Pronto = Rascunho & { chave: string; avaliacao: Avaliacao };
type Gravacao = { pedido: string; nota: number; versoes: number[]; gravado_em: string };
const NOME_PRONTO: Record<string, string> = { nota_mei: "nota MEI", bolo: "bolo", motivacional: "motivação" };
const igual = (a: Rascunho, b: Rascunho) =>
  a.titulo.trim() === b.titulo.trim() && a.legenda.trim() === b.legenda.trim() && a.roteiro.trim() === b.roteiro.trim() && a.duracao_s === b.duracao_s;
const espera = (ms: number, sinal: AbortSignal) => new Promise<void>((ok, falha) => {
  const t = setTimeout(ok, ms);
  sinal.addEventListener("abort", () => { clearTimeout(t); falha(new DOMException("parou", "AbortError")); }, { once: true });
});
const FASES = [
  "lendo o rascunho com a mesma rubrica dos 3.548 posts",
  "classificando formato, gancho, tema e chamada",
  "comparando com o top 10% de conversa",
  "somando os lançamentos",
];
// trocar tema ou pilar não é ajuste, é outro post
type VT = { ready: Promise<void>; finished: Promise<void>; updateCallbackDone: Promise<void>; skipTransition: () => void };
const TIRA = 240; // px de papel à vista saindo da fenda enquanto imprime
const FIXOS = new Set(["tema_principal", "pilar_impulso", "legenda_tamanho"]);

const semEmoji = (t: string) => t.replace(/\p{Extended_Pictographic}|️|‍/gu, "").replace(/\s{2,}/g, " ").trim();
const semTags = (t: string) => semEmoji(t.replace(/#\S+/g, ""));
// títulos todos em maiúsculas viram frase, para caber e ser lidos
const frase = (t: string) => {
  const letras = t.replace(/[^\p{L}]/gu, "");
  if (letras.length < 4 || letras !== letras.toUpperCase()) return t;
  const m = t.toLowerCase();
  return m.charAt(0).toUpperCase() + m.slice(1);
};
// corta o título numa palavra inteira, nunca no meio ("maquinin…")
const curto = (t: string, max = 34) => {
  if (t.length <= max) return t;
  const c = t.slice(0, max + 1).replace(/\s+\S*$/, "");
  return `${c.replace(/[\s,.:;–-]+$/, "")}…`;
};
const mil = (v: number) => `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 })}/mil views`;
const carimbo = () => {
  const d = new Date();
  return `${d.toLocaleDateString("pt-BR")} ${d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
};

// faixas como "30–60 s" não quebram no traço (word joiner dos dois lados)
const junta = (t: string) => t.replace(/(\d)\s?[-–]\s?(\d)/g, "$1⁠–⁠$2");

function valor(campo: string, v: string | boolean) {
  if (typeof v === "boolean") return v ? "sim" : "não";
  return junta(rotulo(`${campo}=${v}`).split(": ")[1] ?? String(v).replaceAll("_", " "));
}

function linhasAvaliacao(av: Avaliacao, o: { titulo: string; duracao?: number; real?: Exemplo; demo?: boolean; pronto?: boolean }): Linha[] {
  const L: Linha[] = [
    { k: "centro", t: "stone · conversa", forte: true },
    { k: "centro", t: "EXTRATO DE ADERÊNCIA" },
    { k: "miudo", t: `${carimbo()} · via do cliente`, centro: true },
  ];
  if (o.demo) L.push({ k: "miudo", t: "MODO DEMO: a API local está desligada. Este é um post real que já foi avaliado.", centro: true });
  if (o.pronto) L.push({ k: "miudo", t: "Rascunho de exemplo: avaliação gravada antes, com o mesmo modelo local.", centro: true });
  L.push({ k: "sep" }, { k: "texto", t: semTags(o.titulo) || o.titulo, forte: true }, { k: "par", a: "origem", b: o.real ? "post real" : o.pronto ? "rascunho de exemplo" : "seu rascunho" });
  if (o.real) {
    L.push({ k: "par", a: "canal", b: semEmoji(o.real.perfil).trim() });
    L.push({ k: "par", a: "conversa", b: mil(o.real.conversa) });
  } else if (o.duracao) L.push({ k: "par", a: "duração", b: `${o.duracao} s` });

  L.push({ k: "sep" }, { k: "rot", t: "lançamentos (pesos)" });
  const lanc = (av.lancamentos ?? []).filter((l) => Math.abs(l.peso) >= 0.01);
  if (lanc.length) {
    for (const l of lanc) L.push({ k: "par", a: junta(rotulo(l.atributo)), b: `${l.peso >= 0 ? "+" : "−"}${Math.abs(l.peso * 100).toFixed(0)}`, tom: l.peso >= 0 ? "cred" : "deb" });
  } else {
    for (const p of av.padroes_cumpridos) L.push({ k: "par", a: rotulo(p.atributo), b: `${p.lift.toFixed(2)}×`, tom: "cred" });
    for (const p of av.antipadroes) L.push({ k: "par", a: rotulo(p.atributo), b: `${p.lift.toFixed(2)}×`, tom: "deb" });
  }
  if (lanc.length && !av.sem_conteudo) {
    const soma = lanc.reduce((t, l) => t + Math.round(l.peso * 100), 0); // soma do que está impresso
    L.push({ k: "sep" }, { k: "par", a: "soma dos pesos", b: `${soma >= 0 ? "+" : "−"}${Math.abs(soma)}` });
  }
  const sug = av.sugestoes.filter((g) => !FIXOS.has(g.campo));
  if (sug.length) {
    L.push({ k: "rot", t: "pendente: pesos a ganhar (não somam)" });
    for (const g of sug) L.push(
      { k: "par", a: rotulo(g.campo), b: `+${(g.ganho * 100).toFixed(0)}`, tom: "pend" },
      { k: "sub", t: `${valor(g.campo, g.de)} → ${valor(g.campo, g.para)}`, tom: "pend" },
    );
  }
  L.push({ k: "sep", duplo: true }, { k: "total", nota: av.nota });
  if (!av.sem_conteudo) L.push({ k: "miudo", t: `A nota é a posição dessa soma na base: ela supera ${av.nota}% dos 3.548 posts.` });
  L.push({ k: "sep", duplo: true });
  if (av.sem_conteudo && av.motivo) L.push({ k: "texto", t: av.motivo });

  const refs = av.referencias.slice(0, 3);
  if (refs.length) {
    L.push({ k: "rot", t: "posts parecidos que geraram conversa" });
    refs.forEach((r, i) => L.push({ k: "ref", n: i + 1, t: semTags(r.titulo) || r.titulo, sub: `${semEmoji(r.perfil)} · ${mil(r.conversa)}`, url: r.url }));
    L.push({ k: "qr", url: refs[0].url, t: "Aponte a câmera para assistir ao post parecido nº 1." });
    L.push({ k: "sep" });
  }
  L.push({ k: "miudo", t: av.aviso });
  L.push({ k: "miudo", t: "conversa, não curtida.", centro: true });
  return L;
}

/* ---------- agente: cada etapa vira uma linha do comprovante ---------- */
type Est = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

function linhaEtapa(e: EtapaAgente, versoes: number[]): { linhas: Linha[]; fase: string } {
  const st = e.estado as Est;
  switch (e.no) {
    case "entender": return {
      linhas: [{ k: "par", a: "negócio", b: semEmoji(String(st.plano?.negocio ?? "").replaceAll("_", " ")) }, { k: "par", a: "segmento", b: NOMES_GRUPO[st.plano?.segmento] ?? st.plano?.segmento ?? "" }],
      fase: "buscando os padrões do segmento",
    };
    case "padroes": return {
      linhas: [
        { k: "par", a: "padrões", b: st.padroes?.fonte_dos_padroes === "segmento" ? "do próprio segmento" : "da base inteira" },
        ...(st.padroes?.confianca ? [{ k: "par", a: "confiança", b: String(st.padroes.confianca) } as Linha] : []),
      ],
      fase: "buscando posts reais parecidos",
    };
    case "referencias": return {
      linhas: [{ k: "par", a: "referências", b: (st.referencias?.length ?? 0) === 1 ? "1 post real" : `${st.referencias?.length ?? 0} posts reais` }],
      fase: "escrevendo a versão 1",
    };
    case "gerar": return { linhas: [{ k: "par", a: `versão ${st.tentativas}`, b: "escrita" }], fase: `avaliando a versão ${st.tentativas}` };
    case "avaliar": {
      const nota = st.avaliacao?.nota ?? 0;
      const v = versoes.length;
      // só problema grave (cena repetida, legenda copiada, roteiro sem fala) faz o agente reescrever
      const problemas = (st.avaliacao?.graves as string[] | undefined)?.length ?? 0;
      return {
        linhas: [
          { k: "par", a: `nota v${v}`, b: `${nota}/100` },
          ...(problemas ? [{ k: "par", a: "texto", b: problemas === 1 ? "1 ajuste" : `${problemas} ajustes` } as Linha] : []),
        ],
        fase: (nota >= 60 && !problemas) || v >= 3 ? "fechando o criativo" : `reescrevendo: versão ${v + 1}`,
      };
    }
    default: return { linhas: [], fase: "imprimindo" };
  }
}

function linhasCriativo(melhor: Est, versoes: number[], refs: Est[]): Linha[] {
  const c = melhor.criativo, av = melhor.avaliacao as Avaliacao;
  const v = (melhor.avaliacao.tentativa as number | undefined) ?? (versoes.indexOf(av.nota) + 1 || versoes.length);
  const L: Linha[] = [
    { k: "sep", duplo: true },
    { k: "texto", t: semEmoji(c.titulo), forte: true },
    { k: "par", a: "criativo", b: `versão ${v} de ${versoes.length}` },
    { k: "rot", t: "gancho (0–3 s)" }, { k: "texto", t: semEmoji(c.gancho) },
    { k: "rot", t: `roteiro · ${String(c.formato).replaceAll("_", " ")} · ${c.duracao_s} s` },
    ...(c.roteiro as string[]).map((r, i): Linha => ({ k: "texto", t: `${i + 1}. ${semEmoji(r)}` })),
  ];
  if (c.texto_na_tela) L.push({ k: "rot", t: "texto na tela" }, { k: "texto", t: semEmoji(c.texto_na_tela) });
  L.push({ k: "rot", t: "legenda" }, { k: "texto", t: semEmoji(c.legenda) });
  L.push({ k: "rot", t: "chamada" }, { k: "texto", t: semEmoji(c.cta) });
  if (c.justificativa) L.push({ k: "rot", t: "por quê" }, { k: "miudo", t: semEmoji(c.justificativa) });
  L.push({ k: "sep", duplo: true }, { k: "total", nota: av.nota }, { k: "sep", duplo: true });
  if (av.nota < 60) L.push({ k: "miudo", t: `Nenhuma versão passou de 60. Esta é a melhor das ${versoes.length}.` });
  const probs = (av as Est).problemas as string[] | undefined;
  if (probs?.length) L.push({ k: "miudo", t: `Revise antes de usar: ${probs.join("; ")}.` });
  const r3 = refs.slice(0, 3);
  if (r3.length) {
    L.push({ k: "rot", t: "posts reais usados como referência" });
    r3.forEach((r, i) => L.push({ k: "ref", n: i + 1, t: semTags(r.titulo) || r.titulo, sub: `${semEmoji(r.nome ?? r.perfil ?? "")} · ${mil(r.conversa)}`, url: r.url }));
    L.push({ k: "qr", url: r3[0].url, t: "Aponte a câmera para assistir à referência nº 1." });
    L.push({ k: "sep" });
  }
  if (av.aviso) L.push({ k: "miudo", t: av.aviso });
  L.push({ k: "miudo", t: "conversa, não curtida.", centro: true });
  return L;
}

/* ícones desenhados num só traço, no lugar de caracteres unicode */
/* a nota sobe de 0 até o valor, desacelerando (como o valor aprovado na tela da maquininha) */
function Contador({ n }: { n: number }) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { setV(n); return; }
    let raf = 0;
    const t0 = performance.now();
    const passo = (t: number) => {
      const k = Math.min(1, (t - t0) / 900);
      setV(Math.round(n * (1 - Math.pow(1 - k, 3))));
      if (k < 1) raf = requestAnimationFrame(passo);
    };
    raf = requestAnimationFrame(passo);
    return () => cancelAnimationFrame(raf);
  }, [n]);
  return <>{v}</>;
}

/* duração digitável: só dígitos; vale ao sair do campo ou no Enter, presa entre 10 e 180 s. Os botões seguem somando 5. */
function CampoDuracao({ valor, mudar }: { valor: number; mudar: (v: number) => void }) {
  const [rasc, setRasc] = useState<string | null>(null);
  const aplicar = () => {
    if (rasc == null) return;
    const n = parseInt(rasc, 10);
    if (!Number.isNaN(n)) mudar(Math.max(10, Math.min(180, n)));
    setRasc(null);
  };
  return (
    <label className={s.duracao}>
      <input
        type="text" inputMode="numeric" aria-label="Duração em segundos" maxLength={3}
        value={rasc ?? String(valor)}
        onFocus={(e) => { setRasc(String(valor)); e.currentTarget.select(); }}
        onChange={(e) => setRasc(e.target.value.replace(/\D/g, ""))}
        onBlur={aplicar}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); e.currentTarget.blur(); }
          if (e.key === "Escape") { setRasc(null); e.currentTarget.blur(); }
          if (e.key === "ArrowUp" || e.key === "ArrowDown") { e.preventDefault(); const n = parseInt(rasc ?? String(valor), 10) || valor; const v = Math.max(10, Math.min(180, n + (e.key === "ArrowUp" ? 1 : -1))); setRasc(String(v)); mudar(v); }
        }}
      />
      <span aria-hidden>s</span>
    </label>
  );
}

function Icone({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

export default function Pagina() {
  const [online, setOnline] = useState(false);
  const [exemplos, setExemplos] = useState<Exemplo[]>([]);
  const [prontos, setProntos] = useState<Pronto[]>([]);
  const [gravacoes, setGravacoes] = useState<Record<string, Gravacao>>({});
  const [modo, setModo] = useState<Modo>("avaliar");
  const [rasc, setRasc] = useState<Rascunho>({ titulo: "", legenda: "", roteiro: "", duracao_s: 45 });
  const [pedido, setPedido] = useState(PRESETS[0].pedido);
  const [tela, setTela] = useState<Tela>({ k: "edita" });
  const [comp, setComp] = useState<Comp | null>(null);
  const [nota3d, setNota3d] = useState<number | null>(null);
  const [ignicao, setIgnicao] = useState(false); // no celular o número aparece por cima, por um instante
  const [toco, setToco] = useState(false);
  const [agora, setAgora] = useState(0);
  const [hora, setHora] = useState("");
  const [vp, setVp] = useState({ w: 1440, h: 900 });

  const campoRef = useRef<HTMLTextAreaElement>(null);
  const abort = useRef<AbortController | null>(null);
  const seq = useRef(0);
  const notaFinal = useRef<{ nota: number; demo?: boolean } | null>(null);

  /* ---------- montagem ---------- */
  useEffect(() => {
    carregar<Exemplo[]>("exemplos").then((e) => setExemplos([...e].sort((a, b) => b.avaliacao.nota - a.avaliacao.nota)));
    carregar<Pronto[]>("rascunhos").then(setProntos).catch(() => {});
    carregar<Record<string, Gravacao>>("agente/indice").then(setGravacoes).catch(() => {});
    apiOnline().then(setOnline);
    const id = setInterval(() => apiOnline().then(setOnline), 8000);
    const relogio = () => setHora(new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }));
    relogio();
    const r = setInterval(relogio, 20000);
    const medir = () => setVp({ w: innerWidth, h: innerHeight });
    medir();
    addEventListener("resize", medir);
    return () => { clearInterval(id); clearInterval(r); removeEventListener("resize", medir); };
  }, []);

  // cronômetro da tela enquanto espera
  useEffect(() => {
    if (tela.k !== "aguarde") return;
    const id = setInterval(() => setAgora(performance.now()), 100);
    return () => clearInterval(id);
  }, [tela.k]);

  const largo = vp.w >= 980;
  const escala = Math.max(0.55, Math.min(1.3, (vp.h * (largo ? 0.9 : 0.8)) / H, (vp.w - 32) / W));
  const focoX = largo ? 0.64 : 0.5;
  /* enquanto imprime, a máquina encolhe o bastante para a tira e o Smart inteiro (com o queixo) caberem na tela */
  const kMaq = comp ? Math.min(escala, (vp.h - 44) / (TIRA + H - FENDA_Y)) : escala;

  /* ---------- comprovantes: imprime uma tira, rasga na fenda e voa para o centro ---------- */
  const [foco, setFoco] = useState<Comp | null>(null);
  const [rasgando, setRasgando] = useState(false);
  const verRef = useRef<HTMLButtonElement>(null);
  // a tira só ganha a sombra da curva quando o papel passou da altura visível (antes disso o topo é o corte de verdade)
  const medirTira = useCallback((el: HTMLDivElement | null) => {
    if (!el) return;
    const ro = new ResizeObserver(() => { el.dataset.cheia = String(el.scrollHeight > el.clientHeight + 1); });
    ro.observe(el);
    if (el.firstElementChild) ro.observe(el.firstElementChild);
    return () => ro.disconnect();
  }, []);
  const fecharRef = useRef<HTMLButtonElement>(null);
  const vtAtual = useRef<VT | null>(null);
  const focoRef = useRef<HTMLDivElement>(null);
  // foco no "voltar" sem rolar o véu: no celular o papel abre pelo topo, não pelo fim
  const abriu = useRef(false);
  useEffect(() => {
    if (foco) { abriu.current = true; fecharRef.current?.focus({ preventScroll: true }); }
    else if (abriu.current) { abriu.current = false; verRef.current?.focus({ preventScroll: true }); }
  }, [foco]);

  const transicao = (f: () => void, voo: "abre" | "fecha") => {
    const d = document as Document & { startViewTransition?: (cb: () => void) => VT };
    if (!d.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) { f(); return; }
    const raiz = document.documentElement;
    raiz.dataset.voo = voo; // o CSS do voo muda conforme o sentido
    vtAtual.current?.skipTransition(); // uma transição por vez: a anterior termina na hora
    const vt = d.startViewTransition(() => flushSync(f));
    vtAtual.current = vt;
    // transição pulada/abortada rejeita estas promessas; não é erro da página
    vt.ready.catch(() => {}); vt.updateCallbackDone.catch(() => {});
    vt.finished.catch(() => {}).finally(() => { if (vtAtual.current === vt) vtAtual.current = null; if (raiz.dataset.voo === voo) delete raiz.dataset.voo; });
  };

  // novo ciclo: some o papel antigo, o número volta a STONE
  const destacar = useCallback(() => {
    setComp(null); setFoco(null); setRasgando(false);
    setNota3d(null); setIgnicao(false);
  }, []);

  const imprimir = useCallback((linhas: Linha[], fim: boolean) => {
    seq.current += 1;
    setToco(false); setFoco(null); setRasgando(false);
    setComp({ id: seq.current, linhas, fim });
  }, []);

  const rasgar = useCallback(() => {
    setRasgando(true); // tranco na fenda
    setTimeout(() => {
      transicao(() => {
        setComp((c) => { if (c) setFoco(c); return null; });
        setToco(true); setRasgando(false);
      }, "abre");
    }, 160);
  }, []);

  const fecharFoco = useCallback(() => {
    transicao(() => setFoco(null), "fecha"); // o foco volta para "Ver comprovante" no efeito abaixo, quando a máquina deixa de ser inert
  }, []);
  const abrirFoco = () => { if (ultimo.current) transicao(() => setFoco(ultimo.current), "abre"); };
  const ultimo = useRef<Comp | null>(null);
  useEffect(() => { if (foco) ultimo.current = foco; }, [foco]);
  useEffect(() => {
    if (!foco) return;
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") { fecharFoco(); return; }
      if (e.key !== "Tab" || !focoRef.current) return;
      // o Tab circula dentro do comprovante (links das referências + "voltar"); o resto da página está inert
      const alvos = [...focoRef.current.querySelectorAll<HTMLElement>("a[href], button")];
      if (!alvos.length) return;
      const i = alvos.indexOf(document.activeElement as HTMLElement);
      const prox = e.shiftKey ? (i <= 0 ? alvos.length - 1 : i - 1) : (i === -1 || i === alvos.length - 1 ? 0 : i + 1);
      e.preventDefault(); alvos[prox].focus();
    };
    addEventListener("keydown", esc);
    return () => removeEventListener("keydown", esc);
  }, [foco, fecharFoco]);

  const acrescentar = useCallback((novas: Linha[], fim = false) => {
    setComp((c) => (c ? { ...c, linhas: novas.length ? [...c.linhas, ...novas] : c.linhas, fim: fim || c.fim } : c));
  }, []);

  // foco volta para a tela com o cursor no fim do texto, pronto para continuar digitando
  const focar = () => requestAnimationFrame(() => {
    const el = campoRef.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  });

  /* ---------- avaliar ---------- */
  const mostrarExemplo = (ex: Exemplo, demo = false) => {
    if (comp) destacar();
    notaFinal.current = { nota: ex.avaliacao.nota, demo };
    setTela({ k: "imprimindo" });
    setTimeout(() => imprimir(linhasAvaliacao(ex.avaliacao, { titulo: ex.titulo, real: ex, demo }), true), comp ? 380 : 0);
  };

  const avaliarAgora = async () => {
    if (![rasc.titulo, rasc.legenda, rasc.roteiro].some((t) => t.trim())) {
      setTela({ k: "aviso", msg: "Escreva o título ou toque num exemplo:" });
      focar();
      return;
    }
    // rascunho de exemplo intacto: a avaliação já está gravada, não precisa do modelo
    const pronto = prontos.find((p) => igual(p, rasc));
    // sem a API não há modelo para ler um texto novo: nunca imprimir um post qualquer no lugar do rascunho
    if (!online && !pronto) {
      const volta = await apiOnline();
      setOnline(volta);
      if (!volta) {
        setTela({ k: "aviso", msg: "API local desligada: só os exemplos prontos e os posts reais funcionam." });
        return;
      }
    }
    if (comp) destacar();
    const ctl = new AbortController(); abort.current = ctl;
    setTela({ k: "aguarde", t0: performance.now(), fase: FASES[0], gravado: !!pronto });
    try {
      let av: Avaliacao;
      if (pronto) {
        // as fases passam rápido, só para mostrar o caminho que o rascunho faz
        for (const f of FASES) {
          setTela((t) => (t.k === "aguarde" ? { ...t, fase: f } : t));
          await espera(320, ctl.signal);
        }
        av = pronto.avaliacao;
      } else av = await avaliar(rasc, ctl.signal);
      notaFinal.current = { nota: av.nota };
      setTela({ k: "imprimindo" });
      imprimir(linhasAvaliacao(av, { titulo: rasc.titulo || rasc.legenda.slice(0, 60), duracao: rasc.duracao_s, pronto: !!pronto }), true);
    } catch (e) {
      if ((e as Error).name === "AbortError") { setTela({ k: "edita" }); return; }
      setTela({ k: "erro", msg: `${(e as Error).message}. Confira se o Ollama está aberto e toque em Tentar de novo.` });
    }
  };

  /* ---------- agente ---------- */
  const gerar = async () => {
    if (!pedido.trim()) { setTela({ k: "aviso", msg: "Escreva o pedido ou toque num exemplo:" }); return; }
    // exemplo com o texto intacto: toca a execução gravada do mesmo agente, sem esperar o modelo
    const preset = PRESETS.find((p) => p.pedido === pedido.trim());
    const grav = preset ? gravacoes[preset.chave] : undefined;
    if (!grav && !online) {
      const volta = await apiOnline();
      setOnline(volta);
      if (!volta) { setTela({ k: "aviso", msg: "API local desligada: só os exemplos gravados funcionam. Toque num:" }); return; }
    }
    if (comp) destacar();
    const ctl = new AbortController(); abort.current = ctl;
    const versoes: number[] = [];
    let melhor: Est | null = null;
    let refs: Est[] = [];
    setTela({ k: "aguarde", t0: performance.now(), fase: "entendendo o pedido", gravado: !!grav });
    setTimeout(() => imprimir([
      { k: "centro", t: "stone · agente", forte: true },
      { k: "centro", t: "PEDIDO DE CRIATIVO" },
      { k: "miudo", t: `${carimbo()} · via do cliente`, centro: true },
      ...(grav ? [{ k: "miudo", t: `Exemplo: execução gravada em ${grav.gravado_em.split(" ")[0]} com o mesmo agente (qwen3-vl:8b local).`, centro: true } as Linha] : []),
      { k: "sep" },
      { k: "texto", t: pedido.trim() },
      { k: "sep" },
    ], false), comp ? 380 : 0);

    const receber = (e: EtapaAgente) => {
      const st = e.estado as Est;
      if (e.no === "referencias") refs = st.referencias ?? [];
      if (e.no === "avaliar") { versoes.push(st.avaliacao?.nota ?? 0); if (st.melhor) melhor = st.melhor; }
      if (e.no === "responder") return;
      const { linhas, fase } = linhaEtapa(e, versoes);
      acrescentar(linhas);
      setTela((t) => (t.k === "aguarde" ? { ...t, fase } : t));
    };
    try {
      if (grav && preset) {
        const txt = await fetch(`/data/agente/${preset.chave}.sse`, { signal: ctl.signal }).then((r) => (r.ok ? r.text() : ""));
        const eventos = txt.replace(/\r\n/g, "\n").split("\n\n").filter((b) => b.startsWith("event: etapa")).map((b) => JSON.parse(b.slice(b.indexOf("data: ") + 6)) as EtapaAgente);
        if (!eventos.length) throw new Error("gravação do exemplo não encontrada");
        for (const ev of eventos) {
          await espera(ev.no === "gerar" || ev.no === "avaliar" ? 750 : 420, ctl.signal);
          receber(ev);
        }
      } else {
        await rodarAgente(pedido, receber, ctl.signal);
      }
      if (!melhor) throw new Error("o agente terminou sem um criativo");
      const m = melhor as Est;
      notaFinal.current = { nota: m.avaliacao.nota };
      setTela({ k: "imprimindo" });
      acrescentar(linhasCriativo(m, versoes, refs), true);
    } catch (e) {
      if ((e as Error).name === "AbortError") {
        acrescentar([{ k: "sep" }, { k: "centro", t: "CANCELADO PELO CLIENTE", forte: true }], true);
        setTela({ k: "edita" });
        return;
      }
      acrescentar([{ k: "sep" }, { k: "centro", t: "FALHA NA OPERAÇÃO", forte: true }, { k: "miudo", t: (e as Error).message, centro: true }], true);
      setTela({ k: "erro", msg: `${(e as Error).message}. Confira se o Ollama está aberto e toque em Tentar de novo.` });
    }
  };

  /* ---------- ações da tela touch ---------- */
  const ocupado = tela.k === "aguarde" || tela.k === "imprimindo";
  const enviar = () => {
    if (ocupado) return;
    if (modo === "agente") gerar(); else avaliarAgora();
  };
  const trocarModo = (m: Modo) => {
    if (ocupado) return;
    setModo(m); setTela({ k: "edita" }); focar();
  };
  const limpar = () => {
    if (modo === "agente") setPedido(""); else setRasc((r) => ({ ...r, titulo: "", legenda: "", roteiro: "" }));
    setTela({ k: "edita" }); focar();
  };
  const exemplosEscolhidos = exemplos.length ? [0, Math.floor(exemplos.length / 2), exemplos.length - 1].map((i) => exemplos[i]) : [];
  const exemplo = (i: number) => {
    if (ocupado) return;
    const ex = exemplosEscolhidos[i];
    if (ex) { setRasc((r) => ({ ...r, titulo: semTags(ex.titulo), legenda: "", roteiro: "" })); mostrarExemplo(ex); }
  };
  // rascunho pronto: só preenche a tela (dá para mostrar o texto antes); Imprimir nota usa a avaliação gravada
  const usarPronto = (p: Pronto) => {
    if (ocupado) return;
    setRasc({ titulo: p.titulo, legenda: p.legenda, roteiro: p.roteiro, duracao_s: p.duracao_s });
    setTela({ k: "edita" });
  };

  // saiu da tela da nota (Editar, Voltar, novo pedido): o fundo volta para STONE; nota só aparece enquanto ela está na tela
  useEffect(() => {
    if (tela.k === "nota" || tela.k === "imprimindo") return;
    setNota3d(null); setIgnicao(false);
  }, [tela.k]);
  const aoTotal = useCallback((n: number) => {
    setNota3d(n); setIgnicao(true);
    setTimeout(() => setIgnicao(false), innerWidth < 980 ? 3600 : 2600);
  }, []);
  const aoFim = useCallback(() => {
    const f = notaFinal.current;
    setTela((t) => (t.k === "imprimindo" && f ? { k: "nota", nota: f.nota, demo: f.demo } : t));
    setTimeout(rasgar, 120); // terminou de imprimir: rasga e entrega na hora
  }, [rasgar]);

  const prontoParaEntrar = modo === "agente" ? !!pedido.trim() : !!(rasc.titulo.trim() || rasc.legenda.trim() || rasc.roteiro.trim());

  /* ---------- tela da máquina: um app touch ---------- */
  const mudarCampo = (c: Campo, v: string) => {
    setRasc((r) => ({ ...r, [c]: v }));
    if (tela.k !== "edita") setTela({ k: "edita" });
  };
  const mudarPedido = (v: string) => {
    setPedido(v);
    if (tela.k !== "edita") setTela({ k: "edita" });
  };
  const teclado = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const linhaUnica = e.currentTarget.dataset.linha === "1";
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey || (linhaUnica && !e.shiftKey))) { e.preventDefault(); enviar(); }
  };
  const seg = tela.k === "aguarde" ? Math.max(0, (agora - tela.t0) / 1000) : 0;
  const estimado = tela.k === "aguarde" && tela.gravado ? (modo === "agente" ? 6 : 1.3) : modo === "agente" ? 180 : 28;
  const LINHAS_CAMPO: Record<Campo, number> = { titulo: 1, legenda: 2, roteiro: 2 }; // título de post é uma linha

  const conteudoTela = (
    <div className={s.app}>
      <div className={s.topo}>
      <div className={s.status}>
        <span>{hora}</span>
        <span className={`${s.sinal} ${online ? s.on : ""}`}><i /><i /><i /> {online ? "ao vivo" : "demo"}</span>
      </div>

      <div className={s.abas} role="tablist" aria-label="O que fazer" data-modo={modo}>
        {(["avaliar", "agente"] as Modo[]).map((m) => (
          <button key={m} type="button" role="tab" aria-selected={modo === m} className={modo === m ? s.abaOn : ""}
            onClick={() => trocarModo(m)} disabled={ocupado && modo !== m}>
            {m === "avaliar" ? "Avaliar post" : "Pedir criativo"}
          </button>
        ))}
      </div>
      </div>

      {(tela.k === "edita" || tela.k === "aviso") && (
        <div className={s.corpoApp}>
          {modo === "avaliar" ? (
            <>
              {CAMPOS.map((c, i) => (
                <label key={c} className={s.campo}>
                  <span className={s.rot}>{NOME_CAMPO[c]}</span>
                  <textarea
                    ref={i === 0 ? campoRef : undefined}
                    rows={LINHAS_CAMPO[c]}
                    data-linha={c === "titulo" ? "1" : undefined}
                    value={rasc[c]}
                    onChange={(e) => mudarCampo(c, e.target.value)}
                    onKeyDown={teclado}
                    placeholder={DICA[c]}
                    autoFocus={i === 0}
                    spellCheck={false}
                  />
                </label>
              ))}
              <div className={s.linhaDur}>
                <span className={s.rot}>duração</span>
                <div className={s.passo}>
                  <button type="button" aria-label="Menos 5 segundos" onClick={() => setRasc((r) => ({ ...r, duracao_s: Math.max(10, r.duracao_s - 5) }))}><Icone d="M5 12h14" /></button>
                  <CampoDuracao valor={rasc.duracao_s} mudar={(v) => setRasc((r) => ({ ...r, duracao_s: v }))} />
                  <button type="button" aria-label="Mais 5 segundos" onClick={() => setRasc((r) => ({ ...r, duracao_s: Math.min(180, r.duracao_s + 5) }))}><Icone d="M5 12h14M12 5v14" /></button>
                </div>
              </div>
              {tela.k === "aviso" && <span className={s.aviso} role="status">{tela.msg}</span>}
              {prontos.length > 0 && (
                <div className={s.exemplos}>
                  <span className={s.rot}>rascunhos prontos</span>
                  <div className={s.pilulas}>
                    {prontos.map((p) => (
                      <button key={p.chave} type="button" aria-pressed={igual(p, rasc)} onClick={() => usarPronto(p)} title={p.titulo}>
                        <i><Icone d="M5 12.5l4.5 4.5L19 7.5" /></i><span>{NOME_PRONTO[p.chave] ?? p.chave}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className={s.exemplos}>
                <span className={s.rot}>ou teste um post real</span>
                <div>
                  {exemplosEscolhidos.map((ex, i) => (
                    <button key={ex.post_id} type="button" onClick={() => exemplo(i)} title={frase(semTags(ex.titulo)) || undefined}>
                      <i><Icone d="M8 5.5v13l10.5-6.5z" /></i><span>{curto(frase(semTags(ex.titulo))) || "post real"}</span>
                    </button>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <>
              <label className={`${s.campo} ${s.campoGrande}`}>
                <span className={s.rot}>o que você precisa</span>
                <textarea
                  ref={campoRef}
                  rows={5}
                  value={pedido}
                  onChange={(e) => mudarPedido(e.target.value)}
                  onKeyDown={teclado}
                  placeholder="Post do Impulso para…"
                  autoFocus
                  spellCheck={false}
                />
              </label>
              <div className={s.exemplos}>
                {tela.k === "aviso" ? <span className={s.aviso} role="status">{tela.msg}</span> : <span className={s.rot}>exemplos gravados · saem na hora</span>}
                <div className={s.pilulas}>
                  {PRESETS.filter((p) => gravacoes[p.chave]).map((p) => (
                    <button key={p.nome} type="button" aria-pressed={pedido === p.pedido} onClick={() => mudarPedido(p.pedido)}><i><Icone d="M12 4v16M4 12h16" /></i><span>{p.nome}</span></button>
                  ))}
                </div>
              </div>
            </>
          )}
          <div className={s.acoes}>
            <button type="button" className={s.limpar} onClick={limpar}>Limpar</button>
            <button type="button" className={s.primario} onClick={enviar} data-pronto={prontoParaEntrar}>
              {modo === "agente" ? "Gerar criativo" : "Imprimir nota"}
            </button>
          </div>
        </div>
      )}

      {tela.k === "aguarde" && (
        <div className={`${s.corpoApp} ${s.centro}`} role="status" aria-live="polite">
          <p className={s.grande}>Aguarde<span className={s.caret} aria-hidden /></p>
          <p className={s.cronometro}>{seg.toFixed(1).replace(".", ",")}<small> s</small></p>
          <p key={tela.fase} className={`${s.fase} ${s.troca}`}>{tela.fase}</p>
          <div className={s.barra} aria-hidden><i style={{ width: `${Math.min(1, seg / estimado) * 100}%` }} /></div>
          <p className={s.dica}>{tela.gravado ? "exemplo gravado: sai em segundos" : modo === "agente" ? "cerca de 1 min por versão" : "cerca de 25 s"}</p>
          <div className={s.acoes}><button type="button" className={s.cancelar} onClick={() => abort.current?.abort()}>Cancelar</button></div>
        </div>
      )}

      {tela.k === "imprimindo" && (
        <div className={`${s.corpoApp} ${s.centro}`} role="status">
          <p className={s.grande}>Imprimindo<span className={s.caret} aria-hidden /></p>
          <p className={s.fase}>o comprovante está saindo pela impressora</p>
        </div>
      )}

      {tela.k === "nota" && (
        /* remonta ao fechar o comprovante: o flash e a contagem acontecem quando a máquina volta à vista */
        <div key={foco ? "nota-atras" : "nota"} className={`${s.corpoApp} ${s.centro} ${s.telaNota}`} role="status" aria-live="polite">
          <span className={s.sr}>Nota {tela.nota} de 100</span>
          <p className={s.nota} aria-hidden><Contador n={tela.nota} /><small>/100</small></p>
          <div className={s.medidor} aria-hidden><i style={{ width: `${tela.nota}%` }} /></div>
          <span className={s.selo}>supera {tela.nota}% da base</span>
          <p className={s.notaDe}>{tela.demo ? "de aderência · post real" : "de aderência ao que gera conversa"}</p>
          <button type="button" ref={verRef} className={s.retire} onClick={abrirFoco}
            style={{ viewTransitionName: foco || comp ? undefined : "extrato" }}>
            <Icone d="M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6" /> Ver comprovante
          </button>
          <div className={s.acoes}>
            <button type="button" className={s.limpar} onClick={() => { setTela({ k: "edita" }); focar(); }}>Editar</button>
            <button type="button" className={s.primario} data-pronto onClick={enviar}>{modo === "agente" ? "Gerar de novo" : "Avaliar de novo"}</button>
          </div>
        </div>
      )}

      {tela.k === "erro" && (
        <div className={`${s.corpoApp} ${s.centro}`} role="alert">
          <p className={`${s.grande} ${s.falha}`}>Falhou</p>
          <p className={s.fase}>{tela.msg}</p>
          <div className={s.acoes}>
            <button type="button" className={s.limpar} onClick={() => { setTela({ k: "edita" }); focar(); }}>Voltar</button>
            <button type="button" className={s.primario} data-pronto onClick={enviar}>Tentar de novo</button>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <main className={s.palco}>
      <Fundo focoX={focoX} />
      <div className={`${s.glifo} ${nota3d != null ? s.glifoAceso : ""} ${ignicao ? s.glifoIgnicao : ""}`} aria-hidden>
        <Glifo3D key={nota3d != null ? "nota" : `ocioso${seq.current}`} texto={nota3d != null ? String(nota3d) : "STONE"} logo={nota3d != null ? undefined : "/stone-logo.png"} rotulo="" formato="1:1" densidade={nota3d != null ? 96 : 120} zoom={nota3d != null ? 0.95 : 0.9} balanco={nota3d != null ? 0.2 : 0.3} intro={largo && nota3d != null} pausado={!!foco} />
      </div>
      <div className={s.grao} aria-hidden />

      {/* logo oficial do Inteli (inteli.edu.br), versão negativa: o azul-escuro #2E2640 virou branco para o fundo escuro; o vermelho fica */}
      <img className={`${s.marca} ${comp ? s.marcaRecua : ""}`} src="/Logo-Inteli-SVG-negativo.svg" alt="Inteli" width={75} height={41} />

      <div className={`${s.mundo} ${foco ? s.mundoRecua : ""}`} inert={!!foco} style={{ left: `${focoX * 100}%` }}>
        <div className={s.escala} style={{ transform: `translateX(-50%) scale(${kMaq})` }}>
          <Maquina
            escala={kMaq}
            ativa={tela.k === "aguarde" || tela.k === "imprimindo"}
            tela={conteudoTela}
            acima={
              <>
                {toco && !comp && <Toco />}
                {comp && (
                  /* a tira: só os últimos centímetros de papel ficam à vista, saindo da fenda */
                  <div key={comp.id} ref={medirTira} className={`${s.tira} ${rasgando ? s.rasgando : ""}`} style={{ viewTransitionName: "extrato" }}>
                    <Recibo linhas={comp.linhas} fim={comp.fim} onTotal={aoTotal} onFim={aoFim} />
                  </div>
                )}
              </>
            }
          />
        </div>
      </div>

      {foco && (
        <div className={s.foco} ref={focoRef} onClick={fecharFoco}>
          <div role="dialog" aria-modal="true" aria-label="Comprovante" onClick={(e) => e.stopPropagation()}
            className={s.focoPapel} style={{ viewTransitionName: "extrato" }}>
            <ReciboAberto linhas={foco.linhas} />
          </div>
          <button type="button" ref={fecharRef} className={s.fechar} onClick={fecharFoco} aria-label="Fechar comprovante">
            <Icone d="M6 6l12 12M18 6L6 18" /> voltar à máquina <kbd>esc</kbd>
          </button>
        </div>
      )}

      <p className={s.credito} inert={!!foco}>
        glifos <a href="https://github.com/winchxyz/afterglyph" target="_blank" rel="noreferrer">afterglyph</a> (MIT) · rubrica Qwen3-VL local<br />Case Stone × Inteli
      </p>
    </main>
  );
}

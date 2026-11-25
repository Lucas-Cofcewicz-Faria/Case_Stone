export type Padrao = { atributo: string; visao: string; lift: number; posts_top: number };
export type Sugestao = { campo: string; de: string | boolean; para: string | boolean; ganho: number; exemplos: { titulo: string; url: string }[] };
export type Referencia = { post_id: string; titulo: string; url: string; perfil: string; conversa: number; similaridade: number };
export type Lancamento = { atributo: string; peso: number; lift: number | null };

export type Avaliacao = {
  nota: number; pontos: number;
  padroes_cumpridos: Padrao[]; antipadroes: Padrao[];
  sugestoes: Sugestao[]; referencias: Referencia[];
  lancamentos?: Lancamento[]; aviso: string;
  sem_conteudo?: boolean; motivo?: string;
  rubrica_do_rascunho?: Record<string, string | number | boolean>;
};

export type Exemplo = {
  post_id: string; titulo: string; url: string; perfil: string; thumb_url: string;
  conversa: number; views: number; comentarios: number; avaliacao: Avaliacao;
};

export type Resumo = {
  posts: number; rankeaveis: number; top10: number; perfis: number;
  auc: { visao: string; auc_cv: number }[];
  quintis: { quintil: number; conversa_mediana: number; pct_top10: number }[];
  padroes: { top10: { fazer: LiftLinha[]; evitar: LiftLinha[] }; top_perfil: { fazer: LiftLinha[]; evitar: LiftLinha[] } };
};
export type LiftLinha = { atributo: string; lift: number; posts_top: number; z: number; tipo: string };

export const API = process.env.NEXT_PUBLIC_API ?? "http://127.0.0.1:8765";

export const NOMES_GRUPO: Record<string, string> = {
  alimentacao: "alimentação", beleza: "beleza", varejo_e_vendas: "varejo e vendas",
  mei_e_contabilidade: "MEI e contabilidade", pagamentos: "pagamentos", gestao_e_financas: "gestão e finanças",
  artesanato_e_festas: "artesanato e festas", servicos_e_outros: "serviços e outros", outros: "outros",
};

const ROTULOS: Record<string, string> = {
  duracao_faixa: "duração", tema_principal: "tema", tipo_hook: "gancho", formato_video: "formato", tom: "tom",
  tipo_cta: "chamada", pilar_impulso: "pilar", legenda_tamanho: "legenda", tipo_post: "tipo",
  forca_hook_0a10: "força do gancho", clareza_mensagem_0a10: "clareza", tem_rosto: "mostra rosto",
  criador_e_empreendedor_real: "empreendedor real", prova_social: "prova social",
  usa_linguagem_regional: "linguagem regional", tem_cta: "pede uma ação", oferta_ou_beneficio_explicito: "oferta explícita",
};
const VALORES: Record<string, string> = {
  "60_180s": "60–180 s", "30_60s": "30–60 s", "15_30s": "15–30 s", ate_15s: "até 15 s", mais_180s: "mais de 3 min",
  burocracia_mei: "MEI e impostos", ferramentas_maquininha: "maquininha", historia_de_empreendedor: "história real",
  humor_esquete: "esquete de humor", lista_dicas: "lista de dicas", talking_head: "pessoa falando",
  noticia_explicacao: "notícia explicada", antes_depois: "antes e depois", sem_gancho: "sem gancho",
  link_na_bio: "link na bio", educacao_financeira: "educação financeira", gestao_e_vendas: "gestão e vendas",
  historias_reais: "histórias reais", inspiracional: "inspiracional", humoristico: "humor", alta: "alta",
  media: "média", baixa: "baixa",
};

export function rotulo(atributo: string): string {
  const [campo, valor] = atributo.split("=");
  const c = ROTULOS[campo] ?? campo.replaceAll("_", " ");
  if (valor === undefined) return c;
  return `${c}: ${VALORES[valor] ?? valor.replaceAll("_", " ")}`;
}

export const carregar = <T,>(nome: string): Promise<T> => fetch(`/data/${nome}.json`).then((r) => r.json());

export async function apiOnline(): Promise<boolean> {
  try {
    const r = await fetch(`${API}/api/saude`, { signal: AbortSignal.timeout(1500) });
    return r.ok;
  } catch {
    return false;
  }
}

export async function avaliar(rascunho: { titulo: string; legenda: string; roteiro: string; duracao_s: number | null }, sinal?: AbortSignal): Promise<Avaliacao> {
  const r = await fetch(`${API}/api/avaliar`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(rascunho), signal: sinal });
  if (!r.ok) throw new Error((await r.json()).erro ?? "falha na avaliação");
  return r.json();
}

export async function avaliarPost(id: string): Promise<Avaliacao> {
  const r = await fetch(`${API}/api/post?id=${encodeURIComponent(id)}`);
  if (!r.ok) throw new Error("post não encontrado");
  return r.json();
}

export type EtapaAgente = { no: string; estado: Record<string, unknown> };

export async function rodarAgente(pedido: string, onEtapa: (e: EtapaAgente) => void, sinal?: AbortSignal) {
  const r = await fetch(`${API}/api/agente`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pedido }), signal: sinal });
  if (!r.body) throw new Error("sem resposta do agente");
  const leitor = r.body.getReader(), dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await leitor.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const bloco = buf.slice(0, i); buf = buf.slice(i + 2);
      const ev = /event: (\w+)/.exec(bloco)?.[1];
      const data = /data: ([\s\S]*)/.exec(bloco)?.[1];
      if (ev === "etapa" && data) onEtapa(JSON.parse(data));
      if (ev === "erro" && data) throw new Error(JSON.parse(data).erro);
    }
  }
}

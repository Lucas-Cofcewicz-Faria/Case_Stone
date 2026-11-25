"""API local para o front-end (só biblioteca padrão, sem dependências novas).

  GET  /api/saude                      → status e tamanho da base
  GET  /api/padroes?segmento=...       → padrões e antipadrões
  GET  /api/referencias?segmento=...&n=5&texto=...
  GET  /api/post?id=...                → avaliação de um post da base
  GET  /api/exemplos?n=6               → posts do top 10% já avaliados (para o modo demo, sem GPU)
  POST /api/avaliar   {titulo, legenda, roteiro, duracao_s}
  POST /api/agente    {pedido}         → stream (text/event-stream) com cada etapa do grafo

Uso:
  python -m stone.api            # http://127.0.0.1:8765
"""
from __future__ import annotations

import json
import math
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .agente import ferramentas as F

PORTA = 8765


def _limpo(o):
    """JSON não aceita NaN/inf nem sets."""
    if isinstance(o, float):
        return None if math.isnan(o) or math.isinf(o) else o
    if isinstance(o, dict):
        return {str(k): _limpo(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_limpo(v) for v in o]
    if hasattr(o, "item"):  # numpy
        return _limpo(o.item())
    return o


def exemplos(n: int = 6) -> list[dict]:
    df = F._base()
    top = df[df["top10"]].sort_values("conversa", ascending=False).drop_duplicates("handle").head(n)
    out = []
    for r in top.to_dict("records"):
        av = F.avaliar(F._modelo(), r)
        av["lancamentos"] = _lancamentos(av, r)
        out.append({"post_id": r["post_id"], "titulo": r["titulo"], "url": r["url"], "perfil": r["nome"],
                    "thumb_url": r.get("thumb_url"), "conversa": r["conversa"], "views": r["views"],
                    "comentarios": r["comentarios"], "avaliacao": av})
    return out


def _lancamentos(av: dict, rub: dict | None = None) -> list[dict]:
    """Extrato: cada atributo presente com o peso que soma na nota (as duas visões)."""
    from .patterns import atributos
    from .evaluator import VISOES
    m = F._modelo()
    attrs = atributos(rub) if rub else set()
    linhas = []
    for a in sorted(attrs):
        peso = sum(float(m.pesos[v]["peso"].get(a, 0.0)) for v in VISOES)
        lift = float(m.pesos["top10"]["lift"].get(a, float("nan"))) if a in m.pesos["top10"].index else None
        linhas.append({"atributo": a, "peso": round(peso, 3), "lift": lift})
    return sorted(linhas, key=lambda x: -abs(x["peso"]))


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _json(self, dados, status=200):
        corpo = json.dumps(_limpo(dados), ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(corpo)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/saude":
                df = F._base()
                return self._json({"ok": True, "posts": len(df), "rankeaveis": int(df["rankeavel"].sum()),
                                   "top10": int(df["top10"].sum()), "perfis": int(df["handle"].nunique()),
                                   "segmentos": list(F.SEGMENTOS)})
            if u.path == "/api/padroes":
                return self._json(F.padroes(q.get("segmento") or None))
            if u.path == "/api/referencias":
                return self._json(F.referencias(q.get("segmento") or None, int(q.get("n", 5)), q.get("texto")))
            if u.path == "/api/post":
                df = F._base()
                linha = df[df["post_id"] == q["id"]]
                if linha.empty:
                    return self._json({"erro": "post não encontrado"}, 404)
                rub = linha.iloc[0].to_dict()
                av = F.avaliar(F._modelo(), rub)
                av["lancamentos"] = _lancamentos(av, rub)
                return self._json(av)
            if u.path == "/api/exemplos":
                return self._json(exemplos(int(q.get("n", 6))))
            return self._json({"erro": "rota desconhecida"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"erro": str(e)}, 500)

    def _corpo(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        u = urlparse(self.path)
        try:
            b = self._corpo()
            if u.path == "/api/avaliar":
                av = F.avaliar_rascunho(b.get("titulo", ""), b.get("legenda", ""), b.get("roteiro", ""),
                                        b.get("duracao_s"))
                rub = dict(av["rubrica_do_rascunho"])
                av["lancamentos"] = _lancamentos(av, rub)
                return self._json(av)
            if u.path == "/api/agente":
                return self._agente(b.get("pedido", ""))
            return self._json({"erro": "rota desconhecida"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"erro": str(e)}, 500)

    def _agente(self, pedido: str):
        from .agente.grafo import construir
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self._cors()
        self.end_headers()

        def enviar(evento: str, dados):
            self.wfile.write(f"event: {evento}\ndata: {json.dumps(_limpo(dados), ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()

        try:
            for passo in construir().stream({"pedido": pedido}, stream_mode="updates"):
                for no, estado in passo.items():
                    enviar("etapa", {"no": no, "estado": estado})
            enviar("fim", {})
        except Exception as e:
            traceback.print_exc()
            enviar("erro", {"erro": str(e)})


def main() -> None:
    F._modelo()  # aquece: monta a base e os pesos antes da primeira chamada
    srv = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    print(f"API em http://127.0.0.1:{PORTA}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()

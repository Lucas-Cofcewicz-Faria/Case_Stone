"""Juiz do deepeval que roda pelo Claude Code (`claude -p`), na assinatura do usuário, sem chave de API.

Cada chamada sai isolada: sem ferramentas, sem MCP, sem settings/plugins/hooks do usuário, sem salvar sessão,
com um system prompt curto (~1,3 mil tokens de overhead por chamada). Saída presa a JSON Schema quando
a métrica pede um schema. O uso de cada chamada fica em tests/evals/juiz_uso.jsonl.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from deepeval.models import DeepEvalBaseLLM

USO = Path(__file__).parent / "juiz_uso.jsonl"
SISTEMA = ("Você é um avaliador rigoroso de criativos de vídeo curto para pequenos empreendedores brasileiros. "
           "Siga exatamente as instruções e o formato pedido. Não use ferramentas.")
_LIMITE = asyncio.Semaphore(int(os.getenv("JUIZ_CONCORRENCIA", "4")))


class JuizClaudeCode(DeepEvalBaseLLM):
    def __init__(self, modelo: str = "sonnet", timeout: int = 300):
        self.modelo, self.timeout = modelo, timeout
        self.exe = shutil.which("claude") or "claude"
        super().__init__(modelo)

    def load_model(self):
        return self

    def get_model_name(self) -> str:
        return f"claude-code:{self.modelo}"

    def _cmd(self, schema) -> list[str]:
        cmd = [self.exe, "-p", "--model", self.modelo, "--output-format", "json", "--system-prompt", SISTEMA,
               "--tools", "", "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands",
               "--no-session-persistence"]
        if schema is not None:
            cmd += ["--json-schema", json.dumps(schema.model_json_schema(), ensure_ascii=False)]
        return cmd

    @staticmethod
    def _env() -> dict:
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)   # força a assinatura (login do Claude Code), nunca a API paga
        return env

    def _ler(self, bruto: bytes, schema, t0: float):
        d = json.loads(bruto.decode("utf-8"))
        if d.get("is_error"):
            raise RuntimeError(f"claude -p falhou: {d.get('subtype')} {str(d.get('result'))[:300]}")
        u = d.get("usage", {})
        with USO.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%H:%M:%S"), "s": round(time.time() - t0, 1),
                                "in": u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                                + u.get("cache_read_input_tokens", 0),
                                "out": u.get("output_tokens", 0), "usd_equiv": d.get("total_cost_usd")}) + "\n")
        if schema is not None:
            dados = d.get("structured_output")
            if dados is None:
                dados = json.loads(d["result"])
            return schema.model_validate(dados)
        return d["result"]

    def generate(self, prompt: str, schema=None, **_):
        t0 = time.time()
        r = subprocess.run(self._cmd(schema), input=prompt.encode("utf-8"), capture_output=True,
                           timeout=self.timeout, env=self._env())
        if r.returncode != 0:
            raise RuntimeError(f"claude -p saiu com {r.returncode}: {r.stderr.decode('utf-8', 'replace')[:300]}")
        return self._ler(r.stdout, schema, t0)

    async def a_generate(self, prompt: str, schema=None, **_):
        async with _LIMITE:
            t0 = time.time()
            p = await asyncio.create_subprocess_exec(*self._cmd(schema), stdin=asyncio.subprocess.PIPE,
                                                     stdout=asyncio.subprocess.PIPE,
                                                     stderr=asyncio.subprocess.PIPE, env=self._env())
            out, err = await asyncio.wait_for(p.communicate(prompt.encode("utf-8")), self.timeout)
            if p.returncode != 0:
                raise RuntimeError(f"claude -p saiu com {p.returncode}: {err.decode('utf-8', 'replace')[:300]}")
            return self._ler(out, schema, t0)

    def supports_structured_outputs(self) -> bool:
        return True

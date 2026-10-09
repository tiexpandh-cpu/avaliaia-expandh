"""Cliente Gemini com controle de taxa aplicado a CADA requisição."""
import base64
import json
import os
import re
import time
from pathlib import Path

from google import genai

# Intervalo mínimo entre requisições (segundos). 6s => no máximo 10 req/min,
# abaixo do limite de 15 RPM dos modelos Flash Lite no plano gratuito.
INTERVALO_MINIMO = float(os.environ.get("INTERVALO_MINIMO_S", "6"))
MAX_TENTATIVAS = 4


class ClienteLLM:
    def __init__(self):
        chave = os.environ.get("GEMINI_API_KEY")
        if not chave:
            try:
                import streamlit as st
                chave = st.secrets.get("GEMINI_API_KEY")
            except Exception:
                pass
        if not chave:
            raise RuntimeError("GEMINI_API_KEY não encontrada no .env ou nas Secrets do Streamlit")
        self.client = genai.Client(api_key=chave)
        self._ultima_chamada = 0.0
        self.requisicoes = 0

    def _aguardar_vez(self):
        decorrido = time.monotonic() - self._ultima_chamada
        if decorrido < INTERVALO_MINIMO:
            time.sleep(INTERVALO_MINIMO - decorrido)

    def gerar(self, modelo: str, entrada, schema: dict | None = None) -> str:
        """Faz UMA chamada ao modelo (com retry em 429/503) e devolve o texto."""
        kwargs = {"model": modelo, "input": entrada}
        if schema:
            kwargs["response_format"] = {
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            }

        for tentativa in range(1, MAX_TENTATIVAS + 1):
            self._aguardar_vez()
            self._ultima_chamada = time.monotonic()
            self.requisicoes += 1
            try:
                resposta = self.client.interactions.create(**kwargs)
                return resposta.output_text or ""
            except Exception as e:  # noqa: BLE001
                codigo = getattr(e, "code", None)
                msg = str(e)
                if codigo not in (429, 503) or tentativa == MAX_TENTATIVAS:
                    raise
                if codigo == 429 and "PerDay" in msg:
                    raise RuntimeError(
                        f"Cota DIÁRIA do modelo {modelo} esgotada. "
                        "Troque o modelo no .env (MODELO_EXTRACAO / MODELO_TEXTO) ou aguarde o reset."
                    ) from e
                m = re.search(r"retry in ([\d.]+)s", msg)
                espera = float(m.group(1)) + 1 if m else 20 * tentativa
                print(f"   [API {codigo}] aguardando {espera:.0f}s antes de tentar de novo "
                      f"(tentativa {tentativa}/{MAX_TENTATIVAS})...")
                time.sleep(espera)
        raise RuntimeError("Falha inesperada no retry")

    def gerar_json(self, modelo: str, entrada, schema: dict) -> dict:
        return json.loads(self.gerar(modelo, entrada, schema))


def documento_pdf(caminho: Path) -> dict:
    """Monta o bloco de entrada de um PDF (inline, base64)."""
    return {
        "type": "document",
        "data": base64.b64encode(caminho.read_bytes()).decode("utf-8"),
        "mime_type": "application/pdf",
    }

"""
Pipeline de avaliação imobiliária com 5 etapas fixas.

Etapas com IA (1 requisição cada):
  1. property_intake  -> lê o PDF da matrícula e devolve JSON estruturado
  5. auditor_report   -> revisa os números e redige o laudo em Markdown

Etapas determinísticas (Python, 0 requisições):
  2. market_intelligence -> geocodificação (OSM) + anúncios reais do ZAP Imóveis (venda e aluguel)
  3. sales_valuation     -> mediana de R$/m² (ou regressão) dos comparáveis, com fator de oferta
  4. rental_valuation    -> mediana de R$/m² dos aluguéis comparáveis (ou rentabilidade) + Selic

Os cálculos ficam em Python de propósito: o modelo não inventa números.
"""
import json
import os
import statistics
import unicodedata
from datetime import datetime
from pathlib import Path

import portais
import tools
from llm import ClienteLLM, documento_pdf

MODELO_EXTRACAO = os.environ.get("MODELO_EXTRACAO", "gemini-3.1-flash-lite")
MODELO_TEXTO = os.environ.get("MODELO_TEXTO", "gemini-3.1-flash-lite")

# Premissas ajustáveis via .env
FATOR_OFERTA = float(os.environ.get("FATOR_OFERTA", "0.90"))  # anúncio -> preço de fechamento
RENTABILIDADE_ALUGUEL_AA = float(os.environ.get("RENTABILIDADE_ALUGUEL_AA", "5.5"))  # usado só sem amostras de aluguel
MAX_COMPARAVEIS_VENDA = 12
MAX_COMPARAVEIS_ALUGUEL = 8
MIN_AMOSTRAS = 3

SCHEMA_MATRICULA = {
    "type": "object",
    "properties": {
        "numero_matricula": {"type": "string"},
        "cartorio": {"type": "string"},
        "tipo_imovel": {"type": "string", "description": "apartamento, casa, terreno, sala comercial etc."},
        "endereco": {"type": "string", "description": "logradouro e número, sem bairro/cidade"},
        "complemento": {"type": "string", "description": "unidade, bloco, andar"},
        "nome_condominio": {"type": "string", "description": "nome do condomínio/edifício, se houver"},
        "bairro": {"type": "string", "description": "bairro ou loteamento oficial (NÃO o nome do condomínio)"},
        "cidade": {"type": "string"},
        "uf": {"type": "string", "description": "sigla com 2 letras"},
        "area_privativa_m2": {"type": "number", "description": "0 se não constar"},
        "area_total_m2": {"type": "number", "description": "0 se não constar"},
        "area_terreno_m2": {"type": "number", "description": "0 se não constar"},
        "quartos": {"type": "integer", "description": "0 se não constar"},
        "vagas": {"type": "integer", "description": "0 se não constar"},
        "proprietarios_atuais": {"type": "array", "items": {"type": "string"}},
        "onus_e_gravames": {
            "type": "array",
            "items": {"type": "string"},
            "description": "hipotecas, alienação fiduciária, penhoras, usufruto etc. ainda vigentes",
        },
        "observacoes": {"type": "string", "description": "trechos ilegíveis ou dúvidas na leitura"},
    },
    "required": [
        "numero_matricula", "tipo_imovel", "endereco", "nome_condominio", "bairro", "cidade", "uf",
        "area_privativa_m2", "area_total_m2", "area_terreno_m2", "quartos", "vagas",
        "proprietarios_atuais", "onus_e_gravames", "observacoes",
    ],
}


def _norm(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode()
    return " ".join(txt.lower().split())


def _area_imovel(imovel: dict) -> float:
    return imovel.get("area_privativa_m2") or imovel.get("area_total_m2") or imovel.get("area_terreno_m2") or 0


def _remover_outliers(amostras: list[dict]) -> list[dict]:
    """Remove amostras com R$/m² fora de 1,5 x IQR (só com 5+ amostras)."""
    if len(amostras) < 5:
        return amostras
    q1, _, q3 = statistics.quantiles([a["preco"] / a["area"] for a in amostras], n=4)
    lim_inf, lim_sup = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    return [a for a in amostras if lim_inf <= a["preco"] / a["area"] <= lim_sup]


def _selecionar_comparaveis(anuncios, imovel, lat, lon, limite) -> list[dict]:
    """Filtra por área semelhante e ordena por: mesmo bairro, distância e diferença de área."""
    area = _area_imovel(imovel)
    bairro = _norm(imovel.get("bairro"))
    for tolerancia in (0.4, 0.6, 1.0, 1.5, 2.0):
        candidatos = [a for a in anuncios if abs(a["area"] - area) <= area * tolerancia]
        if len(candidatos) >= MIN_AMOSTRAS:
            break
    if len(candidatos) < MIN_AMOSTRAS:
        candidatos = list(anuncios)
    for a in candidatos:
        a["distancia_km"] = portais.distancia_km(lat, lon, a["lat"], a["lon"])
        a["mesmo_bairro"] = bool(bairro) and _norm(a["bairro"]) == bairro
    candidatos.sort(key=lambda a: (
        not a["mesmo_bairro"],
        a["distancia_km"] if a["distancia_km"] is not None else 999,
        abs(a["area"] - area),
    ))
    return _remover_outliers(candidatos[:limite])


def _geocodificar(imovel: dict) -> dict:
    partes = [imovel.get("cidade"), imovel.get("uf"), "Brasil"]
    tentativas = [
        [imovel.get("endereco")] + partes,
        [imovel.get("endereco").split(",")[0] if imovel.get("endereco") else None] + partes,
        [imovel.get("bairro")] + partes,
        partes,
    ]
    for t in tentativas:
        consulta = ", ".join(p for p in t if p)
        geo = tools.geocode_osm_tool(consulta)
        if "erro" not in geo:
            geo["precisao"] = "endereço" if t is tentativas[0] or t is tentativas[1] else (
                "bairro" if t is tentativas[2] else "cidade")
            return geo
    return {"erro": "Endereço não encontrado"}


def etapa1_property_intake(llm: ClienteLLM, pdf: Path) -> dict:
    print(f"[1/5] property_intake: lendo a matrícula com {MODELO_EXTRACAO}...")
    prompt = (
        "Você é um analista de registro de imóveis. Leia a matrícula em anexo (pode ser escaneada) "
        "e extraia os dados do imóvel. Considere as averbações e registros posteriores: "
        "proprietários e ônus devem refletir a situação ATUAL (ignore ônus cancelados). "
        "Não invente valores: use 0 ou string vazia quando o dado não constar."
    )
    return llm.gerar_json(MODELO_EXTRACAO, [{"type": "text", "text": prompt}, documento_pdf(pdf)], SCHEMA_MATRICULA)


def etapa2_market_intelligence(imovel: dict) -> dict:
    print("[2/5] market_intelligence: geocodificando e buscando anúncios no ZAP Imóveis...")
    geo = _geocodificar(imovel)
    lat, lon = geo.get("lat"), geo.get("lon")

    tipo = portais.tipo_zap(imovel.get("tipo_imovel"))
    resultado = {"geolocalizacao": geo, "fonte": "ZAP Imóveis", "amostras_simuladas": False}
    try:
        if not tipo:
            raise ValueError(f"Tipo de imóvel '{imovel.get('tipo_imovel')}' ainda não suportado na busca de portais")
        venda = portais.buscar_anuncios(imovel["cidade"], imovel["uf"], tipo, "SALE")
        aluguel = portais.buscar_anuncios(imovel["cidade"], imovel["uf"], tipo, "RENTAL")
        print(f"      {len(venda)} anúncios de venda e {len(aluguel)} de aluguel encontrados na cidade")
    except Exception as e:  # noqa: BLE001
        print(f"      [aviso] busca no portal falhou ({e}); usando amostras simuladas")
        resultado.update({
            "fonte": "SIMULADO", "amostras_simuladas": True, "erro_portal": str(e),
            "amostras": tools.web_scraper_simulado(imovel.get("bairro", ""), imovel.get("tipo_imovel", "")),
            "amostras_aluguel": [],
        })
        return resultado

    # Sem coordenadas do imóvel: usa o centro dos anúncios do mesmo bairro
    if lat is None:
        mesmos = [a for a in venda if _norm(a["bairro"]) == _norm(imovel.get("bairro")) and a["lat"]]
        if mesmos:
            lat = sum(a["lat"] for a in mesmos) / len(mesmos)
            lon = sum(a["lon"] for a in mesmos) / len(mesmos)
            geo.update({"lat": lat, "lon": lon, "precisao": "centro dos anúncios do bairro"})

    resultado["total_anuncios_venda_cidade"] = len(venda)
    resultado["total_anuncios_aluguel_cidade"] = len(aluguel)
    resultado["amostras"] = _selecionar_comparaveis(venda, imovel, lat, lon, MAX_COMPARAVEIS_VENDA)
    resultado["amostras_aluguel"] = _selecionar_comparaveis(aluguel, imovel, lat, lon, MAX_COMPARAVEIS_ALUGUEL)
    return resultado


def etapa3_sales_valuation(imovel: dict, mercado: dict) -> dict:
    print("[3/5] sales_valuation: calculando valor de venda...")
    area = _area_imovel(imovel)
    amostras = mercado.get("amostras", [])
    if not area:
        return {"erro": "Área do imóvel não identificada na matrícula; não é possível calcular o valor."}
    if len(amostras) < MIN_AMOSTRAS:
        return {"erro": f"Apenas {len(amostras)} amostras comparáveis; mínimo de {MIN_AMOSTRAS}."}

    precos_m2 = [a["preco"] / a["area"] for a in amostras]
    mediana_m2 = statistics.median(precos_m2)
    reg = tools.linear_regression_homogenization([{"area": a["area"], "preco": a["preco"]} for a in amostras])

    areas = [a["area"] for a in amostras]
    dentro_da_faixa = min(areas) <= area <= max(areas)
    if "erro" not in reg and len(amostras) >= 5 and dentro_da_faixa and reg["r2_score"] >= 0.7:
        metodo = "Regressão linear (área x preço)"
        valor_oferta = reg["intercepto"] + reg["coeficiente_angular_m2"] * area
    else:
        metodo = "Mediana de R$/m² das amostras"
        valor_oferta = mediana_m2 * area

    valor = valor_oferta * FATOR_OFERTA
    return {
        "area_considerada_m2": area,
        "n_amostras": len(amostras),
        "metodo": metodo,
        "regressao": reg,
        "mediana_m2_oferta": round(mediana_m2, 2),
        "min_m2_oferta": round(min(precos_m2), 2),
        "max_m2_oferta": round(max(precos_m2), 2),
        "valor_oferta_estimado": round(valor_oferta, -3),
        "fator_oferta": FATOR_OFERTA,
        "valor_venda_estimado": round(valor, -3),
        "faixa_min": round(valor * 0.9, -3),
        "faixa_max": round(valor * 1.1, -3),
    }


def etapa4_rental_valuation(imovel: dict, mercado: dict, venda: dict) -> dict:
    print("[4/5] rental_valuation: estimando aluguel e consultando a Selic...")
    selic = tools.bacen_selic_tool()
    area = _area_imovel(imovel)
    amostras = mercado.get("amostras_aluguel", [])
    resultado = {"selic": selic}

    if len(amostras) >= MIN_AMOSTRAS and area:
        mediana_m2 = statistics.median(a["preco"] / a["area"] for a in amostras)
        aluguel = mediana_m2 * area
        resultado.update({
            "metodo": "Mediana de R$/m² dos anúncios de aluguel",
            "n_amostras": len(amostras),
            "mediana_m2_aluguel": round(mediana_m2, 2),
        })
    elif "erro" not in venda:
        aluguel = venda["valor_venda_estimado"] * RENTABILIDADE_ALUGUEL_AA / 100 / 12
        resultado.update({
            "metodo": f"Rentabilidade bruta adotada de {RENTABILIDADE_ALUGUEL_AA}% a.a. sobre o valor de venda "
                      f"(apenas {len(amostras)} anúncios de aluguel comparáveis)",
        })
    else:
        resultado["erro"] = "Sem amostras de aluguel nem valor de venda."
        return resultado

    resultado["aluguel_mensal_estimado"] = round(aluguel, -1)
    if "erro" not in venda and venda["valor_venda_estimado"]:
        rent = aluguel * 12 / venda["valor_venda_estimado"] * 100
        resultado["rentabilidade_bruta_aa"] = round(rent, 2)
        if "selic_meta_aa" in selic:
            resultado["spread_vs_selic_pp"] = round(rent - selic["selic_meta_aa"], 2)
    return resultado


def etapa5_auditor_report(llm: ClienteLLM, dados: dict) -> str:
    print(f"[5/5] auditor_report: revisando e redigindo o laudo com {MODELO_TEXTO}...")
    prompt = (
        "Você é um avaliador imobiliário sênior (padrão NBR 14653). Com base EXCLUSIVAMENTE nos dados JSON abaixo, "
        "redija um laudo de avaliação em Markdown, em português, com as seções: "
        "1. Identificação do imóvel; 2. Situação registral (proprietários e ônus); 3. Localização; "
        "4. Pesquisa de mercado (fonte, tabela das amostras de venda com bairro, área, quartos, vagas, preço, R$/m² "
        "e distância, e tabela das amostras de aluguel); 5. Valor de venda (método, fator de oferta, valor e faixa); "
        "6. Valor de locação (método, rentabilidade e comparação com a Selic); "
        "7. Pontos de atenção da auditoria; 8. Conclusão.\n\n"
        "Regras: não invente números nem dados que não estejam no JSON; use os valores calculados como estão; "
        "formate valores em R$. Deixe claro que as amostras são preços de OFERTA (anúncios), não de venda efetiva. "
        "Na seção 7, aponte inconsistências que encontrar (ex.: amostras distantes, poucas amostras, áreas "
        "muito diferentes, ônus que afetam a liquidez) e, se 'amostras_simuladas' for true, inclua um aviso EM "
        "DESTAQUE de que as amostras são fictícias e o valor NÃO deve ser usado para decisão real.\n\n"
        f"DADOS:\n```json\n{json.dumps(dados, ensure_ascii=False, indent=2)}\n```"
    )
    return llm.gerar(MODELO_TEXTO, prompt)


def executar(pdf: Path, pasta_saida: Path = Path("laudos")) -> Path:
    llm = ClienteLLM()

    imovel = etapa1_property_intake(llm, pdf)
    mercado = etapa2_market_intelligence(imovel)
    venda = etapa3_sales_valuation(imovel, mercado)
    locacao = etapa4_rental_valuation(imovel, mercado, venda)

    dados = {"imovel": imovel, "mercado": mercado, "venda": venda, "locacao": locacao}
    laudo = etapa5_auditor_report(llm, dados)

    pasta_saida.mkdir(exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_laudo = pasta_saida / f"laudo_{carimbo}.md"
    caminho_pdf = pasta_saida / f"laudo_{carimbo}.pdf"
    caminho_json = pasta_saida / f"dados_{carimbo}.json"

    caminho_laudo.write_text(laudo, encoding="utf-8")
    caminho_json.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    import gerar_pdf
    gerar_pdf.criar_laudo_pdf(dados, caminho_pdf)

    print(f"\nRequisições à API do Gemini neste laudo: {llm.requisicoes}")
    print(f"Laudo PDF gerado: {caminho_pdf.resolve()}")
    return caminho_laudo

"""
Módulo de Reavaliação e Auditoria de Carteira de Imóveis.
Cruza anúncios ativos do feed com comparáveis de mercado em tempo real.
Possui cache de mercado em memória para permitir avaliações ultrarrápidas em lote.
"""
import statistics
from datetime import datetime
from typing import Dict, List, Optional

import pipeline
import portais
import tools
from llm import ClienteLLM

# Cache de anúncios do ZAP por chave: (cidade, uf, tipo_zap, negocio)
_CACHE_MERCADO: Dict[str, List[dict]] = {}


def obter_anuncios_mercado_com_cache(cidade: str, uf: str, tipo_zap: str, negocio: str) -> List[dict]:
    """Obtém anúncios do portal com cache em memória para evitar requisições repetidas."""
    chave = f"{cidade.lower().strip()}_{uf.lower().strip()}_{tipo_zap}_{negocio}"
    if chave in _CACHE_MERCADO and _CACHE_MERCADO[chave]:
        return _CACHE_MERCADO[chave]

    anuncios = portais.buscar_anuncios(cidade=cidade, uf=uf, tipo=tipo_zap, negocio=negocio)
    _CACHE_MERCADO[chave] = anuncios
    return anuncios


def limpar_cache_mercado():
    """Limpa o cache de mercado para forçar nova consulta aos portais."""
    global _CACHE_MERCADO
    _CACHE_MERCADO.clear()


def converter_item_feed_para_imovel(item_feed: dict) -> dict:
    """Converte o formato do feed para o formato padrão esperado pelo pipeline de avaliação."""
    area_p = float(item_feed.get("area_principal") or item_feed.get("area_util") or item_feed.get("area_total") or 0.0)
    area_tot = float(item_feed.get("area_total") or area_p)
    return {
        "numero_matricula": f"ANUNCIO_{item_feed.get('id', 'SEM_ID')}",
        "cartorio": "Estoque Ativo (Feed Portais)",
        "tipo_imovel": item_feed.get("tipo", "imovel"),
        "endereco": item_feed.get("endereco", ""),
        "complemento": item_feed.get("complemento", ""),
        "nome_condominio": "",
        "bairro": item_feed.get("bairro", ""),
        "cidade": item_feed.get("cidade", ""),
        "uf": item_feed.get("uf", "SP"),
        "area_privativa_m2": area_p,
        "area_total_m2": area_tot,
        "area_terreno_m2": area_tot,
        "quartos": item_feed.get("quartos", 0),
        "vagas": item_feed.get("vagas", 0),
        "proprietarios_atuais": ["Proprietário Cadastrado"],
        "onus_e_gravames": [],
        "observacoes": f"Código {item_feed.get('id')} - {item_feed.get('titulo', '')}",
    }


# Marco Zero de Sertãozinho (Praça 21 de Abril)
LAT_PRACA_21_ABRIL = -21.13771
LON_PRACA_21_ABRIL = -47.99119

# Ruas do Núcleo da Praça 21 de Abril (que cruzam a praça ou estão na quadra imediata)
RUAS_NUCLEO_PRACA_21 = [
    "barão do rio branco",
    "barao do rio branco",
    "washington luiz",
    "washington luis",
    "aprígio de araújo",
    "aprigio de araujo",
    "sebastião sampaio",
    "sebastiao sampaio",
    "coronel francisco schmidt",
    "francisco schmidt",
    "expedicionário lellis",
    "expedicionario lellis",
    "praça 21 de abril",
    "praca 21 de abril",
]

# Ruas que cruzam os eixos da Praça 21 de Abril ou estão no entorno comercial imediato
RUAS_CRUZANTES_PRACA_21 = [
    "elpídio gomes",
    "elpidio gomes",
    "voluntário otto gomes martins",
    "otto gomes martins",
    "carlos gomes",
    "floriano peixoto",
    "fioravante sicchieri",
    "expedicionário solano",
    "expedicionario solano",
    "frederico ozanan",
    "epitácio pessoa",
    "epitacio pessoa",
    "doutor antônio furlan júnior",
    "antônio furlan júnior",
    "antonio furlan",
    "geremias lunardelli",
    "humberto ortolan",
    "antônio malaquias pedroso",
]


def identificar_fator_corredor(item_feed: dict) -> tuple[float, str]:
    """
    Identifica se o imóvel está no Polo Central da Praça 21 de Abril (núcleo e ruas cruzantes)
    ou em corredores comerciais nobres de Sertãozinho, aplicando a ponderação NBR 14653.
    """
    texto_busca = f"{item_feed.get('endereco', '')} {item_feed.get('titulo', '')} {item_feed.get('descricao', '')} {item_feed.get('bairro', '')}".lower()
    tipo = (item_feed.get("tipo") or "").lower()
    tipo_zap = item_feed.get("tipo_zap")
    transacao = item_feed.get("transacao", "Venda")

    lat = item_feed.get("lat")
    lon = item_feed.get("lon")
    dist_praca = None
    if lat and lon:
        dist_praca = portais.distancia_km(LAT_PRACA_21_ABRIL, LON_PRACA_21_ABRIL, lat, lon)

    is_comercial = (tipo_zap in ["BUSINESS", "OFFICE", "COMMERCIAL"] or "comercial" in tipo or "salão" in tipo or "ponto" in tipo or "prédio" in tipo or "loja" in tipo)
    is_sala = ("sala" in tipo or tipo_zap == "OFFICE")
    is_terreno = (tipo_zap == "LAND_LOT" or "terreno" in tipo or "lote" in tipo)
    is_galpao = ("galpão" in tipo or tipo_zap == "SHED")
    vagas = int(item_feed.get("vagas") or 0)

    # 1. NÚCLEO DA PRAÇA 21 DE ABRIL (Barão do Rio Branco, Washington Luís, Aprígio de Araújo, Sebastião Sampaio, Cel. Francisco Schmidt, Expedicionário Lellis)
    pertence_nucleo = any(r in texto_busca for r in RUAS_NUCLEO_PRACA_21) or (dist_praca is not None and dist_praca <= 0.45 and "centro" in texto_busca)
    if pertence_nucleo:
        if is_terreno:
            f = 1.20 if transacao == "Locação" else 3.00
            return f, f"Núcleo Praça 21 de Abril (Centro). Floc = {f:.2f}x para terrenos no centro."
        elif is_galpao:
            return 1.00, "Centro (Restrição de tráfego pesado/carga para galpões). Floc = 1.00x."
        elif is_sala:
            # Calibração comercial: salas no centro sem vaga sofrem com gargalo de estacionamento
            if transacao == "Locação":
                if vagas > 0:
                    return 1.20, f"Núcleo Praça 21 de Abril ({vagas} vaga(s) privativas). Floc = 1.20x."
                else:
                    return 1.05, "Núcleo Praça 21 de Abril (Sem vaga privativa). Floc = 1.05x (gargalo de estacionamento no centro neutraliza o prêmio)."
            else:
                return 2.20, "Núcleo Praça 21 de Abril (Centro Nobre - Venda). Floc = 2.20x."
        elif is_comercial:
            f = 1.30 if transacao == "Locação" else 2.50
            return f, f"Núcleo Praça 21 de Abril (Comércio de Rua/Varejo). Floc = {f:.2f}x pelo fluxo de pedestres na calçada."
        else:
            return 1.30, "Núcleo Praça 21 de Abril (Centro Nobre). Floc = 1.30x pela infraestrutura e vocação mista/comercial."

    # 2. RUAS CRUZANTES E ENTORNO IMEDIATO DA PRAÇA 21 DE ABRIL
    pertence_cruzantes = any(r in texto_busca for r in RUAS_CRUZANTES_PRACA_21) or (dist_praca is not None and dist_praca <= 0.85 and "centro" in texto_busca)
    if pertence_cruzantes:
        if is_terreno:
            f = 1.10 if transacao == "Locação" else 2.20
            return f, f"Ruas Cruzantes da Praça 21 de Abril (Centro). Floc = {f:.2f}x para terrenos na malha central."
        elif is_galpao:
            return 1.00, "Entorno Central (Galpão com restrição de carga). Floc = 1.00x."
        elif is_sala:
            if transacao == "Locação":
                if vagas > 0:
                    return 1.15, f"Ruas Cruzantes da Praça 21 ({vagas} vaga(s) privativas). Floc = 1.15x."
                else:
                    return 1.00, "Ruas Cruzantes da Praça 21 (Sem vaga privativa). Floc = 1.00x (estacionamento na rua)."
            else:
                return 1.80, "Ruas Cruzantes da Praça 21 (Venda). Floc = 1.80x."
        elif is_comercial:
            f = 1.15 if transacao == "Locação" else 1.90
            return f, f"Ruas Cruzantes da Praça 21. Floc = {f:.2f}x para imóvel comercial no entorno central."
        else:
            return 1.15, "Ruas Cruzantes da Praça 21 de Abril (Centro). Floc = 1.15x para imóveis na malha central."

    # 3. OUTROS EIXOS ESPECÍFICOS FORA DO CENTRO
    if "antônio paschoal" in texto_busca or "antonio paschoal" in texto_busca:
        if is_terreno or is_comercial:
            f = 2.00 if transacao == "Venda" else 1.45
            return f, "Eixo Comercial - Av. Antônio Paschoal (via arterial de grande fluxo e visibilidade)."

    if "affonso trigo" in texto_busca:
        if is_terreno or is_comercial:
            f = 1.75 if transacao == "Venda" else 1.30
            return f, "Eixo Comercial - Av. Affonso Trigo (corredor comercial e de serviços)."

    return 1.00, ""


def reavaliar_imovel_feed(item_feed: dict, fator_oferta: float = 0.90, fator_localizacao: float = None) -> dict:
    """
    Executa a auditoria de preço de um imóvel do feed contra a concorrência ao vivo.
    Suporta fator de localização NBR 14653 para corredores comerciais e vias nobres.
    """
    cidade = item_feed.get("cidade") or "Sertãozinho"
    uf = item_feed.get("uf") or "SP"
    tipo_zap = item_feed.get("tipo_zap")
    negocio = item_feed.get("negocio_zap", "SALE")
    preco_anunciado = float(item_feed.get("preco") or 0.0)
    area = float(item_feed.get("area_principal") or item_feed.get("area_util") or item_feed.get("area_total") or 0.0)

    if not tipo_zap:
        return {
            "sucesso": False,
            "motivo": f"Tipo '{item_feed.get('tipo')}' ainda não possui comparáveis diretos no portal.",
            "preco_anunciado": preco_anunciado,
        }

    if area <= 0:
        return {
            "sucesso": False,
            "motivo": "Imóvel sem área útil/total informada.",
            "preco_anunciado": preco_anunciado,
        }

    imovel_padrao = converter_item_feed_para_imovel(item_feed)

    # 1. Coleta ou recuperação dos comparáveis
    try:
        anuncios_cidade = obter_anuncios_mercado_com_cache(cidade, uf, tipo_zap, negocio)
    except Exception as e:
        return {
            "sucesso": False,
            "motivo": f"Falha na consulta ao portal: {e}",
            "preco_anunciado": preco_anunciado,
        }

    lat = item_feed.get("lat")
    lon = item_feed.get("lon")

    # Se não tiver coordenadas, tenta usar o centro do bairro
    if lat is None or lon is None:
        bairro_norm = pipeline._norm(item_feed.get("bairro"))
        mesmos = [a for a in anuncios_cidade if pipeline._norm(a["bairro"]) == bairro_norm and a.get("lat")]
        if mesmos:
            lat = sum(a["lat"] for a in mesmos) / len(mesmos)
            lon = sum(a["lon"] for a in mesmos) / len(mesmos)

    # 2. Filtragem de comparáveis homogêneos
    limite = pipeline.MAX_COMPARAVEIS_VENDA if negocio == "SALE" else pipeline.MAX_COMPARAVEIS_ALUGUEL
    amostras = pipeline._selecionar_comparaveis(anuncios_cidade, imovel_padrao, lat, lon, limite)

    if len(amostras) < pipeline.MIN_AMOSTRAS:
        return {
            "sucesso": False,
            "motivo": f"Amostras insuficientes no portal ({len(amostras)} encontradas, mínimo {pipeline.MIN_AMOSTRAS}).",
            "preco_anunciado": preco_anunciado,
            "total_anuncios_cidade": len(anuncios_cidade),
        }

    # 3. Cálculo estatístico
    precos_m2 = [a["preco"] / a["area"] for a in amostras]
    mediana_m2_oferta = statistics.median(precos_m2)

    # BENCHMARK EMPÍRICO DA CARTEIRA EXPANDH (Produtos Reais Ativos):
    # Para locação comercial, ancoramos nas medianas comprovadas do estoque Expandh
    # evitando distorções de amostras infladas ou com falta de estacionamento
    tipo_base = item_feed.get("tipo", "")
    tipo_l = tipo_base.lower()
    is_terr = (item_feed.get("tipo_zap") == "LAND_LOT" or "terreno" in tipo_l or "lote" in tipo_l)
    is_com = (item_feed.get("tipo_zap") in ["BUSINESS", "OFFICE", "COMMERCIAL"] or any(k in tipo_l for k in ["comercial", "sala", "salão", "prédio", "galpão"]))

    if negocio == "RENTAL" and (is_com or is_terr):
        regiao = "Centro" if "centro" in (item_feed.get("bairro") or "").lower() else "Bairros"
        benchmark_carteira = {
            "Sala Comercial": {"Centro": 38.20, "Bairros": 26.20},
            "Ponto Comercial / Salão": {"Centro": 22.00, "Bairros": 22.00},
            "Prédio Comercial": {"Centro": 28.00, "Bairros": 22.00},
            "Galpão Industrial": {"Centro": 18.00, "Bairros": 20.00},
            "Terreno Comercial": {"Centro": 4.50, "Bairros": 5.50},
        }
        bench_m2 = benchmark_carteira.get(tipo_base, {}).get(regiao)
        if bench_m2:
            # Ponderação equilibrada: 40% portal ZAP + 60% estoque real comprovado Expandh
            mediana_m2_oferta = round((mediana_m2_oferta * 0.40) + (bench_m2 * 0.60), 2)

    # Identificação ou aplicação de Fator de Localização / Corredor Nobre (NBR 14653)
    fator_loc_auto, justificativa_loc = identificar_fator_corredor(item_feed)
    fator_loc = fator_localizacao if fator_localizacao is not None else fator_loc_auto

    mediana_m2_ajustada = mediana_m2_oferta * fator_loc
    valor_oferta_estimado = mediana_m2_ajustada * area

    tipo_l = (item_feed.get("tipo") or "").lower()
    is_terr = (item_feed.get("tipo_zap") == "LAND_LOT" or "terreno" in tipo_l or "lote" in tipo_l)

    # Fator de oferta para fechamento (terrenos e pontos comerciais nobres no centro têm pouca margem de barganha)
    if fator_loc > 1.0:
        fator_of = 1.0 if is_terr else max(fator_oferta, 0.95)
    else:
        fator_of = fator_oferta

    valor_fechamento_estimado = valor_oferta_estimado * fator_of
    valor_fechamento_estimado = round(valor_fechamento_estimado, -3) if valor_fechamento_estimado > 10000 else round(valor_fechamento_estimado, -1)

    faixa_min = round(valor_fechamento_estimado * 0.90, -3) if valor_fechamento_estimado > 10000 else round(valor_fechamento_estimado * 0.90, -1)
    faixa_max = round(valor_fechamento_estimado * 1.10, -3) if valor_fechamento_estimado > 10000 else round(valor_fechamento_estimado * 1.10, -1)

    # 4. Diagnóstico de Discrepância / Gap
    if valor_fechamento_estimado > 0:
        desvio_pct = round(((preco_anunciado / valor_fechamento_estimado) - 1.0) * 100.0, 1)
        diferenca_rs = round(preco_anunciado - valor_fechamento_estimado, 2)
    else:
        desvio_pct = 0.0
        diferenca_rs = 0.0

    if desvio_pct > 15.0:
        status = "🔴 Muito Acima"
        diagnostico = "Preço significativamente acima da concorrência direta. Alto risco de perda de liquidez e desinteresse de compradores."
        acao_sugerida = "Recomenda-se reunião de reprecificação com o proprietário para alinhar com o teto de mercado."
    elif desvio_pct > 5.0:
        status = "🟡 Acima do Mercado"
        diagnostico = "Preço com margem para negociação, mas ligeiramente acima da média praticada no bairro."
        acao_sugerida = "Pode ser mantido se o imóvel tiver acabamentos superiores, mas pode demorar mais para receber visitas."
    elif desvio_pct >= -7.0:
        status = "🟢 Preço Justo"
        diagnostico = "Preço perfeitamente alinhado com o valor de fechamento estimado na região."
        acao_sugerida = "Manter o valor. Foco total em marketing e destaque nos portais para acelerar o fechamento."
    else:
        status = "🔵 Oportunidade"
        diagnostico = "Preço abaixo da média de mercado. Alta atratividade para compradores e investidores."
        acao_sugerida = "Excelente apelo de venda rápida. Proprietário tem margem para subir o valor se desejar."

    if fator_loc > 1.0:
        diagnostico = f"Preço perfeitamente justificado pela localização no Polo Central da Praça 21 de Abril. {justificativa_loc}"
        if abs(desvio_pct) <= 15.0:
            status = "🟢 Preço Justo"
            acao_sugerida = f"Manter o valor de R$ {preco_anunciado:,.0f}. Ponto comercial nobre/central com alta liquidez e visibilidade."

    return {
        "sucesso": True,
        "codigo": item_feed.get("id"),
        "titulo": item_feed.get("titulo"),
        "bairro": item_feed.get("bairro"),
        "cidade": cidade,
        "area_m2": area,
        "preco_anunciado": preco_anunciado,
        "preco_m2_anunciado": round(preco_anunciado / area, 2) if area else 0,
        "valor_fechamento_estimado": valor_fechamento_estimado,
        "valor_oferta_estimado": round(valor_oferta_estimado, -3),
        "faixa_min": faixa_min,
        "faixa_max": faixa_max,
        "mediana_m2_concorrencia": round(mediana_m2_ajustada, 2),
        "mediana_m2_base": round(mediana_m2_oferta, 2),
        "fator_localizacao_aplicado": fator_loc,
        "justificativa_localizacao": justificativa_loc if fator_loc > 1.0 else "",
        "fator_oferta_aplicado": fator_oferta,
        "desvio_pct": desvio_pct,
        "diferenca_rs": diferenca_rs,
        "status": status,
        "diagnostico": diagnostico,
        "acao_sugerida": acao_sugerida,
        "n_amostras": len(amostras),
        "amostras": amostras,
        "total_anuncios_cidade": len(anuncios_cidade),
    }


def gerar_argumentario_proprietario(reavaliacao: dict, llm: Optional[ClienteLLM] = None) -> str:
    """Gera um roteiro / mensagem de WhatsApp para o corretor conversar com o proprietário."""
    if not reavaliacao.get("sucesso"):
        return "Não foi possível gerar argumentário: dados de mercado insuficientes."

    codigo = reavaliacao.get("codigo", "")
    bairro = reavaliacao.get("bairro", "")
    area = reavaliacao.get("area_m2", 0)
    preco_atual = reavaliacao.get("preco_anunciado", 0)
    valor_estimado = reavaliacao.get("valor_fechamento_estimado", 0)
    desvio = reavaliacao.get("desvio_pct", 0)
    mediana_m2 = reavaliacao.get("mediana_m2_concorrencia", 0)
    n_amostras = reavaliacao.get("n_amostras", 0)

    if llm is None:
        try:
            llm = ClienteLLM()
        except Exception:
            pass

    if llm:
        prompt = (
            f"Você é um consultor imobiliário experiente da imobiliária Expandh. "
            f"Escreva uma mensagem de WhatsApp direta, elegante, profissional e empática para o proprietário do imóvel código {codigo}.\n"
            f"Dados da auditoria de mercado:\n"
            f"- Bairro: {bairro}\n"
            f"- Área útil: {area} m²\n"
            f"- Valor anunciado atualmente: R$ {preco_atual:,.2f}\n"
            f"- Valor justo de mercado calculado: R$ {valor_estimado:,.2f} (faixa recomendada de R$ {reavaliacao['faixa_min']:,.2f} a R$ {reavaliacao['faixa_max']:,.2f})\n"
            f"- Amostras analisadas no bairro/cidade: {n_amostras} imóveis concorrentes com mediana de R$ {mediana_m2:,.2f}/m²\n"
            f"- Variação apurada: {desvio:+.1f}%\n"
            f"- Diagnóstico: {reavaliacao.get('diagnostico')}\n\n"
            f"Instruções:\n"
            f"1. Agradeça pela confiança na imobiliária e explique que a equipe realizou uma auditoria técnica de posicionamento nos portais.\n"
            f"2. Mostre os números com clareza e transparência (sem parecer arrogante).\n"
            f"3. Dê uma recomendação clara para atrair mais compradores e fechar o negócio com segurança.\n"
            f"4. Máximo de 2 parágrafos curtos, prontos para enviar por mensagem."
        )
        try:
            return llm.gerar("gemini-3.1-flash-lite", prompt)
        except Exception:
            pass

    # Fallback estruturado caso a LLM não esteja conectada
    return (
        f"Olá, tudo bem? Estamos fazendo uma revisão técnica periódica dos imóveis anunciados na Expandh "
        f"para garantir que o seu imóvel (Cód. {codigo}) no {bairro} tenha o máximo de visibilidade nos portais.\n\n"
        f"Analisamos {n_amostras} imóveis diretamente concorrentes na mesma região e a média praticada é de "
        f"R$ {mediana_m2:,.2f}/m², o que projeta um valor justo de mercado em torno de R$ {valor_estimado:,.2f}. "
        f"O valor atual anunciado é de R$ {preco_atual:,.2f} ({desvio:+.1f}% em relação à concorrência). "
        f"{reavaliacao.get('acao_sugerida', '')} Vamos conversar sobre essa estratégia para acelerar a venda?"
    )

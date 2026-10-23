"""
Módulo de Reavaliação e Auditoria de Carteira de Imóveis.
Cruza anúncios ativos do feed com comparáveis de mercado em tempo real.
Possui cache de mercado em memória para permitir avaliações ultrarrápidas em lote.
"""
import json
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pipeline
import portais
import tools
from llm import ClienteLLM

PASTA_RAIZ = Path(__file__).resolve().parent
CAMINHO_CONDICIONANTES = PASTA_RAIZ / "dados_condicionantes.json"

# Cache de anúncios do ZAP por chave: (cidade, uf, tipo_zap, negocio)
_CACHE_MERCADO: Dict[str, List[dict]] = {}


def carregar_dados_condicionantes() -> dict:
    """Carrega dados e anotações de condicionantes (ágios, parcelamentos, saldo devedor) do CRM."""
    if CAMINHO_CONDICIONANTES.exists():
        try:
            return json.loads(CAMINHO_CONDICIONANTES.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def salvar_dado_condicionante(codigo: str, dados: dict):
    """Salva ou atualiza a anotação de condicionante de um imóvel."""
    catalogo = carregar_dados_condicionantes()
    catalogo[str(codigo)] = dados
    try:
        CAMINHO_CONDICIONANTES.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


PAT_CONDICIONANTE = re.compile(
    r'(?:mais\s+parcelas?\s+(?:à|a)\s+vencer|\+\s*\d*\s*parcelas?|saldo\s+devedor|assum(?:e|ir)\s+(?:o\s+)?saldo|assum(?:e|ir)\s+(?:as\s+)?parcelas?|repasse\s+de\s+(?:lote|im[oó]vel|financiamento)|[áa]gio|entrada\s+de\s+r\$|faltam\s+\d+\s+parcelas?|restam\s+\d+\s+parcelas?|\d+\s*x\s+de\s+r\$|\d+\s*parcelas?\s+de|lote\s+financiado|im[oó]vel\s+financiado)',
    re.IGNORECASE,
)
PAT_PARCELAS_VALOR = re.compile(r'(\d+)\s*(?:parcelas?|x)\s+(?:de\s+)?(?:r\$\s*)?([\d\.,]+)', re.IGNORECASE)
PAT_SALDO_DEVEDOR = re.compile(r'saldo\s+devedor\s+(?:de\s+)?(?:r\$\s*)?([\d\.,]+)', re.IGNORECASE)


def identificar_condicionante_preco(item_feed: dict) -> dict:
    """
    Identifica se a oferta possui condicionante financeira (ágio / repasse / parcelas a vencer).
    Cruza com base de conhecimento interna do CRM e analisa o texto de descrição e título via NLP/Regex.
    Retorna metadados de condicionante, saldo devedor e preço efetivo total.
    """
    cid = str(item_feed.get("id") or item_feed.get("Código") or "")
    texto_busca = f"{item_feed.get('titulo', '')} {item_feed.get('descricao', '')} {item_feed.get('observacoes', '')}"

    catalogo = carregar_dados_condicionantes()
    dados_cat = catalogo.get(cid) or catalogo.get(cid.replace("V", ""))

    match_regex = PAT_CONDICIONANTE.search(texto_busca)
    is_condicionado = bool(match_regex or dados_cat)

    if not is_condicionado:
        preco_anunc = float(item_feed.get("preco") or item_feed.get("Preço Anunciado (R$)") or 0.0)
        return {
            "is_condicionado": False,
            "tipo_condicao": "Quitado / Preço Integral",
            "detalhes": "",
            "num_parcelas": 0,
            "valor_parcela": 0.0,
            "saldo_devedor_estimado": 0.0,
            "preco_efetivo_total": preco_anunc,
            "observacao_interna": "",
        }

    num_parcelas = 0
    valor_parcela = 0.0
    saldo_devedor = 0.0
    obs = ""
    detalhes = match_regex.group(0) if match_regex else "Condicionante cadastrado no CRM"

    if dados_cat:
        num_parcelas = int(dados_cat.get("num_parcelas") or 0)
        valor_parcela = float(dados_cat.get("valor_parcela") or 0.0)
        saldo_devedor = float(dados_cat.get("saldo_devedor") or (num_parcelas * valor_parcela))
        obs = dados_cat.get("observacoes", "")
    else:
        m_parc = PAT_PARCELAS_VALOR.search(texto_busca)
        m_saldo = PAT_SALDO_DEVEDOR.search(texto_busca)
        if m_parc:
            try:
                num_parcelas = int(m_parc.group(1))
                v_str = m_parc.group(2).rstrip('.,;:').replace('.', '').replace(',', '.')
                valor_parcela = float(v_str)
                saldo_devedor = round(num_parcelas * valor_parcela, 2)
                obs = f"{num_parcelas} parcelas de R$ {valor_parcela:,.2f}"
            except Exception:
                pass
        elif m_saldo:
            try:
                s_str = m_saldo.group(1).rstrip('.,;:').replace('.', '').replace(',', '.')
                saldo_devedor = float(s_str)
                obs = f"Saldo devedor de R$ {saldo_devedor:,.2f}"
            except Exception:
                pass

    preco_anunc = float(item_feed.get("preco") or item_feed.get("Preço Anunciado (R$)") or 0.0)
    preco_efetivo = preco_anunc + saldo_devedor

    return {
        "is_condicionado": True,
        "tipo_condicao": "Ágio / Parcelas a Vencer",
        "detalhes": detalhes,
        "num_parcelas": num_parcelas,
        "valor_parcela": valor_parcela,
        "saldo_devedor_estimado": saldo_devedor,
        "preco_efetivo_total": preco_efetivo,
        "observacao_interna": obs,
    }


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

    # Extração de número para checagem auxiliar caso não haja coordenadas
    numero_int = None
    try:
        numero_int = int("".join(c for c in str(item_feed.get("numero", "")) if c.isdigit()))
    except Exception:
        pass

    # 1. NÚCLEO DA PRAÇA 21 DE ABRIL (Barão do Rio Branco, Washington Luís, Aprígio de Araújo, Sebastião Sampaio, Cel. Francisco Schmidt, Expedicionário Lellis)
    # Exige proximidade física estrita (raio máximo <= 0.38 km da Praça 21), pois essas vias se estendem por quilômetros
    if dist_praca is not None:
        pertence_nucleo = (dist_praca <= 0.38) and (any(r in texto_busca for r in RUAS_NUCLEO_PRACA_21) or "centro" in texto_busca)
    else:
        pertence_nucleo = any(r in texto_busca for r in RUAS_NUCLEO_PRACA_21) and "centro" in texto_busca and (numero_int is None or numero_int <= 1500)

    if pertence_nucleo:
        if is_terreno:
            f = 1.20 if transacao == "Locação" else 3.00
            return f, f"Núcleo Praça 21 de Abril (Centro - {dist_praca*1000:.0f}m da praça). Floc = {f:.2f}x para terrenos no centro."
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
    # Exige proximidade física no anel secundário central (raio máximo <= 0.55 km da Praça 21).
    # Imóveis além de 550m (ex: Fioravante Sicchieri 1570 a 850m/1.4km) ficam fora do polo comercial da praça.
    if dist_praca is not None:
        pertence_cruzantes = (dist_praca <= 0.55) and (any(r in texto_busca for r in RUAS_CRUZANTES_PRACA_21) or "centro" in texto_busca)
    else:
        pertence_cruzantes = any(r in texto_busca for r in RUAS_CRUZANTES_PRACA_21) and "centro" in texto_busca and (numero_int is None or numero_int <= 1000)

    if pertence_cruzantes:
        dist_str = f" ({dist_praca*1000:.0f}m da praça)" if dist_praca is not None else ""
        if is_terreno:
            f = 1.10 if transacao == "Locação" else 2.20
            return f, f"Ruas Cruzantes da Praça 21 de Abril{dist_str}. Floc = {f:.2f}x para terrenos na malha central."
        elif is_galpao:
            return 1.00, "Entorno Central (Galpão com restrição de carga). Floc = 1.00x."
        elif is_sala:
            if transacao == "Locação":
                if vagas > 0:
                    return 1.15, f"Ruas Cruzantes da Praça 21{dist_str} ({vagas} vaga(s) privativas). Floc = 1.15x."
                else:
                    return 1.00, f"Ruas Cruzantes da Praça 21{dist_str} (Sem vaga privativa). Floc = 1.00x (estacionamento na rua)."
            else:
                return 1.80, f"Ruas Cruzantes da Praça 21{dist_str} (Venda). Floc = 1.80x."
        elif is_comercial:
            f = 1.15 if transacao == "Locação" else 1.90
            return f, f"Ruas Cruzantes da Praça 21{dist_str}. Floc = {f:.2f}x para imóvel comercial no entorno central."
        else:
            return 1.15, f"Ruas Cruzantes da Praça 21 de Abril{dist_str}. Floc = 1.15x para imóveis na malha central."

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


def reavaliar_imovel_feed(
    item_feed: dict,
    fator_oferta: float = 0.90,
    fator_localizacao: float = None,
    saldo_devedor_manual: Optional[float] = None,
) -> dict:
    """
    Executa a auditoria de preço de um imóvel do feed contra a concorrência ao vivo.
    Suporta fator de localização NBR 14653 para corredores comerciais e vias nobres,
    e detecção automática de condicionantes financeiras (ágio / repasse / parcelas a vencer).
    """
    cidade = item_feed.get("cidade") or "Sertãozinho"
    uf = item_feed.get("uf") or "SP"
    tipo_zap = item_feed.get("tipo_zap")
    negocio = item_feed.get("negocio_zap", "SALE")
    preco_anunciado = float(item_feed.get("preco") or 0.0)
    area = float(item_feed.get("area_principal") or item_feed.get("area_util") or item_feed.get("area_total") or 0.0)

    # Verificação de condicionante financeira (ágio / repasse de loteamento / parcelas)
    cond_info = identificar_condicionante_preco(item_feed)
    if saldo_devedor_manual is not None and saldo_devedor_manual >= 0:
        cond_info["saldo_devedor_estimado"] = float(saldo_devedor_manual)
        cond_info["preco_efetivo_total"] = preco_anunciado + float(saldo_devedor_manual)
        if saldo_devedor_manual > 0:
            cond_info["is_condicionado"] = True

    is_condicionado = cond_info["is_condicionado"]
    saldo_devedor = cond_info["saldo_devedor_estimado"]
    preco_base_comparacao = preco_anunciado + saldo_devedor if is_condicionado and saldo_devedor > 0 else preco_anunciado

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

    # -------------------------------------------------------------------------
    # BENCHMARK EMPÍRICO & HOMOGENEIZAÇÃO DE CONDOMÍNIOS FECHADOS (NBR 14653)
    # Imóveis em condomínio fechado (casas e terrenos/lotes) possuem infraestrutura
    # completa (portaria 24h, segurança armada, clube, quadras, rede subterrânea)
    # e não podem ser avaliados pelo preço de imóveis em ruas públicas periféricas.
    # -------------------------------------------------------------------------
    texto_busca_completo = f"{item_feed.get('endereco', '')} {item_feed.get('titulo', '')} {item_feed.get('descricao', '')} {item_feed.get('bairro', '')} {item_feed.get('tipo', '')} {item_feed.get('tipo_original', '')}".lower()
    taxa_condominio = float(item_feed.get("condominio") or 0.0)

    # Detecção inequívoca de condomínio fechado
    has_explicit_condo_term = (
        "condomínio" in texto_busca_completo
        or "condominio" in texto_busca_completo
        or "fechado" in texto_busca_completo
        or "bella la vita" in texto_busca_completo
        or "bella la vitta" in texto_busca_completo
        or "alphaville" in texto_busca_completo
        or "damha" in texto_busca_completo
        or "condo" in (item_feed.get("tipo_original") or "").lower()
        or "condomínio" in tipo_l
        or "condominio" in tipo_l
    )
    has_condo_fee = taxa_condominio >= 150.0

    is_condo_house = (
        ("casa" in tipo_l or tipo_zap == "HOME" or "sobrado" in tipo_l)
        and (has_condo_fee or has_explicit_condo_term or any(k in texto_busca_completo for k in ["terra nova", "portal das flores", "aroeiras", "shangri", "morada das estrelas"]))
    )

    is_condo_land = (
        is_terr
        and (has_condo_fee or has_explicit_condo_term)
    )

    is_condo = is_condo_house or is_condo_land
    justificativa_condo = ""
    piso_minimo_condo = None

    if is_condo_house:
        if negocio == "SALE":
            # 1. Condomínio Reserva Terra Nova (Sertãozinho)
            if "terra nova" in texto_busca_completo or "primo rissato" in texto_busca_completo:
                # Diretriz pericial Expandh e histórico de vendas: casas no Reserva Terra Nova partem do piso de R$ 700 mil
                # com padrão construtivo em torno de R$ 5.850/m²
                mediana_m2_oferta = 5850.0
                piso_minimo_condo = 700000.0
                justificativa_condo = "Condomínio Reserva Terra Nova (Portaria 24h, lazer completo e segurança). Casas partem de R$ 700 mil (benchmark R$ 5.850/m²)."
            # 2. Condomínio Portal das Flores
            elif "portal das flores" in texto_busca_completo or "eduardo toniello" in texto_busca_completo:
                mediana_m2_oferta = 4800.0
                piso_minimo_condo = 500000.0
                justificativa_condo = "Condomínio Portal das Flores (Lazer e portaria 24h). Benchmark de R$ 4.800/m²."
            # 3. Condomínios de Alto Padrão (Parque das Aroeiras, Shangri-lá, Morada das Estrelas)
            elif any(k in texto_busca_completo for k in ["aroeiras", "shangri", "palmeiras", "morada das estrelas"]):
                mediana_m2_oferta = 9500.0
                piso_minimo_condo = 1800000.0
                justificativa_condo = "Condomínio Fechado de Alto Padrão (Parque das Aroeiras / Shangri-lá). Benchmark de R$ 9.500/m²."
            # 4. Outros Condomínios Fechados Residenciais
            else:
                fator_condo = 2.15
                mediana_m2_oferta = round(mediana_m2_oferta * fator_condo, 2)
                justificativa_condo = f"Casa em Condomínio Fechado (Fator Condomínio Fechado NBR 14653 = {fator_condo:.2f}x sobre casas de rua aberta)."
        else:
            fator_condo_aluguel = 1.50
            mediana_m2_oferta = round(mediana_m2_oferta * fator_condo_aluguel, 2)
            justificativa_condo = f"Casa em Condomínio Fechado (Locação com portaria e lazer. Fator NBR 14653 = {fator_condo_aluguel:.2f}x)."

    elif is_condo_land:
        if negocio == "SALE":
            # 1. Condomínio Bella La Vita (Alto Padrão - Sertãozinho)
            if "bella la vita" in texto_busca_completo or "bella la vitta" in texto_busca_completo or "athenas" in texto_busca_completo:
                mediana_m2_oferta = 2800.0
                piso_minimo_condo = 800000.0
                justificativa_condo = "Condomínio Residencial Bella La Vita (Alto Padrão fechado, portaria 24h e lazer completo). Benchmark pericial de R$ 2.800/m²."
            # 2. Condomínios Fechados Nobres (Parque das Aroeiras, Quinta da Boa Vista, Reserva Imperial, Shangri-lá)
            elif any(k in texto_busca_completo for k in ["aroeiras", "boa vista", "quinta da boa vista", "reserva imperial", "shangri"]):
                mediana_m2_oferta = 2650.0
                piso_minimo_condo = 900000.0
                justificativa_condo = "Condomínio Fechado de Alto Padrão (Parque das Aroeiras / Quinta da Boa Vista). Benchmark pericial de R$ 2.650/m²."
            # 3. Condomínio Portal das Flores
            elif "portal das flores" in texto_busca_completo:
                mediana_m2_oferta = 1800.0
                piso_minimo_condo = 400000.0
                justificativa_condo = "Condomínio Portal das Flores. Benchmark pericial de R$ 1.800/m²."
            # 4. Outros Condomínios Fechados Residenciais
            else:
                fator_condo_land = 2.85
                mediana_m2_oferta = max(round(mediana_m2_oferta * fator_condo_land, 2), 1800.0)
                justificativa_condo = f"Lote em Condomínio Fechado (Fator Condomínio Fechado NBR 14653 = {fator_condo_land:.2f}x sobre lotes de rua aberta)."
        else:
            fator_condo_aluguel = 1.60
            mediana_m2_oferta = round(mediana_m2_oferta * fator_condo_aluguel, 2)
            justificativa_condo = f"Lote em Condomínio Fechado (Locação. Fator NBR 14653 = {fator_condo_aluguel:.2f}x)."

    tipo_l = (item_feed.get("tipo") or "").lower()
    is_terr = (item_feed.get("tipo_zap") == "LAND_LOT" or "terreno" in tipo_l or "lote" in tipo_l)

    # Identificação ou aplicação de Fator de Localização / Corredor Nobre (NBR 14653)
    fator_loc_auto, justificativa_loc = identificar_fator_corredor(item_feed)
    fator_loc = fator_localizacao if fator_localizacao is not None else fator_loc_auto

    # Homogeneização de Área / Fator de Escala (NBR 14653-2)
    # Evita avaliar glebas/áreas grandes com base em lotes padrão residenciais sem ajuste de escala
    fator_escala = 1.0
    justificativa_escala = ""
    if is_terr and amostras:
        areas_validas = [a["area"] for a in amostras if a.get("area", 0) > 0]
        if areas_validas:
            area_amostras_mediana = statistics.median(areas_validas)
            razao_area = area / area_amostras_mediana
            if razao_area > 1.4:
                # Terreno significativamente maior que os lotes das amostras (gleba/área de expansão)
                fator_escala = round((area_amostras_mediana / area) ** 0.25, 3)
                fator_escala = max(fator_escala, 0.40)
                justificativa_escala = f"Homogeneização de Escala NBR 14653: {fator_escala:.2f}x (área de {area:,.0f} m² vs lote padrão de {area_amostras_mediana:,.0f} m²)."
            elif razao_area < 0.70:
                # Terreno menor que o lote padrão
                fator_escala = round((area_amostras_mediana / area) ** 0.20, 3)
                fator_escala = min(fator_escala, 1.30)
                justificativa_escala = f"Homogeneização de Escala NBR 14653: {fator_escala:.2f}x (lote compacto de {area:,.0f} m² vs padrão de {area_amostras_mediana:,.0f} m²)."

    mediana_m2_ajustada = mediana_m2_oferta * fator_loc * fator_escala
    valor_oferta_estimado = mediana_m2_ajustada * area

    # Fator de oferta para fechamento (terrenos e pontos comerciais nobres no centro têm pouca margem de barganha)
    if fator_loc > 1.0:
        fator_of = 1.0 if is_terr else max(fator_oferta, 0.95)
    elif (is_condo_house or is_condo_land) and negocio == "SALE":
        fator_of = 0.97 # alta liquidez e margem de barganha restrita em condomínio fechado
    else:
        fator_of = fator_oferta

    valor_fechamento_estimado = valor_oferta_estimado * fator_of
    if piso_minimo_condo and valor_fechamento_estimado < piso_minimo_condo:
        valor_fechamento_estimado = piso_minimo_condo
        valor_oferta_estimado = round(piso_minimo_condo / fator_of, -3)

    valor_fechamento_estimado = round(valor_fechamento_estimado, -3) if valor_fechamento_estimado > 10000 else round(valor_fechamento_estimado, -1)

    faixa_min = round(valor_fechamento_estimado * 0.90, -3) if valor_fechamento_estimado > 10000 else round(valor_fechamento_estimado * 0.90, -1)
    faixa_max = round(valor_fechamento_estimado * 1.10, -3) if valor_fechamento_estimado > 10000 else round(valor_fechamento_estimado * 1.10, -1)

    # 4. Diagnóstico de Discrepância / Gap (considerando custo total de aquisição para ofertas condicionadas)
    if valor_fechamento_estimado > 0:
        desvio_pct = round(((preco_base_comparacao / valor_fechamento_estimado) - 1.0) * 100.0, 1)
        diferenca_rs = round(preco_base_comparacao - valor_fechamento_estimado, 2)
    else:
        desvio_pct = 0.0
        diferenca_rs = 0.0

    if is_condicionado and saldo_devedor == 0:
        status = "⚠️ Ágio / Parcelas a Vencer"
        diagnostico = (
            f"Preço anunciado de R$ {preco_anunciado:,.0f} refere-se apenas ao ÁGIO / ENTRADA ('{cond_info['detalhes']}'). "
            f"O imóvel possui parcelas restantes a vencer cujo valor total ainda não foi apurado. "
            f"Não pode ser classificado como oportunidade sem a soma do saldo devedor."
        )
        acao_sugerida = "Consultar o proprietário ou loteadora para apurar a quantidade e o valor das parcelas restantes antes de ofertar."
    elif desvio_pct > 15.0:
        status = "🔴 Muito Acima"
        if is_condicionado:
            diagnostico = (
                f"Custo total de aquisição com parcelas (R$ {preco_base_comparacao:,.2f}) está {desvio_pct:+.1f}% ACIMA do valor de mercado NBR 14653 (R$ {valor_fechamento_estimado:,.0f}). "
                f"Entrada anunciada: R$ {preco_anunciado:,.2f} + Saldo devedor a assumir: R$ {saldo_devedor:,.2f} ({cond_info.get('observacao_interna') or 'parcelas a vencer'}). "
                f"Atenção: Imóveis quitados equivalentes na mesma região saem sensivelmente mais baratos do que assumir este parcelamento!"
            )
            acao_sugerida = "Orientar o proprietário a reduzir a pedida do ágio/entrada, pois o comprador assumirá dívida expressiva."
        else:
            diagnostico = "Preço significativamente acima da concorrência direta. Alto risco de perda de liquidez e desinteresse de compradores."
            acao_sugerida = "Recomenda-se reunião de reprecificação com o proprietário para alinhar com o teto de mercado."
    elif desvio_pct > 5.0:
        status = "🟡 Acima do Mercado"
        if is_condicionado:
            diagnostico = (
                f"Custo total de aquisição com parcelas (R$ {preco_base_comparacao:,.2f}) está {desvio_pct:+.1f}% ligeiramente acima do mercado (R$ {valor_fechamento_estimado:,.0f}). "
                f"Entrada: R$ {preco_anunciado:,.2f} | Saldo devedor a assumir: R$ {saldo_devedor:,.2f}."
            )
            acao_sugerida = "Negociar desconto na entrada para compensar o saldo devedor que o comprador assumirá."
        else:
            diagnostico = "Preço com margem para negociação, mas ligeiramente acima da média praticada no bairro."
            acao_sugerida = "Pode ser mantido se o imóvel tiver acabamentos superiores, mas pode demorar mais para receber visitas."
    elif desvio_pct >= -7.0:
        status = "🟢 Preço Justo"
        if is_condicionado:
            diagnostico = (
                f"Custo total com parcelas (R$ {preco_base_comparacao:,.2f}) alinhado com o mercado NBR 14653 (R$ {valor_fechamento_estimado:,.0f}). "
                f"Entrada de R$ {preco_anunciado:,.2f} + R$ {saldo_devedor:,.2f} de saldo devedor."
            )
            acao_sugerida = "Divulgar a facilidade de repasse das parcelas como atrativo para compradores sem crédito bancário aprovado."
        else:
            diagnostico = "Preço perfeitamente alinhado com o valor de fechamento estimado na região."
            acao_sugerida = "Manter o valor. Foco total em marketing e destaque nos portais para acelerar o fechamento."
    else:
        if is_condicionado:
            status = "🔵 Oportunidade (Custo Real)"
            diagnostico = (
                f"Mesmo somando o saldo devedor de R$ {saldo_devedor:,.2f}, o custo total de R$ {preco_base_comparacao:,.2f} "
                f"permanece {desvio_pct:+.1f}% abaixo do valor de mercado (R$ {valor_fechamento_estimado:,.0f})."
            )
            acao_sugerida = "Excelente oportunidade de repasse com desconto real comprovado. Ofertar para investidores com liquidez."
        else:
            status = "🔵 Oportunidade"
            diagnostico = "Preço abaixo da média de mercado. Alta atratividade para compradores e investidores."
            acao_sugerida = "Excelente apelo de venda rápida. Proprietário tem margem para subir o valor se desejar."

    if fator_loc > 1.0:
        diagnostico = f"Preço perfeitamente justificado pela localização no Polo Central da Praça 21 de Abril. {justificativa_loc}"
        if abs(desvio_pct) <= 15.0:
            status = "🟢 Preço Justo"
            acao_sugerida = f"Manter o valor de R$ {preco_anunciado:,.0f}. Ponto comercial nobre/central com alta liquidez e visibilidade."

    if justificativa_condo:
        diagnostico = f"{justificativa_condo} {diagnostico}"

    if justificativa_escala:
        diagnostico += f" {justificativa_escala}"

    return {
        "sucesso": True,
        "codigo": item_feed.get("id"),
        "titulo": item_feed.get("titulo"),
        "bairro": item_feed.get("bairro"),
        "cidade": cidade,
        "area_m2": area,
        "preco_anunciado": preco_anunciado,
        "preco_m2_anunciado": round(preco_anunciado / area, 2) if area else 0,
        "is_condicionado": is_condicionado,
        "tipo_condicao": cond_info.get("tipo_condicao", "Quitado"),
        "detalhes_condicao": cond_info.get("detalhes", ""),
        "saldo_devedor_estimado": saldo_devedor,
        "num_parcelas": cond_info.get("num_parcelas", 0),
        "valor_parcela": cond_info.get("valor_parcela", 0.0),
        "preco_efetivo_total": preco_base_comparacao,
        "preco_m2_efetivo": round(preco_base_comparacao / area, 2) if area else 0,
        "observacao_condicionante": cond_info.get("observacao_interna", ""),
        "valor_fechamento_estimado": valor_fechamento_estimado,
        "valor_oferta_estimado": round(valor_oferta_estimado, -3),
        "faixa_min": faixa_min,
        "faixa_max": faixa_max,
        "mediana_m2_concorrencia": round(mediana_m2_ajustada, 2),
        "mediana_m2_base": round(mediana_m2_oferta, 2),
        "is_condominio_fechado": is_condo,
        "justificativa_condominio": justificativa_condo,
        "fator_localizacao_aplicado": fator_loc,
        "justificativa_localizacao": justificativa_loc if fator_loc > 1.0 else "",
        "fator_escala_aplicado": fator_escala,
        "justificativa_escala": justificativa_escala,
        "fator_oferta_aplicado": fator_of,
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

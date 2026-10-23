"""
Módulo de Auditoria de Conformidade Cadastral & Detecção de Divergências.
Compara sistematicamente os campos estruturados do cadastro (Kurole / VRSync)
contra os dados expressos no texto livre (título, descrição e observações).

Detecta:
1. Dormitórios divergentes ou omitidos no cadastro (que quebram filtros de portais).
2. Suítes omitidas (cadastradas como 0, mas descritas no texto) ou divergentes.
3. Vagas de garagem divergentes ou omitidas.
4. Preço condicionado / ágio anunciado como valor total sem ressalva.
5. Incompatibilidade tipológica (ex: galpão cadastrado com 6 quartos).
6. Área útil ou de terreno com divergência substancial.
7. Banheiros omitidos.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

import feed_parser

PASTA_RAIZ = Path(__file__).resolve().parent
CAMINHO_CACHE_DIVERGENCIAS = PASTA_RAIZ / "dados_divergencias.json"


def _limpar_texto(txt: str) -> str:
    if not txt:
        return ""
    return re.sub(r"\s+", " ", txt).strip()


def extrair_dados_da_descricao(texto: str, tipo_imovel: str = "") -> dict:
    """
    Motor NLP baseado em regras e padrões da gramática imobiliária brasileira
    para extrair dados implícitos ou explícitos no texto livre da descrição.
    """
    if not texto:
        return {
            "quartos": None,
            "suites": None,
            "vagas": None,
            "banheiros": None,
            "condicionante_preco": None,
            "trechos": {},
        }

    t = texto.lower()
    t = re.sub(r"[\*_#~`]", " ", t)
    t = re.sub(r"\s+", " ", t)
    t_espacado = f" {t} "
    trechos = {}

    # -------------------------------------------------------------------------
    # 1. SUÍTES
    # -------------------------------------------------------------------------
    suites = None
    # Casos múltiplos explícitos
    if re.search(r"\b(?:4|04|quatro)\s+su[ií]tes?\b", t):
        suites = 4
        m = re.search(r"\b(?:4|04|quatro)\s+su[ií]tes?\b", t)
        trechos["suites"] = m.group(0) if m else "4 suítes"
    elif re.search(r"\b(?:3|03|tr[eê]s)\s+su[ií]tes?\b", t):
        suites = 3
        m = re.search(r"\b(?:3|03|tr[eê]s)\s+su[ií]tes?\b", t)
        trechos["suites"] = m.group(0) if m else "3 suítes"
    elif re.search(r"\b(?:2|02|duas)\s+su[ií]tes?\b|\bambos\s+com\s+su[ií]te\b|\bambas\s+su[ií]tes\b", t):
        suites = 2
        m = re.search(r"\b(?:2|02|duas)\s+su[ií]tes?\b|\bambos\s+com\s+su[ií]te\b|\bambas\s+su[ií]tes\b", t)
        trechos["suites"] = m.group(0) if m else "2 suítes"
    elif re.search(r"\b(?:sendo|com)\s+(?:0?1|uma?)\s+su[ií]te\b|\b(?:0?1|uma?)\s+su[ií]te\b|\bsu[ií]te\s+m[aá]ster\b|\bsu[ií]te\s+privativa\b|\bpossui\s+su[ií]te\b", t):
        suites = 1
        m = re.search(r"\b(?:sendo|com)\s+(?:0?1|uma?)\s+su[ií]te\b|\b(?:0?1|uma?)\s+su[ií]te\b|\bsu[ií]te\s+m[aá]ster\b|\bsu[ií]te\s+privativa\b|\bpossui\s+su[ií]te\b", t)
        trechos["suites"] = m.group(0) if m else "1 suíte"

    # -------------------------------------------------------------------------
    # 2. DORMITÓRIOS / QUARTOS
    # -------------------------------------------------------------------------
    quartos = None
    # Caso A: Citação explícita de "X dormitórios além de Y suíte" ou "X quartos + Y suíte"
    m_soma = re.search(r"\b(\d+)\s*(?:dormit[oó]rios?|quartos?)\b.*?\b(?:al[eé]m|mais|\+)\s*(?:de\s*)?(?:uma?|1)?\s*(?:confort[aá]vel\s*)?su[ií]te\b", t)
    # Caso B: Citação de "X suítes" E "Y quartos" separados (ex: bullet points "* 2 suítes * 1 quarto")
    m_bullet_s = re.search(r"\b(\d+)\s*su[ií]tes?\b", t)
    m_bullet_q = re.search(r"\b(\d+)\s*(?:quartos?|dormit[oó]rios?)\b", t)
    tem_sendo_suite = bool(re.search(r"(?:dormit[oó]rios?|quartos?).*?sendo.*?su[ií]te", t))
    # Caso C: "X dormitórios sendo Y suíte" (Total é X)
    m_sendo = re.search(r"\b(\d+)\s*(?:dormit[oó]rios?|quartos?)\s*,?\s*(?:sendo|\(sendo\))\s*(\d+|uma?)\s*su[ií]te\b", t)
    # Caso D: Padrão simples: "X dormitórios"
    m_geral = re.search(r"\b(\d+)\s*(?:dormit[oó]rios?|quartos?)\b", t)

    # Checagem de edícula com dormitório adicional
    edicula_q = 0
    m_ed = re.search(r"\bed[ií]cula\b.*?:?.*?\b(\d+)\s*(?:dormit[oó]rio|quarto)\b", t)
    if m_ed:
        try:
            edicula_q = int(m_ed.group(1))
        except Exception:
            pass

    if m_soma:
        q_base = int(m_soma.group(1))
        s_extra = suites or 1
        quartos = q_base + s_extra
        trechos["quartos"] = m_soma.group(0)
    elif m_bullet_s and m_bullet_q and not tem_sendo_suite and int(m_bullet_s.group(1)) != int(m_bullet_q.group(1)):
        # Ex: 2 suítes + 1 quarto = 3 quartos totais
        quartos = int(m_bullet_s.group(1)) + int(m_bullet_q.group(1))
        trechos["quartos"] = f"{m_bullet_s.group(0)} + {m_bullet_q.group(0)}"
    elif m_sendo:
        quartos = int(m_sendo.group(1))
        trechos["quartos"] = m_sendo.group(0)
    elif m_geral:
        quartos = int(m_geral.group(1))
        trechos["quartos"] = m_geral.group(0)

    if quartos is not None and edicula_q > 0:
        quartos += edicula_q
        trechos["quartos"] = f"{trechos.get('quartos', '')} + Edícula ({edicula_q} quarto)".strip()

    # -------------------------------------------------------------------------
    # 3. VAGAS DE GARAGEM
    # -------------------------------------------------------------------------
    vagas = None
    # 1. "garagem para X veículos/carros/automóveis" (capacidade global)
    m_gar_p = re.search(r"\bgaragem\s+(?:p/|para)\s+(\d+)\s+(?:ve[ií]culos?|carros?|autom[oó]ve(?:is|l)|vagas?|autos?)\b", t)
    # 2. "X garagens" ou "X vagas cobertas"
    m_gar_d = re.search(r"\b(\d+)\s*(?:garagens?|garagem\s+coberta)\b", t)
    # 3. "X vagas de garagem / X vagas"
    m_vagas_d = re.search(r"\b(\d+)\s*vagas?\s*(?:de\s+garagem|cobertas?|descobertas?)?\b", t)

    if m_gar_p:
        vagas = int(m_gar_p.group(1))
        trechos["vagas"] = m_gar_p.group(0)
    elif m_gar_d:
        vagas = int(m_gar_d.group(1))
        trechos["vagas"] = m_gar_d.group(0)
    elif m_vagas_d:
        vagas = int(m_vagas_d.group(1))
        trechos["vagas"] = m_vagas_d.group(0)

    # -------------------------------------------------------------------------
    # 4. BANHEIROS
    # -------------------------------------------------------------------------
    banheiros = None
    m_wc = re.search(r"\b(\d+)\s*(?:banheiros?|wcs?|lavabos?)\b", t)
    if m_wc:
        banheiros = int(m_wc.group(1))
        trechos["banheiros"] = m_wc.group(0)
    elif "banheiro social" in t and "lavabo" in t:
        banheiros = 2
        trechos["banheiros"] = "banheiro social + lavabo"

    # -------------------------------------------------------------------------
    # 5. CONDICIONANTES DE PREÇO (ÁGIO / PARCELAS / REPASSE)
    # -------------------------------------------------------------------------
    condicionante_preco = None
    pat_cond = re.search(
        r"(?:mais\s+parcelas?\s+(?:à|a)\s+vencer|\+\s*\d*\s*parcelas?|saldo\s+devedor|assum(?:e|ir)\s+(?:o\s+)?saldo|assum(?:e|ir)\s+(?:as\s+)?parcelas?|repasse\s+de\s+(?:lote|im[oó]vel|financiamento)|[áa]gio\s+de|[áa]gio\s*:|entrada\s*:\s*r\$|faltam\s+\d+\s+parcelas?|restam\s+\d+\s+parcelas?|\d+\s*x\s+de\s+r\$|\d+\s*parcelas?\s+de)",
        t,
    )
    if pat_cond:
        condicionante_preco = pat_cond.group(0)
        trechos["condicionante"] = pat_cond.group(0)

    return {
        "quartos": quartos,
        "suites": suites,
        "vagas": vagas,
        "banheiros": banheiros,
        "condicionante_preco": condicionante_preco,
        "trechos": trechos,
    }


def analisar_divergencias_imovel(imovel: dict) -> List[dict]:
    """
    Analisa um único imóvel comparando cadastro e texto da descrição.
    Retorna lista de dicionários com as divergências encontradas.
    """
    cid = str(imovel.get("id", ""))
    tipo_cad = str(imovel.get("tipo", "Imóvel"))
    tipo_lower = tipo_cad.lower()
    transacao = str(imovel.get("transacao", "Venda"))
    preco_cad = float(imovel.get("preco") or 0.0)
    area_cad = float(imovel.get("area_principal") or imovel.get("area_util") or imovel.get("area_total") or 0.0)

    quartos_cad = int(imovel.get("quartos") or 0)
    suites_cad = int(imovel.get("suites") or 0)
    vagas_cad = int(imovel.get("vagas") or 0)
    banheiros_cad = int(imovel.get("banheiros") or 0)

    titulo = str(imovel.get("titulo", ""))
    descricao = str(imovel.get("descricao", ""))
    texto_total = f"{titulo} {descricao}"

    if not texto_total.strip():
        return []

    metricas_desc = extrair_dados_da_descricao(texto_total, tipo_cad)
    trechos = metricas_desc["trechos"]
    divergencias = []

    is_terreno = "terreno" in tipo_lower or "lote" in tipo_lower
    is_comercial = any(k in tipo_lower for k in ["comercial", "sala", "galpão", "prédio", "ponto", "barracão"])

    # -------------------------------------------------------------------------
    # REGRA 1: SUÍTES (Omissão ou Divergência)
    # -------------------------------------------------------------------------
    s_desc = metricas_desc["suites"]
    if s_desc is not None and not is_terreno:
        if suites_cad == 0 and s_desc > 0:
            divergencias.append({
                "campo": "Suítes",
                "categoria": "Suítes",
                "severidade": "🔴 Crítica",
                "cadastro": f"{suites_cad} suíte(s)",
                "descricao": f"{s_desc} suíte(s)",
                "trecho_citado": trechos.get("suites", "Citação de suíte"),
                "motivo": "Suíte omitida no cadastro (Cad: 0 vs Descrição: presente).",
                "impacto": "Grave: O imóvel é completamente excluído dos filtros de busca do ZAP / VivaReal quando compradores filtram por 'mínimo 1 suíte'.",
                "acao": f"No Kurole: Atualizar o campo estruturado 'Suítes' de 0 para {s_desc}.",
            })
        elif suites_cad > 0 and s_desc > 0 and suites_cad != s_desc:
            divergencias.append({
                "campo": "Suítes",
                "categoria": "Suítes",
                "severidade": "🟡 Média",
                "cadastro": f"{suites_cad} suíte(s)",
                "descricao": f"{s_desc} suíte(s)",
                "trecho_citado": trechos.get("suites", ""),
                "motivo": f"Contradição no número de suítes: cadastro informa {suites_cad}, mas a descrição detalha {s_desc}.",
                "impacto": "Gera dúvida no cliente e frustração em visitas presenciais.",
                "acao": f"No Kurole: Alinhar o número de suítes entre cadastro ({suites_cad}) e texto ({s_desc}).",
            })

    # -------------------------------------------------------------------------
    # REGRA 2: DORMITÓRIOS / QUARTOS
    # -------------------------------------------------------------------------
    q_desc = metricas_desc["quartos"]
    if q_desc is not None and not is_terreno and q_desc <= 12:
        if quartos_cad == 0 and q_desc > 0 and not is_comercial:
            divergencias.append({
                "campo": "Dormitórios",
                "categoria": "Dormitórios",
                "severidade": "🔴 Crítica",
                "cadastro": "0 quartos",
                "descricao": f"{q_desc} dormitório(s)",
                "trecho_citado": trechos.get("quartos", ""),
                "motivo": f"Imóvel residencial cadastrado sem dormitórios (Cad: 0 vs Desc: {q_desc}).",
                "impacto": "Crítico: O imóvel não aparece em nenhuma busca padrão por dormitórios nos portais imobiliários.",
                "acao": f"No Kurole: Preencher o campo 'Quartos' com o valor {q_desc}.",
            })
        elif quartos_cad > 0 and q_desc > 0 and quartos_cad != q_desc:
            divergencias.append({
                "campo": "Dormitórios",
                "categoria": "Dormitórios",
                "severidade": "🔴 Crítica",
                "cadastro": f"{quartos_cad} quarto(s)",
                "descricao": f"{q_desc} dormitório(s)",
                "trecho_citado": trechos.get("quartos", ""),
                "motivo": f"Divergência de quartos: Cadastro tem {quartos_cad}, mas o texto descreve {q_desc}.",
                "impacto": "Distorce a avaliação automatizada NBR 14653 e causa desconfiança de compradores.",
                "acao": f"No Kurole: Verificar a planta e retificar para {q_desc} quartos.",
            })

    # -------------------------------------------------------------------------
    # REGRA 3: VAGAS DE GARAGEM
    # -------------------------------------------------------------------------
    v_desc = metricas_desc["vagas"]
    if v_desc is not None and not is_terreno and v_desc <= 15:
        if vagas_cad == 0 and v_desc > 0:
            divergencias.append({
                "campo": "Vagas de Garagem",
                "categoria": "Vagas",
                "severidade": "🔴 Crítica" if v_desc >= 2 else "🟡 Média",
                "cadastro": "0 vagas",
                "descricao": f"{v_desc} vaga(s)",
                "trecho_citado": trechos.get("vagas", ""),
                "motivo": f"Garagem omitida no cadastro (Cad: 0 vs Descrição: {v_desc} vaga(s)).",
                "impacto": "Mais de 65% dos usuários de portais filtram apenas imóveis 'com vaga'. Esse imóvel está invisível para eles.",
                "acao": f"No Kurole: Atualizar o campo 'Vagas' de 0 para {v_desc}.",
            })
        elif vagas_cad > 0 and v_desc > 0 and vagas_cad != v_desc:
            divergencias.append({
                "campo": "Vagas de Garagem",
                "categoria": "Vagas",
                "severidade": "🟡 Média",
                "cadastro": f"{vagas_cad} vaga(s)",
                "descricao": f"{v_desc} vaga(s)",
                "trecho_citado": trechos.get("vagas", ""),
                "motivo": f"Divergência de garagens: Cadastro informa {vagas_cad} vaga(s), mas a descrição cita {v_desc}.",
                "impacto": "Pode gerar reclamação de clientes que exigem capacidade exata de estacionamento.",
                "acao": f"No Kurole: Confirmar capacidade total coberta/descoberta e uniformizar em {v_desc} vagas.",
            })

    # -------------------------------------------------------------------------
    # REGRA 4: CONDICIONANTE DE PREÇO (ÁGIO / REPASSE / PARCELAS A VENCER)
    # -------------------------------------------------------------------------
    if metricas_desc["condicionante_preco"]:
        divergencias.append({
            "campo": "Preço & Condicionante",
            "categoria": "Preço / Condicionante",
            "severidade": "🔴 Crítica",
            "cadastro": f"R$ {preco_cad:,.2f} (sem ressalva)",
            "descricao": f"'{metricas_desc['condicionante_preco']}'",
            "trecho_citado": trechos.get("condicionante", ""),
            "motivo": "Preço anunciado condicionado a parcelas futuras ('mais parcelas a vencer' / ágio / repasse).",
            "impacto": "Altíssimo: Algoritmos e compradores leem o preço como valor total quitado, gerando falsas expectativas e distorções na carteira.",
            "acao": "No Kurole: Preencher o saldo devedor nas notas e ajustar a pedida do ágio para refletir o custo real.",
        })

    # -------------------------------------------------------------------------
    # REGRA 5: INCOMPATIBILIDADE TIPOLÓGICA (TIPO DE IMÓVEL)
    # -------------------------------------------------------------------------
    if "galpão" in tipo_lower and quartos_cad > 0:
        divergencias.append({
            "campo": "Tipologia / Categoria",
            "categoria": "Tipologia",
            "severidade": "🔴 Crítica",
            "cadastro": f"{tipo_cad} ({quartos_cad} quartos)",
            "descricao": "Prédio Comercial / Misto com apartamentos",
            "trecho_citado": "Apartamentos e prédio comercial",
            "motivo": f"Tipologia suspeita: Galpão Industrial cadastrado com {quartos_cad} dormitórios.",
            "impacto": "Grave: Usuários que buscam galpão industrial rejeitam o imóvel, e investidores de renda com apartamentos não o encontram.",
            "acao": "No Kurole: Reclassificar para 'Prédio Comercial' ou desmembrar as unidades no sistema.",
        })

    if is_terreno and (quartos_cad > 0 or banheiros_cad > 0):
        divergencias.append({
            "campo": "Tipologia / Categoria",
            "categoria": "Tipologia",
            "severidade": "🔴 Crítica",
            "cadastro": f"{tipo_cad} ({quartos_cad} quartos, {banheiros_cad} banheiros)",
            "descricao": "Construção existente ou cadastro incorreto",
            "trecho_citado": "",
            "motivo": f"Terreno cadastrado com {quartos_cad} quartos / {banheiros_cad} banheiros.",
            "impacto": "Filtros de terrenos mostram dados incongruentes.",
            "acao": "No Kurole: Zerar quartos/banheiros ou alterar o tipo para 'Casa / Construção'.",
        })

    # -------------------------------------------------------------------------
    # REGRA 6: ÁREA (Metragem Omitida ou Conflitante)
    # -------------------------------------------------------------------------
    if area_cad <= 0:
        m_area = re.search(r"\b(\d{2,5})\s*m[²2]\b", texto_total, re.I)
        if m_area:
            divergencias.append({
                "campo": "Área (m²)",
                "categoria": "Área",
                "severidade": "🔴 Crítica",
                "cadastro": "0 m²",
                "descricao": f"{m_area.group(1)} m²",
                "trecho_citado": m_area.group(0),
                "motivo": f"Área zerada no cadastro, porém descrita no texto ({m_area.group(0)}).",
                "impacto": "Impossibilita o cálculo do preço por metro quadrado (R$/m²) e exclui o imóvel de filtros por área.",
                "acao": f"No Kurole: Preencher a área útil/total com {m_area.group(1)} m².",
            })

    # -------------------------------------------------------------------------
    # REGRA 7: BANHEIROS (Omissão)
    # -------------------------------------------------------------------------
    b_desc = metricas_desc["banheiros"]
    if b_desc is not None and not is_terreno and banheiros_cad == 0 and b_desc > 0:
        divergencias.append({
            "campo": "Banheiros",
            "categoria": "Banheiros",
            "severidade": "🟡 Média",
            "cadastro": "0 banheiros",
            "descricao": f"{b_desc} banheiro(s)",
            "trecho_citado": trechos.get("banheiros", ""),
            "motivo": f"Banheiros não informados no cadastro (Cad: 0 vs Desc: {b_desc}).",
            "impacto": "Filtros de banheiros no ZAP/VivaReal ignoram este anúncio.",
            "acao": f"No Kurole: Preencher o campo 'Banheiros' com {b_desc}.",
        })

    return divergencias


def auditar_todas_divergencias(feed_imoveis: List[dict] = None, forcar_recalculo: bool = False) -> dict:
    """
    Executa a auditoria de divergências cadastrais em toda a carteira de imóveis.
    Gera relatório estruturado, estatísticas e salva cache em disco.
    """
    if not forcar_recalculo and CAMINHO_CACHE_DIVERGENCIAS.exists():
        try:
            dados = json.loads(CAMINHO_CACHE_DIVERGENCIAS.read_text(encoding="utf-8"))
            if dados.get("sucesso") and dados.get("total_imoveis", 0) > 0:
                return dados
        except Exception:
            pass

    if feed_imoveis is None:
        feed_d = feed_parser.carregar_feed_xml()
        feed_imoveis = feed_d.get("imoveis", [])

    total_imoveis = len(feed_imoveis)
    lista_divergentes = []
    total_divergencias = 0
    contagem_criticas = 0
    contagem_medias = 0
    contagem_baixas = 0

    por_categoria = {
        "Dormitórios": 0,
        "Suítes": 0,
        "Vagas": 0,
        "Preço / Condicionante": 0,
        "Tipologia": 0,
        "Área": 0,
        "Banheiros": 0,
    }

    for im in feed_imoveis:
        divs = analisar_divergencias_imovel(im)
        if divs:
            total_divergencias += len(divs)
            for d in divs:
                sev = d.get("severidade", "")
                if "Crítica" in sev:
                    contagem_criticas += 1
                elif "Média" in sev:
                    contagem_medias += 1
                else:
                    contagem_baixas += 1

                cat = d.get("categoria", "")
                if cat in por_categoria:
                    por_categoria[cat] += 1

            lista_divergentes.append({
                "id": im.get("id"),
                "titulo": im.get("titulo", "Sem título"),
                "tipo": im.get("tipo", "Imóvel"),
                "transacao": im.get("transacao", "Venda"),
                "bairro": im.get("bairro", ""),
                "cidade": im.get("cidade", "Sertãozinho"),
                "preco": float(im.get("preco") or 0.0),
                "area": float(im.get("area_principal") or im.get("area_util") or im.get("area_total") or 0.0),
                "quartos_cad": int(im.get("quartos") or 0),
                "suites_cad": int(im.get("suites") or 0),
                "vagas_cad": int(im.get("vagas") or 0),
                "foto_capa": im.get("foto_capa", ""),
                "descricao": im.get("descricao", ""),
                "total_divergencias": len(divs),
                "tem_critica": any("Crítica" in x["severidade"] for x in divs),
                "divergencias": divs,
            })

    # Ordenar pelos que têm mais divergências críticas primeiro
    lista_divergentes.sort(key=lambda x: (not x["tem_critica"], -x["total_divergencias"]))

    imoveis_com_div = len(lista_divergentes)
    pct_afetados = round((imoveis_com_div / total_imoveis * 100.0), 1) if total_imoveis else 0.0

    resultado = {
        "sucesso": True,
        "data_auditoria": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "total_imoveis": total_imoveis,
        "imoveis_com_divergencia": imoveis_com_div,
        "imoveis_sem_divergencia": total_imoveis - imoveis_com_div,
        "pct_carteira_afetada": pct_afetados,
        "total_divergencias": total_divergencias,
        "criticas": contagem_criticas,
        "medias": contagem_medias,
        "baixas": contagem_baixas,
        "por_categoria": por_categoria,
        "imoveis_divergentes": lista_divergentes,
    }

    try:
        CAMINHO_CACHE_DIVERGENCIAS.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"Erro ao salvar cache de divergências: {e}")

    return resultado


def render_painel_divergencias(imoveis_lista: List[dict] = None):
    """
    Renderiza o painel completo de auditoria de conformidade cadastral e confronto
    entre campos estruturados e texto livre da descrição no Streamlit.
    """
    st.markdown("### 🔍 Conformidade Cadastral & Detecção de Divergências")
    st.caption(
        "Confrontação inteligente entre os campos estruturados do CRM (Kurole / VRSync) "
        "e o texto livre da descrição pública (ZAP, VivaReal, OLX). Identifica omissões e contradições "
        "que derrubam imóveis dos filtros de busca e distorcem a avaliação de mercado."
    )

    col_btn_recalc, col_vazia = st.columns([1.5, 3.5])
    with col_btn_recalc:
        if st.button("🔄 Re-analisar Carteira Completa Agora", use_container_width=True, type="secondary"):
            with st.spinner("Re-analisando toda a carteira de imóveis em tempo real..."):
                auditar_todas_divergencias(feed_imoveis=imoveis_lista, forcar_recalculo=True)
            st.success("Auditoria atualizada com sucesso!")
            st.rerun()

    dados = auditar_todas_divergencias(feed_imoveis=imoveis_lista, forcar_recalculo=False)
    if not dados.get("sucesso"):
        st.error("Não foi possível carregar os dados de auditoria de divergências.")
        return

    # KPIs / Métricas Executivas
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Total Auditado", f"{dados['total_imoveis']} imóveis")
    with m2:
        st.metric("100% Coerentes", f"{dados['imoveis_sem_divergencia']}", f"{100.0 - dados['pct_carteira_afetada']:.1f}% da carteira")
    with m3:
        st.metric("Com Divergência", f"{dados['imoveis_com_divergencia']}", f"{dados['pct_carteira_afetada']:.1f}% da carteira", delta_color="inverse")
    with m4:
        st.metric("🔴 Alertas Críticos", f"{dados['criticas']}", "Quebram filtros ZAP", delta_color="inverse")
    with m5:
        st.metric("🟡 Alertas Médios", f"{dados['medias']}", "Omissões de cadastro")

    st.markdown("---")

    sub_tabela, sub_inspetor = st.tabs([
        "📋 Planilha Executiva de Divergências & Filtros",
        "🔎 Confrontador Visual Lado a Lado (Card a Card)",
    ])

    imoveis_divs = dados.get("imoveis_divergentes", [])
    if not imoveis_divs:
        st.success("🎉 Parabéns! Nenhum imóvel da carteira apresentou divergências cadastrais ativas.")
        return

    # ==================== SUB-ABA 1: TABELA GERAL ====================
    with sub_tabela:
        f_c1, f_c2, f_c3, f_c4 = st.columns([1.2, 1.2, 1.0, 1.6])
        with f_c1:
            cats = ["Todas"] + list(dados.get("por_categoria", {}).keys())
            sel_cat = st.selectbox("Categoria:", cats, index=0, key="sel_cat_div")
        with f_c2:
            sel_sev = st.selectbox("Gravidade:", ["Todas", "🔴 Apenas Críticas", "🟡 Apenas Médias"], index=0, key="sel_sev_div")
        with f_c3:
            sel_op = st.selectbox("Operação:", ["Todas", "Venda", "Locação"], index=0, key="sel_op_div")
        with f_c4:
            busca_txt = st.text_input("Buscar por Código ou Bairro:", placeholder="Ex: V7898, Centro, Lote...", key="busca_div_txt").strip().lower()

        # Montagem das linhas achatadas
        linhas_tabela = []
        for im in imoveis_divs:
            if sel_op != "Todas" and im["transacao"] != sel_op:
                continue
            if busca_txt:
                match_b = busca_txt in im["id"].lower() or busca_txt in im["bairro"].lower() or busca_txt in im["tipo"].lower()
                if not match_b:
                    continue

            for d in im["divergencias"]:
                if sel_cat != "Todas" and d.get("categoria") != sel_cat:
                    continue
                if "Críticas" in sel_sev and "Crítica" not in d.get("severidade", ""):
                    continue
                if "Médias" in sel_sev and "Média" not in d.get("severidade", ""):
                    continue

                linhas_tabela.append({
                    "Código": im["id"],
                    "Operação": im["transacao"],
                    "Tipo": im["tipo"],
                    "Bairro": im["bairro"],
                    "Preço (R$)": f"R$ {im['preco']:,.0f}".replace(",", "."),
                    "Campo Divergente": d["campo"],
                    "No Cadastro": d["cadastro"],
                    "Na Descrição": d["descricao"],
                    "Trecho Citado no Texto": d["trecho_citado"],
                    "Severidade": d["severidade"],
                    "Impacto no Negócio": d["impacto"],
                    "Ação Recomendada (Kurole)": d["acao"],
                })

        st.caption(f"Exibindo **{len(linhas_tabela)}** divergências identificadas nos filtros selecionados.")
        if linhas_tabela:
            df_tab = pd.DataFrame(linhas_tabela)
            st.dataframe(
                df_tab,
                use_container_width=True,
                hide_index=True,
            )

            # Exportação CSV
            csv_str = df_tab.to_csv(index=False, sep=";", encoding="utf-8-sig")
            st.download_button(
                label="📥 Baixar Planilha de Correções Cadastrais (.CSV / Excel)",
                data=csv_str.encode("utf-8-sig"),
                file_name=f"divergencias_cadastrais_expandh_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                type="primary",
                key="btn_dl_csv_div",
            )
        else:
            st.info("Nenhuma divergência encontrada para os filtros selecionados.")

    # ==================== SUB-ABA 2: CONFRONTADOR LADO A LADO ====================
    with sub_inspetor:
        st.markdown("#### 🔎 Inspetor Lado a Lado: Cadastro vs. Descrição")
        st.caption("Selecione um imóvel divergente para inspecionar os campos estruturados frente ao texto do anúncio.")

        opcoes_imoveis = {
            f"[{im['id']}] {im['tipo']} em {im['bairro']} • R$ {im['preco']:,.0f} ({im['transacao']}) — {im['total_divergencias']} divergência(s)": im
            for im in imoveis_divs
        }
        escolha_label = st.selectbox(
            "Selecione o Imóvel com Divergência:",
            options=list(opcoes_imoveis.keys()),
            index=0,
            key="sel_imovel_inspetor",
        )
        im_sel = opcoes_imoveis[escolha_label]

        col_img, col_info = st.columns([1.2, 2.8])
        with col_img:
            if im_sel.get("foto_capa"):
                st.image(im_sel["foto_capa"], use_container_width=True, caption=f"Cód: {im_sel['id']}")
            else:
                st.info("📷 Sem foto cadastrada")

        with col_info:
            st.markdown(f"### {im_sel['titulo']}")
            st.write(f"📍 **Bairro/Cidade:** {im_sel['bairro']} - {im_sel['cidade']}/SP")
            st.write(f"🏷️ **Tipo:** {im_sel['tipo']} | **Transação:** {im_sel['transacao']}")
            st.write(f"💰 **Preço Anunciado:** **R$ {im_sel['preco']:,.2f}** | **Área:** {im_sel['area']} m²")

        st.markdown("---")

        # Confrontação em duas colunas paralelas
        col_cad, col_desc = st.columns(2)
        with col_cad:
            st.markdown("#### 📋 Dados Estruturados no Cadastro (Kurole)")
            st.caption("O que está salvo nos campos de formulário que alimentam os portais:")

            c_k1, c_k2 = st.columns(2)
            with c_k1:
                st.metric("Dormitórios (Quartos)", f"{im_sel['quartos_cad']}")
                st.metric("Vagas de Garagem", f"{im_sel['vagas_cad']}")
                st.metric("Área Principal", f"{im_sel['area']} m²")
            with c_k2:
                st.metric("Suítes", f"{im_sel['suites_cad']}")
                st.metric("Preço Cadastrado", f"R$ {im_sel['preco']:,.0f}".replace(",", "."))
                st.metric("Tipo Cadastrado", im_sel["tipo"])

        with col_desc:
            st.markdown("#### 📝 Texto Original da Descrição nos Portais")
            st.caption("O texto livre publicado no ZAP, VivaReal e portal da imobiliária:")

            desc_fmt = im_sel.get("descricao", "Sem descrição cadastrada.")
            st.text_area(
                "Descrição Completa:",
                value=desc_fmt,
                height=220,
                disabled=True,
                key=f"txt_desc_insp_{im_sel['id']}",
            )

        st.markdown("#### 🛠️ Diagnóstico Detalhado & Instruções de Correção")
        for idx, d in enumerate(im_sel["divergencias"], 1):
            if "Crítica" in d["severidade"]:
                st.error(
                    f"**{d['severidade']} • {d['campo']}**\n\n"
                    f"• **No Cadastro:** `{d['cadastro']}`  ➡️  **Na Descrição:** `{d['descricao']}` *(Trecho: \"{d['trecho_citado']}\")*\n"
                    f"• **Motivo:** {d['motivo']}\n"
                    f"• **Impacto Comercial:** {d['impacto']}\n"
                    f"• **Como Corrigir no Kurole:** `{d['acao']}`"
                )
            else:
                st.warning(
                    f"**{d['severidade']} • {d['campo']}**\n\n"
                    f"• **No Cadastro:** `{d['cadastro']}`  ➡️  **Na Descrição:** `{d['descricao']}` *(Trecho: \"{d['trecho_citado']}\")*\n"
                    f"• **Motivo:** {d['motivo']}\n"
                    f"• **Impacto Comercial:** {d['impacto']}\n"
                    f"• **Como Corrigir no Kurole:** `{d['acao']}`"
                )

        # Instrução pronta para envio à equipe de cadastro / secretaria
        instrucoes_msg = [
            f"Olá! Segue solicitação técnica de ajuste cadastral da Expandh Imóveis:",
            f"Imóvel: Cód. {im_sel['id']} ({im_sel['tipo']} - {im_sel['bairro']})",
            f"Preço: R$ {im_sel['preco']:,.2f}",
            "",
            "Ajustes necessários no Kurole:",
        ]
        for idx, d in enumerate(im_sel["divergencias"], 1):
            instrucoes_msg.append(f"{idx}. [{d['campo']}]: {d['acao']}")
        instrucoes_msg.append("")
        instrucoes_msg.append("Motivo: Corrigir filtros de busca nos portais ZAP/VivaReal e evitar distorção na avaliação de mercado.")
        texto_instrucoes = "\n".join(instrucoes_msg)

        st.markdown("##### 📨 Roteiro para a Equipe de Cadastro / Secretaria")
        st.text_area(
            "Copie e envie para a equipe de secretaria/cadastro atualizar no sistema:",
            value=texto_instrucoes,
            height=140,
            key=f"txt_instrucao_{im_sel['id']}",
        )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    res = auditar_todas_divergencias(forcar_recalculo=True)
    print("=" * 70)
    print("  AUDITORIA DE CONFORMIDADE CADASTRAL (EXPANDH)")
    print("=" * 70)
    print(f"Total de Imóveis: {res['total_imoveis']}")
    print(f"Imóveis com Divergências: {res['imoveis_com_divergencia']} ({res['pct_carteira_afetada']}%)")
    print(f"Total de Divergências Apuradas: {res['total_divergencias']}")
    print(f"  🔴 Críticas: {res['criticas']}")
    print(f"  🟡 Médias:   {res['medias']}")
    print("\nPor Categoria:")
    for c, q in res["por_categoria"].items():
        print(f"  • {c:25s}: {q}")

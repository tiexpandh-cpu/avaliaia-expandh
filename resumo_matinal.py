"""
Módulo de Resumo Matinal e Monitoramento Diário da Carteira Expandh.
Compara o feed do Kurole (KSI) com o último snapshot para detectar:
1. Novos imóveis cadastrados
2. Imóveis com alteração de preço (reduções ou aumentos)
3. Top 3 Oportunidades do Dia (preço abaixo da NBR 14653 para compradores)
4. Top 3 Imóveis Críticos para Reprecificação (sobrepreço para contato com proprietários)
5. Gera argumentários prontos para WhatsApp.
"""
import argparse
import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import feed_parser
import reavaliacao_carteira
import argumentario

PASTA_RAIZ = Path(__file__).resolve().parent
PASTA_HISTORICO = PASTA_RAIZ / "historico_briefings"
CAMINHO_SNAPSHOT = PASTA_HISTORICO / "snapshot_anterior.json"
CAMINHO_ULTIMO_BRIEFING = PASTA_HISTORICO / "ultimo_briefing.json"
CAMINHO_CACHE_AUDITORIA = PASTA_RAIZ / "dados_auditoria_completa.json"


def _safe_float(val, default: float = 0.0) -> float:
    """Converte valores com segurança evitando erros de NoneType ou strings inválidas."""
    try:
        if val is None or val == "":
            return default
        return float(val)
    except Exception:
        return default


def carregar_snapshot_anterior() -> Dict[str, dict]:
    """Carrega o snapshot anterior de imóveis indexados por código."""
    if CAMINHO_SNAPSHOT.exists():
        try:
            dados = json.loads(CAMINHO_SNAPSHOT.read_text(encoding="utf-8"))
            if isinstance(dados, dict) and "imoveis_mapa" in dados:
                return dados["imoveis_mapa"]
            if isinstance(dados, list):
                return {str(x.get("id")): x for x in dados if x.get("id")}
        except Exception as e:
            print(f"Erro ao carregar snapshot anterior: {e}")
    return {}


def salvar_snapshot_atual(imoveis_lista: List[dict]):
    """Salva o snapshot atual para permitir comparações no próximo dia."""
    PASTA_HISTORICO.mkdir(parents=True, exist_ok=True)
    mapa = {}
    for im in imoveis_lista:
        cid = str(im.get("id", ""))
        if not cid:
            continue
        mapa[cid] = {
            "id": cid,
            "titulo": im.get("titulo", ""),
            "tipo": im.get("tipo", ""),
            "transacao": im.get("transacao", "Venda"),
            "preco": float(im.get("preco") or 0.0),
            "bairro": im.get("bairro", ""),
            "cidade": im.get("cidade", ""),
            "area_util": float(im.get("area_util") or im.get("area_total") or 0.0),
            "data_registro": datetime.now().isoformat(),
        }

    envelope = {
        "data_snapshot": datetime.now().isoformat(),
        "total_imoveis": len(mapa),
        "imoveis_mapa": mapa,
    }
    CAMINHO_SNAPSHOT.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")


def detectar_mudancas(imoveis_atuais: List[dict], snapshot_ant: Dict[str, dict]) -> Tuple[List[dict], List[dict], List[dict]]:
    """Compara o feed atual com o snapshot anterior para identificar novidades."""
    novos = []
    mudancas_preco = []
    atuais_map = {str(im.get("id")): im for im in imoveis_atuais if im.get("id")}

    if not snapshot_ant:
        # Se não há snapshot prévio, não marcamos todos como novos para evitar falso alarme
        return [], [], []

    # Detectar novos e alterações de preço
    for cid, im in atuais_map.items():
        preco_atual = float(im.get("preco") or 0.0)
        if cid not in snapshot_ant:
            novos.append({
                "id": cid,
                "titulo": im.get("titulo", "Novo Imóvel"),
                "tipo": im.get("tipo", "Imóvel"),
                "transacao": im.get("transacao", "Venda"),
                "bairro": im.get("bairro", "Sertãozinho"),
                "preco": preco_atual,
                "preco_formatado": f"{preco_atual:,.0f}".replace(",", "."),
            })
        else:
            ant = snapshot_ant[cid]
            preco_ant = float(ant.get("preco") or 0.0)
            if preco_ant > 0 and abs(preco_atual - preco_ant) >= 100.0:
                diff = preco_atual - preco_ant
                pct = round((diff / preco_ant) * 100.0, 1)
                mudancas_preco.append({
                    "id": cid,
                    "titulo": im.get("titulo", ant.get("titulo", "")),
                    "tipo": im.get("tipo", ant.get("tipo", "")),
                    "transacao": im.get("transacao", "Venda"),
                    "bairro": im.get("bairro", ant.get("bairro", "")),
                    "preco_antigo": preco_ant,
                    "preco_novo": preco_atual,
                    "preco_antigo_fmt": f"{preco_ant:,.0f}".replace(",", "."),
                    "preco_novo_fmt": f"{preco_atual:,.0f}".replace(",", "."),
                    "diferenca": diff,
                    "diferenca_fmt": f"{abs(diff):,.0f}".replace(",", "."),
                    "variacao_pct": pct,
                    "tipo_mudanca": "reducao" if diff < 0 else "aumento",
                })

    # Detectar desativados / vendidos
    desativados = []
    for cid, ant in snapshot_ant.items():
        if cid not in atuais_map:
            desativados.append(ant)

    return novos, mudancas_preco, desativados


def obter_auditoria_completa() -> dict:
    """Lê os dados da auditoria completa salva em disco."""
    if CAMINHO_CACHE_AUDITORIA.exists():
        try:
            return json.loads(CAMINHO_CACHE_AUDITORIA.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Erro ao ler cache de auditoria: {e}")
    return {}


def gerar_briefing_matinal(forcar_download: bool = False) -> dict:
    """Gera o relatório matinal consolidado da Expandh."""
    hoje_str = date.today().strftime("%d/%m/%Y")
    hora_str = datetime.now().strftime("%H:%M")

    # 1. Carregar feed do Kurole
    url_feed = feed_parser.URL_FEED_PADRAO
    feed_res = feed_parser.carregar_feed_xml(url_feed)
    imoveis_lista = feed_res.get("imoveis", [])
    cabecalho = feed_res.get("cabecalho", {})

    if not imoveis_lista:
        return {"sucesso": False, "erro": "Não foi possível carregar o feed do Kurole."}

    # 2. Carregar snapshot anterior e comparar
    snapshot_ant = carregar_snapshot_anterior()
    novos, mudancas_preco, desativados = detectar_mudancas(imoveis_lista, snapshot_ant)

    # 3. Carregar dados de auditoria
    dados_aud = obter_auditoria_completa()
    aud_lista = dados_aud.get("imoveis", [])

    # Indexar auditoria por ID
    aud_map = {}
    for item in aud_lista:
        cid = str(item.get("Código") or item.get("id") or "")
        if cid:
            aud_map[cid] = item

    # 4. Estatísticas gerais
    total_ativos = len(imoveis_lista)
    total_vendas = sum(1 for x in imoveis_lista if x.get("transacao") == "Venda")
    total_locacao = sum(1 for x in imoveis_lista if x.get("transacao") == "Locação")

    q_justo = sum(1 for x in aud_lista if "Preço Justo" in str(x.get("Status", "")))
    q_muito_acima = sum(1 for x in aud_lista if "Muito Acima" in str(x.get("Status", "")))
    q_acima = sum(1 for x in aud_lista if "Acima do Mercado" in str(x.get("Status", "")) or "Levemente Acima" in str(x.get("Status", "")))
    q_oportunidade = sum(1 for x in aud_lista if "Oportunidade" in str(x.get("Status", "")))

    # 5. Top Oportunidades do Dia (Menor desvio / maior desconto em relação à NBR)
    # Filtro anti-armadilha: exclui imóveis com condicionante de preço (ágio / parcelas a vencer)
    oportunidades_candidatas = [
        x for x in aud_lista
        if ("Oportunidade" in str(x.get("Status", "")) or _safe_float(x.get("Desvio_Num")) < -5.0)
        and not x.get("Condicionante Preço", False)
        and not any(k in str(x.get("Status", "")) for k in ["Ágio", "Parcelas", "Condicionado"])
    ]
    oportunidades_candidatas.sort(key=lambda x: _safe_float(x.get("Desvio_Num")))

    def _formatar_item_oportunidade(item):
        cid = str(item.get("Código", ""))
        preco_anunc = _safe_float(item.get("Preço Anunciado (R$)"))
        preco_merc = _safe_float(item.get("Valor Mercado Estimado (R$)"))
        desvio = _safe_float(item.get("Desvio_Num"))
        trans = item.get("Transação", "Venda" if cid.startswith("V") else "Locação")

        msg_wa = argumentario.gerar_argumentario_whatsapp(
            dados_imovel=item,
            tipo_publico="comprador",
            nome_cliente="Investidor/Comprador" if trans == "Venda" else "Prezado(a) Locatário(a)",
            nome_corretor="Equipe Expandh"
        )
        link_wa = argumentario.criar_link_direto_whatsapp(mensagem=msg_wa)

        return {
            "codigo": cid,
            "titulo": item.get("Título", "Imóvel"),
            "tipo": item.get("Tipo", "Imóvel"),
            "transacao": trans,
            "bairro": item.get("Bairro", "Sertãozinho"),
            "preco_anunciado": preco_anunc,
            "preco_anunciado_fmt": f"{preco_anunc:,.0f}".replace(",", "."),
            "valor_mercado": preco_merc,
            "valor_mercado_fmt": f"{preco_merc:,.0f}".replace(",", "."),
            "desvio_pct": desvio,
            "desvio_fmt": f"{desvio:.1f}%",
            "diagnostico": item.get("Diagnóstico", "Preço altamente competitivo."),
            "mensagem_wa": msg_wa,
            "link_wa": link_wa,
        }

    op_venda_cands = [x for x in oportunidades_candidatas if x.get("Transação") == "Venda" or str(x.get("Código", "")).startswith("V")]
    op_loc_cands = [x for x in oportunidades_candidatas if x.get("Transação") == "Locação" or str(x.get("Código", "")).startswith("L")]

    top_oportunidades = [_formatar_item_oportunidade(x) for x in oportunidades_candidatas[:3]]
    top_oportunidades_venda = [_formatar_item_oportunidade(x) for x in op_venda_cands[:3]]
    top_oportunidades_locacao = [_formatar_item_oportunidade(x) for x in op_loc_cands[:3]]

    # 6. Alertas de Reprecificação (Maior sobrepreço em relação à NBR)
    sobrepreco_candidatas = [
        x for x in aud_lista
        if "Muito Acima" in str(x.get("Status", "")) or _safe_float(x.get("Desvio_Num")) > 15.0
    ]
    sobrepreco_candidatas.sort(key=lambda x: _safe_float(x.get("Desvio_Num")), reverse=True)

    def _formatar_item_reprecificacao(item):
        cid = str(item.get("Código", ""))
        preco_anunc = _safe_float(item.get("Preço Anunciado (R$)"))
        preco_merc = _safe_float(item.get("Valor Mercado Estimado (R$)"))
        desvio = _safe_float(item.get("Desvio_Num"))
        trans = item.get("Transação", "Venda" if cid.startswith("V") else "Locação")

        msg_wa = argumentario.gerar_argumentario_whatsapp(
            dados_imovel=item,
            tipo_publico="proprietario",
            nome_cliente="Proprietário(a)",
            nome_corretor="Equipe Expandh"
        )
        link_wa = argumentario.criar_link_direto_whatsapp(mensagem=msg_wa)

        return {
            "codigo": cid,
            "titulo": item.get("Título", "Imóvel"),
            "tipo": item.get("Tipo", "Imóvel"),
            "transacao": trans,
            "bairro": item.get("Bairro", "Sertãozinho"),
            "preco_anunciado": preco_anunc,
            "preco_anunciado_fmt": f"{preco_anunc:,.0f}".replace(",", "."),
            "valor_mercado": preco_merc,
            "valor_mercado_fmt": f"{preco_merc:,.0f}".replace(",", "."),
            "desvio_pct": desvio,
            "desvio_fmt": f"+{desvio:.1f}%",
            "diagnostico": item.get("Diagnóstico", "Sobrepreço crítico com perda de liquidez."),
            "mensagem_wa": msg_wa,
            "link_wa": link_wa,
        }

    rep_venda_cands = [x for x in sobrepreco_candidatas if x.get("Transação") == "Venda" or str(x.get("Código", "")).startswith("V")]
    rep_loc_cands = [x for x in sobrepreco_candidatas if x.get("Transação") == "Locação" or str(x.get("Código", "")).startswith("L")]

    top_reprecificacao = [_formatar_item_reprecificacao(x) for x in sobrepreco_candidatas[:3]]
    top_reprecificacao_venda = [_formatar_item_reprecificacao(x) for x in rep_venda_cands[:3]]
    top_reprecificacao_locacao = [_formatar_item_reprecificacao(x) for x in rep_loc_cands[:3]]

    briefing = {
        "sucesso": True,
        "data_briefing": hoje_str,
        "hora_geracao": hora_str,
        "timestamp": datetime.now().isoformat(),
        "total_ativos": total_ativos,
        "total_vendas": total_vendas,
        "total_locacao": total_locacao,
        "estatisticas_diagnostico": {
            "preco_justo": q_justo,
            "muito_acima": q_muito_acima,
            "levemente_acima": q_acima,
            "oportunidades": q_oportunidade,
        },
        "estatisticas_vendas": {
            "total": total_vendas,
            "oportunidades": len(op_venda_cands),
            "muito_acima": len(rep_venda_cands),
        },
        "estatisticas_locacao": {
            "total": total_locacao,
            "oportunidades": len(op_loc_cands),
            "muito_acima": len(rep_loc_cands),
        },
        "novos_imoveis": novos,
        "total_novos": len(novos),
        "mudancas_preco": mudancas_preco,
        "total_mudancas_preco": len(mudancas_preco),
        "top_oportunidades": top_oportunidades,
        "top_oportunidades_venda": top_oportunidades_venda,
        "top_oportunidades_locacao": top_oportunidades_locacao,
        "top_reprecificacao": top_reprecificacao,
        "top_reprecificacao_venda": top_reprecificacao_venda,
        "top_reprecificacao_locacao": top_reprecificacao_locacao,
        "data_kurole_pub": cabecalho.get("data_publicacao", ""),
    }

    # Salvar no histórico
    PASTA_HISTORICO.mkdir(parents=True, exist_ok=True)
    nome_arquivo_dia = f"briefing_{date.today().isoformat()}.json"
    (PASTA_HISTORICO / nome_arquivo_dia).write_text(json.dumps(briefing, ensure_ascii=False, indent=2), encoding="utf-8")
    CAMINHO_ULTIMO_BRIEFING.write_text(json.dumps(briefing, ensure_ascii=False, indent=2), encoding="utf-8")

    # Atualizar snapshot para a próxima rodada
    salvar_snapshot_atual(imoveis_lista)

    return briefing


def obter_ou_carregar_ultimo_briefing(forcar_atualizacao: bool = False) -> dict:
    """Retorna o briefing de hoje já gerado ou executa a geração se não existir."""
    if not forcar_atualizacao and CAMINHO_ULTIMO_BRIEFING.exists():
        try:
            dados = json.loads(CAMINHO_ULTIMO_BRIEFING.read_text(encoding="utf-8"))
            if dados.get("data_briefing") == date.today().strftime("%d/%m/%Y"):
                return dados
        except Exception:
            pass
def render_painel_briefing(departamento: str = "Total"):
    """Renderiza a aba interativa de Briefing Matinal & Oportunidades no Streamlit, adaptada por departamento."""
    import streamlit as st

    c_tit, c_btn = st.columns([3.5, 1.2])
    with c_tit:
        if departamento == "Vendas":
            st.subheader("☀️ Briefing Matinal • Departamento de VENDAS")
            st.caption("Oportunidades com deságio NBR e radar de reprecificação urgente para compradores e proprietários de venda.")
        elif departamento == "Locação":
            st.subheader("☀️ Briefing Matinal • Departamento de LOCAÇÃO")
            st.caption("Oportunidades de locação com cap rate atrativo e radar de aluguéis acima da média de mercado.")
        else:
            st.subheader("☀️ Briefing Matinal Expandh • Inteligência da Carteira")
            st.caption("Visão estratégica do dia para a diretoria e equipe de corretores.")
    with c_btn:
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Atualizar Briefing Agora", type="secondary", use_container_width=True, help="Recalcula as oportunidades e sincroniza com o feed mais recente"):
            st.session_state["forcar_refresh_briefing"] = True
            st.rerun()

    forcar = st.session_state.pop("forcar_refresh_briefing", False)
    with st.spinner("Compilando briefing matinal e oportunidades..."):
        briefing = obter_ou_carregar_ultimo_briefing(forcar_atualizacao=forcar)

    if not briefing or not briefing.get("sucesso"):
        st.warning("Não foi possível compilar o briefing no momento.")
        return

    # Banner informativo com data e hora (Estilo Expandh BI)
    if departamento == "Vendas":
        badge_feed = f"🏷️ Feed Kurole: {briefing.get('total_vendas')} imóveis à venda"
    elif departamento == "Locação":
        badge_feed = f"🔑 Feed Kurole: {briefing.get('total_locacao')} imóveis para locação"
    else:
        badge_feed = f"📡 Feed Kurole: {briefing.get('total_ativos')} imóveis ativos ({briefing.get('total_vendas')} Venda | {briefing.get('total_locacao')} Locação)"

    st.markdown(f"""
    <div class="glass-card" style="background: linear-gradient(135deg, rgba(14, 165, 233, 0.15) 0%, rgba(37, 99, 235, 0.15) 100%); border: 1px solid rgba(56, 189, 248, 0.35); border-left: 5px solid #0ea5e9; padding: 18px 22px; margin-bottom: 24px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.35);">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div>
                <span style="font-size: 1.15rem; font-weight: 800; color: #ffffff;">📅 Relatório do Dia: {briefing.get('data_briefing')}</span>
                <span style="font-size: 0.85rem; color: #94a3b8; margin-left: 10px;">(Gerado às {briefing.get('hora_geracao')})</span>
            </div>
            <div style="font-size: 0.8rem; font-weight: 700; color: #38bdf8; background: rgba(14, 165, 233, 0.15); border: 1px solid rgba(56, 189, 248, 0.3); padding: 5px 12px; border-radius: 9999px;">
                {badge_feed}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Métricas Rápidas
    k1, k2, k3, k4, k5 = st.columns(5)
    diag = briefing.get("estatisticas_diagnostico", {})

    if departamento == "Vendas":
        total_radar = briefing.get("total_vendas", 0)
        q_oport = briefing.get("estatisticas_vendas", {}).get("oportunidades", 0)
        q_acima = briefing.get("estatisticas_vendas", {}).get("muito_acima", 0)
    elif departamento == "Locação":
        total_radar = briefing.get("total_locacao", 0)
        q_oport = briefing.get("estatisticas_locacao", {}).get("oportunidades", 0)
        q_acima = briefing.get("estatisticas_locacao", {}).get("muito_acima", 0)
    else:
        total_radar = briefing.get("total_ativos", 0)
        q_oport = diag.get("oportunidades", 0)
        q_acima = diag.get("muito_acima", 0)

    with k1:
        st.metric("🏢 Total no Radar", f"{total_radar} imóveis")
    with k2:
        st.metric("🆕 Novos Hoje", f"{briefing.get('total_novos')} novos")
    with k3:
        st.metric("🏷️ Mudanças de Preço", f"{briefing.get('total_mudancas_preco')} alterados")
    with k4:
        st.metric("🔵 Oportunidades (< -7%)", f"{q_oport} imóveis")
    with k5:
        st.metric("🔴 Muito Acima (> 15%)", f"{q_acima} imóveis")

    st.markdown("---")

    # SEÇÃO 1: TOP 3 OPORTUNIDADES
    if departamento == "Vendas":
        st.markdown("### 🚀 Top 3 Oportunidades de VENDA • Para Compradores e Investidores")
        top_op = briefing.get("top_oportunidades_venda") or [x for x in briefing.get("top_oportunidades", []) if x.get("transacao") == "Venda"]
    elif departamento == "Locação":
        st.markdown("### 🚀 Top 3 Oportunidades de LOCAÇÃO • Para Novos Locatários")
        top_op = briefing.get("top_oportunidades_locacao") or [x for x in briefing.get("top_oportunidades", []) if x.get("transacao") == "Locação"]
    else:
        st.markdown("### 🚀 Top 3 Oportunidades do Dia • Para Compradores e Investidores")
        top_op = briefing.get("top_oportunidades", [])

    st.caption("Imóveis com maior desconto em relação ao valor justo de fechamento calculado pela NBR 14653.")
    if top_op:
        cols_op = st.columns(len(top_op))
        for idx, op in enumerate(top_op):
            with cols_op[idx]:
                st.markdown(f"""
                <div class="glass-card" style="border: 1px solid rgba(56, 189, 248, 0.35); border-top: 4px solid #0ea5e9; border-radius: 1rem; padding: 18px; min-height: 260px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 0 15px rgba(14, 165, 233, 0.1);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-weight: 800; color: #38bdf8; font-size: 1.1rem; letter-spacing: -0.01em;">{op['codigo']}</span>
                        <span style="background: rgba(14, 165, 233, 0.18); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); font-size: 0.75rem; font-weight: 800; padding: 3px 10px; border-radius: 9999px;">{op['desvio_fmt']}</span>
                    </div>
                    <div style="font-weight: 700; font-size: 0.95rem; color: #f8fafc; margin-bottom: 4px;">{op['tipo']} • {op['bairro']}</div>
                    <div style="color: #94a3b8; font-size: 0.8rem; margin-bottom: 12px; line-height: 1.3;">{op['titulo'][:45]}...</div>
                    <hr style="border: none; border-top: 1px solid rgba(255, 255, 255, 0.08); margin: 10px 0;" />
                    <div style="font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; font-weight: 600;">Preço de Oferta:</div>
                    <div style="font-size: 1.25rem; font-weight: 800; color: #34d399; margin-bottom: 6px;">R$ {op['preco_anunciado_fmt']}</div>
                    <div style="font-size: 0.8rem; color: #94a3b8;">Valor de Mercado (NBR): <b style="color: #f8fafc;">R$ {op['valor_mercado_fmt']}</b></div>
                    <div style="margin-top: 12px; font-size: 0.78rem; color: #cbd5e1; background: rgba(15, 23, 42, 0.7); padding: 10px; border-radius: 0.65rem; border: 1px solid rgba(255, 255, 255, 0.06); line-height: 1.3;">
                        💡 {op['diagnostico']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f"""
                <a href="{op['link_wa']}" target="_blank" style="text-decoration: none;">
                    <div style="background: linear-gradient(90deg, #10b981 0%, #059669 100%); color: white; text-align: center; padding: 10px 14px; border-radius: 0.75rem; font-weight: 700; font-size: 0.85rem; margin-top: 10px; margin-bottom: 10px; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.35); transition: all 0.2s ease;">
                        📲 Enviar WhatsApp Comprador
                    </div>
                </a>
                """, unsafe_allow_html=True)
                with st.expander("👁️ Ver Mensagem Pronta"):
                    st.text_area("Texto do WhatsApp:", value=op['mensagem_wa'], height=130, key=f"wa_op_{idx}", disabled=True)
    else:
        st.info("Nenhuma oportunidade crítica identificada hoje.")

    st.markdown("<br>", unsafe_allow_html=True)

    # SEÇÃO 2: TOP 3 REPRECIFICAÇÃO
    if departamento == "Vendas":
        st.markdown("### ⚠️ Radar de Reprecificação de VENDA • Para Contatar Proprietários")
        top_rep = briefing.get("top_reprecificacao_venda") or [x for x in briefing.get("top_reprecificacao", []) if x.get("transacao") == "Venda"]
    elif departamento == "Locação":
        st.markdown("### ⚠️ Radar de Aluguéis Acima do Mercado • Para Negociação de Locação")
        top_rep = briefing.get("top_reprecificacao_locacao") or [x for x in briefing.get("top_reprecificacao", []) if x.get("transacao") == "Locação"]
    else:
        st.markdown("### ⚠️ Radar de Reprecificação Urgente • Para Contatar Proprietários")
        top_rep = briefing.get("top_reprecificacao", [])

    st.caption("Imóveis com maior sobrepreço (>15%), com risco de perda de liquidez e desinteresse nos portais.")
    if top_rep:
        cols_rep = st.columns(len(top_rep))
        for idx, rep in enumerate(top_rep):
            with cols_rep[idx]:
                st.markdown(f"""
                <div class="glass-card" style="border: 1px solid rgba(244, 63, 94, 0.35); border-top: 4px solid #f43f5e; border-radius: 1rem; padding: 18px; min-height: 260px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 0 15px rgba(244, 63, 94, 0.1);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-weight: 800; color: #fb7185; font-size: 1.1rem; letter-spacing: -0.01em;">{rep['codigo']}</span>
                        <span style="background: rgba(244, 63, 94, 0.18); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.4); font-size: 0.75rem; font-weight: 800; padding: 3px 10px; border-radius: 9999px;">{rep['desvio_fmt']}</span>
                    </div>
                    <div style="font-weight: 700; font-size: 0.95rem; color: #f8fafc; margin-bottom: 4px;">{rep['tipo']} • {rep['bairro']}</div>
                    <div style="color: #94a3b8; font-size: 0.8rem; margin-bottom: 12px; line-height: 1.3;">{rep['titulo'][:45]}...</div>
                    <hr style="border: none; border-top: 1px solid rgba(255, 255, 255, 0.08); margin: 10px 0;" />
                    <div style="font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; font-weight: 600;">Preço Anunciado:</div>
                    <div style="font-size: 1.25rem; font-weight: 800; color: #fb7185; margin-bottom: 6px;">R$ {rep['preco_anunciado_fmt']}</div>
                    <div style="font-size: 0.8rem; color: #94a3b8;">Teto Recomendado (NBR): <b style="color: #f8fafc;">R$ {rep['valor_mercado_fmt']}</b></div>
                    <div style="margin-top: 12px; font-size: 0.78rem; color: #cbd5e1; background: rgba(15, 23, 42, 0.7); padding: 10px; border-radius: 0.65rem; border: 1px solid rgba(255, 255, 255, 0.06); line-height: 1.3;">
                        🚨 {rep['diagnostico']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f"""
                <a href="{rep['link_wa']}" target="_blank" style="text-decoration: none;">
                    <div style="background: linear-gradient(90deg, #10b981 0%, #059669 100%); color: white; text-align: center; padding: 10px 14px; border-radius: 0.75rem; font-weight: 700; font-size: 0.85rem; margin-top: 10px; margin-bottom: 10px; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.35); transition: all 0.2s ease;">
                        📲 Enviar WhatsApp Proprietário
                    </div>
                </a>
                """, unsafe_allow_html=True)
                with st.expander("👁️ Ver Mensagem Pronta"):
                    st.text_area("Texto do WhatsApp:", value=rep['mensagem_wa'], height=130, key=f"wa_rep_{idx}", disabled=True)
    else:
        st.info("Nenhum imóvel com sobrepreço crítico (> 15%) identificado hoje.")

    st.markdown("<br>", unsafe_allow_html=True)

    # SEÇÃO 3: MOVIMENTAÇÕES RECENTES
    st.markdown("### 📋 Movimentações e Novidades da Carteira")
    c_nov, c_mud = st.columns(2)

    novos_imoveis = briefing.get("novos_imoveis", [])
    mudancas_preco = briefing.get("mudancas_preco", [])

    if departamento == "Vendas":
        novos_imoveis = [x for x in novos_imoveis if x.get("transacao") == "Venda" or str(x.get("id", "")).startswith("V")]
        mudancas_preco = [x for x in mudancas_preco if x.get("transacao") == "Venda" or str(x.get("id", "")).startswith("V")]
    elif departamento == "Locação":
        novos_imoveis = [x for x in novos_imoveis if x.get("transacao") == "Locação" or str(x.get("id", "")).startswith("L")]
        mudancas_preco = [x for x in mudancas_preco if x.get("transacao") == "Locação" or str(x.get("id", "")).startswith("L")]

    with c_nov:
        st.markdown(f"**🆕 Novos Imóveis Cadastrados ({len(novos_imoveis)}):**")
        if novos_imoveis:
            for ni in novos_imoveis:
                st.markdown(f"- **{ni['id']}** • {ni['tipo']} ({ni['bairro']}) — **R$ {ni['preco_formatado']}** ({ni['transacao']})")
        else:
            st.success("✅ Nenhum novo cadastro de imóvel nas últimas 24 horas.")

    with c_mud:
        st.markdown(f"**🏷️ Alterações Recentes de Preço ({len(mudancas_preco)}):**")
        if mudancas_preco:
            for mp in mudancas_preco:
                icone = "📉" if mp['tipo_mudanca'] == 'reducao' else "📈"
                st.markdown(f"- {icone} **{mp['id']}** • {mp['tipo']} ({mp['bairro']}): De R$ {mp['preco_antigo_fmt']} para **R$ {mp['preco_novo_fmt']}** ({mp['variacao_pct']:+.1f}%)")
        else:
            st.info("ℹ️ Nenhuma alteração de valor de anúncio registrada em relação ao dia anterior.")


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Executa o Resumo Matinal da Expandh")
    parser.add_argument("--salvar", action="store_true", help="Salva o briefing no histórico e atualiza snapshot")
    args = parser.parse_args()

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iniciando Resumo Matinal Expandh...")
    res = gerar_briefing_matinal(forcar_download=True)
    if res.get("sucesso"):
        print(f"[OK] Briefing concluido com sucesso!")
        print(f"Total Imoveis Ativos: {res['total_ativos']}")
        print(f"Novos Imoveis: {res['total_novos']}")
        print(f"Alteracoes de Preco: {res['total_mudancas_preco']}")
        print(f"Top Oportunidades: {len(res['top_oportunidades'])}")
        print(f"Top Reprecificacoes: {len(res['top_reprecificacao'])}")
    else:
        print(f"[ERRO] Falha: {res.get('erro')}")

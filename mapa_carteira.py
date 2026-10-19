"""
Módulo de Mapeamento Geográfico e Inteligência Espacial da Carteira (Sertãozinho/SP).
Renderiza mapa interativo 2D/3D via Pydeck com georreferenciamento de todos os imóveis,
camada do Polo Nobre da Praça 21 de Abril e gerador integrado de WhatsApp.
"""
import pandas as pd
import pydeck as pdk
import streamlit as st
import argumentario


# Coordenadas de Referência Central: Praça 21 de Abril (Centro, Sertãozinho/SP)
LAT_PRACA_21 = -21.1388
LON_PRACA_21 = -48.0645


def _obter_cor_status(status: str) -> list[int]:
    """Retorna RGBA do pino no mapa de acordo com a saúde do preço NBR 14653."""
    if not status or not isinstance(status, str):
        return [156, 163, 175, 190]  # Cinza
    if "Muito Acima" in status:
        return [239, 68, 68, 220]    # Vermelho
    elif "Acima do Mercado" in status or "Levemente Acima" in status:
        return [234, 179, 8, 220]     # Amarelo
    elif "Preço Justo" in status:
        return [34, 197, 94, 220]     # Verde
    elif "Oportunidade" in status:
        return [59, 130, 246, 220]    # Azul
    return [156, 163, 175, 190]       # Cinza (Aguardando / Outro)


def preparar_dados_mapa(imoveis_lista: list, dados_aud: dict) -> pd.DataFrame:
    """Cruza a lista de imóveis do feed XML com os resultados da auditoria de mercado."""
    # Mapear auditorias por código
    aud_map = {}
    for op in ["vendas", "locacao", "venda", "locacao"]:
        sub = dados_aud.get(op, {})
        for im in sub.get("imoveis", []):
            cid = str(im.get("Código", im.get("id", "")))
            if cid:
                aud_map[cid] = im

    # Fallback lista geral
    for im in dados_aud.get("imoveis", []):
        cid = str(im.get("Código", im.get("id", "")))
        if cid and cid not in aud_map:
            aud_map[cid] = im

    registros = []
    for im in imoveis_lista:
        lat = im.get("lat")
        lon = im.get("lon")
        if lat is None or lon is None:
            continue

        cid = str(im.get("id", ""))
        aud = aud_map.get(cid, {})

        status = aud.get("Status", "⚪ Aguardando Auditoria")
        desvio = aud.get("Desvio (%)", "-")
        preco_ped = im.get("preco", 0.0)
        preco_merc = aud.get("Valor Mercado Estimado (R$)", None)
        transacao = im.get("transacao", "Venda")
        rotulo_preco = "Preço Venda" if transacao == "Venda" else "Aluguel/mês"

        registros.append({
            "id": cid,
            "titulo": im.get("titulo", "Imóvel"),
            "tipo": im.get("tipo", "Imóvel"),
            "bairro": im.get("bairro") or "Sertãozinho",
            "cidade": im.get("cidade") or "Sertãozinho",
            "endereco_rua": im.get("endereco_rua", ""),
            "lat": float(lat),
            "lon": float(lon),
            "transacao": transacao,
            "preco": preco_ped,
            "preco_formatado": f"{preco_ped:,.0f}".replace(",", "."),
            "mercado_formatado": f"{preco_merc:,.0f}".replace(",", ".") if preco_merc else "Em análise",
            "desvio": desvio,
            "status": status,
            "rotulo_preco": rotulo_preco,
            "color": _obter_cor_status(status),
            "radius": 50 if "Muito Acima" not in status else 65,
        })

    return pd.DataFrame(registros)


def render_painel_mapa(imoveis_lista: list, dados_aud: dict):
    """Renderiza a aba de inteligência geográfica com filtros e visualização Pydeck."""
    st.subheader("🗺️ Mapeamento Espacial da Carteira • Sertãozinho e Região")
    st.caption("Distribuição geográfica dos 240 imóveis ativos e diagnóstico de preços NBR 14653.")

    df_mapa = preparar_dados_mapa(imoveis_lista, dados_aud)

    if df_mapa.empty:
        st.warning("Nenhum imóvel com coordenadas geográficas encontrado no momento.")
        return

    # Barra de Filtros
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        op_sel = st.selectbox("Operação:", ["Todas as Operações", "Venda", "Locação"], index=0, key="map_op")
    with f2:
        status_opts = [
            "Todos os Diagnósticos",
            "🔴 Apenas Muito Acima",
            "🟡 Apenas Levemente Acima",
            "🟢 Apenas Preço Justo",
            "🔵 Apenas Oportunidades",
            "⚪ Aguardando Auditoria",
        ]
        stat_sel = st.selectbox("Diagnóstico NBR 14653:", status_opts, index=0, key="map_stat")
    with f3:
        tipos_disponiveis = ["Todos os Tipos"] + sorted(list(df_mapa["tipo"].unique()))
        tipo_sel = st.selectbox("Tipo de Imóvel:", tipos_disponiveis, index=0, key="map_tipo")
    with f4:
        bairros_disponiveis = ["Todos os Bairros"] + sorted(list(df_mapa["bairro"].unique()))
        bairro_sel = st.selectbox("Bairro:", bairros_disponiveis, index=0, key="map_bairro")

    # Aplicação dos Filtros
    df_f = df_mapa.copy()
    if op_sel != "Todas as Operações":
        df_f = df_f[df_f["transacao"] == op_sel]
    if "Muito Acima" in stat_sel:
        df_f = df_f[df_f["status"].str.contains("Muito Acima", na=False)]
    elif "Levemente Acima" in stat_sel:
        df_f = df_f[df_f["status"].str.contains("Acima do Mercado|Levemente Acima", na=False)]
    elif "Preço Justo" in stat_sel:
        df_f = df_f[df_f["status"].str.contains("Preço Justo", na=False)]
    elif "Oportunidades" in stat_sel:
        df_f = df_f[df_f["status"].str.contains("Oportunidade", na=False)]
    elif "Aguardando" in stat_sel:
        df_f = df_f[df_f["status"].str.contains("Aguardando", na=False)]

    if tipo_sel != "Todos os Tipos":
        df_f = df_f[df_f["tipo"] == tipo_sel]
    if bairro_sel != "Todos os Bairros":
        df_f = df_f[df_f["bairro"] == bairro_sel]

    # KPIs da seleção filtrada
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("📍 Imóveis no Mapa", f"{len(df_f)} imóveis")
    with m2:
        q_justo = sum(1 for s in df_f["status"] if "Preço Justo" in str(s))
        st.metric("🟢 No Preço Justo", f"{q_justo} imóveis")
    with m3:
        q_super = sum(1 for s in df_f["status"] if "Muito Acima" in str(s))
        st.metric("🔴 Muito Acima", f"{q_super} imóveis")
    with m4:
        q_acima = sum(1 for s in df_f["status"] if "Acima do Mercado" in str(s) or "Levemente Acima" in str(s))
        st.metric("🟡 Levemente Acima", f"{q_acima} imóveis")
    with m5:
        q_oport = sum(1 for s in df_f["status"] if "Oportunidade" in str(s))
        st.metric("🔵 Oportunidades", f"{q_oport} imóveis")

    st.markdown("---")

    # Centro do mapa baseado na seleção ou na Praça 21 de Abril
    lat_centro = df_f["lat"].mean() if not df_f.empty else LAT_PRACA_21
    lon_centro = df_f["lon"].mean() if not df_f.empty else LON_PRACA_21

    # Camada 1: Imóveis
    camada_imoveis = pdk.Layer(
        "ScatterplotLayer",
        data=df_f,
        get_position="[lon, lat]",
        get_color="color",
        get_radius="radius",
        pickable=True,
        opacity=0.85,
        stroked=True,
        filled=True,
        line_width_min_pixels=1,
        get_line_color=[255, 255, 255, 200],
    )

    # Camada 2: Polo Nobre da Praça 21 de Abril (Destaque do Centro Comercial NBR 14653)
    df_praca = pd.DataFrame([{
        "lat": LAT_PRACA_21,
        "lon": LON_PRACA_21,
        "nome": "Polo Praça 21 de Abril (Centro Comercial Nobre)",
        "color": [245, 158, 11, 70],
    }])

    camada_praca = pdk.Layer(
        "ScatterplotLayer",
        data=df_praca,
        get_position="[lon, lat]",
        get_color="color",
        get_radius=450,
        pickable=True,
        stroked=True,
        filled=True,
        line_width_min_pixels=2,
        get_line_color=[245, 158, 11, 230],
    )

    tooltip = {
        "html": """
        <div style="background-color: #1e293b; color: #f8fafc; padding: 12px; border-radius: 8px; font-family: sans-serif; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); font-size: 0.85rem;">
            <div style="font-weight: 700; color: #38bdf8; font-size: 1.0rem; margin-bottom: 4px;">🏢 {id} • {tipo}</div>
            <div><b>Endereço:</b> {endereco_rua}, {bairro}</div>
            <div><b>Operação:</b> {transacao}</div>
            <hr style="border: none; border-top: 1px solid #475569; margin: 6px 0;" />
            <div><b>Preço Anunciado:</b> R$ {preco_formatado}</div>
            <div><b>Valor Mercado (NBR):</b> R$ {mercado_formatado}</div>
            <div><b>Diagnóstico:</b> <span style="font-weight: 600;">{status}</span> ({desvio})</div>
        </div>
        """,
        "style": {"zIndex": "1000"},
    }

    view_state = pdk.ViewState(
        latitude=lat_centro,
        longitude=lon_centro,
        zoom=13.3,
        pitch=30,
        bearing=0,
    )

    deck = pdk.Deck(
        layers=[camada_praca, camada_imoveis],
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style="light",
    )

    st.pydeck_chart(deck, use_container_width=True)

    # Legenda e Observações Técnicas
    st.markdown("""
    <div style="display: flex; gap: 20px; justify-content: center; margin-top: 5px; margin-bottom: 25px; flex-wrap: wrap;">
        <span style="font-size: 0.85rem;"><span style="color: #22C55E;">●</span> <b>Verde:</b> Preço Justo (±5%)</span>
        <span style="font-size: 0.85rem;"><span style="color: #EF4444;">●</span> <b>Vermelho:</b> Muito Acima (> 15%)</span>
        <span style="font-size: 0.85rem;"><span style="color: #EAB308;">●</span> <b>Amarelo:</b> Levemente Acima (+5% a 15%)</span>
        <span style="font-size: 0.85rem;"><span style="color: #3B82F6;">●</span> <b>Azul:</b> Oportunidades (< -7%)</span>
        <span style="font-size: 0.85rem;"><span style="color: #F59E0B;">⭘</span> <b>Anel Dourado:</b> Polo Praça 21 de Abril (Centro Comercial)</span>
    </div>
    """, unsafe_allow_html=True)

    # ==================== AÇÃO RÁPIDA: ARGUMENTÁRIO WHATSAPP DO MAPA ====================
    st.markdown("---")
    st.markdown("### 💬 Ação Rápida de Balcão • Gerar WhatsApp de um Imóvel do Mapa")
    st.caption("Selecione qualquer imóvel exibido no mapa acima para criar a mensagem de WhatsApp pronta para envio.")

    if not df_f.empty:
        col_sel_map, col_cfg_cli, col_cfg_cor = st.columns([2, 1, 1])

        imoveis_opcoes = {
            f"{r['id']} - {r['tipo']} ({r['bairro']}) | R$ {r['preco_formatado']} | {r['status']}": r
            for _, r in df_f.iterrows()
        }

        with col_sel_map:
            escolha_imovel_mapa = st.selectbox(
                "Escolha o Imóvel:",
                options=list(imoveis_opcoes.keys()),
                key="sel_imovel_mapa_wa",
            )
            item_sel = imoveis_opcoes[escolha_imovel_mapa]

        with col_cfg_cli:
            nome_cli = st.text_input("Nome do Cliente/Proprietário:", value="Dr. / Sr.", key="map_cli_nome")
        with col_cfg_cor:
            nome_cor = st.text_input("Nome do Consultor:", value="Consultor Expandh", key="map_cor_nome")

        col_tipo_msg, col_fone, col_btn_act = st.columns([1.5, 1.2, 1.3])
        with col_tipo_msg:
            tipo_dest = st.selectbox(
                "Objetivo da Mensagem:",
                options=[
                    ("proprietario", "🎯 Reprecificação com Proprietário"),
                    ("comprador", "🤝 Apresentação para Comprador/Investidor"),
                ],
                format_func=lambda x: x[1],
                key="map_tipo_dest",
            )[0]

        with col_fone:
            fone_dest = st.text_input("WhatsApp com DDD (opcional):", placeholder="16999998888", key="map_fone")

        with col_btn_act:
            st.write("")
            st.write("")
            btn_gerar_mapa = st.button("⚡ Gerar Mensagem com IA", key="btn_gerar_wa_mapa", type="primary", use_container_width=True)

        if btn_gerar_mapa:
            with st.spinner("IA gerando argumentário comercial persuasivo..."):
                dados_para_wa = {
                    "Código": item_sel["id"],
                    "Tipo": item_sel["tipo"],
                    "Bairro": item_sel["bairro"],
                    "Cidade": item_sel["cidade"],
                    "Endereço": item_sel["endereco_rua"],
                    "Preço Anunciado (R$)": item_sel["preco"],
                    "Valor Mercado Estimado (R$)": item_sel["preco"] if item_sel["mercado_formatado"] == "Em análise" else float(item_sel["mercado_formatado"].replace(".", "")),
                    "Desvio (%)": item_sel["desvio"],
                    "Status": item_sel["status"],
                    "Amostras Usadas": 10,
                }

                msg_gerada = argumentario.gerar_argumentario_whatsapp(
                    dados_para_wa,
                    tipo_publico=tipo_dest,
                    nome_cliente=nome_cli,
                    nome_corretor=nome_cor,
                )
                st.session_state[f"wa_msg_cache_{item_sel['id']}"] = msg_gerada

        msg_final = st.session_state.get(f"wa_msg_cache_{item_sel['id']}", "")
        if msg_final:
            st.markdown("#### 📱 Mensagem Pronta para Envio:")
            msg_editavel = st.text_area("Texto formatado para WhatsApp:", value=msg_final, height=220, key=f"area_msg_{item_sel['id']}")
            
            link_wa = argumentario.criar_link_direto_whatsapp(msg_editavel, fone_dest)
            
            col_b1, col_b2 = st.columns([1, 2])
            with col_b1:
                st.link_button("📲 Abrir no WhatsApp Web / Celular", link_wa, type="primary", use_container_width=True)
            with col_b2:
                st.success("✅ Mensagem pronta! Você pode clicar no botão verde para disparar ou editar o texto acima.")

"""
Módulo de Sistema de Design Expandh BI (Tema Único Executivo Obsidian Dark).
Portado diretamente da Suite Executiva de BI da Expandh Imóveis:
- Paleta Obsidian Dark (#0b1120) com acentos Ciano Reluzente (#0ea5e9, #38bdf8)
- Glassmorphism com backdrop-filter blur, bordas sutis e glow suave
- Tipografia oficial Inter (Google Fonts)
- Navegação em abas no formato Pill Buttons com realce ciano
- Modal Gatekeeper de segurança com criptografia 2026
"""
import base64
from pathlib import Path
import streamlit as st


def obter_css_tema() -> str:
    """Retorna o bloco completo de CSS com o tema executivo definitivo da Expandh."""
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

    :root {
        --bg-main: #0b1120;
        --card-bg: rgba(30, 41, 59, 0.75);
        --card-border: rgba(255, 255, 255, 0.08);
        --text-main: #f8fafc;
        --text-muted: #94a3b8;
        --sidebar-bg: #060d1a;
        --input-bg: rgba(15, 23, 42, 0.9);
        --cyan-primary: #0ea5e9;
        --cyan-light: #38bdf8;
        --cyan-glow: rgba(14, 165, 233, 0.4);
    }

    /* Tipografia e Fundo Geral */
    html, body, [class*="css"], .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        background-color: var(--bg-main) !important;
        color: var(--text-main) !important;
    }

    .stApp {
        background-color: var(--bg-main) !important;
    }

    /* Títulos e Textos Principais */
    h1, h2, h3, h4, h5, h6 {
        color: #f8fafc !important;
        font-weight: 800 !important;
        letter-spacing: -0.02em !important;
    }
    p, span, label {
        color: #e2e8f0;
    }

    /* Scrollbar Personalizada */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: var(--bg-main);
    }
    ::-webkit-scrollbar-thumb {
        background: #334155;
        border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: var(--cyan-primary);
    }

    /* Glassmorphism Cards */
    .glass-card {
        background: var(--card-bg) !important;
        backdrop-filter: blur(14px) !important;
        -webkit-backdrop-filter: blur(14px) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 1rem !important;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.35), 0 8px 10px -6px rgba(0, 0, 0, 0.3) !important;
        color: var(--text-main) !important;
    }

    /* Topo Executivo (Header Card) */
    .header-card {
        background: var(--card-bg) !important;
        backdrop-filter: blur(14px) !important;
        -webkit-backdrop-filter: blur(14px) !important;
        border: 1px solid var(--card-border) !important;
        border-left: 5px solid #0ea5e9 !important;
        border-radius: 1rem !important;
        padding: 20px 24px !important;
        margin-bottom: 20px !important;
        box-shadow: 0 12px 30px -10px rgba(0, 0, 0, 0.45) !important;
    }

    /* Metric Cards do Streamlit */
    [data-testid="stMetric"] {
        background: var(--card-bg) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 1rem !important;
        padding: 14px 18px !important;
        box-shadow: 0 8px 20px -4px rgba(0, 0, 0, 0.25) !important;
        transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease !important;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-2px) !important;
        border-color: rgba(14, 165, 233, 0.45) !important;
        box-shadow: 0 12px 25px -5px var(--cyan-glow) !important;
    }
    [data-testid="stMetricLabel"] p, [data-testid="stMetricLabel"] {
        font-size: 0.72rem !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        color: var(--text-muted) !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.35rem !important;
        font-weight: 800 !important;
        color: #ffffff !important;
        letter-spacing: -0.02em !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
    [data-testid="stMetricDelta"] {
        font-weight: 600 !important;
        font-size: 0.8rem !important;
    }

    /* Navegação em Abas (Pill Buttons) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px !important;
        background-color: transparent !important;
        border-bottom: 1px solid var(--card-border) !important;
        padding-bottom: 12px !important;
        margin-bottom: 20px !important;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: rgba(30, 41, 59, 0.75) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 0.85rem !important;
        padding: 10px 20px !important;
        color: #cbd5e1 !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.15) !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background-color: rgba(56, 189, 248, 0.15) !important;
        color: #ffffff !important;
        border-color: rgba(14, 165, 233, 0.4) !important;
    }
    .stTabs [aria-selected="true"] {
        background: #0ea5e9 !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        border: 1px solid #38bdf8 !important;
        box-shadow: 0 0 20px -2px rgba(14, 165, 233, 0.5) !important;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        display: none !important;
    }

    /* Botões Primários (Degradê Ciano / Azul Expandh) */
    .stButton > button[kind="primary"], 
    .stButton > button[data-testid="stBaseButton-primary"],
    .stLinkButton > a[kind="primary"],
    .stDownloadButton > button[kind="primary"] {
        background: linear-gradient(90deg, #06b6d4 0%, #2563eb 100%) !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 0.75rem !important;
        padding: 0.65rem 1.4rem !important;
        box-shadow: 0 4px 15px rgba(6, 182, 212, 0.35) !important;
        transition: all 0.2s ease !important;
        text-shadow: 0 1px 2px rgba(0,0,0,0.2) !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stLinkButton > a[kind="primary"]:hover,
    .stDownloadButton > button[kind="primary"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 25px rgba(6, 182, 212, 0.5) !important;
        filter: brightness(1.1) !important;
    }

    /* Botões Secundários */
    .stButton > button[kind="secondary"], 
    .stButton > button[data-testid="stBaseButton-secondary"],
    .stDownloadButton > button[kind="secondary"] {
        background: var(--card-bg) !important;
        border: 1px solid var(--card-border) !important;
        color: var(--text-main) !important;
        font-weight: 600 !important;
        border-radius: 0.75rem !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="secondary"]:hover,
    .stDownloadButton > button[kind="secondary"]:hover {
        background: rgba(56, 189, 248, 0.12) !important;
        border-color: rgba(14, 165, 233, 0.4) !important;
        color: #38bdf8 !important;
    }

    /* Barra Lateral (Sidebar) */
    [data-testid="stSidebar"] {
        background-color: var(--sidebar-bg) !important;
        border-right: 1px solid var(--card-border) !important;
    }
    [data-testid="stSidebar"] [data-testid="stMetric"] {
        background: rgba(15, 23, 42, 0.7) !important;
        border-radius: 0.75rem !important;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #f8fafc !important;
    }
    [data-testid="stSidebar"] .stCaption {
        color: #94a3b8 !important;
    }

    /* Menu Lateral de Navegação (Executive Sidebar Navigation Pill Menu) */
    [data-testid="stSidebar"] div[data-testid="stRadio"] > div {
        gap: 6px !important;
    }
    [data-testid="stSidebar"] label[data-baseweb="radio"] {
        background: rgba(30, 41, 59, 0.45) !important;
        border: 1px solid rgba(255, 255, 255, 0.06) !important;
        border-radius: 0.8rem !important;
        padding: 9px 14px !important;
        margin: 2px 0 !important;
        width: 100% !important;
        cursor: pointer !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.15) !important;
    }
    /* Esconder o círculo nativo do radio */
    [data-testid="stSidebar"] label[data-baseweb="radio"] > div:first-child {
        display: none !important;
    }
    [data-testid="stSidebar"] label[data-baseweb="radio"] div[data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] label[data-baseweb="radio"] span {
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        color: #cbd5e1 !important;
        letter-spacing: -0.01em !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
    [data-testid="stSidebar"] label[data-baseweb="radio"]:hover {
        background: rgba(56, 189, 248, 0.14) !important;
        border-color: rgba(14, 165, 233, 0.4) !important;
        transform: translateX(4px) !important;
    }
    [data-testid="stSidebar"] label[data-baseweb="radio"]:hover p {
        color: #ffffff !important;
    }
    /* Item Selecionado / Ativo */
    [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked),
    [data-testid="stSidebar"] label[data-baseweb="radio"][aria-checked="true"] {
        background: linear-gradient(90deg, rgba(14, 165, 233, 0.28) 0%, rgba(14, 165, 233, 0.08) 100%) !important;
        border: 1px solid rgba(14, 165, 233, 0.55) !important;
        border-left: 4px solid #0ea5e9 !important;
        box-shadow: 0 4px 18px -2px rgba(14, 165, 233, 0.35) !important;
    }
    [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) p,
    [data-testid="stSidebar"] label[data-baseweb="radio"][aria-checked="true"] p {
        color: #38bdf8 !important;
        font-weight: 700 !important;
    }

    [data-testid="stSidebar"] [data-testid="stExpander"] {
        background: rgba(15, 23, 42, 0.6) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 0.75rem !important;
        margin-top: 10px !important;
    }

    /* Inputs, Selectboxes e Dropdowns */
    [data-baseweb="input"], [data-baseweb="base-input"] {
        background-color: var(--input-bg) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 0.75rem !important;
        color: #ffffff !important;
    }
    [data-baseweb="select"] > div {
        background-color: var(--input-bg) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 0.75rem !important;
        color: #ffffff !important;
    }
    /* Menu suspenso de opções dos Selectboxes */
    [data-baseweb="popover"], [data-baseweb="menu"], ul[role="listbox"] {
        background-color: #0f172a !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 0.75rem !important;
    }
    li[role="option"] {
        color: #f8fafc !important;
    }
    li[role="option"]:hover, li[aria-selected="true"] {
        background-color: rgba(14, 165, 233, 0.25) !important;
        color: #38bdf8 !important;
    }
    .stTextInput input, .stNumberInput input {
        color: #ffffff !important;
    }

    /* Sliders e Toggles */
    [data-testid="stSlider"] {
        color: #38bdf8 !important;
    }

    /* Expanders */
    [data-testid="stExpander"] {
        background: var(--card-bg) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 0.85rem !important;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15) !important;
    }

    /* Tabelas e Dataframes */
    [data-testid="stDataFrame"] {
        border: 1px solid var(--card-border) !important;
        border-radius: 0.75rem !important;
        overflow: hidden !important;
    }

    /* Badges e Pílulas de Status */
    .badge-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        padding: 4px 12px;
        border-radius: 9999px;
    }
    .badge-cyan {
        background: rgba(14, 165, 233, 0.15);
        color: #38bdf8;
        border: 1px solid rgba(14, 165, 233, 0.35);
    }
    .badge-emerald {
        background: rgba(16, 185, 129, 0.15);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.35);
    }
    .badge-rose {
        background: rgba(244, 63, 94, 0.15);
        color: #fb7185;
        border: 1px solid rgba(244, 63, 94, 0.35);
    }
    .badge-amber {
        background: rgba(245, 158, 11, 0.15);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.35);
    }

    .math-formula {
        background: rgba(15, 23, 42, 0.85);
        border-left: 3px solid #0ea5e9;
        padding: 10px 14px;
        border-radius: 0.5rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.82rem;
        color: #38bdf8;
        margin: 6px 0;
    }
    </style>
    """


def obter_logo_base64() -> str:
    """Carrega o logotipo da Expandh em base64 para uso inline em HTML."""
    caminhos = [
        Path("assets/logo_expandh.png"),
        Path("real_estate_evaluator/assets/logo_expandh.png"),
        Path("../real_estate_evaluator/assets/logo_expandh.png"),
    ]
    for p in caminhos:
        if p.exists():
            try:
                with open(p, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
    return ""


def render_gatekeeper_login(senha_esperada: str) -> bool:
    """
    Renderiza o Modal Gatekeeper idêntico ao do projeto BI:
    - Fundo escuro com backdrop blur
    - Card central em glassmorphism com ícone de cadeado ciano reluzente
    - Subtítulo em ciano caixa alta
    - Botão degradê ciano/azul com sombra profunda
    - Rodapé criptografado 2026
    """
    if st.session_state.get("authenticated", False):
        return True

    # Centralização com colunas
    _, col_centro, _ = st.columns([1, 1.8, 1])

    with col_centro:
        st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
        
        logo_b64 = obter_logo_base64()
        img_html = f'<img src="data:image/png;base64,{logo_b64}" width="160" style="margin: 0 auto 12px auto; display: block;" />' if logo_b64 else ''

        st.markdown(f"""
        <div class="glass-card" style="padding: 36px 30px; text-align: center; border: 1px solid rgba(56, 189, 248, 0.3); box-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.6), 0 0 25px rgba(14, 165, 233, 0.15);">
            <div style="display: inline-flex; align-items: center; justify-content: center; width: 64px; height: 64px; border-radius: 18px; background: rgba(14, 165, 233, 0.12); border: 1px solid rgba(56, 189, 248, 0.35); color: #38bdf8; margin-bottom: 16px; box-shadow: 0 0 20px rgba(14, 165, 233, 0.25);">
                <svg width="32" height="32" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
            </div>
            {img_html}
            <h2 style="font-size: 1.75rem; font-weight: 800; color: #ffffff; margin: 0 0 4px 0; letter-spacing: -0.02em;">Expandh Imóveis</h2>
            <div style="color: #38bdf8; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 10px;">Portal de Inteligência Imobiliária & NBR 14653</div>
            <p style="color: #94a3b8; font-size: 0.82rem; margin: 0 0 20px 0; line-height: 1.4;">Acesso restrito à Diretoria e Equipe Técnica da Expandh</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("form_gatekeeper_login"):
            senha_digitada = st.text_input(
                "Senha de Acesso:",
                type="password",
                placeholder="Digite a senha institucional...",
                help="Insira a senha fornecida pela diretoria da Expandh",
            )
            
            c_lembrar, _ = st.columns([1, 1])
            with c_lembrar:
                st.checkbox("Lembrar neste aparelho", value=True, key="login_remember")

            btn_entrar = st.form_submit_button("Acessar Painel Executivo 🚀", use_container_width=True, type="primary")

            if btn_entrar:
                if senha_digitada == senha_esperada:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("❌ Senha incorreta. Verifique com a administração da Expandh.")

        st.markdown("""
        <div style="text-align: center; color: #64748b; font-size: 0.72rem; margin-top: 15px;">
            Expandh Imóveis &bull; Ambiente Criptografado &bull; 2026
        </div>
        """, unsafe_allow_html=True)

    return False


def render_header_executivo(total_ativos: int, total_venda: int, total_locacao: int, data_pub: str):
    """
    Renderiza o Topo Executivo idêntico ao do projeto BI:
    - Borda lateral ciano forte (border-l-4 border-cyan-500)
    - Tag 'EXPANDH BI SUITE • AVALIAIA'
    - Título 'Sistema de Inteligência Imobiliária & NBR 14653'
    - Badges dinâmicos de status Kurole e CRECI
    """
    logo_b64 = obter_logo_base64()
    logo_tag = f'<img src="data:image/png;base64,{logo_b64}" height="42" style="vertical-align: middle; margin-right: 14px;" />' if logo_b64 else ''

    st.markdown(f"""
    <div class="header-card">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
            <div>
                <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px;">
                    <span class="badge-pill badge-cyan">Expandh BI Suite • AvaliaIA</span>
                    <span class="badge-pill badge-emerald">🟢 Kurole Live Sync ({total_ativos} ativos)</span>
                    <span style="font-size: 0.78rem; color: #94a3b8;">Publicado no XML: {data_pub}</span>
                </div>
                <div style="display: flex; align-items: center;">
                    {logo_tag}
                    <div>
                        <h1 style="font-size: 1.85rem; font-weight: 800; margin: 0; color: #ffffff; letter-spacing: -0.02em;">
                            Sistema de Avaliação & Inteligência Imobiliária
                        </h1>
                        <p style="font-size: 0.88rem; color: #94a3b8; margin: 3px 0 0 0;">
                            Auditoria NBR 14653-2, Amostragem em Tempo Real ZAP Imóveis e Laudos Periciais com IA • Sertãozinho/SP
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_modal_metodologia():
    """Renderiza a documentação de metodologia executiva e fórmulas da NBR 14653."""
    with st.expander("📖 Metodologia Científica & Fórmulas de Avaliação (NBR 14653-2)", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(r"""
            #### 1. Método Comparativo Direto (MCDDM)
            A precificação é determinada pela mediana dos comparáveis diretos anunciados no mesmo bairro/cidade com saneamento de outliers (regra de 3 desvios-padrão).
            
            #### 2. Fator de Redução de Oferta ($F_{of}$)
            Margem de negociação efetiva entre anúncio público e escritura de fechamento:
            <div class="math-formula">V_{fechamento} = V_{anúncio} \times F_{of} \quad (Padrão: 0.90 / 10\% de barganha)</div>
            
            #### 3. Fator de Homogeneização de Escala ($F_{esc}$)
            Aplicado para terrenos com área discrepante em relação ao lote padrão do bairro ($A_{pad} = 300\text{ m}^2$):
            <div class="math-formula">F_{esc} = (A_{pad} / A_{imovel})^{0.25}</div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown("""
            #### 4. Corredor Nobre & Praça 21 de Abril ($F_{loc}$)
            Imóveis comerciais no Polo Central recebem ponderação específica com validação estrita de distância:
            - **Núcleo Nobre (até 380m):** $F_{loc} = 2.45\times$
            - **Cruzantes Centrais (até 550m):** $F_{loc} = 1.70\times$
            - **Demais Vias:** Sem acréscimo indevido ($1.00\times$)

            #### 5. Condomínios Fechados de Alto Padrão
            Pisos de garantia e benchmarks dedicados:
            - **Reserva Terra Nova:** Piso mínimo R$ 700.000 (benchmark R$ 5.850/m²)
            - **Portal das Flores:** Piso mínimo R$ 500.000 (benchmark R$ 4.800/m²)
            - **Parque das Aroeiras:** Benchmark R$ 9.500/m²
            """, unsafe_allow_html=True)

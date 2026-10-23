"""
Interface Web Interativa para Avaliação Imobiliária Inteligente (NBR 14653).
Construído com Streamlit, consumindo os modelos do Google AI Studio e dados reais do ZAP.
"""
import glob
import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

import feed_parser
import gerar_pdf
import pipeline
import reavaliacao_carteira
import argumentario
import mapa_carteira
import resumo_matinal
import tema_bi
import auditoria_divergencias
import importlib
importlib.reload(reavaliacao_carteira)
importlib.reload(argumentario)
importlib.reload(mapa_carteira)
importlib.reload(resumo_matinal)
importlib.reload(tema_bi)
importlib.reload(auditoria_divergencias)
import tools
from llm import ClienteLLM, obter_chave_gemini, testar_conexao_gemini

# Configuração da página
st.set_page_config(
    page_title="AvaliaIA • Inteligência Imobiliária Expandh",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Injeção do Sistema de Design Expandh BI (Tema Único Executivo Obsidian Dark)
st.markdown(tema_bi.obter_css_tema(), unsafe_allow_html=True)


# ==================== CONTROLE DE ACESSO (AUTENTICAÇÃO POR SENHA & DEPARTAMENTO) ====================
def check_password() -> bool:
    """Verifica se o usuário está autenticado ou exibe o Gatekeeper executivo segmentado."""
    if st.session_state.get("authenticated", False):
        if "perfil_usuario" not in st.session_state:
            st.session_state["perfil_usuario"] = "Diretoria"
        if "departamento_ativo" not in st.session_state:
            st.session_state["departamento_ativo"] = "Total"
        return True

    def _obter_senha(chave_secret, chave_env, default):
        s = default
        try:
            if chave_secret in st.secrets:
                s = str(st.secrets[chave_secret])
        except Exception:
            pass
        return os.getenv(chave_env, s)

    senhas_dict = {
        "master": _obter_senha("APP_PASSWORD", "APP_PASSWORD", "expandh2026"),
        "vendas": _obter_senha("APP_PASSWORD_VENDAS", "APP_PASSWORD_VENDAS", "vendas2026"),
        "locacao": _obter_senha("APP_PASSWORD_LOCACAO", "APP_PASSWORD_LOCACAO", "locacao2026"),
    }

    return tema_bi.render_gatekeeper_login(senhas_dict)

if not check_password():
    st.stop()


# ==================== CARREGAMENTO CENTRAL DO FEED XML ====================
@st.cache_data(ttl=600, show_spinner=False)
def _obter_dados_feed(url: str):
    return feed_parser.carregar_feed_xml(url)

try:
    dados_feed = _obter_dados_feed(feed_parser.URL_FEED_PADRAO)
    imoveis_lista = dados_feed.get("imoveis", [])
    cabecalho = dados_feed.get("cabecalho", {})
except Exception as e:
    st.error(f"Erro ao carregar o feed XML: {e}")
    imoveis_lista = []
    cabecalho = {}

imoveis_venda = [x for x in imoveis_lista if x.get("transacao") == "Venda"]
imoveis_locacao = [x for x in imoveis_lista if x.get("transacao") == "Locação"]

# Informações de publicação do Kurole
data_pub_raw = cabecalho.get("data_publicacao", "")
data_pub_formatada = "Desconhecida"
if data_pub_raw:
    try:
        dt = datetime.fromisoformat(data_pub_raw)
        data_pub_formatada = dt.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        data_pub_formatada = data_pub_raw


# Contagem prévia de divergências para o badge do menu
dados_div_resumo = auditoria_divergencias.auditar_todas_divergencias(feed_imoveis=imoveis_lista, forcar_recalculo=False)
detalhes_div = dados_div_resumo.get("detalhes", []) if dados_div_resumo else []
total_alertas_div = dados_div_resumo.get("imoveis_com_divergencia", 0) if dados_div_resumo else 0
total_alertas_venda = len(set(d.get("Código") for d in detalhes_div if d.get("Transação") == "Venda" or str(d.get("Código", "")).startswith("V")))
total_alertas_loc = len(set(d.get("Código") for d in detalhes_div if d.get("Transação") == "Locação" or str(d.get("Código", "")).startswith("L")))

# ==================== BARRA LATERAL (NAVEGAÇÃO & CONFIGURAÇÕES) ====================
with st.sidebar:
    if Path("assets/logo_expandh.png").exists():
        st.image("assets/logo_expandh.png", width=160)
    else:
        st.image("https://img.icons8.com/fluency/96/real-estate.png", width=64)
    st.title("AvaliaIA Pro")
    st.caption("Engenharia de Avaliações com IA • NBR 14653")
    
    perfil_usr = st.session_state.get("perfil_usuario", "Diretoria")
    dep_ativo = st.session_state.get("departamento_ativo", "Total")

    # Status de login e botão de Sair
    col_status, col_btn = st.columns([1.8, 1.2])
    with col_status:
        badge_perfil = "🌐 Diretoria" if perfil_usr == "Diretoria" else ("🏷️ Equipe Vendas" if perfil_usr == "Vendas" else "🔑 Equipe Locação")
        st.markdown(f"<small style='color: #10b981; font-weight: 700;'>🟢 CONECTADO</small><br><small style='color: var(--text-muted);'>{badge_perfil}</small>", unsafe_allow_html=True)
    with col_btn:
        if st.button("🚪 Sair", key="btn_logout", help="Encerrar sessão no painel"):
            st.session_state["authenticated"] = False
            st.session_state.pop("perfil_usuario", None)
            st.session_state.pop("departamento_ativo", None)
            st.rerun()

    # Se for perfil Diretoria, exibe o seletor rápido para alternar visões
    if perfil_usr == "Diretoria":
        st.markdown(
            "<div style='font-size: 0.70rem; font-weight: 800; letter-spacing: 0.08em; color: #38bdf8; text-transform: uppercase; margin: 10px 0 4px 0;'>🏢 Visão Departamental</div>",
            unsafe_allow_html=True,
        )
        opcoes_visao = ["🌐 Total", "🏷️ Vendas", "🔑 Locação"]
        idx_visao = 0
        if dep_ativo == "Vendas":
            idx_visao = 1
        elif dep_ativo == "Locação":
            idx_visao = 2

        dep_escolhido = st.radio(
            "Visão Departamental:",
            options=opcoes_visao,
            index=idx_visao,
            label_visibility="collapsed",
            key="radio_seletor_visao",
            horizontal=True,
        )
        novo_dep = "Total"
        if "Vendas" in dep_escolhido:
            novo_dep = "Vendas"
        elif "Locação" in dep_escolhido:
            novo_dep = "Locação"

        if novo_dep != dep_ativo:
            st.session_state["departamento_ativo"] = novo_dep
            st.rerun()
    elif perfil_usr == "Vendas":
        st.markdown(
            "<div style='background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.35); padding: 6px 10px; border-radius: 8px; font-size: 0.72rem; font-weight: 800; color: #38bdf8; text-align: center; margin: 8px 0 4px 0;'>🏷️ DEPARTAMENTO DE VENDAS</div>",
            unsafe_allow_html=True,
        )
        st.session_state["departamento_ativo"] = "Vendas"
    elif perfil_usr == "Locação":
        st.markdown(
            "<div style='background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); padding: 6px 10px; border-radius: 8px; font-size: 0.72rem; font-weight: 800; color: #10b981; text-align: center; margin: 8px 0 4px 0;'>🔑 DEPARTAMENTO DE LOCAÇÃO</div>",
            unsafe_allow_html=True,
        )
        st.session_state["departamento_ativo"] = "Locação"

    st.markdown("---")

    # ==================== MENU LATERAL DE NAVEGAÇÃO SEGMENTADO ====================
    st.markdown(
        "<div style='font-size: 0.72rem; font-weight: 800; letter-spacing: 0.08em; color: #94a3b8; text-transform: uppercase; margin-bottom: 8px;'>🧭 Navegação Principal</div>",
        unsafe_allow_html=True,
    )
    
    departamento_ativo = st.session_state.get("departamento_ativo", "Total")

    if departamento_ativo == "Vendas":
        opcoes_menu = [
            "☀️ Briefing Matinal & Oportunidades",
            f"🏷️ Carteira de VENDAS ({len(imoveis_venda)} imóveis)",
            f"🔍 Conformidade Cadastral ({total_alertas_venda} alertas)",
            f"🗺️ Mapa da Carteira ({len(imoveis_venda)} imóveis)",
            "📄 Avaliação via Matrícula",
            "📂 Histórico de Laudos Gerados",
        ]
    elif departamento_ativo == "Locação":
        opcoes_menu = [
            "☀️ Briefing Matinal & Oportunidades",
            f"🔑 Carteira de LOCAÇÃO ({len(imoveis_locacao)} imóveis)",
            f"🔍 Conformidade Cadastral ({total_alertas_loc} alertas)",
            f"🗺️ Mapa da Carteira ({len(imoveis_locacao)} imóveis)",
            "📄 Avaliação via Matrícula",
            "📂 Histórico de Laudos Gerados",
        ]
    else:  # Total
        opcoes_menu = [
            "☀️ Briefing Matinal & Oportunidades",
            f"🏷️ Carteira de VENDAS ({len(imoveis_venda)} imóveis)",
            f"🔑 Carteira de LOCAÇÃO ({len(imoveis_locacao)} imóveis)",
            f"🔍 Conformidade Cadastral ({total_alertas_div} alertas)",
            f"🗺️ Mapa da Carteira ({len(imoveis_lista)} imóveis)",
            "📄 Avaliação via Matrícula",
            "📂 Histórico de Laudos Gerados",
        ]

    # Previne quebra de índice se a aba selecionada anteriormente sumir no perfil
    menu_salvo = st.session_state.get("menu_lateral_expandh")
    idx_menu = 0
    if menu_salvo and menu_salvo in opcoes_menu:
        idx_menu = opcoes_menu.index(menu_salvo)

    aba_selecionada = st.radio(
        "Navegação:",
        options=opcoes_menu,
        index=idx_menu,
        label_visibility="collapsed",
        key="menu_lateral_expandh",
    )

    st.markdown("---")
    
    # Status e Sincronização do Feed Kurole em Expander Compacto
    with st.expander("📡 Sincronização Kurole (KSI)", expanded=False):
        st.markdown(f"**Carga no XML:** `{data_pub_formatada}`")
        st.caption(f"**Total Ativo no Feed:** {len(imoveis_lista)} imóveis ({len(imoveis_venda)} Venda | {len(imoveis_locacao)} Locação)")
        if st.button("🔄 Sincronizar Feed XML Agora", use_container_width=True, help="Recarrega o arquivo XML mais recente publicado no servidor Kurole"):
            st.cache_data.clear()
            st.rerun()

    # Configurações Técnicas da Avaliação em Expander Compacto
    with st.expander("⚙️ Configurações da Avaliação", expanded=False):
        modelo_selecionado = st.selectbox(
            "Modelo de IA (Google AI Studio)",
            options=["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"],
            index=0,
            help="O Flash-Lite possui 500 requisições diárias gratuitas e lê PDFs nativamente com OCR.",
        )
        os.environ["MODELO_EXTRACAO"] = modelo_selecionado
        os.environ["MODELO_TEXTO"] = modelo_selecionado

        fator_oferta_input = st.slider(
            "Fator de Redução de Oferta",
            min_value=0.80,
            max_value=1.00,
            value=0.90,
            step=0.01,
            help="Percentual de conversão do preço de anúncio para fechamento efetivo (0.90 = 10% de margem de barganha).",
        )
        pipeline.FATOR_OFERTA = fator_oferta_input

        rentabilidade_input = st.number_input(
            "Premissa Cap Rate Aluguel (% a.a.)",
            min_value=3.0,
            max_value=15.0,
            value=5.5,
            step=0.1,
            help="Utilizado quando não houver amostras suficientes de locação na região.",
        )
        pipeline.RENTABILIDADE_ALUGUEL_AA = rentabilidade_input

        api_key = obter_chave_gemini()
        if api_key and len(api_key) >= 20:
            st.success("🟢 Gemini Conectado e Operacional")
        else:
            st.error("🔴 Motor Gemini não configurado")

        if perfil_usr == "Diretoria":
            with st.expander("⚙️ Gerenciar Chave Gemini (AI Studio)", expanded=not bool(api_key)):
                st.caption("Configuração administrativa da chave da IA (Google AI Studio).")
                nova_chave_side = st.text_input(
                    "Chave do Google AI Studio:",
                    type="password",
                    placeholder="Cole a chave aqui...",
                    key="input_gemini_key_sidebar"
                ).strip()
                col_sb1, col_sb2 = st.columns(2)
                with col_sb1:
                    if st.button("💾 Salvar", use_container_width=True, key="btn_save_key_sidebar"):
                        if len(nova_chave_side) >= 20:
                            st.session_state["gemini_api_key_override"] = nova_chave_side
                            os.environ["GEMINI_API_KEY"] = nova_chave_side
                            try:
                                caminho_env = Path(".env")
                                linhas = []
                                if caminho_env.exists():
                                    for l in caminho_env.read_text(encoding="utf-8").splitlines():
                                        if l.startswith("GEMINI_API_KEY="):
                                            linhas.append(f'GEMINI_API_KEY="{nova_chave_side}"')
                                        else:
                                            linhas.append(l)
                                else:
                                    linhas.append(f'GEMINI_API_KEY="{nova_chave_side}"')
                                caminho_env.write_text("\n".join(linhas), encoding="utf-8")
                            except Exception:
                                pass
                            st.success("Chave salva com sucesso!")
                            st.rerun()
                        else:
                            st.error("Chave inválida.")
                with col_sb2:
                    if st.button("⚡ Testar", use_container_width=True, key="btn_test_key_sidebar"):
                        chave_teste = nova_chave_side or api_key
                        if chave_teste:
                            ok, msg = testar_conexao_gemini(chave_teste)
                            if ok:
                                st.success("✅ Conexão ativa!")
                            else:
                                st.error(f"❌ Erro: {msg}")
                        else:
                            st.warning("Insira uma chave.")
                st.caption("👉 [Obter chave no Google AI Studio](https://aistudio.google.com/apikey)")

    st.caption("Versão 2.0 • Coleta ao vivo ZAP Imóveis")


# ==================== CABEÇALHO EXECUTIVO EXPANDH BI ====================
tema_bi.render_header_executivo(
    total_ativos=len(imoveis_lista),
    total_venda=len(imoveis_venda),
    total_locacao=len(imoveis_locacao),
    data_pub=data_pub_formatada,
    departamento_ativo=departamento_ativo,
)
tema_bi.render_modal_metodologia()


def render_avaliacao_matricula():
    api_key_atual = obter_chave_gemini()
    perfil_usr = st.session_state.get("perfil_usuario", "Diretoria")

    if not api_key_atual or len(api_key_atual) < 20:
        if perfil_usr == "Diretoria":
            st.warning(
                "🔑 **Chave do Google AI Studio Requerida para OCR Visual de Matrículas:**\n\n"
                "A leitura e extração de dados da matrícula em PDF utiliza a IA do Google Gemini. "
                "Por favor, configure sua chave de API gerada no Google AI Studio abaixo:"
            )
            col_k1, col_k2 = st.columns([3, 1])
            with col_k1:
                nova_chave = st.text_input(
                    "Cole aqui sua chave do Google AI Studio:",
                    type="password",
                    placeholder="Insira sua chave...",
                    key="nova_gemini_key_matricula"
                ).strip()
            with col_k2:
                st.write("")
                st.write("")
                if st.button("💾 Salvar Chave", type="primary", use_container_width=True, key="btn_salvar_key_mat"):
                    if len(nova_chave) >= 20:
                        st.session_state["gemini_api_key_override"] = nova_chave
                        os.environ["GEMINI_API_KEY"] = nova_chave
                        try:
                            caminho_env = Path(".env")
                            linhas = []
                            if caminho_env.exists():
                                for l in caminho_env.read_text(encoding="utf-8").splitlines():
                                    if l.startswith("GEMINI_API_KEY="):
                                        linhas.append(f'GEMINI_API_KEY="{nova_chave}"')
                                    else:
                                        linhas.append(l)
                            else:
                                linhas.append(f'GEMINI_API_KEY="{nova_chave}"')
                            caminho_env.write_text("\n".join(linhas), encoding="utf-8")
                        except Exception:
                            pass
                        st.success("Chave salva com sucesso!")
                        st.rerun()
                    else:
                        st.error("Chave inválida. Verifique o valor copiado do Google AI Studio.")
            st.caption("👉 [Obtenha uma chave gratuita no Google AI Studio (10 segundos)](https://aistudio.google.com/apikey)")
            st.markdown("---")
        else:
            st.error("⚠️ O serviço de OCR com IA não está ativo no momento. Solicite a um administrador da Diretoria para configurar a chave no sistema.")
            return

    col_upload, col_opcoes = st.columns([2, 1])

    with col_upload:
        uploaded_file = st.file_uploader(
            "Selecione ou arraste o PDF da Matrícula do Imóvel:",
            type=["pdf"],
            help="O documento pode ser escaneado ou digitalizado. O Gemini aplicará OCR nativo.",
        )

    with col_opcoes:
        st.markdown("**Ou utilize a matrícula de teste:**")
        usar_exemplo = st.button("📁 Carregar 'matricula.pdf' (Sertãozinho/SP)", use_container_width=True)

    caminho_pdf_processar = None

    if uploaded_file is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.read())
            caminho_pdf_processar = Path(tmp.name)
    elif usar_exemplo:
        exemplo_path = Path("matricula.pdf")
        if exemplo_path.exists():
            caminho_pdf_processar = exemplo_path
        else:
            st.error("Arquivo 'matricula.pdf' não encontrado na pasta raiz.")

    if caminho_pdf_processar:
        st.info(f"📄 Arquivo pronto para processamento: **{caminho_pdf_processar.name}**")
        
        if st.button("🚀 Iniciar Avaliação Completa do Imóvel", type="primary", use_container_width=True):
            progresso = st.progress(0, text="Iniciando motor de inteligência...")

            try:
                llm = ClienteLLM()

                # Etapa 1
                progresso.progress(20, text="[1/5] Lendo matrícula e executando OCR visual com Gemini Flash-Lite...")
                imovel = pipeline.etapa1_property_intake(llm, caminho_pdf_processar)

                # Etapa 2
                progresso.progress(40, text="[2/5] Geocodificando endereço e coletando anúncios ao vivo no ZAP Imóveis...")
                mercado = pipeline.etapa2_market_intelligence(imovel)

                # Etapa 3
                progresso.progress(60, text="[3/5] Aplicando homogeneização estatística e cálculo de venda...")
                venda = pipeline.etapa3_sales_valuation(imovel, mercado)

                # Etapa 4
                progresso.progress(80, text="[4/5] Estimando valor locatício e consultando taxa Selic no Bacen...")
                locacao = pipeline.etapa4_rental_valuation(imovel, mercado, venda)

                # Etapa 5
                progresso.progress(95, text="[5/5] Redigindo laudo técnico e compilando PDF executivo...")
                dados = {"imovel": imovel, "mercado": mercado, "venda": venda, "locacao": locacao}
                laudo_md = pipeline.etapa5_auditor_report(llm, dados)

                # Salvar arquivos
                pasta_saida = Path("laudos")
                pasta_saida = Path("laudos")
                pasta_saida.mkdir(exist_ok=True)
                carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
                caminho_laudo_md = pasta_saida / f"laudo_{carimbo}.md"
                caminho_laudo_com = pasta_saida / f"laudo_comercial_{carimbo}.pdf"
                caminho_laudo_per = pasta_saida / f"laudo_pericial_{carimbo}.pdf"
                caminho_dados_json = pasta_saida / f"dados_{carimbo}.json"

                caminho_laudo_md.write_text(laudo_md, encoding="utf-8")
                caminho_dados_json.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
                gerar_pdf.criar_laudo_pdf(dados, caminho_laudo_com, tipo_laudo="comercial")
                gerar_pdf.criar_laudo_pdf(dados, caminho_laudo_per, tipo_laudo="completo")

                progresso.progress(100, text="✅ Avaliação concluída com sucesso!")
                st.toast("Laudo gerado com sucesso!", icon="🎉")

                # ==================== EXIBIÇÃO DOS RESULTADOS ====================
                st.markdown("---")
                st.subheader("📊 Resumo Executivo da Avaliação")

                # KPIs Principais
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                with kpi1:
                    v_est = venda.get("valor_venda_estimado", 0)
                    st.metric("Valor de Venda Estimado", f"R$ {v_est:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                with kpi2:
                    f_min = venda.get("faixa_min", 0)
                    f_max = venda.get("faixa_max", 0)
                    st.metric("Faixa de Negociação (±10%)", f"R$ {f_min/1000:.0f}k - {f_max/1000:.0f}k")
                with kpi3:
                    alug = locacao.get("aluguel_mensal_estimado", 0)
                    st.metric("Aluguel Mensal Estimado", f"R$ {alug:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                with kpi4:
                    cap = locacao.get("rentabilidade_bruta_aa", locacao.get("rentabilidade_bruta_aa_adotada", 0))
                    st.metric("Cap Rate (Rentabilidade)", f"{cap:.2f}% a.a.")

                # Botões de Download em Destaque
                st.markdown("### 📥 Documentos Oficiais Expandh")
                col_btn1, col_btn2, col_btn3 = st.columns(3)
                with col_btn1:
                    with open(caminho_laudo_com, "rb") as f_com:
                        st.download_button(
                            label="📄 Baixar Laudo Comercial (1 Pág)",
                            data=f_com,
                            file_name=f"Laudo_Comercial_Expandh_{imovel.get('cidade')}_{carimbo}.pdf",
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True,
                            help="Documento visual de 1 página com logo Expandh e QR Code, perfeito para WhatsApp e proprietários."
                        )
                with col_btn2:
                    with open(caminho_laudo_per, "rb") as f_per:
                        st.download_button(
                            label="📑 Baixar Laudo Pericial NBR 14653",
                            data=f_per,
                            file_name=f"Laudo_Pericial_Expandh_{imovel.get('cidade')}_{carimbo}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                            help="Laudo técnico completo de 3-4 páginas com fundamentação ABNT e comparáveis ZAP."
                        )
                with col_btn3:
                    with open(caminho_dados_json, "rb") as f_json:
                        st.download_button(
                            label="📊 Baixar Dados Brutos (.json)",
                            data=f_json,
                            file_name=f"Dados_{carimbo}.json",
                            mime="application/json",
                            use_container_width=True,
                        )
                    with open(caminho_dados_json, "rb") as f_json:
                        st.download_button(
                            label="📊 Baixar Dados Brutos (.json)",
                            data=f_json,
                            file_name=f"Dados_{carimbo}.json",
                            mime="application/json",
                            use_container_width=True,
                        )

                # Detalhes do Imóvel e Amostras
                st.markdown("---")
                col_detalhes, col_amostras = st.columns([1, 1])

                with col_detalhes:
                    st.subheader("📌 Dados da Matrícula Extraídos")
                    st.write(f"**Matrícula:** {imovel.get('numero_matricula')} ({imovel.get('cartorio')})")
                    st.write(f"**Imóvel:** {imovel.get('tipo_imovel')} • {imovel.get('nome_condominio', '-')}")
                    st.write(f"**Endereço:** {imovel.get('endereco')}, {imovel.get('bairro')} - {imovel.get('cidade')}/{imovel.get('uf')}")
                    st.write(f"**Área Privativa:** {imovel.get('area_privativa_m2')} m² | **Área Total:** {imovel.get('area_total_m2')} m²")
                    st.write(f"**Configuração:** {imovel.get('quartos')} quartos | {imovel.get('vagas')} vaga(s)")
                    st.write(f"**Proprietário(s):** {', '.join(imovel.get('proprietarios_atuais', []))}")
                    onus_list = imovel.get('onus_e_gravames', [])
                    if onus_list:
                        st.warning(f"⚠️ **Ônus e Gravames:** {', '.join(onus_list)}")
                    else:
                        st.success("✅ Nenhum gravame registrado")

                with col_amostras:
                    st.subheader("🏘️ Amostras do Mercado (ZAP Imóveis)")
                    amostras_v = mercado.get("amostras", [])
                    if amostras_v:
                        df_amostras = pd.DataFrame([
                            {
                                "Bairro": a.get("bairro"),
                                "Área": f"{a.get('area')} m²",
                                "Preço": f"R$ {a.get('preco'):,.0f}",
                                "R$/m²": f"R$ {a.get('preco')/a.get('area'):,.0f}",
                                "Dist.": f"{a.get('distancia_km'):.2f} km" if a.get('distancia_km') else "-",
                            }
                            for a in amostras_v[:6]
                        ])
                        st.dataframe(df_amostras, use_container_width=True, hide_index=True)
                    else:
                        st.info("Nenhuma amostra direta formatada.")

                # Visualização do Laudo na Tela
                with st.expander("👁️ Visualizar Laudo Completo em Texto"):
                    st.markdown(laudo_md)

            except Exception as e:
                msg_erro = str(e)
                perfil_usr = st.session_state.get("perfil_usuario", "Diretoria")
                if any(x in msg_erro for x in ["401", "API key not valid", "UNAUTHENTICATED", "ACCESS_TOKEN_TYPE_UNSUPPORTED"]):
                    st.error("❌ **Erro de Autenticação com o Serviço de IA:** A chave configurada expirou ou não foi reconhecida.")
                    if perfil_usr == "Diretoria":
                        st.warning("💡 **Atualização Administrativa da Chave:** Cole a nova chave ativa abaixo:")
                        col_err1, col_err2 = st.columns([3, 1])
                        with col_err1:
                            chave_erro = st.text_input(
                                "Nova Chave do Google AI Studio:",
                                type="password",
                                placeholder="Insira a chave...",
                                key="chave_correcao_401"
                            ).strip()
                        with col_err2:
                            st.write("")
                            st.write("")
                            if st.button("💾 Salvar e Reprocessar", type="primary", use_container_width=True, key="btn_salvar_erro_401"):
                                if len(chave_erro) >= 20:
                                    st.session_state["gemini_api_key_override"] = chave_erro
                                    os.environ["GEMINI_API_KEY"] = chave_erro
                                    try:
                                        caminho_env = Path(".env")
                                        linhas = []
                                        if caminho_env.exists():
                                            for l in caminho_env.read_text(encoding="utf-8").splitlines():
                                                if l.startswith("GEMINI_API_KEY="):
                                                    linhas.append(f'GEMINI_API_KEY="{chave_erro}"')
                                                else:
                                                    linhas.append(l)
                                        else:
                                            linhas.append(f'GEMINI_API_KEY="{chave_erro}"')
                                        caminho_env.write_text("\n".join(linhas), encoding="utf-8")
                                    except Exception:
                                        pass
                                    st.success("Chave salva! Clique novamente em Iniciar Avaliação.")
                                    st.rerun()
                                else:
                                    st.error("Chave inválida. Verifique o valor copiado.")
                        st.caption("ℹ️ *Dica para o Streamlit Cloud:* Você também pode salvar esta chave de forma definitiva nas configurações do aplicativo no menu **App Settings > Secrets** com `GEMINI_API_KEY = \"sua_chave\"`.")
                    else:
                        st.info("Comunique um administrador da Diretoria para atualizar a chave de API nas configurações do sistema.")
                else:
                    st.error(f"Erro durante o processamento: {e}")


# ==================== CARREGAMENTO DA AUDITORIA CONSOLIDADA ====================
PASTA_PROJETO = Path(__file__).resolve().parent
CAMINHO_CACHE_AUDITORIA = PASTA_PROJETO / "dados_auditoria_completa.json"


def obter_dados_auditoria_atualizados() -> dict:
    """Lê sempre a auditoria mais recente do arquivo no disco."""
    if CAMINHO_CACHE_AUDITORIA.exists():
        try:
            return json.loads(CAMINHO_CACHE_AUDITORIA.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def executar_auditoria_com_progresso_ui(operacao: str):
    """Executa a reavaliação de carteira exibindo cronômetro, temporizador e progresso ao vivo."""
    import auditar_carteira_completa

    st.markdown("---")
    st.markdown(f"### ⏱️ Reavaliação em Tempo Real • Carteira de {operacao}")
    st.caption("Cruzando todo o estoque ativo com comparáveis reais do ZAP Imóveis (NBR 14653).")

    card_container = st.container()
    with card_container:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            ph_tempo_dec = st.empty()
            ph_tempo_dec.metric("⏱️ Tempo Decorrido", "00:00")
        with c2:
            ph_tempo_est = st.empty()
            ph_tempo_est.metric("⏳ Estimado Restante", "Calculando...")
        with c3:
            ph_progresso = st.empty()
            ph_progresso.metric("📊 Progresso", "0 / 0 (0%)")
        with c4:
            ph_velocidade = st.empty()
            ph_velocidade.metric("⚡ Velocidade", "-")

        ph_bar = st.progress(0.0)
        ph_status = st.empty()
        ph_status.info("🚀 Iniciando auditoria: conectando ao feed e coletando comparáveis em paralelo...")

    def _prog_callback(atual, total, msg, seg_decorrido, seg_restante):
        pct = min(1.0, max(0.0, atual / total)) if total > 0 else 0.0
        ph_bar.progress(pct)

        m_dec, s_dec = divmod(int(seg_decorrido), 60)
        ph_tempo_dec.metric("⏱️ Tempo Decorrido", f"{m_dec:02d}:{s_dec:02d}")

        if seg_restante > 0 and atual > 3:
            m_res, s_res = divmod(int(seg_restante), 60)
            ph_tempo_est.metric("⏳ Estimado Restante", f"{m_res:02d}:{s_res:02d}")
        else:
            ph_tempo_est.metric("⏳ Estimado Restante", "Calculando...")

        ph_progresso.metric("📊 Progresso", f"{atual}/{total} ({pct*100:.0f}%)")

        if seg_decorrido > 0.5 and atual > 0:
            vel = atual / seg_decorrido
            ph_velocidade.metric("⚡ Velocidade", f"{vel:.1f} imov/s")

        ph_status.markdown(f"🔍 **Analisando:** `{msg}`")

    auditar_carteira_completa.executar_auditoria_completa(progress_callback=_prog_callback)

    ph_bar.progress(1.0)
    ph_tempo_est.metric("⏳ Estimado Restante", "00:00")
    ph_status.success("🎉 **Reavaliação concluída com sucesso! Atualizando painel...**")
    time.sleep(1.2)
    st.rerun()


def render_painel_operacao(imoveis_lista: list, operacao: str, api_key_val: str = ""):
    imoveis_op = [x for x in imoveis_lista if x.get("transacao") == operacao]
    key_suf = "vendas" if operacao == "Venda" else "locacao"
    rotulo_preco = "Preço de Venda" if operacao == "Venda" else "Aluguel Mensal"
    rotulo_m2 = "R$/m² de Venda" if operacao == "Venda" else "R$/m² Aluguel"
    icone = "🏷️" if operacao == "Venda" else "🔑"

    dados_aud = obter_dados_auditoria_atualizados()
    secao_aud = dados_aud.get(key_suf, {}) or dados_aud.get(key_suf.rstrip("s"), {})
    stats = secao_aud.get("estatisticas", {})
    auditados_op_raw = secao_aud.get("imoveis", [])

    # Fallback se a estrutura não tiver o nó específico
    if not auditados_op_raw and imoveis_op:
        auditados_op_raw = [r for r in dados_aud.get("imoveis", []) if r.get("Transação") == operacao]

    # Sincronização dinâmica com os imóveis ativos do Feed XML:
    auditados_map = {str(r.get("Código")): r for r in auditados_op_raw if r.get("Código")}
    auditados_op = []
    
    for im in imoveis_op:
        im_id = str(im.get("id"))
        if im_id in auditados_map:
            auditados_op.append(auditados_map[im_id])
        else:
            # Imóvel novo do XML ainda sem auditoria ZAP
            auditados_op.append({
                "Código": im_id,
                "Título": im.get("titulo", "-"),
                "Transação": operacao,
                "Tipo": im.get("tipo", "-"),
                "Bairro": im.get("bairro", "-"),
                "Cidade": im.get("cidade", "-"),
                "UF": im.get("uf", "SP"),
                "Endereço": im.get("endereco_rua", "-"),
                "Área (m²)": im.get("area_principal", 0),
                "Quartos": im.get("quartos", 0),
                "Vagas": im.get("vagas", 0),
                "Preço Anunciado (R$)": im.get("preco", 0),
                "R$/m² Anunciado": im.get("preco_m2", 0),
                "Valor Mercado Estimado (R$)": None,
                "Faixa Mínima (R$)": None,
                "Faixa Máxima (R$)": None,
                "Desvio (%)": "-",
                "Desvio_Num": None,
                "Diferença (R$)": None,
                "Status": "⚪ Aguardando Auditoria",
                "Mediana R$/m² Região": None,
                "Amostras Usadas": 0,
                "Diagnóstico": "Imóvel recém-adicionado no feed XML. Execute a reavaliação para coletar amostras ZAP.",
                "Ação Comercial Recomendada": "Reexecutar auditoria de carteira",
                "Foto": im.get("foto_capa", ""),
                "Data Auditoria": None,
            })

    residenciais_com_desvio = [r for r in auditados_op if r.get("Desvio_Num") is not None]
    total_res = len(residenciais_com_desvio)

    # Barra de Resumo no Topo
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(f"Total {operacao}", f"{len(imoveis_op)} imóveis", f"Imobiliária: {cabecalho.get('imobiliaria', 'Expandh')}")
    with c2:
        pct_audit = (total_res / len(imoveis_op) * 100) if imoveis_op else 0
        st.metric("Auditados com Mercado", f"{total_res} de {len(imoveis_op)} imóveis", f"{pct_audit:.0f}% da carteira auditada")
    with c3:
        if operacao == "Venda":
            precos = [x["preco"] for x in imoveis_op if x["preco"] > 0]
            vgv = sum(precos)
            st.metric("VGV Total da Carteira", f"R$ {vgv/1_000_000:.1f} Milhões", f"Ticket Médio: R$ {vgv/len(precos):,.0f}" if precos else "-")
        else:
            alugueis = [x["preco"] for x in imoveis_op if x["preco"] > 0]
            alug_medio = sum(alugueis)/len(alugueis) if alugueis else 0
            st.metric("Aluguel Médio Anunciado", f"R$ {alug_medio:,.2f}/mês", f"{len(alugueis)} unidades locáveis")
    with c4:
        cidades_op = sorted(list({x['cidade'] for x in imoveis_op if x['cidade']}))
        st.metric("Praças Atendidas", f"{len(cidades_op)} cidades", ", ".join(cidades_op[:2]))

    st.markdown("---")

    sub_tab_lote, sub_tab_ind = st.tabs([
        f"📊 Diagnóstico Geral da Carteira ({len(imoveis_op)} imóveis)",
        f"🔍 Auditar Imóvel Individual de {operacao}",
    ])

    with sub_tab_lote:
        if auditados_op:
            q_super = sum(1 for r in auditados_op if r.get("Status") and "Muito Acima" in r["Status"])
            q_acima = sum(1 for r in auditados_op if r.get("Status") and "Acima do Mercado" in r["Status"])
            q_justo = sum(1 for r in auditados_op if r.get("Status") and "Preço Justo" in r["Status"])
            q_oport = sum(1 for r in auditados_op if r.get("Status") and "Oportunidade" in r["Status"])
            q_aguardando = sum(1 for r in auditados_op if r.get("Status") and "Aguardando Auditoria" in r["Status"])

            col_h1, col_h2 = st.columns([3, 1])
            with col_h1:
                st.markdown(f"#### 📈 Saúde e Posicionamento da Carteira de {operacao.upper()}")
            with col_h2:
                if st.button(f"🔄 Reexecutar Auditoria de {operacao}", key=f"reexec_{key_suf}", use_container_width=True):
                    executar_auditoria_com_progresso_ui(operacao)

            if q_aguardando > 0:
                st.info(f"💡 Foram identificados **{q_aguardando} novo(s) imóvel(is)** no feed XML que ainda não possuem amostragem ZAP. Clique no botão ao lado **'🔄 Reexecutar Auditoria de {operacao}'** para calculá-los.")

            k1, k2, k3, k4 = st.columns(4)
            with k1:
                st.metric(
                    "🔴 Muito Acima (> 15%)",
                    f"{q_super} imóveis",
                    f"{q_super/total_res*100:.1f}% da base" if total_res else "0%",
                    help=f"Imóveis com alto risco de ficarem encalhados e baixa liquidez. Prioridade para renegociação com proprietário.",
                )
            with k2:
                st.metric(
                    "🟡 Levemente Acima (+5% a 15%)",
                    f"{q_acima} imóveis",
                    f"{q_acima/total_res*100:.1f}% da base" if total_res else "0%",
                    help="Margem para negociação comercial com compradores ou inquilinos.",
                )
            with k3:
                st.metric(
                    "🟢 No Preço Justo (±5%)",
                    f"{q_justo} imóveis",
                    f"{q_justo/total_res*100:.1f}% da base" if total_res else "0%",
                    help="Posicionamento perfeito e alta competitividade nos portais.",
                )
            with k4:
                st.metric(
                    "🔵 Oportunidades (< -7%)",
                    f"{q_oport} imóveis",
                    f"{q_oport/total_res*100:.1f}% da base" if total_res else "0%",
                    help="Preço abaixo do mercado. Potencial de fechamento acelerado.",
                )

            st.markdown("---")

            col_f_status, col_btn_csv = st.columns([2, 1])
            with col_f_status:
                q_condicionado = sum(1 for r in auditados_op if r.get("Condicionante Preço") or "Ágio" in r.get("Status", "") or "Parcelas" in r.get("Status", ""))
                opcoes_status = [
                    f"Todos os Imóveis de {operacao} ({len(auditados_op)})",
                    f"🔴 Apenas Muito Acima ({q_super})",
                    f"🟡 Apenas Acima do Mercado ({q_acima})",
                    f"🟢 Apenas no Preço Justo ({q_justo})",
                    f"🔵 Apenas Oportunidades ({q_oport})",
                ]
                if q_condicionado > 0:
                    opcoes_status.append(f"⚠️ Ágio / Condicionados ({q_condicionado})")
                if q_aguardando > 0:
                    opcoes_status.append(f"⚪ Aguardando Auditoria ({q_aguardando})")
                opcoes_status.append(f"⚪ Sem Comparáveis Suficientes ({len(auditados_op) - total_res - q_aguardando})")

                escolha_st = st.selectbox("Filtrar tabela por diagnóstico:", opcoes_status, index=0, key=f"st_sel_{key_suf}")

            tabela_f = auditados_op
            if "Muito Acima" in escolha_st:
                tabela_f = [r for r in tabela_f if "Muito Acima" in r.get("Status", "")]
            elif "Acima do Mercado" in escolha_st:
                tabela_f = [r for r in tabela_f if "Acima do Mercado" in r.get("Status", "")]
            elif "Preço Justo" in escolha_st:
                tabela_f = [r for r in tabela_f if "Preço Justo" in r.get("Status", "")]
            elif "Oportunidades" in escolha_st:
                tabela_f = [r for r in tabela_f if "Oportunidade" in r.get("Status", "")]
            elif "Ágio" in escolha_st or "Condicionados" in escolha_st:
                tabela_f = [r for r in tabela_f if r.get("Condicionante Preço") or "Ágio" in r.get("Status", "") or "Parcelas" in r.get("Status", "")]
            elif "Aguardando Auditoria" in escolha_st:
                tabela_f = [r for r in tabela_f if "Aguardando Auditoria" in r.get("Status", "")]
            elif "Sem Comparáveis" in escolha_st:
                tabela_f = [r for r in tabela_f if r.get("Desvio_Num") is None and "Aguardando Auditoria" not in r.get("Status", "")]

            df_ex = pd.DataFrame(tabela_f)
            df_fmt = df_ex.copy()
            df_fmt[rotulo_preco] = df_fmt["Preço Anunciado (R$)"].apply(lambda v: f"R$ {v:,.0f}".replace(",", ".") if pd.notnull(v) and v else "R$ 0")
            df_fmt["Valor Mercado"] = df_fmt["Valor Mercado Estimado (R$)"].apply(
                lambda v: f"R$ {v:,.0f}".replace(",", ".") if pd.notnull(v) and v else "-"
            )
            df_fmt["Diferença"] = df_fmt["Diferença (R$)"].apply(
                lambda v: f"R$ {v:+,.0f}".replace(",", ".") if pd.notnull(v) and v is not None else "-"
            )

            cols_tab = ["Código", "Tipo", "Bairro", "Área (m²)", rotulo_preco, "Valor Mercado", "Desvio (%)", "Status"]
            if "Tipo Condição" in df_fmt.columns:
                cols_tab.append("Tipo Condição")
            cols_tab.append("Ação Comercial Recomendada")
            st.dataframe(df_fmt[cols_tab], use_container_width=True, hide_index=True)

            with col_btn_csv:
                st.write("")
                csv_nome = f"auditoria_{key_suf}_expandh.csv"
                caminho_csv = PASTA_PROJETO / "laudos" / csv_nome
                if caminho_csv.exists():
                    with open(caminho_csv, "rb") as f_c:
                        st.download_button(
                            label=f"📥 Baixar Planilha de {operacao} (.CSV / Excel)",
                            data=f_c,
                            file_name=csv_nome,
                            mime="text/csv",
                            type="primary",
                            key=f"btn_dl_{key_suf}",
                            use_container_width=True,
                        )
        else:
            st.warning(f"Nenhuma auditoria executada ainda para a carteira de {operacao}.")
            if st.button(f"🚀 Executar Auditoria Geral de {operacao} Agora", type="primary", key=f"btn_init_{key_suf}"):
                executar_auditoria_com_progresso_ui(operacao)

    with sub_tab_ind:
        st.markdown(f"#### 🎯 Selecionar Imóvel de {operacao}")
        fc1, fc2, fc3 = st.columns([1.2, 1.5, 1.5])
        with fc1:
            tipos_disp = ["Todos"] + sorted(list({x["tipo"] for x in imoveis_op if x.get("tipo")}))
            f_tp = st.selectbox("Tipo de Imóvel", tipos_disp, index=0, key=f"ftp_{key_suf}")
        with fc2:
            bairros_disp = ["Todos"] + sorted(list({x["bairro"] for x in imoveis_op if x.get("bairro")}))
            f_br = st.selectbox("Bairro", bairros_disp, index=0, key=f"fbr_{key_suf}")
        with fc3:
            f_bc = st.text_input("Buscar Código ou Logradouro", placeholder="Ex: código ou rua...", key=f"fbc_{key_suf}")

        filtrados_ind = imoveis_op
        if f_tp != "Todos":
            filtrados_ind = [x for x in filtrados_ind if x["tipo"] == f_tp]
        if f_br != "Todos":
            filtrados_ind = [x for x in filtrados_ind if x["bairro"] == f_br]
        if f_bc:
            bterm = f_bc.lower().strip()
            filtrados_ind = [
                x for x in filtrados_ind
                if bterm in x.get("id", "").lower()
                or bterm in x.get("endereco", "").lower()
                or bterm in x.get("titulo", "").lower()
                or bterm in x.get("bairro", "").lower()
            ]

        if not filtrados_ind:
            st.warning("Nenhum imóvel encontrado com os filtros selecionados.")
        else:
            opcoes_im = {
                f"[{x['id']}] {x['tipo']} • {x['bairro']} • R$ {x['preco']:,.0f}" + (
                    f" (Pacote R$ {x['preco'] + x['condominio'] + x['iptu']:,.0f})" if operacao == "Locação" else ""
                ): x
                for x in filtrados_ind
            }
            sel_label = st.selectbox("Selecione o imóvel para auditar:", list(opcoes_im.keys()), key=f"sel_im_{key_suf}")
            imovel_sel = opcoes_im[sel_label]

            col_f, col_d = st.columns([1, 2])
            with col_f:
                if imovel_sel.get("foto_capa"):
                    st.image(
                        imovel_sel["foto_capa"],
                        use_container_width=True,
                        caption=f"Foto • Cód: {imovel_sel['id']}",
                    )
                else:
                    st.info("📷 Sem foto principal cadastrada")

            with col_d:
                st.markdown(f"### {imovel_sel.get('titulo') or imovel_sel.get('tipo')}")
                st.write(f"📍 **Endereço:** {imovel_sel.get('endereco')}, {imovel_sel.get('bairro')} - {imovel_sel.get('cidade')}/SP")
                st.write(f"📐 **Área:** {imovel_sel.get('area_principal')} m² ({imovel_sel.get('quartos')} quartos | {imovel_sel.get('suites')} suíte(s) | {imovel_sel.get('vagas')} vagas)")
                st.write(f"💰 **{rotulo_preco}:** R$ {imovel_sel.get('preco', 0):,.2f} ({rotulo_m2}: R$ {imovel_sel.get('preco_m2', 0):,.2f}/m²)")
                if operacao == "Locação":
                    pct_total = imovel_sel.get("preco", 0) + imovel_sel.get("condominio", 0) + imovel_sel.get("iptu", 0)
                    st.info(f"📦 **Pacote Completo de Locação:** **R$ {pct_total:,.2f} / mês** (Aluguel R$ {imovel_sel.get('preco', 0):,.0f} + Condomínio R$ {imovel_sel.get('condominio', 0):,.0f} + IPTU R$ {imovel_sel.get('iptu', 0):,.0f})")
                elif imovel_sel.get("condominio") or imovel_sel.get("iptu"):
                    st.write(f"🏷️ Condomínio: R$ {imovel_sel.get('condominio', 0):,.2f} | IPTU: R$ {imovel_sel.get('iptu', 0):,.2f}")

            # Detecção de Condicionante Financeira (Ágio / Parcelas a Vencer)
            cond_auto = reavaliacao_carteira.identificar_condicionante_preco(imovel_sel)
            if cond_auto["is_condicionado"]:
                obs_crm_txt = f"\n• **Observação do CRM:** {cond_auto['observacao_interna']}" if cond_auto.get("observacao_interna") else ""
                st.warning(
                    f"⚠️ **Alerta de Condicionante Financeira (Ágio / Parcelas a Vencer Detectadas)**\n\n"
                    f"• **Gatilho no Anúncio:** *\"{cond_auto['detalhes']}\"*\n"
                    f"• **Preço Anunciado:** **R$ {imovel_sel.get('preco', 0):,.2f}** *(refere-se apenas à entrada / repasse)*{obs_crm_txt}\n\n"
                    f"💡 *Para evitar distorções, o sistema calcula o **Custo Efetivo Total de Aquisição** (Entrada + Saldo Devedor a Vencer) para balizar o valor justo real da NBR 14653.*"
                )

            with st.expander("💳 Apuração de Saldo Devedor & Parcelas (Anti-Armadilha de Ágio)", expanded=cond_auto["is_condicionado"]):
                cp1, cp2, cp3 = st.columns(3)
                with cp1:
                    n_parc_input = st.number_input(
                        "Parcelas Restantes a Vencer:",
                        min_value=0,
                        max_value=420,
                        value=int(cond_auto.get("num_parcelas") or 0),
                        step=1,
                        key=f"n_parc_{imovel_sel['id']}_{key_suf}",
                        help="Número de parcelas que o comprador assumirá junto à loteadora ou instituição financeira."
                    )
                with cp2:
                    val_parc_input = st.number_input(
                        "Valor da Parcela Atual (R$):",
                        min_value=0.0,
                        max_value=100000.0,
                        value=float(cond_auto.get("valor_parcela") or 0.0),
                        step=50.0,
                        key=f"val_parc_{imovel_sel['id']}_{key_suf}",
                        help="Valor nominal de cada parcela mensal."
                    )
                with cp3:
                    saldo_dev_padrao = (n_parc_input * val_parc_input) if (n_parc_input > 0 and val_parc_input > 0) else float(cond_auto.get("saldo_devedor_estimado") or 0.0)
                    saldo_dev_input = st.number_input(
                        "Saldo Devedor Total a Assumir (R$):",
                        min_value=0.0,
                        max_value=10000000.0,
                        value=float(saldo_dev_padrao),
                        step=1000.0,
                        key=f"saldo_dev_{imovel_sel['id']}_{key_suf}",
                        help="Dívida total a ser somada à entrada anunciada para apurar o custo total real de aquisição."
                    )

            # Detecção e Ajuste de Corredor Nobre / Comercial (NBR 14653)
            fator_loc_auto, justif_auto = reavaliacao_carteira.identificar_fator_corredor(imovel_sel)
            if fator_loc_auto > 1.0:
                st.info(f"⭐ **Polo de Valorização / Corredor Comercial Nobre Detectado:**\n{justif_auto}")

            with st.expander("⚙️ Ajuste Técnico de Localização (NBR 14653 • Fator de Corredor / Zona)", expanded=(fator_loc_auto > 1.0)):
                fator_loc_input = st.slider(
                    "Fator de Ponderação de Localização (Floc):",
                    min_value=0.50,
                    max_value=3.50,
                    value=float(fator_loc_auto),
                    step=0.05,
                    key=f"slider_floc_{imovel_sel['id']}_{key_suf}",
                    help="Ajusta o valor unitário caso o imóvel esteja em via nobre/comercial, esquina ou corredor arterial em relação aos comparáveis gerais da cidade.",
                )

            btn_rev_ind = st.button(f"🚀 Reavaliar Este Imóvel de {operacao} no ZAP", type="primary", use_container_width=True, key=f"btn_reval_{key_suf}")

            if btn_rev_ind:
                with st.spinner(f"Consultando concorrência ao vivo no ZAP para {imovel_sel.get('tipo')} no {imovel_sel.get('bairro')}..."):
                    saldo_manual = saldo_dev_input if (cond_auto["is_condicionado"] or saldo_dev_input > 0) else None
                    res_aud = reavaliacao_carteira.reavaliar_imovel_feed(
                        imovel_sel,
                        fator_oferta=pipeline.FATOR_OFERTA,
                        fator_localizacao=fator_loc_input,
                        saldo_devedor_manual=saldo_manual,
                    )

                if not res_aud.get("sucesso"):
                    st.warning(f"⚠️ Não foi possível reavaliar: {res_aud.get('motivo')}")
                else:
                    st.success("✅ Auditoria de mercado concluída com sucesso!")
                    st.markdown("---")

                    if res_aud.get("is_condicionado"):
                        st.markdown("##### 💳 Composição do Custo Real de Aquisição (Ágio + Parcelas)")
                        rk0, rk1, rk2, rk3 = st.columns(4)
                        with rk0:
                            st.metric(
                                "Entrada / Ágio Anunciado",
                                f"R$ {res_aud['preco_anunciado']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                            )
                        with rk1:
                            st.metric(
                                "Saldo Devedor a Vencer",
                                f"R$ {res_aud['saldo_devedor_estimado']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                            )
                        with rk2:
                            st.metric(
                                "Custo Efetivo Total",
                                f"R$ {res_aud['preco_efetivo_total']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                            )
                        with rk3:
                            dp = res_aud["desvio_pct"]
                            st.metric(
                                "Valor Mercado NBR",
                                f"R$ {res_aud['valor_fechamento_estimado']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                                f"{dp:+.1f}% ({res_aud['status']})",
                                delta_color="inverse" if dp > 0 else "normal",
                            )

                        if "vista da lago" in (imovel_sel.get("bairro") or "").lower():
                            st.info(
                                "🏘️ **Análise Comparativa com Lotes Vizinhos Quitados no Vista da Lago:**\n\n"
                                "• **Lotes Quitados na Mesma Região (ex: V78521 e V48521 - 240 m²):** Anunciados por **R$ 119.000,00** (R$ 495,83/m²) 100% quitados e escriturados.\n"
                                f"• **Este Lote ({imovel_sel['id']} - 254 m²):** Custa **R$ {res_aud['preco_efetivo_total']:,.2f}** ao final das parcelas (R$ {res_aud['preco_efetivo_total']/imovel_sel['area_principal']:,.2f}/m²).\n"
                                f"• **Veredito de Mercado:** Comprar o lote quitado vizinho economiza **R$ {res_aud['preco_efetivo_total'] - 119000:,.2f}** para o adquirente!"
                            )
                    else:
                        rk1, rk2, rk3, rk4 = st.columns(4)
                        with rk1:
                            st.metric(
                                f"{rotulo_preco} Anunciado",
                                f"R$ {res_aud['preco_anunciado']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                            )
                        with rk2:
                            st.metric(
                                "Valor Justo de Mercado",
                                f"R$ {res_aud['valor_fechamento_estimado']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                                f"Faixa: R$ {res_aud['faixa_min']:,.0f} - R$ {res_aud['faixa_max']:,.0f}",
                            )
                        with rk3:
                            dp = res_aud["desvio_pct"]
                            st.metric(
                                "Desvio vs. Mercado",
                                f"{dp:+.1f}%",
                                res_aud["status"],
                                delta_color="inverse" if dp > 0 else "normal",
                            )
                        with rk4:
                            st.metric(
                                "Mediana da Concorrência",
                                f"R$ {res_aud['mediana_m2_concorrencia']:,.2f}/m²",
                                f"{res_aud['n_amostras']} imóveis analisados",
                            )

                    st.info(f"**Diagnóstico:** {res_aud['diagnostico']}\n\n**Ação Comercial Recomendada:** {res_aud['acao_sugerida']}")

                    # Amostras do ZAP
                    amostras = res_aud.get("amostras", [])
                    if amostras:
                        st.markdown(f"#### 🏘️ Comparáveis Reais de {operacao} no ZAP Imóveis")
                        df_cp = pd.DataFrame([
                            {
                                "Bairro": a.get("bairro"),
                                "Área": f"{a.get('area')} m²",
                                rotulo_preco: f"R$ {a.get('preco'):,.0f}",
                                rotulo_m2: f"R$ {a.get('preco')/a.get('area'):,.0f}",
                                "Distância": f"{a.get('distancia_km'):.2f} km" if a.get("distancia_km") else "-",
                                "Link do Anúncio": a.get("url", ""),
                            }
                            for a in amostras
                        ])
                        st.dataframe(
                            df_cp,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Link do Anúncio": st.column_config.LinkColumn("Ver no ZAP")
                            },
                        )

                    # Roteiro WhatsApp (IA & NBR 14653)
                    st.markdown("#### 💬 Gerador de Argumentário de WhatsApp (IA)")
                    st.caption("Cria mensagem persuasiva pronta para envio direto pelo WhatsApp com dados técnicos da NBR 14653.")

                    col_wa_o, col_wa_c, col_wa_k = st.columns([1.5, 1.2, 1.3])
                    with col_wa_o:
                        tipo_wa_ind = st.selectbox(
                            "Objetivo da Mensagem:",
                            options=[
                                ("proprietario", "🎯 Reprecificação com Proprietário"),
                                ("comprador", "🤝 Apresentação para Comprador/Inquilino"),
                            ],
                            format_func=lambda x: x[1],
                            key=f"wa_obj_{imovel_sel['id']}_{key_suf}",
                        )[0]
                    with col_wa_c:
                        cli_wa_ind = st.text_input("Nome do Cliente:", value="Dr. / Sr.", key=f"wa_cli_{imovel_sel['id']}_{key_suf}")
                    with col_wa_k:
                        cor_wa_ind = st.text_input("Nome do Consultor:", value="Consultor Expandh", key=f"wa_cor_{imovel_sel['id']}_{key_suf}")

                    col_wa_f, col_wa_btn = st.columns([1.5, 2.5])
                    with col_wa_f:
                        fone_wa_ind = st.text_input("WhatsApp com DDD (opcional):", placeholder="16999998888", key=f"wa_tel_{imovel_sel['id']}_{key_suf}")
                    with col_wa_btn:
                        st.write("")
                        st.write("")
                        btn_gerar_ind = st.button("⚡ Gerar Mensagem com IA", key=f"btn_wa_ind_{imovel_sel['id']}_{key_suf}", type="secondary", use_container_width=True)

                    cache_key_ind = f"msg_wa_cache_{imovel_sel['id']}_{tipo_wa_ind}"
                    if btn_gerar_ind or cache_key_ind not in st.session_state:
                        dados_para_wa_ind = {
                            "Código": imovel_sel["id"],
                            "Tipo": imovel_sel.get("tipo", "Imóvel"),
                            "Bairro": imovel_sel.get("bairro", "-"),
                            "Cidade": imovel_sel.get("cidade", "Sertãozinho"),
                            "Endereço": imovel_sel.get("endereco_rua", "-"),
                            "Preço Anunciado (R$)": res_aud["preco_anunciado"],
                            "Valor Mercado Estimado (R$)": res_aud["valor_mercado_estimado"],
                            "Desvio (%)": f"{res_aud['desvio_percentual']:+.1f}%",
                            "Status": res_aud["status"],
                            "Amostras Usadas": res_aud["n_amostras"],
                        }
                        st.session_state[cache_key_ind] = argumentario.gerar_argumentario_whatsapp(
                            dados_para_wa_ind,
                            tipo_publico=tipo_wa_ind,
                            nome_cliente=cli_wa_ind,
                            nome_corretor=cor_wa_ind,
                        )

                    msg_texto_ind = st.text_area(
                        "Mensagem Pronta para WhatsApp:",
                        value=st.session_state.get(cache_key_ind, ""),
                        height=160,
                        key=f"txt_rot_{imovel_sel['id']}_{key_suf}",
                    )

                    link_wa_ind = argumentario.criar_link_direto_whatsapp(msg_texto_ind, fone_wa_ind)
                    st.link_button("📲 Abrir no WhatsApp Web / Celular", link_wa_ind, type="primary")

                    st.markdown("---")

                    # Emissão de Laudos PDF com Identidade Oficial Expandh
                    st.markdown("#### 📑 Emissão de Laudos em PDF (Identidade Oficial Expandh)")
                    st.caption("Laudos personalizados com logotipo oficial da Expandh Imobiliária, dados de contato e QR Code de validação.")

                    col_pdf1, col_pdf2 = st.columns(2)
                    with col_pdf1:
                        if st.button("📄 Gerar Laudo Comercial (1 Pág)", key=f"btn_pdf_com_{imovel_sel['id']}_{key_suf}", use_container_width=True):
                            with st.spinner("Gerando Laudo Comercial Expandh..."):
                                pasta_s = Path("laudos")
                                pasta_s.mkdir(exist_ok=True)
                                carimbo_f = datetime.now().strftime("%Y%m%d_%H%M%S")
                                caminho_pdf_com = pasta_s / f"laudo_comercial_{key_suf}_{imovel_sel['id']}_{carimbo_f}.pdf"

                                imp = reavaliacao_carteira.converter_item_feed_para_imovel(imovel_sel)
                                merp = pipeline.etapa2_market_intelligence(imp)
                                venp = pipeline.etapa3_sales_valuation(imp, merp)
                                locp = pipeline.etapa4_rental_valuation(imp, merp, venp)
                                dp = {"imovel": imp, "mercado": merp, "venda": venp, "locacao": locp}

                                gerar_pdf.criar_laudo_pdf(dp, caminho_pdf_com, tipo_laudo="comercial")
                                st.session_state[f"pdf_com_{imovel_sel['id']}"] = str(caminho_pdf_com)

                        pdf_com_path = st.session_state.get(f"pdf_com_{imovel_sel['id']}")
                        if pdf_com_path and Path(pdf_com_path).exists():
                            with open(pdf_com_path, "rb") as fp_c:
                                st.download_button(
                                    label="📥 Baixar Laudo Comercial (1 Pág)",
                                    data=fp_c,
                                    file_name=Path(pdf_com_path).name,
                                    mime="application/pdf",
                                    type="primary",
                                    key=f"dl_pdf_com_{imovel_sel['id']}_{key_suf}",
                                    use_container_width=True,
                                    help="Relatório executivo conciso com logo Expandh e QR Code, ideal para WhatsApp e proprietários."
                                )

                    with col_pdf2:
                        if st.button("📑 Gerar Laudo Pericial NBR 14653", key=f"btn_pdf_per_{imovel_sel['id']}_{key_suf}", use_container_width=True):
                            with st.spinner("Compilando Laudo Pericial NBR 14653..."):
                                pasta_s = Path("laudos")
                                pasta_s.mkdir(exist_ok=True)
                                carimbo_f = datetime.now().strftime("%Y%m%d_%H%M%S")
                                caminho_pdf_per = pasta_s / f"laudo_pericial_{key_suf}_{imovel_sel['id']}_{carimbo_f}.pdf"

                                imp = reavaliacao_carteira.converter_item_feed_para_imovel(imovel_sel)
                                merp = pipeline.etapa2_market_intelligence(imp)
                                venp = pipeline.etapa3_sales_valuation(imp, merp)
                                locp = pipeline.etapa4_rental_valuation(imp, merp, venp)
                                dp = {"imovel": imp, "mercado": merp, "venda": venp, "locacao": locp}

                                gerar_pdf.criar_laudo_pdf(dp, caminho_pdf_per, tipo_laudo="completo")
                                st.session_state[f"pdf_per_{imovel_sel['id']}"] = str(caminho_pdf_per)

                        pdf_per_path = st.session_state.get(f"pdf_per_{imovel_sel['id']}")
                        if pdf_per_path and Path(pdf_per_path).exists():
                            with open(pdf_per_path, "rb") as fp_p:
                                st.download_button(
                                    label="📥 Baixar Laudo Pericial Completo",
                                    data=fp_p,
                                    file_name=Path(pdf_per_path).name,
                                    mime="application/pdf",
                                    key=f"dl_pdf_per_{imovel_sel['id']}_{key_suf}",
                                    use_container_width=True,
                                    help="Documento técnico completo com fundamentação ABNT, regressão estatística e comparáveis."
                                )


def render_historico_laudos():
    st.subheader("Laudos Gerados Anteriormente")
    arquivos_laudos = sorted(glob.glob("laudos/*.pdf"), reverse=True)

    if arquivos_laudos:
        for arq in arquivos_laudos:
            p = Path(arq)
            col_l1, col_l2 = st.columns([3, 1])
            with col_l1:
                st.write(f"📄 **{p.name}** • {datetime.fromtimestamp(p.stat().st_mtime).strftime('%d/%m/%Y às %H:%M')}")
            with col_l2:
                with open(p, "rb") as f_down:
                    st.download_button(
                        label="📥 Baixar PDF",
                        data=f_down,
                        file_name=p.name,
                        mime="application/pdf",
                        key=p.name,
                    )
    else:
        st.info("Nenhum laudo gerado ainda na pasta `laudos/`.")


# ==================== DISPATCHER DA NAVEGAÇÃO LATERAL ====================
if "Briefing Matinal" in aba_selecionada:
    resumo_matinal.render_painel_briefing(departamento=departamento_ativo)

elif "Carteira de VENDAS" in aba_selecionada:
    st.subheader("🏷️ Carteira de VENDAS • Auditoria & Reprecificação")
    st.caption("Precificação de venda, comparação com fechamentos NBR e diagnóstico de liquidez.")
    render_painel_operacao(imoveis_lista, "Venda", api_key)

elif "Carteira de LOCAÇÃO" in aba_selecionada:
    st.subheader("🔑 Carteira de LOCAÇÃO • Auditoria & Rentabilidade")
    st.caption("Precificação de aluguel mensal, custo total de ocupação (pacote) e comparáveis ao vivo.")
    render_painel_operacao(imoveis_lista, "Locação", api_key)

elif "Conformidade Cadastral" in aba_selecionada:
    auditoria_divergencias.render_painel_divergencias(imoveis_lista=imoveis_lista, departamento=departamento_ativo)

elif "Mapa da Carteira" in aba_selecionada:
    mapa_carteira.render_painel_mapa(imoveis_lista, obter_dados_auditoria_atualizados(), departamento=departamento_ativo)

elif "Avaliação via Matrícula" in aba_selecionada:
    render_avaliacao_matricula()

elif "Histórico de Laudos" in aba_selecionada:
    render_historico_laudos()

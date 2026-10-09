"""
Interface Web Interativa para Avaliação Imobiliária Inteligente (NBR 14653).
Construído com Streamlit, consumindo os modelos do Google AI Studio e dados reais do ZAP.
"""
import glob
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

import gerar_pdf
import pipeline
import tools
from llm import ClienteLLM

# Configuração da página
st.set_page_config(
    page_title="AvaliaIA • Avaliação Imobiliária",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilização visual moderna
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.0rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #1E3A8A;
    }
    .metric-label {
        font-size: 0.8rem;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        padding: 8px 16px;
    }
</style>
""", unsafe_allow_html=True)


# ==================== BARRA LATERAL (CONFIGURAÇÕES) ====================
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/real-estate.png", width=64)
    st.title("AvaliaIA Pro")
    st.caption("Engenharia de Avaliações com IA • NBR 14653")
    st.markdown("---")

    st.subheader("⚙️ Configurações da Avaliação")
    
    # Modelo LLM
    modelo_selecionado = st.selectbox(
        "Modelo de IA (Google AI Studio)",
        options=["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"],
        index=0,
        help="O Flash-Lite possui 500 requisições diárias gratuitas e lê PDFs nativamente com OCR.",
    )
    os.environ["MODELO_EXTRACAO"] = modelo_selecionado
    os.environ["MODELO_TEXTO"] = modelo_selecionado

    # Fator de oferta
    fator_oferta_input = st.slider(
        "Fator de Redução de Oferta",
        min_value=0.80,
        max_value=1.00,
        value=0.90,
        step=0.01,
        help="Percentual de conversão do preço de anúncio para fechamento efetivo (0.90 = 10% de margem de barganha).",
    )
    pipeline.FATOR_OFERTA = fator_oferta_input

    # Rentabilidade Aluguel
    rentabilidade_input = st.number_input(
        "Premissa Cap Rate Aluguel (% a.a.)",
        min_value=3.0,
        max_value=15.0,
        value=5.5,
        step=0.1,
        help="Utilizado quando não houver amostras suficientes de locação na região.",
    )
    pipeline.RENTABILIDADE_ALUGUEL_AA = rentabilidade_input

    st.markdown("---")
    
    # Status da API
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        try:
            api_key = st.secrets.get("GEMINI_API_KEY", "")
        except Exception:
            pass

    if api_key:
        st.success("🟢 Chave do Google AI Studio Conectada")
    else:
        st.error("🔴 GEMINI_API_KEY não encontrada (.env ou Secrets)")

    st.caption("Versão 2.0 • Coleta ao vivo ZAP Imóveis")


# ==================== CABEÇALHO PRINCIPAL ====================
st.markdown('<div class="main-header">Sistema de Avaliação Imobiliária Inteligente</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Extração automática de matrículas com Visão Computacional, amostragem em tempo real e laudo pericial NBR 14653</div>', unsafe_allow_html=True)

tab_nova, tab_historico = st.tabs(["📄 Nova Avaliação", "📂 Histórico de Laudos Gerados"])


# ==================== ABA 1: NOVA AVALIAÇÃO ====================
with tab_nova:
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
                pasta_saida.mkdir(exist_ok=True)
                carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
                caminho_laudo_md = pasta_saida / f"laudo_{carimbo}.md"
                caminho_laudo_pdf = pasta_saida / f"laudo_{carimbo}.pdf"
                caminho_dados_json = pasta_saida / f"dados_{carimbo}.json"

                caminho_laudo_md.write_text(laudo_md, encoding="utf-8")
                caminho_dados_json.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
                gerar_pdf.criar_laudo_pdf(dados, caminho_laudo_pdf)

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
                st.markdown("### 📥 Documentos Gerados")
                col_btn1, col_btn2, col_btn3 = st.columns(3)
                with col_btn1:
                    with open(caminho_laudo_pdf, "rb") as f_pdf:
                        st.download_button(
                            label="📑 Baixar Laudo Oficial em PDF",
                            data=f_pdf,
                            file_name=f"Laudo_Avaliacao_{imovel.get('cidade')}_{carimbo}.pdf",
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True,
                        )
                with col_btn2:
                    with open(caminho_laudo_md, "rb") as f_md:
                        st.download_button(
                            label="📄 Baixar Texto em Markdown (.md)",
                            data=f_md,
                            file_name=f"Laudo_{carimbo}.md",
                            mime="text/markdown",
                            use_container_width=True,
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
                st.error(f"Erro durante o processamento: {e}")


# ==================== ABA 2: HISTÓRICO DE LAUDOS ====================
with tab_historico:
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

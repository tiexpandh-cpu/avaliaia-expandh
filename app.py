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
import importlib
importlib.reload(reavaliacao_carteira)
importlib.reload(argumentario)
importlib.reload(mapa_carteira)
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


# ==================== CONTROLE DE ACESSO (AUTENTICAÇÃO POR SENHA) ====================
def check_password() -> bool:
    """Verifica se o usuário está autenticado ou solicita a senha de acesso."""
    if st.session_state.get("authenticated", False):
        return True

    # Obter senha esperada (Streamlit Cloud Secrets > .env > padrão "expandh2026")
    senha_esperada = "expandh2026"
    try:
        if "APP_PASSWORD" in st.secrets:
            senha_esperada = str(st.secrets["APP_PASSWORD"])
    except Exception:
        pass
    senha_esperada = os.getenv("APP_PASSWORD", senha_esperada)

    # Layout centralizado da tela de login
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        logo_base64 = ""
        caminho_logo = Path("assets/logo_expandh.png")
        if caminho_logo.exists():
            import base64
            with open(caminho_logo, "rb") as f:
                logo_base64 = base64.b64encode(f.read()).decode("utf-8")
        img_tag = f'<img src="data:image/png;base64,{logo_base64}" width="140" style="margin-bottom: 8px;" />' if logo_base64 else '<img src="https://img.icons8.com/fluency/96/real-estate.png" width="72" style="margin-bottom: 8px;" />'

        st.markdown(f"""
        <div style="background: #ffffff; padding: 25px; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); text-align: center;">
            {img_tag}
            <h2 style="color: #1E3A8A; margin-bottom: 4px; margin-top: 4px;">Expandh Imobiliária</h2>
            <p style="color: #64748B; font-size: 0.95rem; margin-bottom: 12px;">Portal de Inteligência & Avaliação de Carteira • NBR 14653</p>
            <div style="background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 8px; padding: 10px; margin-bottom: 15px;">
                <span style="color: #1E40AF; font-size: 0.85rem; font-weight: 500;">🔒 Área Restrita para a Equipe de Corretores e Diretoria</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("form_login"):
            senha_digitada = st.text_input(
                "Digite a Senha de Acesso",
                type="password",
                placeholder="••••••••",
                help="Insira a senha fornecida pela diretoria da Expandh Imobiliária"
            )
            btn_entrar = st.form_submit_button("Acessar Painel 🚀", use_container_width=True, type="primary")

            if btn_entrar:
                if senha_digitada == senha_esperada:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("❌ Senha incorreta. Verifique com a administração da Expandh.")

    return False

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


# ==================== BARRA LATERAL (CONFIGURAÇÕES) ====================
with st.sidebar:
    if Path("assets/logo_expandh.png").exists():
        st.image("assets/logo_expandh.png", width=160)
    else:
        st.image("https://img.icons8.com/fluency/96/real-estate.png", width=64)
    st.title("AvaliaIA Pro")
    st.caption("Engenharia de Avaliações com IA • NBR 14653")
    
    # Status de login e botão de Sair
    col_status, col_btn = st.columns([1.8, 1.2])
    with col_status:
        st.markdown("<small style='color: #16A34A; font-weight: 600;'>🟢 Conectado</small><br><small style='color: #64748B;'>Equipe Expandh</small>", unsafe_allow_html=True)
    with col_btn:
        if st.button("🚪 Sair", key="btn_logout", help="Encerrar sessão no painel"):
            st.session_state["authenticated"] = False
            st.rerun()
            
    st.markdown("---")
    
    # Status e Sincronização do Feed Kurole
    st.subheader("📡 Sincronização Kurole (KSI)")
    st.markdown(f"**Carga no XML:** `{data_pub_formatada}`")
    st.caption(f"**Total Ativo no Feed:** {len(imoveis_lista)} imóveis ({len(imoveis_venda)} Venda | {len(imoveis_locacao)} Locação)")
    
    if st.button("🔄 Sincronizar Feed XML Agora", use_container_width=True, help="Recarrega o arquivo XML mais recente publicado no servidor Kurole"):
        st.cache_data.clear()
        st.rerun()

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

tab_nova, tab_vendas, tab_locacao, tab_mapa, tab_historico = st.tabs([
    "📄 Avaliação via Matrícula",
    f"🏷️ Carteira de VENDAS ({len(imoveis_venda)} imóveis)",
    f"🔑 Carteira de LOCAÇÃO ({len(imoveis_locacao)} imóveis)",
    f"🗺️ Mapa da Carteira ({len(imoveis_lista)} imóveis)",
    "📂 Histórico de Laudos Gerados",
])


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
                opcoes_status = [
                    f"Todos os Imóveis de {operacao} ({len(auditados_op)})",
                    f"🔴 Apenas Muito Acima ({q_super})",
                    f"🟡 Apenas Acima do Mercado ({q_acima})",
                    f"🟢 Apenas no Preço Justo ({q_justo})",
                    f"🔵 Apenas Oportunidades ({q_oport})",
                ]
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

            cols_tab = ["Código", "Tipo", "Bairro", "Área (m²)", rotulo_preco, "Valor Mercado", "Desvio (%)", "Status", "Ação Comercial Recomendada"]
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
                    res_aud = reavaliacao_carteira.reavaliar_imovel_feed(imovel_sel, fator_oferta=pipeline.FATOR_OFERTA, fator_localizacao=fator_loc_input)

                if not res_aud.get("sucesso"):
                    st.warning(f"⚠️ Não foi possível reavaliar: {res_aud.get('motivo')}")
                else:
                    st.success("✅ Auditoria de mercado concluída com sucesso!")
                    st.markdown("---")

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


# ==================== ABA 2: CARTEIRA DE VENDAS ====================
with tab_vendas:
    st.subheader("🏷️ Carteira de VENDAS • Auditoria & Reprecificação")
    st.caption("Precificação de venda, comparação com fechamentos NBR e diagnóstico de liquidez.")
    render_painel_operacao(imoveis_lista, "Venda", api_key)


# ==================== ABA 3: CARTEIRA DE LOCAÇÃO ====================
with tab_locacao:
    st.subheader("🔑 Carteira de LOCAÇÃO • Auditoria & Rentabilidade")
    st.caption("Precificação de aluguel mensal, custo total de ocupação (pacote) e comparáveis ao vivo.")
    render_painel_operacao(imoveis_lista, "Locação", api_key)


# ==================== ABA 4: MAPA GEOGRÁFICO DA CARTEIRA ====================
with tab_mapa:
    mapa_carteira.render_painel_mapa(imoveis_lista, obter_dados_auditoria_atualizados())


# ==================== ABA 5: HISTÓRICO DE LAUDOS ====================
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

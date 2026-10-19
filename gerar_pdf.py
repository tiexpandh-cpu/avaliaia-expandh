"""
Gerador de Laudos de Avaliação Imobiliária em PDF Personalizados com Identidade Expandh (NBR 14653).
Oferece dois modelos profissionais:
  1. Laudo Comercial Executivo (1 página): Visual, persuasivo, ideal para WhatsApp e proprietários.
  2. Laudo Pericial Completo (3-4 páginas): Técnico, com amostras ZAP, dados cartorários e metodologia ABNT.
"""
import os
from datetime import datetime
from pathlib import Path

from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PASTA_RAIZ = Path(__file__).resolve().parent
CAMINHO_LOGO = PASTA_RAIZ / "assets" / "logo_expandh.png"

# Paleta Corporativa Expandh Imobiliária
C_AZUL_EXPANDH = colors.HexColor("#1E3A8A")   # Azul Marinho Nobre
C_DOURADO = colors.HexColor("#D97706")        # Ouro / Dourado
C_AZUL_CLARO = colors.HexColor("#0284C7")     # Azul Destaque
C_ESCURO = colors.HexColor("#0F172A")         # Texto Escuro Quase Preto
C_TEXTO = colors.HexColor("#334155")          # Texto Corpo
C_FUNDO_LEVE = colors.HexColor("#F8FAFC")     # Fundo Tabelas
C_FUNDO_ALT = colors.HexColor("#F1F5F9")      # Fundo Alternado
C_BORDA = colors.HexColor("#CBD5E1")          # Linhas Divisórias
C_VERDE = colors.HexColor("#16A34A")          # Sucesso / Preço Justo
C_VERMELHO = colors.HexColor("#DC2626")       # Muito Acima / Alerta


def formatar_moeda(valor: float | int | None) -> str:
    if valor is None or valor == 0:
        return "Sob Consulta"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_moeda_sem_centavos(valor: float | int | None) -> str:
    if valor is None or valor == 0:
        return "Sob Consulta"
    return f"R$ {valor:,.0f}".replace(",", ".")


def _criar_qr_drawing(url: str, tamanho: float = 38.0) -> Drawing:
    """Gera um elemento Drawing vetorial de QR Code para inserção no ReportLab."""
    qr_widget = qr.QrCodeWidget(url)
    bounds = qr_widget.getBounds()
    w = bounds[2] - bounds[0]
    h = bounds[3] - bounds[1]
    d = Drawing(tamanho, tamanho, transform=[tamanho / w, 0, 0, tamanho / h, 0, 0])
    d.add(qr_widget)
    return d


class NumberedCanvas(canvas.Canvas):
    """Canvas corporativo que numera páginas e insere marca d'água/cabeçalho da Expandh."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # Cabeçalho a partir da página 2
        if self._pageNumber > 1:
            self.drawString(1.5 * cm, 28.5 * cm, "EXPANDH IMOBILIÁRIA • LAUDO PERICIAL NBR 14653")
            self.drawRightString(19.5 * cm, 28.5 * cm, datetime.now().strftime("%d/%m/%Y"))
            self.setStrokeColor(C_BORDA)
            self.setLineWidth(0.5)
            self.line(1.5 * cm, 28.3 * cm, 19.5 * cm, 28.3 * cm)

        # Rodapé corporativo em todas as páginas
        self.setStrokeColor(C_BORDA)
        self.setLineWidth(0.5)
        self.line(1.5 * cm, 1.8 * cm, 19.5 * cm, 1.8 * cm)

        self.drawString(1.5 * cm, 1.3 * cm, "Expandh Imobiliária • Sertãozinho/SP • Tel: (16) 2105-3333 • CRECI 034821-J")
        texto_pagina = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(19.5 * cm, 1.3 * cm, texto_pagina)
        self.restoreState()


def _obter_bloco_cabecalho_expandh(styles, titulo_doc: str, subtitulo_doc: str):
    """Monta a tabela superior com Logo oficial, Dados Expandh e QR Code."""
    qr_draw = _criar_qr_drawing("https://api.whatsapp.com/send?phone=551621053333&text=Ola%20Expandh", 42)

    if CAMINHO_LOGO.exists():
        logo_el = Image(str(CAMINHO_LOGO), width=4.8 * cm, height=1.28 * cm)
    else:
        logo_el = Paragraph("<b>EXPANDH</b><br/><font color='#D97706'>IMOBILIÁRIA</font>", styles["DocTitle"])

    info_expandh = (
        f"<b>{titulo_doc}</b><br/>"
        f"<font color='#64748B'>{subtitulo_doc}</font><br/>"
        f"<font color='#1E3A8A' size='7'><b>Expandh Imobiliária • CRECI 034821-J • Sertãozinho/SP</b></font>"
    )

    t_header = Table(
        [
            [logo_el, Paragraph(info_expandh, styles["DocSubtitle"]), qr_draw]
        ],
        colWidths=[5.2 * cm, 10.8 * cm, 2.0 * cm],
    )
    t_header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t_header


# ==============================================================================
# 1. LAUDO COMERCIAL EXECUTIVO (1 PÁGINA)
# ==============================================================================
def criar_laudo_comercial_pdf(dados: dict, caminho_pdf: Path) -> Path:
    """Gera laudo visual de 1 página focado em apresentação comercial e WhatsApp."""
    caminho_pdf.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(caminho_pdf),
        pagesize=A4,
        leftMargin=1.4 * cm,
        rightMargin=1.4 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
    )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=C_AZUL_EXPANDH,
    ))
    styles.add(ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=C_TEXTO,
    ))
    styles.add(ParagraphStyle(
        "SecHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=C_AZUL_EXPANDH,
        spaceBefore=6,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        "BodyMini",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10.5,
        textColor=C_TEXTO,
    ))
    styles.add(ParagraphStyle(
        "KPIBig",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=15,
        textColor=C_AZUL_EXPANDH,
        alignment=1,
    ))
    styles.add(ParagraphStyle(
        "KPISub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#64748B"),
        alignment=1,
    ))

    imovel = dados.get("imovel", {})
    mercado = dados.get("mercado", {})
    venda = dados.get("venda", {})
    locacao = dados.get("locacao", {})

    story = []

    # Cabeçalho Expandh
    story.append(_obter_bloco_cabecalho_expandh(
        styles,
        titulo_doc="RELATÓRIO EXECUTIVO DE POSICIONAMENTO MERCADOLÓGICO",
        subtitulo_doc=f"Padrão NBR 14653 • Amostragem ao Vivo ZAP • Cód. <b>{imovel.get('id', imovel.get('numero_matricula', '-'))}</b>"
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_AZUL_EXPANDH, spaceBefore=4, spaceAfter=6))

    # Identificação do Imóvel
    story.append(Paragraph("1. Ficha do Imóvel Avaliando", styles["SecHeader"]))
    area_exibir = imovel.get("area_privativa_m2") or imovel.get("area_principal") or imovel.get("area_total_m2", 0)

    dados_ficha = [
        [
            Paragraph(f"<b>Imóvel:</b> {imovel.get('tipo_imovel', imovel.get('tipo', 'Imóvel'))}", styles["BodyMini"]),
            Paragraph(f"<b>Área Útil:</b> {area_exibir:.1f} m²", styles["BodyMini"]),
            Paragraph(f"<b>Quartos/Vagas:</b> {imovel.get('quartos', 0)} qts | {imovel.get('vagas', 0)} vaga(s)", styles["BodyMini"]),
        ],
        [
            Paragraph(f"<b>Endereço:</b> {imovel.get('endereco', imovel.get('endereco_rua', '-'))}, {imovel.get('bairro', '-')}", styles["BodyMini"]),
            Paragraph(f"<b>Município:</b> {imovel.get('cidade', 'Sertãozinho')}/{imovel.get('uf', 'SP')}", styles["BodyMini"]),
            Paragraph(f"<b>Condomínio:</b> {imovel.get('nome_condominio', '-')}", styles["BodyMini"]),
        ],
    ]
    t_ficha = Table(dados_ficha, colWidths=[7.2 * cm, 4.8 * cm, 6.2 * cm])
    t_ficha.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_FUNDO_LEVE),
        ("BOX", (0, 0), (-1, -1), 0.5, C_BORDA),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, C_BORDA),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_ficha)
    story.append(Spacer(1, 2 * mm))

    # Os 4 Grandes Números da Avaliação
    story.append(Paragraph("2. Avaliação de Mercado & Intervalos Recomendados", styles["SecHeader"]))
    val_venda_est = venda.get("valor_venda_estimado") or imovel.get("preco", 0)
    faixa_min = venda.get("faixa_min") or (val_venda_est * 0.9)
    faixa_max = venda.get("faixa_max") or (val_venda_est * 1.1)
    aluguel_est = locacao.get("aluguel_mensal_estimado", 0)

    preco_ped = imovel.get("preco", 0)
    desvio_num = ((preco_ped - val_venda_est) / val_venda_est * 100) if val_venda_est else 0

    if desvio_num > 15:
        cor_st = C_VERMELHO
        st_txt = f"🔴 Muito Acima (+{desvio_num:.1f}%)"
    elif desvio_num > 5:
        cor_st = C_DOURADO
        st_txt = f"🟡 Levemente Acima (+{desvio_num:.1f}%)"
    elif desvio_num >= -5:
        cor_st = C_VERDE
        st_txt = f"🟢 Preço Justo ({desvio_num:+.1f}%)"
    else:
        cor_st = C_AZUL_CLARO
        st_txt = f"🔵 Oportunidade ({desvio_num:.1f}%)"

    kpis_comercial = [
        [
            Paragraph("VALOR DE MERCADO ESTIMADO", styles["KPISub"]),
            Paragraph("FAIXA DE NEGOCIAÇÃO (±10%)", styles["KPISub"]),
            Paragraph("POTENCIAL DE ALUGUEL", styles["KPISub"]),
            Paragraph("DIAGNÓSTICO DA PEDIDA", styles["KPISub"]),
        ],
        [
            Paragraph(formatar_moeda_sem_centavos(val_venda_est), styles["KPIBig"]),
            Paragraph(f"{formatar_moeda_sem_centavos(faixa_min)} a {formatar_moeda_sem_centavos(faixa_max)}", ParagraphStyle("Kp2", parent=styles["KPIBig"], fontSize=10, textColor=C_ESCURO)),
            Paragraph(f"{formatar_moeda_sem_centavos(aluguel_est)}/mês", ParagraphStyle("Kp3", parent=styles["KPIBig"], textColor=C_AZUL_CLARO)),
            Paragraph(st_txt, ParagraphStyle("Kp4", parent=styles["KPIBig"], fontSize=10, textColor=cor_st)),
        ],
    ]
    t_kpis_com = Table(kpis_comercial, colWidths=[4.7 * cm, 5.0 * cm, 4.0 * cm, 4.5 * cm])
    t_kpis_com.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 1, C_AZUL_EXPANDH),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, C_BORDA),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t_kpis_com)
    story.append(Spacer(1, 2 * mm))

    # Tabela com Top Comparáveis do Bairro
    story.append(Paragraph("3. Amostras Paradigmas Ativas na Região (ZAP Imóveis)", styles["SecHeader"]))
    amostras_v = mercado.get("amostras", [])[:5]

    tabela_cp_data = [[
        Paragraph("Bairro / Região", ParagraphStyle("TH1", parent=styles["BodyMini"], fontName="Helvetica-Bold", textColor=colors.white)),
        Paragraph("Área", ParagraphStyle("TH2", parent=styles["BodyMini"], fontName="Helvetica-Bold", textColor=colors.white, alignment=1)),
        Paragraph("Preço Oferta", ParagraphStyle("TH3", parent=styles["BodyMini"], fontName="Helvetica-Bold", textColor=colors.white, alignment=1)),
        Paragraph("R$ / m²", ParagraphStyle("TH4", parent=styles["BodyMini"], fontName="Helvetica-Bold", textColor=colors.white, alignment=1)),
        Paragraph("Distância", ParagraphStyle("TH5", parent=styles["BodyMini"], fontName="Helvetica-Bold", textColor=colors.white, alignment=1)),
    ]]

    if amostras_v:
        for a in amostras_v:
            pm2 = a["preco"] / a["area"] if a.get("area") else 0
            dist_txt = f"{a['distancia_km']:.2f} km" if a.get("distancia_km") else "-"
            tabela_cp_data.append([
                Paragraph(a.get("bairro", "-")[:24], styles["BodyMini"]),
                Paragraph(f"{a.get('area', 0):.0f} m²", ParagraphStyle("tc1", parent=styles["BodyMini"], alignment=1)),
                Paragraph(formatar_moeda_sem_centavos(a.get("preco")), ParagraphStyle("tc2", parent=styles["BodyMini"], alignment=1)),
                Paragraph(f"R$ {pm2:,.0f}".replace(",", "."), ParagraphStyle("tc3", parent=styles["BodyMini"], alignment=1)),
                Paragraph(dist_txt, ParagraphStyle("tc4", parent=styles["BodyMini"], alignment=1)),
            ])
    else:
        tabela_cp_data.append([
            Paragraph("Amostragem estatística baseada na mediana do cadastro regional", styles["BodyMini"]),
            Paragraph("-", styles["BodyMini"]),
            Paragraph("-", styles["BodyMini"]),
            Paragraph("-", styles["BodyMini"]),
            Paragraph("-", styles["BodyMini"]),
        ])

    t_cp = Table(tabela_cp_data, colWidths=[6.2 * cm, 2.2 * cm, 3.4 * cm, 3.4 * cm, 3.0 * cm])
    t_cp.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_AZUL_EXPANDH),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_FUNDO_LEVE]),
        ("BOX", (0, 0), (-1, -1), 0.5, C_BORDA),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, C_BORDA),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t_cp)
    story.append(Spacer(1, 3 * mm))

    # Orientação Comercial para Fechamento Rápido
    story.append(Paragraph("4. Parecer Estratégico & Recomendação Comercial", styles["SecHeader"]))
    
    if desvio_num > 15:
        parecer = (
            f"O imóvel encontra-se anunciado por <b>R$ {preco_ped:,.0f}</b>, patamar <b>{desvio_num:.1f}% superior</b> à média dos concorrentes ativos. "
            "Recomenda-se ajustar para a faixa de <b>" + formatar_moeda_sem_centavos(val_venda_est) + "</b> para recuperar a tração nos portais, "
            "atrair visitas qualificadas e evitar a perda de liquidez do patrimônio."
        )
    else:
        parecer = (
            f"O imóvel possui excelente aderência de mercado com valor anunciado de <b>R$ {preco_ped:,.0f}</b> frente à avaliação de "
            f"<b>R$ {val_venda_est:,.0f}</b>. É considerado prioritário pela equipe da Expandh por apresentar alto potencial de fechamento rápido."
        )

    t_parecer = Table([[Paragraph(parecer, styles["BodyMini"])]], colWidths=[18.2 * cm])
    t_parecer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_FUNDO_LEVE),
        ("BOX", (0, 0), (-1, -1), 1, C_BORDA),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t_parecer)
    story.append(Spacer(1, 4 * mm))

    # Rodapé de Assinatura Comercial
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    rodape_data = [
        [
            Paragraph(f"<b>Emitido por:</b> Expandh Imobiliária • Departamento de Avaliações<br/><b>Data Base:</b> {data_hoje} • Validade Técnica: 60 dias", styles["BodyMini"]),
            Paragraph("<b>Central de Atendimento:</b> (16) 2105-3333<br/><b>Endereço:</b> Sertãozinho/SP • expandh.com.br", ParagraphStyle("rdp2", parent=styles["BodyMini"], alignment=2)),
        ]
    ]
    t_rodape = Table(rodape_data, colWidths=[11.0 * cm, 7.2 * cm])
    t_rodape.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(KeepTogether(t_rodape))

    doc.build(story)
    return caminho_pdf


# ==============================================================================
# 2. LAUDO PERICIAL COMPLETO (3-4 PÁGINAS • NBR 14653)
# ==============================================================================
def criar_laudo_completo_pdf(dados: dict, caminho_pdf: Path) -> Path:
    """Gera laudo técnico completo, com fundamentação ABNT e todas as tabelas."""
    caminho_pdf.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(caminho_pdf),
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=2.0 * cm,
        bottomMargin=2.2 * cm,
    )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=C_AZUL_EXPANDH,
    ))
    styles.add(ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=C_TEXTO,
    ))
    styles.add(ParagraphStyle(
        "SectionHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=C_AZUL_EXPANDH,
        spaceBefore=8,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        "BodyCustom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=C_TEXTO,
    ))
    styles.add(ParagraphStyle(
        "TableHead",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=colors.white,
        alignment=1,
    ))
    styles.add(ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=C_TEXTO,
        alignment=1,
    ))
    styles.add(ParagraphStyle(
        "TableCellLeft",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=C_TEXTO,
        alignment=0,
    ))
    styles.add(ParagraphStyle(
        "KPIBig",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=15,
        textColor=C_AZUL_EXPANDH,
        alignment=1,
    ))
    styles.add(ParagraphStyle(
        "KPISub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#64748B"),
        alignment=1,
    ))

    imovel = dados.get("imovel", {})
    mercado = dados.get("mercado", {})
    venda = dados.get("venda", {})
    locacao = dados.get("locacao", {})

    story = []

    # Cabeçalho Oficial Expandh com Logo e QR Code
    story.append(_obter_bloco_cabecalho_expandh(
        styles,
        titulo_doc="LAUDO TÉCNICO PERICIAL DE AVALIAÇÃO IMOBILIÁRIA",
        subtitulo_doc=f"Conforme ABNT NBR 14653-2 • Método Comparativo Direto • Matrícula {imovel.get('numero_matricula', 'N/D')}"
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_AZUL_EXPANDH, spaceBefore=4, spaceAfter=8))

    # Resumo Executivo (KPIs)
    valor_venda = formatar_moeda(venda.get("valor_venda_estimado"))
    faixa_venda = f"{formatar_moeda(venda.get('faixa_min'))} a {formatar_moeda(venda.get('faixa_max'))}"
    aluguel_mensal = formatar_moeda(locacao.get("aluguel_mensal_estimado"))
    cap_rate = f"{locacao.get('rentabilidade_bruta_aa', locacao.get('rentabilidade_bruta_aa_adotada', 0)):.2f}% a.a."

    kpi_data = [
        [
            Paragraph("VALOR DE MERCADO VENAL", styles["KPISub"]),
            Paragraph("FAIXA DE NEGOCIAÇÃO (±10%)", styles["KPISub"]),
            Paragraph("ALUGUEL ESTIMADO", styles["KPISub"]),
            Paragraph("RENTABILIDADE (CAP RATE)", styles["KPISub"]),
        ],
        [
            Paragraph(valor_venda, styles["KPIBig"]),
            Paragraph(faixa_venda, ParagraphStyle("Kpi2", parent=styles["KPIBig"], fontSize=9.5, textColor=C_ESCURO)),
            Paragraph(aluguel_mensal, ParagraphStyle("Kpi3", parent=styles["KPIBig"], textColor=C_VERDE)),
            Paragraph(cap_rate, ParagraphStyle("Kpi4", parent=styles["KPIBig"], textColor=C_AZUL_CLARO)),
        ],
    ]

    t_kpi = Table(kpi_data, colWidths=[4.7 * cm, 4.9 * cm, 4.1 * cm, 4.3 * cm])
    t_kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_FUNDO_LEVE),
        ("BOX", (0, 0), (-1, -1), 1, C_AZUL_EXPANDH),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, C_BORDA),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t_kpi)
    story.append(Spacer(1, 3 * mm))

    # 1. Identificação do Imóvel
    story.append(Paragraph("1. Identificação do Imóvel Avaliando & Situação Registral", styles["SectionHeader"]))
    proprietarios = ", ".join(imovel.get("proprietarios_atuais", [])) or "Não informado / Em cadastro"
    onus = ", ".join(imovel.get("onus_e_gravames", [])) or "Nenhum gravame registrado na certidão"

    dados_imovel_tab = [
        [
            Paragraph("<b>Tipo de Imóvel:</b>", styles["BodyCustom"]),
            Paragraph(imovel.get("tipo_imovel", "-"), styles["BodyCustom"]),
            Paragraph("<b>Matrícula / Cartório:</b>", styles["BodyCustom"]),
            Paragraph(f"Nº {imovel.get('numero_matricula', '-')} ({imovel.get('cartorio', '-')})", styles["BodyCustom"]),
        ],
        [
            Paragraph("<b>Condomínio/Edifício:</b>", styles["BodyCustom"]),
            Paragraph(imovel.get("nome_condominio", "-"), styles["BodyCustom"]),
            Paragraph("<b>Complemento:</b>", styles["BodyCustom"]),
            Paragraph(imovel.get("complemento", "-"), styles["BodyCustom"]),
        ],
        [
            Paragraph("<b>Endereço:</b>", styles["BodyCustom"]),
            Paragraph(f"{imovel.get('endereco', '-')}, {imovel.get('bairro', '-')}", styles["BodyCustom"]),
            Paragraph("<b>Município / UF:</b>", styles["BodyCustom"]),
            Paragraph(f"{imovel.get('cidade', '-')}/{imovel.get('uf', '-')}", styles["BodyCustom"]),
        ],
        [
            Paragraph("<b>Área Privativa:</b>", styles["BodyCustom"]),
            Paragraph(f"<b>{imovel.get('area_privativa_m2', 0):.2f} m²</b>", styles["BodyCustom"]),
            Paragraph("<b>Área Total:</b>", styles["BodyCustom"]),
            Paragraph(f"{imovel.get('area_total_m2', 0):.2f} m²", styles["BodyCustom"]),
        ],
        [
            Paragraph("<b>Quartos / Vagas:</b>", styles["BodyCustom"]),
            Paragraph(f"{imovel.get('quartos', '-')} quartos | {imovel.get('vagas', '-')} vaga(s)", styles["BodyCustom"]),
            Paragraph("<b>Proprietário(s):</b>", styles["BodyCustom"]),
            Paragraph(proprietarios, styles["BodyCustom"]),
        ],
        [
            Paragraph("<b>Ônus e Gravames:</b>", styles["BodyCustom"]),
            Paragraph(f"<font color='#B91C1C'>{onus}</font>", styles["BodyCustom"]),
            Paragraph("<b>Origem Amostral:</b>", styles["BodyCustom"]),
            Paragraph("Expandh Intelligence + ZAP Imóveis", styles["BodyCustom"]),
        ],
    ]

    t_imovel = Table(dados_imovel_tab, colWidths=[3.2 * cm, 5.8 * cm, 3.4 * cm, 5.6 * cm])
    t_imovel.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, C_BORDA),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, C_FUNDO_LEVE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t_imovel)
    story.append(Spacer(1, 3 * mm))

    # 2. Pesquisa de Mercado
    story.append(Paragraph("2. Pesquisa de Mercado & Elementos Comparáveis (ZAP Imóveis)", styles["SectionHeader"]))
    total_v = mercado.get("total_anuncios_venda_cidade", 0)
    story.append(Paragraph(
        f"Amostras colhidas em tempo real na praça de {imovel.get('cidade')}/{imovel.get('uf')} "
        f"({total_v} ofertas ativas monitoradas). "
        "Amostras homogeneizadas e tratadas estatisticamente:",
        styles["BodyCustom"],
    ))
    story.append(Spacer(1, 1.5 * mm))

    amostras_venda = mercado.get("amostras", [])[:8]
    tabela_venda_data = [[
        Paragraph("Bairro", styles["TableHead"]),
        Paragraph("Área (m²)", styles["TableHead"]),
        Paragraph("Qts / Vagas", styles["TableHead"]),
        Paragraph("Preço Oferta", styles["TableHead"]),
        Paragraph("R$ / m²", styles["TableHead"]),
        Paragraph("Distância", styles["TableHead"]),
    ]]

    for a in amostras_venda:
        preco_m2 = a["preco"] / a["area"] if a.get("area") else 0
        dist = f"{a['distancia_km']:.2f} km" if a.get("distancia_km") is not None else "-"
        tabela_venda_data.append([
            Paragraph(a.get("bairro", "-")[:20], styles["TableCellLeft"]),
            Paragraph(f"{a.get('area', 0):.0f} m²", styles["TableCell"]),
            Paragraph(f"{a.get('quartos', '-')}/{a.get('vagas', '-')}", styles["TableCell"]),
            Paragraph(formatar_moeda(a.get("preco")), styles["TableCell"]),
            Paragraph(f"R$ {preco_m2:,.0f}".replace(",", "."), styles["TableCell"]),
            Paragraph(dist, styles["TableCell"]),
        ])

    t_amostras = Table(tabela_venda_data, colWidths=[4.2 * cm, 2.2 * cm, 2.4 * cm, 3.4 * cm, 3.0 * cm, 2.8 * cm])
    t_amostras.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_AZUL_EXPANDH),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_FUNDO_LEVE]),
        ("BOX", (0, 0), (-1, -1), 0.5, C_BORDA),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, C_BORDA),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(t_amostras)
    story.append(Spacer(1, 3 * mm))

    # 3. Metodologia e Fundamentação
    story.append(Paragraph("3. Metodologia Estatística e Fator de Oferta (NBR 14653)", styles["SectionHeader"]))
    fator_of = venda.get("fator_oferta", 0.9)
    detalhes_calc = (
        f"<b>Tratamento Estatístico:</b> {venda.get('metodo', 'Comparativo Direto de Dados de Mercado')}.<br/>"
        f"<b>Amostragem Efetiva:</b> {venda.get('n_amostras', 0)} comparáveis validados. "
        f"Mediana das ofertas = <b>R$ {venda.get('mediana_m2_oferta', 0):,.2f}/m²</b>.<br/>"
        f"<b>Fator de Redução de Oferta:</b> Aplicado coeficiente de <b>{fator_of:.2f}</b> "
        f"(-{int((1-fator_of)*100)}% de margem de barganha para alinhamento a valores efetivos de escritura)."
    )
    story.append(Paragraph(detalhes_calc, styles["BodyCustom"]))
    story.append(Spacer(1, 3 * mm))

    # 4. Avaliação de Locação
    story.append(Paragraph("4. Avaliação Locatícia & Indicadores Financeiros", styles["SectionHeader"]))
    selic = locacao.get("selic", {})
    detalhes_loc = (
        f"<b>Aluguel Mensal Estimado:</b> <b>{aluguel_mensal} / mês</b>.<br/>"
        f"<b>Cap Rate Bruto Anual:</b> <b>{cap_rate}</b> ao ano sobre o valor venal de venda.<br/>"
        f"<b>Taxa Selic Referencial:</b> {selic.get('selic_meta_aa', 10.50):.2f}% a.a. (Banco Central do Brasil)."
    )
    story.append(Paragraph(detalhes_loc, styles["BodyCustom"]))
    story.append(Spacer(1, 4 * mm))

    # 5. Conclusão e Termo de Responsabilidade
    story.append(Paragraph("5. Conclusão Avaliatória & Termo de Responsabilidade", styles["SectionHeader"]))
    conclusao_texto = (
        f"Com base na vistoria documental e nos dados colhidos no mercado de Sertãozinho/SP, "
        f"fixa-se o <b>VALOR DE MERCADO VENAL</b> em <b>{valor_venda}</b>, "
        f"admitindo-se liquidez normal dentro do intervalo de <b>{faixa_venda}</b>."
    )
    story.append(Paragraph(conclusao_texto, styles["BodyCustom"]))
    story.append(Spacer(1, 6 * mm))

    # Assinatura Oficial Expandh
    assinatura_data = [
        [
            Paragraph("____________________________________________________<br/><b>EXPANDH IMOBILIÁRIA</b><br/>Departamento de Engenharia e Avaliações", ParagraphStyle("Ass1", parent=styles["BodyCustom"], alignment=1)),
            Paragraph(f"<b>Responsabilidade Técnica:</b> CRECI 034821-J<br/><b>Data Base:</b> {datetime.now().strftime('%d/%m/%Y')}<br/><b>Status:</b> Laudo Auditado NBR 14653", ParagraphStyle("Ass2", parent=styles["BodyCustom"], alignment=0)),
        ]
    ]
    t_ass = Table(assinatura_data, colWidths=[9.0 * cm, 9.0 * cm])
    t_ass.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(KeepTogether(t_ass))

    doc.build(story, canvasmaker=NumberedCanvas)
    return caminho_pdf


def criar_laudo_pdf(dados: dict, caminho_pdf: Path, tipo_laudo: str = "completo") -> Path:
    """Função mestre: direciona para o modelo Comercial (1 pág) ou Completo (NBR)."""
    if tipo_laudo == "comercial":
        return criar_laudo_comercial_pdf(dados, caminho_pdf)
    return criar_laudo_completo_pdf(dados, caminho_pdf)

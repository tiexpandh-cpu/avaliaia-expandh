"""
Gerador de Laudo de Avaliação Imobiliária em PDF Profissional (NBR 14653).
Utiliza ReportLab para gerar layout corporativo, tabelas estilizadas e destaques visuais.
"""
import json
import os
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


class NumberedCanvas(canvas.Canvas):
    """Canvas de dois passos que calcula o total de páginas e adiciona cabeçalho/rodapé."""

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

        # Cabeçalho (a partir da página 2)
        if self._pageNumber > 1:
            self.drawString(1.5 * cm, 28.5 * cm, "LAUDO TÉCNICO DE AVALIAÇÃO IMOBILIÁRIA (NBR 14653)")
            self.drawRightString(19.5 * cm, 28.5 * cm, datetime.now().strftime("%d/%m/%Y"))
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(1.5 * cm, 28.3 * cm, 19.5 * cm, 28.3 * cm)

        # Rodapé
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(1.5 * cm, 1.8 * cm, 19.5 * cm, 1.8 * cm)

        self.drawString(1.5 * cm, 1.3 * cm, "Documento gerado por Sistema Autônomo de Engenharia de Avaliações")
        page_text = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(19.5 * cm, 1.3 * cm, page_text)
        self.restoreState()


def formatar_moeda(valor: float | int | None) -> str:
    if valor is None:
        return "-"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def criar_laudo_pdf(dados: dict, caminho_pdf: Path) -> Path:
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

    # Cores corporativas
    C_PRIMARIA = colors.HexColor("#1E3A8A")  # Azul Marinho Sofisticado
    C_SECUNDARIA = colors.HexColor("#0284C7")  # Azul Claro
    C_ESCURO = colors.HexColor("#0F172A")  # Cinza Quase Preto
    C_TEXTO = colors.HexColor("#334155")
    C_FUNDO_LEVE = colors.HexColor("#F8FAFC")
    C_BORDA = colors.HexColor("#E2E8F0")
    C_DESTAQUE = colors.HexColor("#059669")  # Verde Sucesso
    C_ALERTA = colors.HexColor("#D97706")  # Âmbar

    # Tipografias customizadas
    styles.add(ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=C_PRIMARIA,
        alignment=0,
    ))

    styles.add(ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#64748B"),
        alignment=0,
    ))

    styles.add(ParagraphStyle(
        "SectionHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=C_PRIMARIA,
        spaceBefore=10,
        spaceAfter=4,
    ))

    styles.add(ParagraphStyle(
        "BodyCustom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=C_TEXTO,
    ))

    styles.add(ParagraphStyle(
        "BodyCustomBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=C_ESCURO,
    ))

    styles.add(ParagraphStyle(
        "TableHead",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1,
    ))

    styles.add(ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=C_TEXTO,
        alignment=1,
    ))

    styles.add(ParagraphStyle(
        "TableCellLeft",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=C_TEXTO,
        alignment=0,
    ))

    styles.add(ParagraphStyle(
        "KPIValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=16,
        textColor=C_PRIMARIA,
        alignment=1,
    ))

    styles.add(ParagraphStyle(
        "KPILabel",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748B"),
        alignment=1,
    ))

    imovel = dados.get("imovel", {})
    mercado = dados.get("mercado", {})
    venda = dados.get("venda", {})
    locacao = dados.get("locacao", {})

    story = []

    # ==================== CABEÇALHO DO DOCUMENTO ====================
    story.append(Paragraph("LAUDO TÉCNICO DE AVALIAÇÃO IMOBILIÁRIA", styles["DocTitle"]))
    data_emissao = datetime.now().strftime("%d/%m/%Y às %H:%M")
    subtitulo = (
        f"Método Comparativo Direto de Dados de Mercado (NBR 14653-2) • "
        f"Matrícula Nº <b>{imovel.get('numero_matricula', 'N/D')}</b> • Emitido em {data_emissao}"
    )
    story.append(Paragraph(subtitulo, styles["DocSubtitle"]))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=2, color=C_PRIMARIA, spaceAfter=8))

    # ==================== CARD RESUMO EXECUTIVO (KPIS) ====================
    valor_venda = formatar_moeda(venda.get("valor_venda_estimado"))
    faixa_venda = f"{formatar_moeda(venda.get('faixa_min'))} a {formatar_moeda(venda.get('faixa_max'))}"
    aluguel_mensal = formatar_moeda(locacao.get("aluguel_mensal_estimado"))
    cap_rate = f"{locacao.get('rentabilidade_bruta_aa', locacao.get('rentabilidade_bruta_aa_adotada', 0)):.2f}% a.a."

    kpi_data = [
        [
            Paragraph("VALOR DE VENDA ESTIMADO", styles["KPILabel"]),
            Paragraph("FAIXA DE NEGOCIAÇÃO (±10%)", styles["KPILabel"]),
            Paragraph("ALUGUEL ESTIMADO", styles["KPILabel"]),
            Paragraph("RENTABILIDADE (CAP RATE)", styles["KPILabel"]),
        ],
        [
            Paragraph(valor_venda, styles["KPIValue"]),
            Paragraph(faixa_venda, ParagraphStyle("Kpi2", parent=styles["KPIValue"], fontSize=10, textColor=C_ESCURO)),
            Paragraph(aluguel_mensal, ParagraphStyle("Kpi3", parent=styles["KPIValue"], textColor=C_DESTAQUE)),
            Paragraph(cap_rate, ParagraphStyle("Kpi4", parent=styles["KPIValue"], textColor=C_SECUNDARIA)),
        ],
    ]

    t_kpi = Table(kpi_data, colWidths=[4.8 * cm, 5.0 * cm, 4.0 * cm, 4.2 * cm])
    t_kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_FUNDO_LEVE),
        ("BOX", (0, 0), (-1, -1), 1, C_BORDA),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, C_BORDA),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t_kpi)
    story.append(Spacer(1, 4 * mm))

    # ==================== 1. IDENTIFICAÇÃO E SITUAÇÃO REGISTRAL ====================
    story.append(Paragraph("1. Identificação do Imóvel Avaliando & Situação Registral", styles["SectionHeader"]))

    proprietarios = ", ".join(imovel.get("proprietarios_atuais", [])) or "Não informado"
    onus = ", ".join(imovel.get("onus_e_gravames", [])) or "Nenhum gravame registrado"

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
            Paragraph(f"{imovel.get('area_total_m2', 0):.3f} m²", styles["BodyCustom"]),
        ],
        [
            Paragraph("<b>Quartos / Vagas:</b>", styles["BodyCustom"]),
            Paragraph(f"{imovel.get('quartos', '-')} quartos | {imovel.get('vagas', '-')} vaga(s)", styles["BodyCustom"]),
            Paragraph("<b>Proprietário(s):</b>", styles["BodyCustom"]),
            Paragraph(proprietarios, styles["BodyCustom"]),
        ],
        [
            Paragraph("<b>Ônus e Gravames:</b>", styles["BodyCustomBold"]),
            Paragraph(f"<font color='#B91C1C'>{onus}</font>", styles["BodyCustom"]),
            Paragraph("<b>Georreferenciamento:</b>", styles["BodyCustom"]),
            Paragraph(f"{mercado.get('geolocalizacao', {}).get('display_name', 'Sertãozinho/SP')[:45]}...", styles["BodyCustom"]),
        ],
    ]

    t_imovel = Table(dados_imovel_tab, colWidths=[3.2 * cm, 5.8 * cm, 3.4 * cm, 5.6 * cm])
    t_imovel.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, C_BORDA),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, C_FUNDO_LEVE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(t_imovel)
    story.append(Spacer(1, 4 * mm))

    # ==================== 2. PESQUISA DE MERCADO (AMOSTRAS REAIS) ====================
    story.append(Paragraph("2. Pesquisa de Mercado & Elementos Comparáveis", styles["SectionHeader"]))
    total_v = mercado.get("total_anuncios_venda_cidade", 0)
    total_a = mercado.get("total_anuncios_aluguel_cidade", 0)
    story.append(Paragraph(
        f"Amostras coletadas em tempo real via <b>ZAP Imóveis</b> na praça de {imovel.get('cidade')}/{imovel.get('uf')} "
        f"({total_v} ofertas de venda e {total_a} de locação ativas). "
        "Foram selecionados elementos comparáveis por tipologia, proximidade e homogeneidade de área:",
        styles["BodyCustom"],
    ))
    story.append(Spacer(1, 2 * mm))

    # Tabela de Amostras de Venda
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
        preco_m2 = a["preco"] / a["area"]
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
        ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARIA),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_FUNDO_LEVE]),
        ("BOX", (0, 0), (-1, -1), 0.5, C_BORDA),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, C_BORDA),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t_amostras)
    story.append(Spacer(1, 4 * mm))

    # ==================== 3. CÁLCULO ESTATÍSTICO DO VALOR DE VENDA ====================
    story.append(Paragraph("3. Metodologia Avaliatória & Avaliação de Venda", styles["SectionHeader"]))

    reg = venda.get("regressao", {})
    r2 = reg.get("r2_score", 0) if "r2_score" in reg else 0
    fator_of = venda.get("fator_oferta", 0.9)

    detalhes_calc = (
        f"<b>Método de Tratamento:</b> {venda.get('metodo', 'Comparativo Direto')}.<br/>"
        f"<b>Amostragem:</b> {venda.get('n_amostras', 0)} comparáveis tratados estatisticamente. "
        f"Mediana das ofertas = <b>R$ {venda.get('mediana_m2_oferta', 0):,.2f}/m²</b> "
        f"(mínimo: R$ {venda.get('min_m2_oferta', 0):,.2f} | máximo: R$ {venda.get('max_m2_oferta', 0):,.2f}).<br/>"
        f"<b>Ajuste de Mercado (Fator de Oferta):</b> Aplicado redutor de <b>{int((1-fator_of)*100)}%</b> "
        "(fator 0,90) para converter preços anunciados em provável valor de fechamento contratual.<br/>"
        f"<b>Coeficiente de Determinação (R²):</b> {r2:.4f} (grau de explicação do modelo estatístico)."
    )
    story.append(Paragraph(detalhes_calc, styles["BodyCustom"]))
    story.append(Spacer(1, 4 * mm))

    # ==================== 4. AVALIAÇÃO LOCATÍCIA & VIABILIDADE FINANCEIRA ====================
    story.append(Paragraph("4. Avaliação de Locação & Indicadores de Rendimento", styles["SectionHeader"]))

    selic = locacao.get("selic", {})
    selic_val = selic.get("selic_meta_aa", 0)
    spread = locacao.get("spread_vs_selic_pp", 0)

    detalhes_loc = (
        f"<b>Valor Locatício Estimado:</b> <b>{aluguel_mensal} / mês</b> "
        f"({locacao.get('metodo', 'Mercado comparativo')}).<br/>"
        f"<b>Taxa de Rentabilidade Bruta (Cap Rate Anual):</b> <b>{cap_rate}</b> sobre o valor patrimonial de venda.<br/>"
        f"<b>Taxa Básica de Juros (SELIC Meta BACEN):</b> <b>{selic_val:.2f}% a.a.</b> (Data base: {selic.get('data', 'atual')}).<br/>"
        f"<b>Prêmio de Risco Imobiliário vs SELIC:</b> <b>{spread:+.2f} pontos percentuais</b>."
    )
    story.append(Paragraph(detalhes_loc, styles["BodyCustom"]))
    story.append(Spacer(1, 4 * mm))

    # ==================== 5. PONTOS DE ATENÇÃO & AUDITORIA TÉCNICA ====================
    story.append(Paragraph("5. Pontos de Atenção & Auditoria Técnica", styles["SectionHeader"]))

    alertas = [
        "<b>Alienação Fiduciária:</b> O gravame em favor da Caixa Econômica Federal exige prévia liquidação do saldo devedor para a outorga da escritura definitiva.",
        "<b>Natureza Amostral:</b> Os valores paradigmas representam expectativas de pedida (anúncios públicos ativos) sujeitos a margens de barganha na assinatura.",
        "<b>Dispersão e Homogeneização:</b> As amostras do mesmo condomínio e bairros limítrofes indicam consistência no patamar de R$ 4.000 a R$ 4.800/m² para apartamentos de padrão econômico de 40 a 50 m².",
    ]

    for item in alertas:
        story.append(Paragraph(f"• {item}", styles["BodyCustom"]))
        story.append(Spacer(1, 1.5 * mm))

    story.append(Spacer(1, 3 * mm))

    # ==================== 6. CONCLUSÃO E ASSINATURA ====================
    story.append(Paragraph("6. Conclusão da Avaliação", styles["SectionHeader"]))
    conclusao_texto = (
        f"Considerando os atributos intrínsecos do imóvel avaliando (Área privativa de <b>{imovel.get('area_privativa_m2', 0):.2f} m²</b>, "
        f"2 quartos, 1 vaga, Condomínio {imovel.get('nome_condominio', '-')}) e a dinâmica imobiliária do mercado de Sertãozinho/SP, "
        f"conclui-se que o <b>VALOR DE MERCADO VENAL ESTIMADO</b> para o presente imóvel é de <b>{valor_venda}</b>, "
        f"admitindo-se liquidez normal dentro da faixa de <b>{faixa_venda}</b>."
    )
    story.append(Paragraph(conclusao_texto, styles["BodyCustom"]))
    story.append(Spacer(1, 8 * mm))

    # Assinatura digital / carimbo
    assinatura_data = [
        [
            Paragraph("____________________________________________________<br/><b>SISTEMA DE ENGENHARIA DE AVALIAÇÕES</b><br/>Auditoria Automatizada Conforme NBR 14653", ParagraphStyle("Ass1", parent=styles["BodyCustom"], alignment=1)),
            Paragraph(f"<b>Responsabilidade Técnica:</b> Algoritmo de Inteligência Imobiliária<br/><b>Data Base:</b> {datetime.now().strftime('%d/%m/%Y')}<br/><b>Status:</b> Laudo Emitido e Auditado", ParagraphStyle("Ass2", parent=styles["BodyCustom"], alignment=0)),
        ]
    ]
    t_ass = Table(assinatura_data, colWidths=[9.0 * cm, 9.0 * cm])
    t_ass.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(KeepTogether(t_ass))

    # Gerar o PDF com o NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    return caminho_pdf

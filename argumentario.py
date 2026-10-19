"""
Módulo de Geração de Argumentários Comerciais e Mensagens de WhatsApp.
Utiliza IA (Gemini) para transformar auditorias técnicas NBR 14653 em mensagens persuasivas,
humanizadas e profissionais para corretores enviarem a proprietários e compradores.
"""
import json
import os
import urllib.parse
from llm import ClienteLLM


PROMPT_PROPRIETARIO = """Você é um especialista em negociação imobiliária de alto nível da Expandh Imobiliária em Sertãozinho/SP.
Sua missão é redigir uma mensagem de WhatsApp para enviar a um PROPRIETÁRIO cujo imóvel está anunciado por um valor diferente do mercado.

DADOS DO IMÓVEL:
- Código: {codigo}
- Tipo: {tipo}
- Endereço / Bairro: {endereco}, {bairro} - {cidade}/SP
- Preço Anunciado Atual: R$ {preco_anunciado:,.2f}
- Valor Médio de Mercado (NBR 14653): R$ {valor_mercado:,.2f}
- Desvio / Diagnóstico: {desvio} ({status})
- Amostras de Mercado Analisadas: {amostras} anúncios concorrentes ativos no ZAP/VivaReal
- Nome do Proprietário: {nome_cliente}
- Nome do Corretor / Consultor: {nome_corretor}

DIRETRIZES DA MENSAGEM:
1. Tom: Extremamente respeitoso, empático, consultivo e profissional (nunca agressivo ou desvalorizando o patrimônio dele).
2. Mostre que a Expandh está monitorando ativamente a liquidez do imóvel dele na região.
3. Use a autoridade dos dados: mencione que foi feita uma amostragem técnica com {amostras} imóveis reais na região de {bairro}.
4. Se o imóvel estiver ACIMA do mercado: explique que o preço atual afasta os compradores nos filtros dos portais e faz o imóvel "envelhecer" no mercado. Sugira uma revisão estratégica para o valor de R$ {valor_mercado:,.2f} para aquecer as visitas e fechar negócio rápido.
5. Se o imóvel estiver NO PREÇO JUSTO ou OPORTUNIDADE: parabenize o proprietário pela excelente competitividade e reforce que ele é prioridade da equipe.
6. Use formatação do WhatsApp: negrito com asteriscos (*texto*), quebras de linha limpas e emojis com moderação profissional.
7. Termine com uma chamada para ação (CTA) simples e convidativa (ex: tomar um café na Expandh ou uma ligação rápida).
8. Responda APENAS com o texto final da mensagem para envio no WhatsApp. Não adicione notas ou explicações fora da mensagem.
"""

PROMPT_COMPRADOR = """Você é um consultor imobiliário sênior da Expandh Imobiliária em Sertãozinho/SP.
Sua missão é redigir uma mensagem de WhatsApp para apresentar um imóvel a um CLIENTE COMPRADOR OU INVESTIDOR interessado.

DADOS DO IMÓVEL:
- Código: {codigo}
- Tipo: {tipo}
- Bairro: {bairro} - {cidade}/SP
- Preço de Oferta: R$ {preco_anunciado:,.2f}
- Avaliação Técnica de Mercado: R$ {valor_mercado:,.2f}
- Situação de Preço: {status} ({desvio})
- Nome do Cliente: {nome_cliente}
- Nome do Corretor: {nome_corretor}

DIRETRIZES DA MENSAGEM:
1. Tom: Entusiasmado, profissional, ágil e focado em oportunidade.
2. Apresente o imóvel destacando a localização no bairro {bairro} e a segurança da precificação técnica validada pela Expandh.
3. Se for Oportunidade ou Preço Justo: reforce que o imóvel está com valor altamente competitivo frente à média de Sertãozinho e com grande potencial de valorização.
4. Use formatação de WhatsApp (*negrito*, quebras de linha e emojis elegantes).
5. Termine convidando para agendar uma visita presencial ou envio do material completo/fotos.
6. Responda APENAS com a mensagem pronta para envio.
"""


def _formatar_template_fallback_proprietario(dados: dict, nome_cliente: str, nome_corretor: str) -> str:
    saudacao = f"Olá, {nome_cliente}!" if nome_cliente else "Olá! Tudo bem?"
    assinatura = f"{nome_corretor} • Expandh Imobiliária" if nome_corretor else "Equipe Expandh Imobiliária"
    
    codigo = dados.get("Código", dados.get("id", "-"))
    tipo = dados.get("Tipo", "Imóvel")
    bairro = dados.get("Bairro", "Sertãozinho")
    preco_ped = dados.get("Preço Anunciado (R$)", 0)
    preco_merc = dados.get("Valor Mercado Estimado (R$)", 0)
    desvio = dados.get("Desvio (%)", "")
    status = dados.get("Status", "")

    if "Muito Acima" in status or "Acima" in status:
        return (
            f"{saudacao} Aqui é o {assinatura.split('•')[0].strip()} da *Expandh Imobiliária*.\n\n"
            f"Estive fazendo hoje uma revisão técnica da nossa carteira ativa em Sertãozinho, "
            f"especialmente sobre o seu *{tipo} no {bairro} (Cód. {codigo})*.\n\n"
            f"📊 Cruzamos os dados dos portais com as normas periciais (NBR 14653) e notamos que "
            f"a média de mercado para imóveis semelhantes na região está em torno de *R$ {preco_merc:,.0f}* "
            f"(o valor anunciado atual está em R$ {preco_ped:,.0f}).\n\n"
            f"💡 *Por que isso é importante?*\n"
            f"Quando o anúncio fica acima da faixa de busca, o algoritmo dos portais reduz as visualizações "
            f"e os compradores acabam priorizando outras opções do bairro.\n\n"
            f"Podemos alinhar uma calibragem estratégica no valor para *aquecer as visitas e acelerar o fechamento*? "
            f"Se preferir, posso te ligar ou te receber aqui na imobiliária para um café!\n\n"
            f"Um abraço,\n*{assinatura}*"
        )
    else:
        return (
            f"{saudacao} Aqui é o {assinatura.split('•')[0].strip()} da *Expandh Imobiliária*.\n\n"
            f"Passando para te dar uma ótima notícia sobre o seu *{tipo} no {bairro} (Cód. {codigo})*!\n\n"
            f"Concluímos a auditoria técnica de mercado desta semana e o seu imóvel está com um *posicionamento excelente* "
            f"(avaliado em R$ {preco_merc:,.0f} vs. pedido de R$ {preco_ped:,.0f}).\n\n"
            f"Ele está entre os imóveis com melhor competitividade da nossa carteira e estamos dando prioridade máxima "
            f"nas indicações aos clientes que buscam na região.\n\n"
            f"Qualquer novidade nas visitas te mantenho informado!\n\n"
            f"Um abraço,\n*{assinatura}*"
        )


def _formatar_template_fallback_comprador(dados: dict, nome_cliente: str, nome_corretor: str) -> str:
    saudacao = f"Olá, {nome_cliente}!" if nome_cliente else "Olá! Tudo bem?"
    assinatura = f"{nome_corretor} • Expandh Imobiliária" if nome_corretor else "Equipe Expandh Imobiliária"
    
    codigo = dados.get("Código", dados.get("id", "-"))
    tipo = dados.get("Tipo", "Imóvel")
    bairro = dados.get("Bairro", "Sertãozinho")
    preco_ped = dados.get("Preço Anunciado (R$)", 0)

    return (
        f"{saudacao} Tudo bem?\n\n"
        f"Lembrei do seu perfil de busca e selecionei uma oportunidade que acabou de ser avaliada pela nossa equipe: "
        f"um excelente *{tipo} no {bairro} (Cód. {codigo})*.\n\n"
        f"✨ *Destaques:*\n"
        f"• Localização privilegiada no {bairro}\n"
        f"• Valor anunciado: *R$ {preco_ped:,.0f}*\n"
        f"• Precificação 100% auditada com o mercado de Sertãozinho\n\n"
        f"Acredito que encaixa muito bem no que você procura. Posso te enviar as fotos completas ou agendarmos uma visita rápida esta semana?\n\n"
        f"Abraço,\n*{assinatura}*"
    )


def _chamar_groq(prompt: str) -> str:
    """Chama Groq via REST com qwen/qwen3.8-27b caso configurado."""
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        return ""
    import requests
    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
    }
    r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=12)
    if r.status_code == 200:
        return r.json()["choices"][0]["message"]["content"].strip()
    return ""


def gerar_argumentario_whatsapp(
    dados_imovel: dict,
    tipo_publico: str = "proprietario",
    nome_cliente: str = "",
    nome_corretor: str = "",
    modelo_llm: str = "gemini-3.1-flash-lite",
) -> str:
    """Gera mensagem pronta de WhatsApp personalizada via IA (Gemini / Groq) com fallback de alta conversão."""
    nome_cli = nome_cliente.strip() if nome_cliente else "Proprietário(a)"
    nome_cor = nome_corretor.strip() if nome_corretor else "Consultor Expandh"

    prompt_base = PROMPT_PROPRIETARIO if tipo_publico == "proprietario" else PROMPT_COMPRADOR
    prompt = prompt_base.format(
        codigo=dados_imovel.get("Código", dados_imovel.get("id", "-")),
        tipo=dados_imovel.get("Tipo", "Imóvel"),
        endereco=dados_imovel.get("Endereço", "-"),
        bairro=dados_imovel.get("Bairro", "-"),
        cidade=dados_imovel.get("Cidade", "Sertãozinho"),
        preco_anunciado=float(dados_imovel.get("Preço Anunciado (R$)", 0) or 0),
        valor_mercado=float(dados_imovel.get("Valor Mercado Estimado (R$)", 0) or 0),
        desvio=dados_imovel.get("Desvio (%)", "0%"),
        status=dados_imovel.get("Status", "Em análise"),
        amostras=dados_imovel.get("Amostras Usadas", 6),
        nome_cliente=nome_cli,
        nome_corretor=nome_cor,
    )

    # 1. Tentar Groq (ultrarrápido, < 1s)
    try:
        resp_groq = _chamar_groq(prompt)
        if resp_groq and len(resp_groq) > 30:
            return resp_groq
    except Exception:
        pass

    # 2. Tentar Gemini se Groq falhar
    try:
        chave_gemini = os.environ.get("GEMINI_API_KEY", "")
        if chave_gemini:
            llm = ClienteLLM()
            resp_gemini = llm.gerar(modelo_llm, prompt)
            if resp_gemini and len(resp_gemini.strip()) > 30:
                return resp_gemini.strip()
    except Exception:
        pass

    # 3. Fallback determinístico de alta conversão comercial
    if tipo_publico == "proprietario":
        return _formatar_template_fallback_proprietario(dados_imovel, nome_cli, nome_cor)
    return _formatar_template_fallback_comprador(dados_imovel, nome_cli, nome_cor)


def criar_link_direto_whatsapp(mensagem: str, telefone: str = "") -> str:
    """Gera URL com encode UTF-8 para abrir diretamente no WhatsApp Web ou App."""
    texto_encoded = urllib.parse.quote(mensagem)
    fone_limpo = "".join(filter(str.isdigit, telefone)) if telefone else ""
    if fone_limpo:
        if not fone_limpo.startswith("55") and len(fone_limpo) in (10, 11):
            fone_limpo = f"55{fone_limpo}"
        return f"https://api.whatsapp.com/send?phone={fone_limpo}&text={texto_encoded}"
    return f"https://api.whatsapp.com/send?text={texto_encoded}"

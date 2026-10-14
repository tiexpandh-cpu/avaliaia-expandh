import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

from google.antigravity import types, LocalAgentConfig
from google.antigravity.hooks import hooks

@hooks.pre_turn
async def slow_down(data: str) -> types.HookResult:
    print("[Aguardando 25s para blindar contra o limite de 5 requisições por minuto...] ")
    await asyncio.sleep(25)
    return types.HookResult(allow=True)

# Usando o Gemini 3.5 Flash agora que a cota diária resetou! (O modelo de alto QI para não alucinar)
MODELO_GEMINI = "gemini-3.5-flash"

property_intake = types.SubagentConfig(
    name="property_intake",
    description="Responsável por extrair dados textuais de imóveis.",
    model=MODELO_GEMINI,
    system_instruction=(
        "Você processa o texto bruto da matrícula ou descrição do imóvel fornecida pelo usuário. "
        "Sua saída deve ser um resumo estruturado com localização, área e características do imóvel alvo."
    ),
    hooks=[slow_down],
    capabilities=types.SubagentCapabilities(
        agent_behavior=types.AgentBehavior.AUTONOMOUS
    )
)

market_intelligence = types.SubagentConfig(
    name="market_intelligence",
    description="Responsável por buscar amostras comparáveis no mercado.",
    model=MODELO_GEMINI,
    system_instruction=(
        "Você busca amostras comparáveis no mercado baseadas no imóvel alvo. "
        "Use sua ferramenta de busca de anúncios e retorne as amostras formatadas."
    ),
    hooks=[slow_down],
    capabilities=types.SubagentCapabilities(
        agent_behavior=types.AgentBehavior.AUTONOMOUS
    )
)

sales_valuation = types.SubagentConfig(
    name="sales_valuation",
    description="Responsável por calcular o valor de venda do imóvel com base em regressão.",
    model=MODELO_GEMINI,
    system_instruction=(
        "Você calcula o valor de venda do imóvel alvo utilizando as amostras do mercado. "
        "Faça cálculos corretos e estipule o valor total."
    ),
    hooks=[slow_down],
    capabilities=types.SubagentCapabilities(
        agent_behavior=types.AgentBehavior.AUTONOMOUS
    )
)

rental_valuation = types.SubagentConfig(
    name="rental_valuation",
    description="Responsável por calcular a locação com base na Selic.",
    model=MODELO_GEMINI,
    system_instruction=(
        "Você calcula o Cap Rate e viabilidade de locação. "
        "Consulte a taxa Selic e estime o valor de locação."
    ),
    hooks=[slow_down],
    capabilities=types.SubagentCapabilities(
        agent_behavior=types.AgentBehavior.AUTONOMOUS
    )
)

auditor_report = types.SubagentConfig(
    name="auditor_report",
    description="Responsável por redigir o laudo final em Markdown.",
    model=MODELO_GEMINI,
    system_instruction=(
        "Você consolida a avaliação final. Revise os cálculos de Venda e Locação e "
        "gere um laudo impecável em formato Markdown."
    ),
    hooks=[slow_down],
    capabilities=types.SubagentCapabilities(
        agent_behavior=types.AgentBehavior.AUTONOMOUS
    )
)

orchestrator_config = LocalAgentConfig(
    model=MODELO_GEMINI,
    system_instruction=(
        "Você é o gerente do projeto de avaliação. Cumpra o pipeline estrito delegando tarefas:\n"
        "1. Chame o 'property_intake' para entender os dados brutos.\n"
        "2. Passe o resumo para 'market_intelligence' buscar as amostras.\n"
        "3. Chame 'sales_valuation' e 'rental_valuation' fornecendo as amostras.\n"
        "4. Envie os resultados para 'auditor_report' redigir o Laudo Final.\n"
        "Mostre apenas o laudo formatado."
    ),
    subagents=[
        property_intake,
        market_intelligence,
        sales_valuation,
        rental_valuation,
        auditor_report
    ],
    hooks=[slow_down],
    capabilities=types.CapabilitiesConfig(
        enable_subagents=True,
        enable_write_tools=False,
        enable_read_tools=False,
        allowed_subagents=[
            "property_intake",
            "market_intelligence",
            "sales_valuation",
            "rental_valuation",
            "auditor_report"
        ]
    )
)

"""
Módulo de Integração Direta com a API REST / WebService do Kurole (KSI).
Permite sincronização ao vivo e instantânea dos imóveis da Expandh, com fallback
automático para o feed XML caso a API esteja temporariamente em manutenção ou aguardando liberação.
"""
import os
import requests
import feed_parser
from datetime import datetime

KUROLE_ENDPOINT_PADRAO = "https://www.expandhimoveis.com.br/kurole_include/api/webservice/escopos/?id=31"
KUROLE_CHAVE_PADRAO = os.environ.get("KUROLE_API_KEY", "e52ab0d18b01831d3333b2a059c74567")


def testar_conexao_kurole(chave: str = KUROLE_CHAVE_PADRAO, endpoint: str = KUROLE_ENDPOINT_PADRAO) -> dict:
    """Testa o status e as permissões de acesso ao endpoint do Kurole."""
    headers = {
        "Authorization": f"Bearer {chave}",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(endpoint, headers=headers, timeout=12)
        if resp.status_code == 200:
            try:
                dados_json = resp.json()
                if isinstance(dados_json, list) and len(dados_json) > 0:
                    info = dados_json[0]
                    sucesso = bool(info.get("sucesso") == 1 or info.get("sucesso") == "1")
                    return {
                        "online": True,
                        "sucesso": sucesso,
                        "msg": info.get("msg", "Conexão estabelecida"),
                        "dados_brutos": info.get("dados", []),
                    }
                elif isinstance(dados_json, dict):
                    return {
                        "online": True,
                        "sucesso": bool(dados_json.get("sucesso") == 1),
                        "msg": dados_json.get("msg", ""),
                        "dados_brutos": dados_json.get("dados", []),
                    }
            except Exception:
                pass
        return {
            "online": False,
            "sucesso": False,
            "status_code": resp.status_code,
            "msg": f"HTTP {resp.status_code}: {resp.text[:150]}",
        }
    except Exception as e:
        return {
            "online": False,
            "sucesso": False,
            "msg": f"Erro de conexão com o servidor Kurole: {e}",
        }


def normalizar_imovel_kurole_api(item: dict) -> dict:
    """Converte um objeto JSON bruto da API Kurole para o formato padrão do AvaliaIA."""
    # Mapeamento flexível de chaves comuns do Kurole KSI
    codigo = str(item.get("id") or item.get("codigo") or item.get("cod") or item.get("codigo_imovel") or "")
    titulo = item.get("titulo") or item.get("nome") or item.get("descricao_curta") or f"Imóvel {codigo}"
    
    transacao_raw = (item.get("finalidade") or item.get("transacao") or item.get("operacao") or "Venda").lower()
    transacao = "Locação" if any(k in transacao_raw for k in ["loca", "alug", "rent"]) else "Venda"
    negocio_zap = "RENTAL" if transacao == "Locação" else "SALE"
    
    tipo_bruto = str(item.get("tipo") or item.get("subtipo") or item.get("categoria") or "Casa")
    tipo_amigavel, tipo_zap = feed_parser.MAPEAMENTO_TIPOS.get(tipo_bruto.lower(), (tipo_bruto, "HOME"))
    
    # Preços
    preco = float(item.get("valor") or item.get("preco") or item.get("valor_venda") or item.get("valor_locacao") or 0.0)
    condominio = float(item.get("condominio") or item.get("taxa_condominio") or 0.0)
    iptu = float(item.get("iptu") or item.get("valor_iptu") or 0.0)
    
    # Áreas
    area_util = float(item.get("area_util") or item.get("area_construida") or item.get("area_privativa") or 0.0)
    area_total = float(item.get("area_total") or item.get("area_terreno") or 0.0)
    area_principal = area_util if area_util > 0 else area_total
    
    # Endereço
    end_rua = item.get("logradouro") or item.get("rua") or item.get("endereco") or ""
    numero = str(item.get("numero") or "")
    bairro = item.get("bairro") or ""
    cidade = item.get("cidade") or "Sertãozinho"
    uf = item.get("uf") or item.get("estado") or "SP"
    cep = str(item.get("cep") or "")
    
    # Coordenadas
    lat = None
    lon = None
    try:
        if item.get("lat") or item.get("latitude"):
            lat = float(item.get("lat") or item.get("latitude"))
        if item.get("lon") or item.get("lng") or item.get("longitude"):
            lon = float(item.get("lon") or item.get("lng") or item.get("longitude"))
    except Exception:
        pass

    # Fotos
    fotos_raw = item.get("fotos") or item.get("imagens") or []
    fotos = []
    if isinstance(fotos_raw, list):
        for f in fotos_raw:
            if isinstance(f, str) and f.startswith("http"):
                fotos.append(f)
            elif isinstance(f, dict) and f.get("url"):
                fotos.append(f["url"])
    foto_capa = fotos[0] if fotos else (item.get("foto_capa") or "")

    descricao = item.get("descricao") or item.get("texto") or ""
    
    # Refinamentos inteligentes de tipo (Condomínio / Terrenos)
    texto_busca = f"{titulo} {end_rua} {descricao} {bairro}".lower()
    if ("condomínio" in texto_busca or "condominio" in texto_busca or "terra nova" in texto_busca or "portal das flores" in texto_busca or condominio >= 200.0) and "casa" in tipo_amigavel.lower():
        tipo_amigavel = "Casa em Condomínio"
        tipo_zap = "HOME"
        
    preco_m2 = round(preco / area_principal, 2) if area_principal > 0 and preco > 0 else 0.0

    return {
        "id": codigo,
        "titulo": titulo,
        "transacao": transacao,
        "transacao_raw": transacao_raw,
        "negocio_zap": negocio_zap,
        "tipo": tipo_amigavel,
        "tipo_original": tipo_bruto,
        "tipo_zap": tipo_zap,
        "preco": preco,
        "preco_m2": preco_m2,
        "condominio": condominio,
        "iptu": iptu,
        "area_util": area_util,
        "area_total": area_total,
        "area_principal": area_principal,
        "quartos": int(item.get("quartos") or item.get("dormitorios") or 0),
        "suites": int(item.get("suites") or 0),
        "banheiros": int(item.get("banheiros") or 0),
        "vagas": int(item.get("vagas") or item.get("garagens") or 0),
        "bairro": bairro,
        "cidade": cidade,
        "uf": uf,
        "endereco": f"{end_rua}, {numero}".strip(", "),
        "endereco_rua": end_rua,
        "numero": numero,
        "complemento": str(item.get("complemento") or ""),
        "cep": cep,
        "lat": lat,
        "lon": lon,
        "foto_capa": foto_capa,
        "fotos": fotos,
        "descricao": descricao,
        "caracteristicas": item.get("caracteristicas") or [],
        "tipo_publicacao": "STANDARD",
    }


def carregar_dados_carteira_hibrida() -> dict:
    """
    Obtém os imóveis da carteira Expandh.
    Tenta primeiro a API Kurole em tempo real; se indisponível ou pendente de escopo,
    utiliza o Feed XML como contingência garantindo 100% de disponibilidade.
    """
    teste = testar_conexao_kurole()
    if teste.get("online") and teste.get("sucesso") and teste.get("dados_brutos"):
        imoveis = [normalizar_imovel_kurole_api(it) for it in teste["dados_brutos"] if isinstance(it, dict)]
        if imoveis:
            return {
                "origem": "API Kurole (Tempo Real)",
                "sucesso": True,
                "total_imoveis": len(imoveis),
                "imoveis": imoveis,
                "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "aviso": None,
            }

    # Fallback automático para o Feed XML
    dados_xml = feed_parser.carregar_feed_xml()
    aviso_api = teste.get("msg") if teste.get("online") else "API Kurole temporariamente inacessível"
    
    return {
        "origem": "Feed XML (Kurole KSI)",
        "sucesso": True,
        "total_imoveis": len(dados_xml.get("imoveis", [])),
        "imoveis": dados_xml.get("imoveis", []),
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "aviso": f"API Kurole detectada. Status: {aviso_api}. Utilizando contingência do Feed XML.",
    }

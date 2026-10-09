"""
Coleta de anúncios reais no ZAP Imóveis (mesma base do VivaReal).

Usa a API JSON que o próprio site consome (glue-api). Não é uma API oficial/documentada:
pode mudar ou ser bloqueada a qualquer momento, e o uso deve respeitar os termos do portal.
"""
import math
import time

import requests

BASE_URL = "https://glue-api.zapimoveis.com.br/v2/listings"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "x-domain": "www.zapimoveis.com.br",
}
TAMANHO_PAGINA = 24     # a API recusa páginas acima de ~30
MAX_ANUNCIOS = 240      # teto por busca (10 páginas)
PAUSA_ENTRE_PAGINAS = 1.0

UF_NOME = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará",
    "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}

# Parâmetros de tipo que efetivamente filtram na API (testado com apartamentos).
FILTROS_TIPO = {
    "APARTMENT": {
        "unitTypes": "APARTMENT",
        "unitTypesV3": "APARTMENT",
        "unitSubTypes": "UnitSubType_NONE,DUPLEX,TRIPLEX",
        "usageTypes": "RESIDENTIAL",
    },
    "HOME": {
        "unitTypes": "HOME",
        "unitTypesV3": "HOME",
        "unitSubTypes": "UnitSubType_NONE,SINGLE_STOREY_HOUSE,VILLAGE_HOUSE,KITNET",
        "usageTypes": "RESIDENTIAL",
    },
}


def tipo_zap(tipo_imovel: str) -> str | None:
    t = (tipo_imovel or "").lower()
    if "apart" in t or "apto" in t or "flat" in t:
        return "APARTMENT"
    if "casa" in t or "sobrado" in t:
        return "HOME"
    return None


def _primeiro(lista, padrao=0):
    return lista[0] if lista else padrao


def _normalizar(item: dict, negocio: str) -> dict | None:
    l = item.get("listing", {})
    preco = next((p.get("price") for p in l.get("pricingInfos", []) if p.get("businessType") == negocio), None)
    area = _primeiro(l.get("usableAreas")) or _primeiro(l.get("totalAreas"))
    if not preco or not area:
        return None
    end = l.get("address", {})
    ponto = end.get("point") or {}
    link = (item.get("link") or {}).get("href", "")
    return {
        "id": l.get("id"),
        "tipo": _primeiro(l.get("unitTypes"), ""),
        "preco": float(preco),
        "area": float(area),
        "quartos": _primeiro(l.get("bedrooms")),
        "vagas": _primeiro(l.get("parkingSpaces")),
        "condominio": next((p.get("monthlyCondoFee") for p in l.get("pricingInfos", [])), None),
        "bairro": end.get("neighborhood", ""),
        "endereco": " ".join(x for x in [end.get("street", ""), end.get("streetNumber", "")] if x),
        "lat": ponto.get("lat"),
        "lon": ponto.get("lon"),
        "url": f"https://www.zapimoveis.com.br{link}" if link else "",
        "fonte": "ZAP Imóveis",
    }


def buscar_anuncios(cidade: str, uf: str, tipo: str, negocio: str = "SALE") -> list[dict]:
    """Baixa os anúncios da cidade (venda: SALE, aluguel: RENTAL) para o tipo informado."""
    params = {
        "business": negocio,
        "categoryPage": "RESULT",
        "listingType": "USED",
        "addressCity": cidade,
        "addressState": UF_NOME.get(uf.upper(), uf),
        "size": TAMANHO_PAGINA,
        **FILTROS_TIPO[tipo],
    }
    anuncios, vistos, inicio, total = [], set(), 0, None
    while inicio < MAX_ANUNCIOS and (total is None or inicio < total):
        params["from"] = inicio
        r = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        busca = r.json()["search"]
        total = busca.get("totalCount", 0)
        itens = busca["result"]["listings"]
        if not itens:
            break
        for item in itens:
            a = _normalizar(item, negocio)
            if a and a["tipo"] == tipo and a["id"] not in vistos:
                vistos.add(a["id"])
                anuncios.append(a)
        inicio += TAMANHO_PAGINA
        time.sleep(PAUSA_ENTRE_PAGINAS)
    return anuncios


def distancia_km(lat1, lon1, lat2, lon2) -> float | None:
    if None in (lat1, lon1, lat2, lon2):
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, map(float, (lat1, lon1, lat2, lon2)))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))

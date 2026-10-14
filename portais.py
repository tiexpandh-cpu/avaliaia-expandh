"""
Coleta de anúncios reais no ZAP Imóveis (mesma base do VivaReal).
Suporta Residencial (Casas, Apartamentos), Terrenos/Lotes e Comercial (Salas, Salões, Galpões).
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
TAMANHO_PAGINA = 24
MAX_ANUNCIOS = 240
PAUSA_ENTRE_PAGINAS = 0.5

UF_NOME = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará",
    "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}

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

MAPEAMENTO_UNIT_TYPES = {
    "APARTMENT": ["APARTMENT", "FLAT", "KITNET"],
    "HOME": ["HOME", "CONDOMINIUM", "VILLAGE_HOUSE"],
    "LAND_LOT": ["RESIDENTIAL_ALLOTMENT_LAND", "COMMERCIAL_ALLOTMENT_LAND", "LAND_LOT", "ALLOTMENT_LAND"],
    "OFFICE": ["OFFICE", "COMMERCIAL_BUILDING"],
    "SHED": ["SHED_DEPOSIT_WAREHOUSE"],
    "BUSINESS": ["BUSINESS", "COMMERCIAL_PROPERTY", "COMMERCIAL_BUILDING", "STORE", "COMMERCIAL"],
    "COMMERCIAL_ALL": ["OFFICE", "BUSINESS", "SHED_DEPOSIT_WAREHOUSE", "COMMERCIAL_BUILDING", "COMMERCIAL_PROPERTY", "STORE", "COMMERCIAL"],
    "FARM": ["FARM", "AGRICULTURAL"],
}


def tipo_zap(tipo_imovel: str) -> str | None:
    t = (tipo_imovel or "").lower()
    if "apart" in t or "apto" in t or "flat" in t or "kitnet" in t:
        return "APARTMENT"
    if "casa" in t or "sobrado" in t or "condo" in t:
        return "HOME"
    if "terreno" in t or "lote" in t or "allotment" in t:
        return "LAND_LOT"
    if "sala" in t or "escrit" in t or "office" in t or "consult" in t:
        return "OFFICE"
    if "galp" in t or "barrac" in t or "armaz" in t or "industrial" in t or "shed" in t:
        return "SHED"
    if "ponto" in t or "loja" in t or "sal" in t or "comercial" in t or "business" in t or "edificio" in t:
        return "BUSINESS"
    if "chac" in t or "sitio" in t or "rancho" in t or "farm" in t:
        return "FARM"
    return None


def _primeiro(lista, padrao=0):
    return lista[0] if lista else padrao


def _normalizar(item: dict, negocio: str) -> dict | None:
    l = item.get("listing", {})
    preco = next((p.get("price") for p in l.get("pricingInfos", []) if p.get("businessType") == negocio), None)
    # Para terrenos, prefere área total do terreno; para construídos, área útil
    area = _primeiro(l.get("usableAreas")) or _primeiro(l.get("totalAreas"))
    if not preco or not area or float(area) <= 0:
        return None
    end = l.get("address", {})
    ponto = end.get("point") or {}
    link = (item.get("link") or {}).get("href", "")
    uts = l.get("unitTypes", [])
    tipo_real = uts[0] if uts else ""
    return {
        "id": l.get("id"),
        "tipo": tipo_real,
        "tipos_lista": uts,
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
    """Baixa os anúncios da cidade para a tipologia solicitada (Residencial, Terreno, Comercial)."""
    params = {
        "business": negocio,
        "categoryPage": "RESULT",
        "listingType": "USED",
        "addressCity": cidade,
        "addressState": UF_NOME.get(uf.upper(), uf),
        "size": TAMANHO_PAGINA,
    }

    if tipo in FILTROS_TIPO:
        params.update(FILTROS_TIPO[tipo])
    elif tipo in ("OFFICE", "SHED", "BUSINESS", "COMMERCIAL_ALL"):
        params["usageTypes"] = "COMMERCIAL"

    tipos_validos = MAPEAMENTO_UNIT_TYPES.get(tipo, [tipo])
    # Fallback amplo se for comercial
    eh_comercial = tipo in ("OFFICE", "SHED", "BUSINESS")

    anuncios, vistos, inicio, total = [], set(), 0, None
    while inicio < MAX_ANUNCIOS and (total is None or inicio < total):
        params["from"] = inicio
        try:
            r = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=25)
            r.raise_for_status()
            busca = r.json()["search"]
            total = busca.get("totalCount", 0)
            itens = busca["result"]["listings"]
        except Exception:
            break

        if not itens:
            break

        for item in itens:
            a = _normalizar(item, negocio)
            if not a:
                continue
            # Verifica compatibilidade de tipologia
            bate_tipo = a["tipo"] in tipos_validos or any(ut in tipos_validos for ut in a.get("tipos_lista", []))
            if bate_tipo and a["id"] not in vistos:
                vistos.add(a["id"])
                anuncios.append(a)

        inicio += TAMANHO_PAGINA
        time.sleep(PAUSA_ENTRE_PAGINAS)

    # Se coletou poucas amostras para um subtipo comercial específico (ex: galpão ou sala),
    # complementa com outros comerciais da mesma cidade para não deixar sem amostragem
    if eh_comercial and len(anuncios) < 3 and tipo != "COMMERCIAL_ALL":
        comerciais_gerais = buscar_anuncios(cidade, uf, "COMMERCIAL_ALL", negocio)
        for cg in comerciais_gerais:
            if cg["id"] not in vistos:
                vistos.add(cg["id"])
                anuncios.append(cg)

    return anuncios


def distancia_km(lat1, lon1, lat2, lon2) -> float | None:
    if None in (lat1, lon1, lat2, lon2):
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, map(float, (lat1, lon1, lat2, lon2)))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))

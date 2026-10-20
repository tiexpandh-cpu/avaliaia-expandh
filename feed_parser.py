"""
Módulo de Ingestão e Processamento do Feed de Imóveis (Padrão VivaReal / ZAP VRSync).
Suporta leitura direta de XML via URL (Object Storage / CDN) ou arquivo local.
"""
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


URL_FEED_PADRAO = "https://axvliw1bcpyx.objectstorage.sa-vinhedo-1.oci.customer-oci.com/n/axvliw1bcpyx/b/ksi/o/682/xml/xml_ksi_zap_vrsync_1_0_3.xml"

# Mapeamento do tipo de imóvel do feed para rótulo amigável e tipo de busca ZAP
MAPEAMENTO_TIPOS = {
    "residential / home": ("Casa", "HOME"),
    "residential / apartment": ("Apartamento", "APARTMENT"),
    "residential / condo": ("Casa em Condomínio", "HOME"),
    "residential / land lot": ("Terreno Residencial", "LAND_LOT"),
    "commercial / land lot": ("Terreno Comercial", "LAND_LOT"),
    "commercial / office": ("Sala Comercial", "OFFICE"),
    "commercial / industrial": ("Galpão Industrial", "SHED"),
    "commercial / business": ("Ponto Comercial / Salão", "BUSINESS"),
    "commercial / edificio comercial": ("Prédio Comercial", "BUSINESS"),
    "residential / farm ranch": ("Chácara / Sítio", "FARM"),
}


def _extrair_texto(elemento, tag: str, padrao: str = "") -> str:
    """Extrai texto com segurança de um elemento XML ignorando namespace se necessário."""
    if elemento is None:
        return padrao
    # Tenta busca direta com namespace local ou global
    el = elemento.find(f".//{{*}}{tag}")
    if el is None:
        el = elemento.find(tag)
    if el is not None and el.text:
        return el.text.strip()
    return padrao


def _extrair_float(elemento, tag: str, padrao: float = 0.0) -> float:
    texto = _extrair_texto(elemento, tag, "")
    try:
        return float(texto)
    except (ValueError, TypeError):
        return padrao


def _extrair_int(elemento, tag: str, padrao: int = 0) -> int:
    texto = _extrair_texto(elemento, tag, "")
    try:
        return int(float(texto))
    except (ValueError, TypeError):
        return padrao


def carregar_feed_xml(fonte: str = URL_FEED_PADRAO) -> dict:
    """
    Baixa e processa o feed XML VRSync.
    Retorna dicionário com metadados do cabeçalho e lista estruturada de imóveis.
    """
    if fonte.startswith("http://") or fonte.startswith("https://"):
        req = urllib.request.Request(
            fonte,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            conteudo = resp.read()
    else:
        conteudo = Path(fonte).read_bytes()

    root = ET.fromstring(conteudo)

    # 1. Metadados do Cabeçalho (Header)
    header_el = root.find(".//{*}Header")
    header_info = {
        "provedor": _extrair_texto(header_el, "Provider", "Sistema Imobiliário"),
        "imobiliaria": _extrair_texto(header_el, "ContactName", "Imobiliária"),
        "email": _extrair_texto(header_el, "Email", ""),
        "telefone": _extrair_texto(header_el, "Telephone", ""),
        "data_publicacao": _extrair_texto(header_el, "PublishDate", ""),
    }

    # 2. Imóveis (Listings)
    listings_els = root.findall(".//{*}Listing")
    imoveis = []

    for l in listings_els:
        listing_id = _extrair_texto(l, "ListingID")
        titulo = _extrair_texto(l, "Title")
        transacao_raw = _extrair_texto(l, "TransactionType", "For Sale")
        tipo_publicacao = _extrair_texto(l, "PublicationType", "STANDARD")

        loc_el = l.find(".//{*}Location")
        pais = _extrair_texto(loc_el, "Country", "Brasil")
        uf = _extrair_texto(loc_el, "State", "SP")
        cidade = _extrair_texto(loc_el, "City", "")
        bairro = _extrair_texto(loc_el, "Neighborhood", "")
        endereco_rua = _extrair_texto(loc_el, "Address", "")
        numero = _extrair_texto(loc_el, "StreetNumber", "")
        complemento = _extrair_texto(loc_el, "Complement", "")
        cep = _extrair_texto(loc_el, "PostalCode", "")
        lat = _extrair_float(loc_el, "Latitude", None)
        lon = _extrair_float(loc_el, "Longitude", None)

        det_el = l.find(".//{*}Details")
        tipo_raw = _extrair_texto(det_el, "PropertyType", "")
        tipo_lower = tipo_raw.lower()
        tipo_amigavel, tipo_zap = MAPEAMENTO_TIPOS.get(tipo_lower, (tipo_raw, None))

        # Preço varia se é venda ou aluguel
        preco_venda = _extrair_float(det_el, "ListPrice", 0.0)
        preco_locacao = _extrair_float(det_el, "RentalPrice", 0.0)

        is_rent = "rent" in transacao_raw.lower() or (preco_locacao > 0 and preco_venda == 0)
        transacao = "Locação" if is_rent else "Venda"
        preco_atual = preco_locacao if is_rent else preco_venda
        negocio_zap = "RENTAL" if is_rent else "SALE"

        condominio = _extrair_float(det_el, "PropertyAdministrationFee", 0.0)
        iptu = _extrair_float(det_el, "Iptu", 0.0)
        area_util = _extrair_float(det_el, "LivingArea", 0.0)
        area_total = _extrair_float(det_el, "LotArea", 0.0)
        area_principal = area_util if area_util > 0 else area_total
        quartos = _extrair_int(det_el, "Bedrooms", 0)
        suites = _extrair_int(det_el, "Suites", 0)
        banheiros = _extrair_int(det_el, "Bathrooms", 0)
        vagas = _extrair_int(det_el, "Garage", 0)
        descricao = _extrair_texto(det_el, "Description", "")

        # Refinamento inteligente de tipo para terrenos e lotes mal categorizados no XML
        texto_analise = f"{titulo} {endereco_rua} {descricao}".lower()
        if ("terreno" in texto_analise or "lote" in texto_analise) and area_util == 0:
            if "comercial" in texto_analise or "business" in tipo_lower or "commercial" in tipo_lower:
                tipo_amigavel = "Terreno Comercial"
                tipo_zap = "LAND_LOT"
            elif "chácara" in texto_analise or "sitio" in texto_analise:
                tipo_amigavel = "Chácara / Sítio"
                tipo_zap = "FARM"
            else:
                tipo_amigavel = "Terreno Residencial"
                tipo_zap = "LAND_LOT"
        elif "terrenos área" in titulo.lower() and "farm ranch" in tipo_lower:
            tipo_amigavel = "Terreno Comercial" if "comercial" in texto_analise else "Terreno Residencial"
            tipo_zap = "LAND_LOT"

        # Refinamento inteligente para Casas em Condomínio Fechado
        if ("condomínio" in texto_analise or "condominio" in texto_analise or "terra nova" in texto_analise or "portal das flores" in texto_analise or condominio >= 200.0) and "casa" in tipo_amigavel.lower():
            tipo_amigavel = "Casa em Condomínio"
            tipo_zap = "HOME"

        # Features / Características
        features = [f.text.strip() for f in det_el.findall(".//{*}Feature") if f.text]

        # Fotos
        fotos = []
        foto_capa = ""
        for media_item in l.findall(".//{*}Item"):
            if media_item.get("medium") == "image" and media_item.text:
                url_img = media_item.text.strip()
                fotos.append(url_img)
                if media_item.get("primary") == "true" or not foto_capa:
                    foto_capa = url_img

        preco_m2 = round(preco_atual / area_principal, 2) if area_principal > 0 and preco_atual > 0 else 0.0

        imoveis.append({
            "id": listing_id,
            "titulo": titulo,
            "transacao": transacao,
            "transacao_raw": transacao_raw,
            "negocio_zap": negocio_zap,
            "tipo": tipo_amigavel,
            "tipo_original": tipo_raw,
            "tipo_zap": tipo_zap,
            "preco": preco_atual,
            "preco_m2": preco_m2,
            "condominio": condominio,
            "iptu": iptu,
            "area_util": area_util,
            "area_total": area_total,
            "area_principal": area_principal,
            "quartos": quartos,
            "suites": suites,
            "banheiros": banheiros,
            "vagas": vagas,
            "bairro": bairro,
            "cidade": cidade,
            "uf": uf,
            "endereco": f"{endereco_rua}, {numero}".strip(", "),
            "endereco_rua": endereco_rua,
            "numero": numero,
            "complemento": complemento,
            "cep": cep,
            "lat": lat,
            "lon": lon,
            "foto_capa": foto_capa,
            "fotos": fotos,
            "descricao": descricao,
            "caracteristicas": features,
            "tipo_publicacao": tipo_publicacao,
        })

    return {
        "cabecalho": header_info,
        "total": len(imoveis),
        "imoveis": imoveis,
    }


if __name__ == "__main__":
    feed = carregar_feed_xml()
    print("Cabeçalho:", feed["cabecalho"])
    print(f"Total de imóveis carregados: {feed['total']}")
    if feed["imoveis"]:
        print("Exemplo 1:", feed["imoveis"][0]["id"], feed["imoveis"][0]["titulo"][:50], feed["imoveis"][0]["preco"])

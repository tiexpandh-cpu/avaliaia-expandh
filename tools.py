import requests
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

def geocode_osm_tool(endereco: str) -> dict:
    """Busca as coordenadas de um endereço usando o OpenStreetMap (Gratuito)."""
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "RealEstateEvaluator/1.0"}
    params = {"q": endereco, "format": "json", "limit": 1}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
    except requests.RequestException as e:
        return {"erro": f"Falha ao consultar OSM: {e}"}
    if response.status_code == 200 and len(response.json()) > 0:
        data = response.json()[0]
        return {"lat": data["lat"], "lon": data["lon"], "display_name": data["display_name"]}
    return {"erro": "Endereço não encontrado"}

def bacen_selic_tool() -> dict:
    """Consulta a API do Banco Central (SGS) para obter a meta da taxa Selic (% a.a.) (Gratuito)."""
    # Código 432 = Meta Selic definida pelo Copom (% a.a.)
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
    try:
        response = requests.get(url, timeout=15)
    except requests.RequestException as e:
        return {"erro": f"Falha ao consultar o Bacen: {e}"}
    if response.status_code == 200:
        return {"selic_meta_aa": float(response.json()[0]["valor"]), "data": response.json()[0]["data"]}
    return {"erro": "Não foi possível obter a Selic"}

def linear_regression_homogenization(amostras: list[dict]) -> dict:
    """
    Aplica Regressão Linear para encontrar a relação entre área e preço.
    Espera uma lista de dicionários: [{'area': 100, 'preco': 500000}, ...]
    """
    df = pd.DataFrame(amostras)
    if len(df) < 3:
        return {"erro": "Amostras insuficientes para regressão linear. Mínimo de 3 necessárias."}
    
    X = df[['area']].values
    y = df['preco'].values
    
    modelo = LinearRegression()
    modelo.fit(X, y)
    
    return {
        "coeficiente_angular_m2": round(modelo.coef_[0], 2),
        "intercepto": round(modelo.intercept_, 2),
        "r2_score": round(modelo.score(X, y), 4)
    }

def web_scraper_simulado(bairro: str, tipologia: str) -> list:
    """
    Simula uma extração de anúncios do mercado. 
    Na prática, aqui entraria um BeautifulSoup rastreando um portal aberto.
    """
    return [
        {"endereco": f"Rua A, {bairro}", "area": 80, "preco": 800000, "vagas": 1},
        {"endereco": f"Rua B, {bairro}", "area": 85, "preco": 830000, "vagas": 2},
        {"endereco": f"Rua C, {bairro}", "area": 78, "preco": 750000, "vagas": 1},
    ]

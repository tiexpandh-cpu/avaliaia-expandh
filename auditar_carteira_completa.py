"""
Script de Execução da Auditoria Completa da Carteira de Imóveis.
Executa a reavaliação de todos os imóveis da base contra o mercado (ZAP Ao Vivo),
salva relatórios em CSV e JSON, e gera a base para o dashboard do Streamlit.
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Garante path e encoding corretos
diretorio_raiz = Path(__file__).resolve().parent
sys.path.insert(0, str(diretorio_raiz))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import feed_parser
import concurrent.futures
import pandas as pd
import pipeline
import reavaliacao_carteira


def executar_auditoria_completa(progress_callback=None):
    inicio_global = time.time()
    print("=" * 70)
    print("  AUDITORIA GERAL DE CARTEIRA - REAVALIACAO DE ESTOQUE ATIVO")
    print("=" * 70)

    # 1. Carregar feed
    if progress_callback:
        progress_callback(0, 100, "Baixando feed XML atualizado da imobiliária...", 0, 0)
    print("\n[1/3] Baixando e processando feed XML da imobiliaria...")
    dados_feed = feed_parser.carregar_feed_xml()
    imoveis = dados_feed.get("imoveis", [])
    cabecalho = dados_feed.get("cabecalho", {})
    total = len(imoveis)
    print(f"      Imobiliaria: {cabecalho.get('imobiliaria')} ({cabecalho.get('provedor')})")
    print(f"      Total de imoveis ativos no feed: {total}")

    # 2. Pré-carregar cache de mercado para Sertãozinho e demais praças em paralelo
    if progress_callback:
        t_dec = time.time() - inicio_global
        progress_callback(1, total, "Conectando ao ZAP e coletando comparáveis em paralelo...", t_dec, 0)
    print("\n[2/3] Conectando ao ZAP Imoveis e pre-carregando anuncios da concorrencia (paralelo)...")

    # Identifica todas as combinações únicas presentes no feed para pre-cachear
    combos = list({
        (
            im.get("cidade") or "Sertãozinho",
            im.get("uf") or "SP",
            im.get("tipo_zap"),
            im.get("negocio_zap", "SALE" if im.get("transacao") == "Venda" else "RENTAL")
        )
        for im in imoveis if im.get("tipo_zap")
    })

    def _carregar_combo(item):
        cid, uf, tzap, neg = item
        try:
            anuncios = reavaliacao_carteira.obter_anuncios_mercado_com_cache(cid, uf, tzap, neg)
            return (cid, tzap, neg, len(anuncios), None)
        except Exception as e:
            return (cid, tzap, neg, 0, str(e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futuros = {executor.submit(_carregar_combo, c): c for c in combos}
        for f in concurrent.futures.as_completed(futuros):
            cid, tzap, neg, n_anunc, err = f.result()
            if err:
                print(f"      [AVISO] {cid} - {tzap} ({neg}): {err}")
            else:
                print(f"      [OK] {cid} - {tzap} ({neg}): {n_anunc} anuncios coletados")

    # 3. Processar todos os imóveis da base
    print(f"\n[3/3] Avaliando todos os {total} imóveis da carteira...")
    resultados = []
    inicio_loop = time.time()

    qtd_avaliados = 0
    qtd_sem_amostras = 0

    for idx, im in enumerate(imoveis, 1):
        codigo = im.get("id", f"ID_{idx}")
        tipo = im.get("tipo", "Imóvel")
        bairro = im.get("bairro", "")
        cidade = im.get("cidade", "")
        transacao = im.get("transacao", "Venda")
        preco_anunciado = float(im.get("preco") or 0.0)
        area = float(im.get("area_principal") or im.get("area_util") or im.get("area_total") or 0.0)

        # Se tiver tipo compatível com ZAP
        if im.get("tipo_zap") and area > 0:
            res = reavaliacao_carteira.reavaliar_imovel_feed(im, fator_oferta=pipeline.FATOR_OFERTA)
            if res.get("sucesso"):
                qtd_avaliados += 1
                desvio = res["desvio_pct"]
                status = res["status"]
                valor_est = res["valor_fechamento_estimado"]
                dif = res["diferenca_rs"]
                diagnostico = res["diagnostico"]
                acao = res["acao_sugerida"]
                mediana_m2 = res["mediana_m2_concorrencia"]
                amostras_qtd = res["n_amostras"]
            else:
                qtd_sem_amostras += 1
                status = "⚪ Sem Comparáveis Suficientes"
                desvio = None
                valor_est = None
                dif = None
                diagnostico = res.get("motivo", "Amostras insuficientes no portal")
                acao = "Coletar amostras adicionais manualmente"
                mediana_m2 = None
                amostras_qtd = res.get("n_amostras", 0)
        else:
            qtd_sem_amostras += 1
            status = "ℹ️ Sem Área Cadastrada"
            desvio = None
            valor_est = None
            dif = None
            diagnostico = "Imóvel sem área útil ou de terreno informada no feed."
            acao = "Completar cadastro no sistema"
            mediana_m2 = None
            amostras_qtd = 0

        item_resultado = {
            "Código": codigo,
            "Título": im.get("titulo", ""),
            "Transação": transacao,
            "Tipo": tipo,
            "Bairro": bairro,
            "Cidade": cidade,
            "UF": im.get("uf", "SP"),
            "Endereço": im.get("endereco", ""),
            "Área (m²)": area,
            "Quartos": im.get("quartos", 0),
            "Vagas": im.get("vagas", 0),
            "Preço Anunciado (R$)": preco_anunciado,
            "R$/m² Anunciado": round(preco_anunciado / area, 2) if area > 0 else 0.0,
            "Valor Mercado Estimado (R$)": valor_est,
            "Faixa Mínima (R$)": res.get("faixa_min") if im.get("tipo_zap") and res.get("sucesso") else None,
            "Faixa Máxima (R$)": res.get("faixa_max") if im.get("tipo_zap") and res.get("sucesso") else None,
            "Desvio (%)": f"{desvio:+.1f}%" if desvio is not None else "-",
            "Desvio_Num": desvio,
            "Diferença (R$)": dif,
            "Status": status,
            "Mediana R$/m² Região": mediana_m2,
            "Amostras Usadas": amostras_qtd,
            "Diagnóstico": diagnostico,
            "Ação Comercial Recomendada": acao,
            "Foto": im.get("foto_capa", ""),
            "Fator Localização": res.get("fator_localizacao_aplicado", 1.0) if res.get("sucesso") else 1.0,
            "Justificativa Localização": res.get("justificativa_localizacao", "") if res.get("sucesso") else "",
            "Fator Escala": res.get("fator_escala_aplicado", 1.0) if res.get("sucesso") else 1.0,
            "Justificativa Escala": res.get("justificativa_escala", "") if res.get("sucesso") else "",
            "Data Auditoria": datetime.now().strftime("%d/%m/%Y"),
        }
        resultados.append(item_resultado)

        tempo_decorrido = time.time() - inicio_global
        tempo_no_loop = time.time() - inicio_loop
        if idx > 2 and tempo_no_loop > 0.1:
            tempo_por_item = tempo_no_loop / idx
            tempo_restante = (total - idx) * tempo_por_item
        else:
            tempo_restante = 0

        if progress_callback:
            msg_curr = f"[{codigo}] {tipo} • {bairro or cidade} ({transacao})"
            progress_callback(idx, total, msg_curr, tempo_decorrido, tempo_restante)

        if idx % 30 == 0 or idx == total:
            print(f"      Progresso: {idx}/{total} imoveis processados...")

    tempo_total = time.time() - inicio_global
    print(f"\n[SUCESSO] Auditoria concluida em {tempo_total:.1f} segundos!")
    print(f"  - Imoveis avaliados com comparaveis ao vivo no ZAP: {qtd_avaliados}")
    print(f"  - Imoveis sem comparaveis suficientes no momento:   {qtd_sem_amostras}")

    # 4. Estatísticas separadas: VENDAS e LOCAÇÃO
    vendas_lista = [r for r in resultados if r["Transação"] == "Venda"]
    locacao_lista = [r for r in resultados if r["Transação"] == "Locação"]

    vendas_avaliadas = [r for r in vendas_lista if r["Desvio_Num"] is not None]
    locacao_avaliada = [r for r in locacao_lista if r["Desvio_Num"] is not None]

    def _calc_stats(lista):
        if not lista:
            return {"muito_acima": 0, "acima": 0, "justo": 0, "oportunidade": 0, "total": 0}
        return {
            "muito_acima": sum(1 for r in lista if "Muito Acima" in r["Status"]),
            "acima": sum(1 for r in lista if "Acima do Mercado" in r["Status"]),
            "justo": sum(1 for r in lista if "Preço Justo" in r["Status"]),
            "oportunidade": sum(1 for r in lista if "Oportunidade" in r["Status"]),
            "total": len(lista),
        }

    stats_vendas = _calc_stats(vendas_avaliadas)
    stats_locacao = _calc_stats(locacao_avaliada)

    print("\n" + "=" * 70)
    print("  DIAGNOSTICO DE VENDAS (Residenciais)")
    print("=" * 70)
    print(f"  Total Vendas no Feed: {len(vendas_lista)} | Residenciais Auditados: {len(vendas_avaliadas)}")
    if vendas_avaliadas:
        print(f"  [!] Muito Acima (> 15%): {stats_vendas['muito_acima']} ({stats_vendas['muito_acima']/len(vendas_avaliadas)*100:.1f}%)")
        print(f"  [*] Levemente Acima (+5% a 15%): {stats_vendas['acima']} ({stats_vendas['acima']/len(vendas_avaliadas)*100:.1f}%)")
        print(f"  [OK] No Preco Justo (+-5%): {stats_vendas['justo']} ({stats_vendas['justo']/len(vendas_avaliadas)*100:.1f}%)")
        print(f"  [$] Oportunidades (< -7%): {stats_vendas['oportunidade']} ({stats_vendas['oportunidade']/len(vendas_avaliadas)*100:.1f}%)")

    print("\n" + "=" * 70)
    print("  DIAGNOSTICO DE LOCACAO (Residenciais)")
    print("=" * 70)
    print(f"  Total Locacao no Feed: {len(locacao_lista)} | Residenciais Auditados: {len(locacao_avaliada)}")
    if locacao_avaliada:
        print(f"  [!] Aluguel Muito Acima (> 15%): {stats_locacao['muito_acima']} ({stats_locacao['muito_acima']/len(locacao_avaliada)*100:.1f}%)")
        print(f"  [*] Levemente Acima (+5% a 15%): {stats_locacao['acima']} ({stats_locacao['acima']/len(locacao_avaliada)*100:.1f}%)")
        print(f"  [OK] No Preco Justo (+-5%): {stats_locacao['justo']} ({stats_locacao['justo']/len(locacao_avaliada)*100:.1f}%)")
        print(f"  [$] Oportunidades (< -7%): {stats_locacao['oportunidade']} ({stats_locacao['oportunidade']/len(locacao_avaliada)*100:.1f}%)")
    print("=" * 70)

    # 5. Salvar arquivos separados por operação
    pasta_saida = diretorio_raiz / "laudos"
    pasta_saida.mkdir(exist_ok=True)

    caminho_csv_total = pasta_saida / "auditoria_completa_carteira_expandh.csv"
    caminho_csv_vendas = pasta_saida / "auditoria_vendas_expandh.csv"
    caminho_csv_locacao = pasta_saida / "auditoria_locacao_expandh.csv"

    caminho_json = pasta_saida / "auditoria_completa_carteira_expandh.json"
    caminho_cache_app = diretorio_raiz / "dados_auditoria_completa.json"

    df_total = pd.DataFrame(resultados)
    df_total.to_csv(caminho_csv_total, index=False, sep=";", encoding="utf-8-sig")

    df_vendas = pd.DataFrame(vendas_lista)
    df_vendas.to_csv(caminho_csv_vendas, index=False, sep=";", encoding="utf-8-sig")

    df_locacao = pd.DataFrame(locacao_lista)
    df_locacao.to_csv(caminho_csv_locacao, index=False, sep=";", encoding="utf-8-sig")

    print(f"\n[Planilhas Salvas]")
    print(f"  - Todas Operações: {caminho_csv_total}")
    print(f"  - Apenas Vendas:   {caminho_csv_vendas}")
    print(f"  - Apenas Locação:  {caminho_csv_locacao}")

    dados_salvar = {
        "cabecalho": cabecalho,
        "data_execucao": datetime.now().isoformat(),
        "total_imoveis": total,
        "vendas": {
            "total": len(vendas_lista),
            "avaliados": len(vendas_avaliadas),
            "estatisticas": stats_vendas,
            "imoveis": vendas_lista,
        },
        "locacao": {
            "total": len(locacao_lista),
            "avaliados": len(locacao_avaliada),
            "estatisticas": stats_locacao,
            "imoveis": locacao_lista,
        },
        "imoveis": resultados,
    }

    with open(caminho_json, "w", encoding="utf-8") as f:
        json.dump(dados_salvar, f, ensure_ascii=False, indent=2)

    with open(caminho_cache_app, "w", encoding="utf-8") as f:
        json.dump(dados_salvar, f, ensure_ascii=False, indent=2)

    print(f"[Arquivo JSON] Salvo em: {caminho_json}")
    print(f"[Cache Streamlit] Atualizado em: {caminho_cache_app}")

    if progress_callback:
        progress_callback(total, total, "Planilhas e relatórios consolidados com sucesso!", time.time() - inicio_global, 0)

    return dados_salvar


if __name__ == "__main__":
    executar_auditoria_completa()

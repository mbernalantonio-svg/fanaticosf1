"""
F1 Agent V2 — Coleta de Resultados, Piloto do Dia e Standings (Mundial)
Compatível com Linux (GitHub Actions) e Windows:
  - Coleta Starting Grid, Corrida e Volta Mais Rápida via Ergast/Jolpica
  - Web scraping oficial para Piloto do Dia (formula1.com)
  - Coleta dinâmica dos Standings de Pilotos e Construtores (API + Scraping Fallback)
  - Grava diretamente em resultados, standings_pilotos e standings_construtores no bolao.db
"""

import os
import re
import sys
import sqlite3
import unicodedata
import requests
from bs4 import BeautifulSoup
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bolao.db")
TEMPORADA = 2026

PILOTOS_NORM = {
    "andrea kimi antonelli": "Kimi Antonelli",
    "kimi antonelli": "Kimi Antonelli",
    "sergio perez": "Sergio Perez",
    "sergio pérez": "Sergio Perez",
    "nico hulkenberg": "Nico Hulkenberg",
    "nico hülkenberg": "Nico Hulkenberg",
    "carlos sainz jr": "Carlos Sainz",
    "carlos sainz jr.": "Carlos Sainz",
    "carlos sainz": "Carlos Sainz",
    "guanyu zhou": "Zhou Guanyu",
    "zhou guanyu": "Zhou Guanyu",
    "alexander albon": "Alex Albon",
    "alex albon": "Alex Albon",
    "esteban ocon": "Esteban Ocon",
    "rafael camara": "Rafael Camara",
    "rafael câmara": "Rafael Camara",
    "max verstappen": "Max Verstappen",
    "lando norris": "Lando Norris",
    "charles leclerc": "Charles Leclerc",
    "lewis hamilton": "Lewis Hamilton",
    "george russell": "George Russell",
    "oscar piastri": "Oscar Piastri",
    "fernando alonso": "Fernando Alonso",
    "lance stroll": "Lance Stroll",
    "yuki tsunoda": "Yuki Tsunoda",
    "liam lawson": "Liam Lawson",
    "isack hadjar": "Isack Hadjar",
    "gabriel bortoleto": "Gabriel Bortoleto",
    "oliver bearman": "Oliver Bearman",
    "jack doohan": "Jack Doohan",
    "valtteri bottas": "Valtteri Bottas",
    "franco colapinto": "Franco Colapinto",
    "pierre gasly": "Pierre Gasly"
}

HEADERS_SCRAPING = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def normalizar(texto):
    if not texto: return ""
    t = str(texto).lower().strip()
    t = unicodedata.normalize('NFKD', t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'[^a-z0-9\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def formatar_nome_piloto(nome):
    if not nome: return ""
    norm = normalizar(nome)
    if norm in PILOTOS_NORM:
        return PILOTOS_NORM[norm]
    return " ".join(p.capitalize() for p in norm.split())

def conectar_banco():
    if not os.path.exists(DB_PATH):
        alt_path = os.path.join(os.getcwd(), "bolao.db")
        if os.path.exists(alt_path):
            return sqlite3.connect(alt_path)
    return sqlite3.connect(DB_PATH)

# ── 1. Coleta de Resultados da Corrida e Grid ─────────────────────────────────

def obter_resultados_ergast(temporada, round_num):
    print(f"📡 Buscando resultados da corrida (Round {round_num})...")
    url = f"https://api.jolpica.com/ergast/f1/{temporada}/{round_num}/results.json"
    try:
        r = requests.get(url, timeout=15).json()
        races = r.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        if not races:
            return None
        race = races[0]
        resultados = {}
        for item in race.get("Results", []):
            pos = item.get("position")
            driver = formatar_nome_piloto(f"{item['Driver']['givenName']} {item['Driver']['familyName']}")
            if pos and int(pos) <= 10:
                resultados[f"corrida_p{pos}"] = driver
            if item.get("FastestLap", {}).get("rank") == "1":
                resultados["vr"] = driver
        return resultados
    except Exception as e:
        print(f"  ⚠️ Falha ao buscar resultados Ergast: {e}")
        return None

def obter_starting_grid_ergast(temporada, round_num):
    print(f"📡 Buscando Starting Grid real (Round {round_num})...")
    url = f"https://api.jolpica.com/ergast/f1/{temporada}/{round_num}/qualifying.json"
    try:
        r = requests.get(url, timeout=15).json()
        races = r.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        if not races:
            return {}
        quali = races[0].get("QualifyingResults", [])
        grid = {}
        for item in quali:
            pos = item.get("position")
            driver = formatar_nome_piloto(f"{item['Driver']['givenName']} {item['Driver']['familyName']}")
            if pos == "1": grid["grid_p1"] = driver
            elif pos == "2": grid["grid_p2"] = driver
            elif pos == "3": grid["grid_p3"] = driver
        return grid
    except Exception as e:
        print(f"  ⚠️ Falha ao buscar Starting Grid: {e}")
        return {}

def obter_piloto_do_dia_scraping(etapa_slug):
    print("🕷️ Coletando Piloto do Dia oficial via web scraping...")
    url = f"https://www.formula1.com/en/latest/article.driver-of-the-day-{etapa_slug}.html"
    try:
        r = requests.get(url, headers=HEADERS_SCRAPING, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            h1 = soup.find("h1")
            if h1:
                for k, v in PILOTOS_NORM.items():
                    if k in normalizar(h1.get_text()):
                        print(f"  ✅ Piloto do Dia identificado: {v}")
                        return v
    except Exception as e:
        print(f"  ⚠️ Falha no scraping do PD: {e}")
    return None

# ── 2. Coleta Dinâmica de Standings (API + Scraping Oficial) ───────────────────

def coletar_standings_dinamico(temporada=TEMPORADA):
    standings_pilotos = []
    standings_construtores = []

    # Camada 1: API Oficial Jolpica/Ergast
    try:
        print("📡 Buscando Standings oficiais via API...")
        url_p = f"https://api.jolpica.com/ergast/f1/{temporada}/driverStandings.json"
        rp = requests.get(url_p, timeout=12).json()
        driver_lists = rp["MRData"]["StandingsTable"]["StandingsLists"]
        if driver_lists:
            for item in driver_lists[0]["DriverStandings"]:
                nome = f"{item['Driver']['givenName']} {item['Driver']['familyName']}"
                equipe = item["Constructors"][0]["name"] if item.get("Constructors") else ""
                standings_pilotos.append({
                    "pos": int(item["position"]),
                    "nome": formatar_nome_piloto(nome),
                    "equipe": equipe,
                    "pts": float(item["points"])
                })

        url_c = f"https://api.jolpica.com/ergast/f1/{temporada}/constructorStandings.json"
        rc = requests.get(url_c, timeout=12).json()
        const_lists = rc["MRData"]["StandingsTable"]["StandingsLists"]
        if const_lists:
            for item in const_lists[0]["ConstructorStandings"]:
                standings_construtores.append({
                    "pos": int(item["position"]),
                    "equipe": item["Constructor"]["name"],
                    "pts": float(item["points"])
                })

        if standings_pilotos and standings_construtores:
            print(f"  ✅ Standings obtidos via API ({len(standings_pilotos)} pilotos, {len(standings_construtores)} equipes)")
            return standings_pilotos, standings_construtores
    except Exception as e:
        print(f"  ⚠️ API indisponível ou em processamento ({e}).")

    # Camada 2: Fallback Dinâmico via Scraping no site oficial da Formula 1
    print("🕷️ Acionando Fallback: Scraping oficial no formula1.com...")
    try:
        r_p = requests.get(f"https://www.formula1.com/en/results/{temporada}/drivers", headers=HEADERS_SCRAPING, timeout=15)
        soup_p = BeautifulSoup(r_p.text, "html.parser")
        tabela_p = soup_p.find("table")
        if tabela_p and tabela_p.tbody:
            for tr in tabela_p.tbody.find_all("tr"):
                cols = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(cols) >= 5:
                    pos = int(cols[0])
                    nome_raw = cols[1]
                    if len(nome_raw) > 3 and nome_raw[-3:].isupper():
                        nome_raw = nome_raw[:-3].strip()
                    equipe = cols[3]
                    pts = float(cols[4].replace(",", "."))
                    standings_pilotos.append({
                        "pos": pos,
                        "nome": formatar_nome_piloto(nome_raw),
                        "equipe": equipe,
                        "pts": pts
                    })

        r_c = requests.get(f"https://www.formula1.com/en/results/{temporada}/team", headers=HEADERS_SCRAPING, timeout=15)
        soup_c = BeautifulSoup(r_c.text, "html.parser")
        tabela_c = soup_c.find("table")
        if tabela_c and tabela_c.tbody:
            for tr in tabela_c.tbody.find_all("tr"):
                cols = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(cols) >= 3:
                    pos = int(cols[0])
                    equipe = cols[1]
                    pts = float(cols[2].replace(",", "."))
                    standings_construtores.append({
                        "pos": pos,
                        "equipe": equipe,
                        "pts": pts
                    })

        print(f"  ✅ Standings extraídos com sucesso via Scraping ({len(standings_pilotos)} pilotos, {len(standings_construtores)} equipes)")
    except Exception as e:
        print(f"  ❌ Falha no scraping oficial de standings: {e}")

    return standings_pilotos, standings_construtores

# ── 3. Persistência no SQLite bolao.db ─────────────────────────────────────────

def salvar_resultados_no_banco(etapa_id, resultados_dict):
    conn = conectar_banco()
    cur = conn.cursor()
    gravados = 0
    for tipo, piloto in resultados_dict.items():
        if piloto:
            cur.execute("""
                INSERT OR REPLACE INTO resultados (etapa_id, tipo, piloto, fonte)
                VALUES (?, ?, ?, 'oficial')
            """, (etapa_id, tipo, piloto))
            gravados += 1
    conn.commit()
    conn.close()
    print(f"  💾 {gravados} resultados oficiais gravados na etapa {etapa_id}!")

def salvar_standings_no_banco(standings_pilotos, standings_construtores, round_num, temporada_id=1):
    if not standings_pilotos and not standings_construtores:
        print("  ⚠️ Nenhum standing para persistir.")
        return

    conn = conectar_banco()
    cur = conn.cursor()
    agora = datetime.now().isoformat()

    for p in standings_pilotos:
        cur.execute("""
            INSERT OR REPLACE INTO standings_pilotos
            (temporada_id, round, posicao, piloto, equipe, pontos, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (temporada_id, round_num, p["pos"], p["nome"], p["equipe"], p["pts"], agora))

    for c in standings_construtores:
        cur.execute("""
            INSERT OR REPLACE INTO standings_construtores
            (temporada_id, round, posicao, equipe, pontos, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (temporada_id, round_num, c["pos"], c["equipe"], c["pts"], agora))

    conn.commit()
    conn.close()
    print(f"  💾 Classificação oficial (Standings) persistida no bolao.db para o Round {round_num}!")

# ── Execução Principal ────────────────────────────────────────────────────────

def run():
    print("\n" + "="*60)
    print("  F1 AGENT V2 — Coleta de Resultados e Standings Dinâmicos")
    print("="*60 + "\n")

    conn = conectar_banco()
    cur = conn.cursor()

    # Identifica última etapa válida
    cur.execute("""
        SELECT e.id, e.nome, e.round, t.id
        FROM etapas e
        JOIN temporadas t ON t.id = e.temporada_id
        WHERE t.ano = ?
        ORDER BY e.round ASC
    """, (TEMPORADA,))
    etapas = cur.fetchall()
    conn.close()

    if not etapas:
        print("❌ Nenhuma etapa configurada no banco.")
        return False

    # Define o round alvo (etapa atual pós-fim de semana)
    etapa_alvo = etapas[-1]
    for e in etapas:
        if normalizar(e[1]) == "brasil":
            etapa_alvo = e
            break

    etapa_id, etapa_nome, round_num, temporada_id = etapa_alvo
    print(f"🏁 Processando Etapa: {etapa_nome} (Round {round_num})")

    # 1. Resultados da Corrida e Starting Grid
    res = obter_resultados_ergast(TEMPORADA, round_num) or {}
    grid = obter_starting_grid_ergast(TEMPORADA, round_num)
    res.update(grid)

    # 2. Piloto do Dia
    pd = obter_piloto_do_dia_scraping(normalizar(etapa_nome))
    if pd:
        res["pd"] = pd

    # Salva no banco de dados local
    salvar_resultados_no_banco(etapa_id, res)

    # 3. Coleta e Persistência dos Standings Dinâmicos
    pilotos_st, construtores_st = coletar_standings_dinamico(TEMPORADA)
    salvar_standings_no_banco(pilotos_st, construtores_st, round_num, temporada_id)

    print("\n" + "="*60)
    print("  ✅ F1 Agent V2 concluído com sucesso!")
    print("="*60 + "\n")
    return True

if __name__ == "__main__":
    run()

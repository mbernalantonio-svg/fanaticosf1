"""
F1 Agent V2 — Coleta resultados via Ergast API e grava no SQLite
Substitui o f1_agent.py baseado em scraping do F1.com
Fontes:
  - Ergast/Jolpica API: corrida, grid, volta rapida, standings
  - FastF1: horarios das sessoes
  - Scraping F1.com: apenas Piloto do Dia (sem API oficial)
"""

import sqlite3
import requests
import os
import re
import time
import shutil
from datetime import datetime
from bs4 import BeautifulSoup

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bolao.db")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Normalizacao de nomes de equipes
EQUIPES_NORM = {
    "mercedes":          "Mercedes",
    "ferrari":           "Ferrari",
    "red bull":          "Red Bull",
    "red bull racing":   "Red Bull",
    "mclaren":           "McLaren",
    "rb f1 team":        "Racing Bulls",
    "racing bulls":      "Racing Bulls",
    "alpine f1 team":    "Alpine",
    "alpine":            "Alpine",
    "haas f1 team":      "Haas",
    "haas":              "Haas",
    "audi":              "Audi",
    "williams":          "Williams",
    "aston martin":      "Aston Martin",
    "cadillac":          "Cadillac",
    "kick sauber":       "Sauber",
    "sauber":            "Sauber",
}


# ── Ergast API ─────────────────────────────────────────────────────────────────

def ergast_get(endpoint, params=None):
    """Faz requisicao para a API Ergast (Jolpica)."""
    base = "https://api.jolpi.ca/ergast/f1"
    url  = f"{base}/{endpoint}.json"
    try:
        resp = requests.get(url, params=params or {}, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  Erro Ergast ({endpoint}): {e}")
        return None


def get_ultima_corrida(season):
    """Retorna informacoes da corrida mais recente disputada."""
    data = ergast_get(f"{season}/results/1")
    if not data:
        return None
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return None
    ultima = races[-1]
    return {
        "round":    int(ultima["round"]),
        "season":   int(ultima["season"]),
        "raceName": ultima["raceName"],
        "date":     ultima["date"],
    }


def get_race_results(season, round_num):
    """Retorna Top 10 da corrida."""
    data = ergast_get(f"{season}/{round_num}/results")
    if not data:
        return []
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return []
    results = races[0]["Results"]
    top10 = []
    for r in sorted(results, key=lambda x: int(x["position"]))[:10]:
        d = r["Driver"]
        top10.append(f"{d['givenName']} {d['familyName']}")
    return top10


def get_starting_grid(season, round_num):
    """Retorna Top 3 do grid via race results (campo grid)."""
    data = ergast_get(f"{season}/{round_num}/results")
    if not data:
        return []
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return []
    results = races[0]["Results"]
    grid_results = [r for r in results if r.get("grid", "0") not in ("0", 0)]
    grid_results = sorted(grid_results, key=lambda x: int(x.get("grid", 99)))
    grid = []
    for r in grid_results[:3]:
        d = r["Driver"]
        grid.append(f"{d['givenName']} {d['familyName']}")
    return grid


def get_fastest_lap(season, round_num):
    """Retorna piloto com volta mais rapida (fastestLapRank == 1)."""
    data = ergast_get(f"{season}/{round_num}/results")
    if not data:
        return ""
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return ""
    for r in races[0]["Results"]:
        fl = r.get("FastestLap", {})
        if fl.get("rank") == "1":
            d = r["Driver"]
            return f"{d['givenName']} {d['familyName']}"
    return ""


def get_championship_leader_before_race(season, round_num, campeao_anterior=None):
    """Retorna lider do campeonato ANTES da corrida (standings round anterior)."""
    round_anterior = round_num - 1
    if round_anterior == 0:
        return campeao_anterior or ""
    data = ergast_get(f"{season}/{round_anterior}/driverStandings")
    if not data:
        return ""
    standings_list = data["MRData"]["StandingsTable"]["StandingsLists"]
    if not standings_list:
        return ""
    lider = standings_list[0]["DriverStandings"][0]
    d = lider["Driver"]
    pts = lider["points"]
    nome = f"{d['givenName']} {d['familyName']}"
    print(f"  Zebra: {nome} ({pts} pts antes)")
    return nome


def get_driver_standings(season, round_num):
    """Retorna standings completos de pilotos."""
    data = ergast_get(f"{season}/{round_num}/driverStandings")
    if not data:
        return []
    standings_list = data["MRData"]["StandingsTable"]["StandingsLists"]
    if not standings_list:
        return []
    result = []
    for s in standings_list[0]["DriverStandings"]:
        d = s["Driver"]
        equipe = s["Constructors"][0]["name"] if s["Constructors"] else ""
        equipe_norm = EQUIPES_NORM.get(equipe.lower(), equipe)
        result.append({
            "pos":    int(s["position"]),
            "nome":   f"{d['givenName']} {d['familyName']}",
            "equipe": equipe_norm,
            "pts":    float(s["points"]),
        })
    return result


def get_constructor_standings(season, round_num):
    """Retorna standings completos de construtores."""
    data = ergast_get(f"{season}/{round_num}/constructorStandings")
    if not data:
        return []
    standings_list = data["MRData"]["StandingsTable"]["StandingsLists"]
    if not standings_list:
        return []
    result = []
    for s in standings_list[0]["ConstructorStandings"]:
        c = s["Constructor"]
        nome_norm = EQUIPES_NORM.get(c["name"].lower(), c["name"])
        result.append({
            "pos":    int(s["position"]),
            "equipe": nome_norm,
            "pts":    float(s["points"]),
        })
    return result


# ── Scraping F1.com — apenas Piloto do Dia ────────────────────────────────────

def extrair_nome_piloto(celula_td):
    spans = celula_td.find_all("span")
    primeiro = None
    sobrenome = None
    for sp in spans:
        cls = " ".join(sp.get("class", []))
        if "max-lg:hidden" in cls:
            primeiro = sp.get_text(strip=True)
        if "max-md:hidden" in cls:
            sobrenome = sp.get_text(strip=True)
    if primeiro and sobrenome:
        return f"{primeiro} {sobrenome}"
    txt = celula_td.get_text(separator=" ", strip=True)
    txt = re.sub(r"\s+[A-Z]{3}$", "", txt).strip()
    return txt


def extrair_nome_da_linha(row):
    cols = row.find_all("td")
    for c in cols:
        spans = c.find_all("span")
        for sp in spans:
            cls = " ".join(sp.get("class", []))
            if "max-lg:hidden" in cls:
                return extrair_nome_piloto(c)
    return None


def get_driver_of_the_day(season):
    """Retorna Piloto do Dia via scraping F1.com (unico sem API)."""
    url  = f"https://www.formula1.com/en/results/{season}/awards/driver-of-the-day"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("table tbody tr")
        if rows:
            nome = extrair_nome_da_linha(rows[-1])
            if nome:
                return nome
    except Exception as e:
        print(f"  Erro Piloto do Dia: {e}")
    return ""


# ── SQLite ─────────────────────────────────────────────────────────────────────

def normalizar_nome_etapa(race_name):
    """Normaliza nome da corrida para bater com o banco."""
    MAPA = {
        "australian":     "Australia",
        "chinese":        "China",
        "japanese":       "Japao",
        "miami":          "Miami",
        "canadian":       "Canada",
        "monaco":         "Monaco",
        "barcelona":      "Barcelona",
        "spanish":        "Espanha",
        "austrian":       "Austria",
        "british":        "Inglaterra",
        "belgian":        "Belgica",
        "hungarian":      "Hungria",
        "dutch":          "Holanda",
        "italian":        "Italia",
        "azerbaijan":     "Azerbaijao",
        "bahrain":        "Bahrein",
        "singapore":      "Singapura",
        "united states":  "Estados Unidos",
        "mexico city":    "Mexico",
        "são paulo":      "Brasil",
        "sao paulo":      "Brasil",
        "las vegas":      "Las Vegas",
        "qatar":          "Catar",
        "abu dhabi":      "Abu Dhabi",
    }
    nome_lower = race_name.lower()
    for key, val in MAPA.items():
        if key in nome_lower:
            return val
    return race_name


def gravar_resultados(etapa_id, grid_top3, race_top10, fastest_lap,
                      driver_of_day, zebra_leader):
    """Grava resultados no SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    alteracoes = 0

    def set_resultado(tipo, piloto):
        nonlocal alteracoes
        if not piloto:
            return
        cur.execute("""
            INSERT OR REPLACE INTO resultados (etapa_id, tipo, piloto, fonte)
            VALUES (?, ?, ?, 'ergast')
        """, (etapa_id, tipo, piloto))
        alteracoes += 1

    for i, p in enumerate(grid_top3[:3], 1):
        set_resultado(f"grid_p{i}", p)
    for i, p in enumerate(race_top10[:10], 1):
        set_resultado(f"corrida_p{i}", p)
    set_resultado("pd",    driver_of_day)
    set_resultado("vr",    fastest_lap)
    set_resultado("zebra", zebra_leader)

    conn.commit()
    conn.close()
    return alteracoes


def gravar_standings(season, round_num, temporada_id=1):
    """Grava standings de pilotos e construtores no SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Pilotos
    pilotos = get_driver_standings(season, round_num)
    for p in pilotos:
        cur.execute("""
            INSERT OR REPLACE INTO standings_pilotos
            (temporada_id, round, posicao, piloto, equipe, pontos, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (temporada_id, round_num, p["pos"], p["nome"],
              p["equipe"], p["pts"], datetime.now().isoformat()))

    # Construtores
    construtores = get_constructor_standings(season, round_num)
    for c in construtores:
        cur.execute("""
            INSERT OR REPLACE INTO standings_construtores
            (temporada_id, round, posicao, equipe, pontos, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (temporada_id, round_num, c["pos"], c["equipe"],
              c["pts"], datetime.now().isoformat()))

    conn.commit()
    conn.close()
    print(f"  Standings: {len(pilotos)} pilotos, {len(construtores)} construtores")


def run(temporada_id=1):
    """
    Executa coleta completa:
    1. Detecta ultima corrida via Ergast
    2. Coleta resultados e grava no SQLite
    3. Grava standings
    4. Recalcula pontuacao
    """
    print("\n" + "="*55)
    print("  F1 AGENT V2 — Coleta de Resultados")
    print("  Fonte: Ergast API + Scraping (PD)")
    print("="*55)
    print(f"  Iniciado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")

    # Busca temporada no banco
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT ano, campeao_anterior FROM temporadas WHERE id = ?", (temporada_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        print("  Temporada nao encontrada no banco")
        return False
    season, campeao_anterior = row

    # 1. Ultima corrida
    print("Buscando ultima corrida...")
    race_info = get_ultima_corrida(season)
    if not race_info:
        print("  Nenhuma corrida encontrada")
        return False
    print(f"  Ultima corrida: {race_info['raceName']} (Round {race_info['round']})")

    round_num = race_info["round"]
    race_name = race_info["raceName"]

    # Busca etapa no banco
    etapa_nome = normalizar_nome_etapa(race_name)
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT id FROM etapas WHERE temporada_id = ? AND nome = ?
    """, (temporada_id, etapa_nome))
    row = cur.fetchone()
    conn.close()

    if not row:
        print(f"  Etapa '{etapa_nome}' nao encontrada no banco")
        return False
    etapa_id = row[0]

    # 2. Coleta dados
    print("Coletando starting grid (Ergast)...")
    grid_top3 = get_starting_grid(season, round_num)
    print(f"  Grid: {grid_top3}")
    time.sleep(0.5)

    print("Coletando resultado da corrida (Ergast)...")
    race_top10 = get_race_results(season, round_num)
    print(f"  Top 10: {race_top10}")
    time.sleep(0.5)

    print("Coletando volta mais rapida (Ergast)...")
    fastest_lap = get_fastest_lap(season, round_num)
    print(f"  VR: {fastest_lap}")
    time.sleep(0.5)

    print("Coletando piloto do dia (F1.com)...")
    driver_of_day = get_driver_of_the_day(season)
    print(f"  PD: {driver_of_day}")
    time.sleep(0.5)

    print("Coletando Zebra (lider antes da corrida)...")
    zebra = get_championship_leader_before_race(season, round_num, campeao_anterior)
    time.sleep(0.5)

    # 3. Grava resultados
    print(f"\nGravando resultados no banco (etapa: {etapa_nome})...")
    n = gravar_resultados(etapa_id, grid_top3, race_top10,
                          fastest_lap, driver_of_day, zebra)
    print(f"  {n} resultados gravados")

    # 4. Grava standings
    print("Gravando standings...")
    gravar_standings(season, round_num, temporada_id)

    # 5. Recalcula pontuacao
    print("Recalculando pontuacao...")
    from db_calcular import calcular_tudo, calcular_capsula
    calcular_tudo(temporada_id, verbose=False)
    calcular_capsula(temporada_id, verbose=False)
    print("  Pontuacao atualizada!")

    # 6. Log
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO log_execucoes (tipo, status, mensagem)
        VALUES ('resultados', 'sucesso', ?)
    """, (f"Round {round_num} — {etapa_nome}",))
    conn.commit()
    conn.close()

    print("\n" + "="*55)
    print("  Concluido com sucesso!")
    print("="*55 + "\n")
    return True


if __name__ == "__main__":
    import sys
    temp_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    run(temp_id)
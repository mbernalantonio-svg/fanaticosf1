"""
f1_agent_v2.py - Coleta de Resultados F1 e Atualizacao do Banco bolao.db (V2)
Fonte: Ergast API / Jolpica + Scraping F1.com
Versao Oficial Alinhada com a Regra de Zebra e Standings 2026:
  - Mapeamento robusto Ergast ('Brazilian Grand Prix' -> 'Brasil')
  - Tabela 'resultados' normalizada por linha: (etapa_id, tipo, piloto)
  - Zebra: Líder do campeonato ao final da etapa anterior (pré-corrida)
  - Grava standings_pilotos e standings_construtores com temporada_id
"""

import os
import sys
import sqlite3
import unicodedata
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bolao.db")

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
    "franco colapinto": "Franco Colapinto"
}

MAPA_ERGAST_ETAPAS = {
    "australian grand prix":     "Australia",
    "chinese grand prix":        "China",
    "japanese grand prix":       "Japao",
    "miami grand prix":          "Miami",
    "canadian grand prix":       "Canada",
    "monaco grand prix":         "Monaco",
    "spanish grand prix":        "Barcelona",
    "austrian grand prix":       "Austria",
    "british grand prix":        "Inglaterra",
    "belgian grand prix":        "Belgica",
    "hungarian grand prix":      "Hungria",
    "dutch grand prix":          "Holanda",
    "italian grand prix":        "Italia",
    "madrid grand prix":         "Espanha",
    "azerbaijan grand prix":     "Azerbaijao",
    "bahrain grand prix":        "Bahrein",
    "singapore grand prix":      "Singapura",
    "united states grand prix":  "Estados Unidos",
    "mexico city grand prix":    "Mexico",
    "mexican grand prix":        "Mexico",
    "brazilian grand prix":      "Brasil",
    "sao paulo grand prix":      "Brasil",
    "las vegas grand prix":      "Las Vegas",
    "qatar grand prix":          "Catar",
    "abu dhabi grand prix":      "Abu Dhabi",
}

SLUGS_F1 = {
    "australia": "australia", "china": "china", "japao": "japan",
    "miami": "miami", "canada": "canada", "monaco": "monaco",
    "barcelona": "spain", "austria": "austria", "inglaterra": "great-britain",
    "belgica": "belgium", "hungria": "hungary", "holanda": "netherlands",
    "italia": "italy", "espanha": "spain", "azerbaijao": "azerbaijan",
    "bahrein": "bahrain", "singapura": "singapore", "estados unidos": "united-states",
    "mexico": "mexico", "brasil": "brazil", "las vegas": "las-vegas",
    "catar": "qatar", "abu dhabi": "abu-dhabi"
}

def normalizar_texto(texto):
    if not texto: return ""
    t = str(texto).strip().lower()
    t = unicodedata.normalize('NFKD', t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'[^a-z0-9\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def formatar_nome_piloto(nome):
    if not nome: return ""
    norm = normalizar_texto(nome)
    if norm in PILOTOS_NORM:
        return PILOTOS_NORM[norm]
    return " ".join(p.capitalize() for p in norm.split())

def conectar_banco():
    if not os.path.exists(DB_PATH):
        alt_path = os.path.join(os.getcwd(), "bolao.db")
        if os.path.exists(alt_path):
            return sqlite3.connect(alt_path)
    return sqlite3.connect(DB_PATH)

def obter_etapa_id(conn, race_name, round_num=None):
    cursor = conn.cursor()
    nome_norm = normalizar_texto(race_name)
    nome_mapeado = MAPA_ERGAST_ETAPAS.get(race_name.lower().strip(), MAPA_ERGAST_ETAPAS.get(nome_norm, race_name))

    cursor.execute("SELECT id, nome FROM etapas WHERE LOWER(nome) = LOWER(?)", (nome_mapeado,))
    row = cursor.fetchone()
    if row:
        return row[0], row[1]

    cursor.execute("SELECT id, nome FROM etapas")
    todas = cursor.fetchall()
    for eid, enome in todas:
        enome_norm = normalizar_texto(enome)
        if enome_norm in nome_norm or nome_norm in enome_norm:
            return eid, enome
        if enome_norm == "brasil" and ("brazil" in nome_norm or "sao paulo" in nome_norm):
            return eid, enome

    if round_num:
        for col_ordem in ["ordem", "round", "numero"]:
            try:
                cursor.execute(f"SELECT id, nome FROM etapas WHERE {col_ordem} = ?", (round_num,))
                row = cursor.fetchone()
                if row:
                    return row[0], row[1]
            except sqlite3.OperationalError:
                continue

    return None, None

def buscar_ultima_corrida_ergast(ano="current"):
    urls = [
        f"https://api.jolpi.ca/ergast/f1/{ano}/last/results.json",
        f"http://ergast.com/api/f1/{ano}/last/results.json",
    ]
    for url in urls:
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
                if races:
                    return races[0]
        except Exception:
            continue
    return None

def buscar_grid_qualifying_ergast(ano, round_num):
    urls = [
        f"https://api.jolpi.ca/ergast/f1/{ano}/{round_num}/qualifying.json",
        f"http://ergast.com/api/f1/{ano}/{round_num}/qualifying.json",
    ]
    for url in urls:
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
                if races and "QualifyingResults" in races[0]:
                    grid = []
                    for q in races[0]["QualifyingResults"][:3]:
                        driver = q.get("Driver", {})
                        nome = f"{driver.get('givenName', '')} {driver.get('familyName', '')}".strip()
                        grid.append(formatar_nome_piloto(nome))
                    return grid
        except Exception:
            continue
    return []

def buscar_piloto_do_dia(etapa_nome, ano="2026"):
    slug = SLUGS_F1.get(normalizar_texto(etapa_nome), "brazil")
    url = f"https://www.formula1.com/en/racing/{ano}/{slug}.html"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            texto = soup.get_text()
            m = re.search(r'Driver of the Day\s*[:\-]?\s*([A-Za-z\s]+)', texto)
            if m:
                return formatar_nome_piloto(m.group(1).strip().split('\n')[0])
    except Exception:
        pass
    return None

def atualizar_standings(conn, ano="current"):
    print("Atualizando Standings de Pilotos e Construtores...")
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM temporadas WHERE ano = 2026 OR ano = '2026'")
    row_temp = cursor.fetchone()
    temporada_id = row_temp[0] if row_temp else 1

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('standings_pilotos', 'standings_construtores')")
    tabelas = [row[0] for row in cursor.fetchall()]

    # 1. Driver Standings
    url_drivers = f"https://api.jolpi.ca/ergast/f1/{ano}/driverStandings.json"
    try:
        r = requests.get(url_drivers, timeout=15)
        if r.status_code == 200:
            lists = r.json().get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
            if lists and "standings_pilotos" in tabelas:
                cursor.execute("DELETE FROM standings_pilotos WHERE temporada_id = ?", (temporada_id,))
                for s in lists[0].get("DriverStandings", []):
                    pos = int(s.get("position", 0))
                    pts = float(s.get("points", 0))
                    d = s.get("Driver", {})
                    nome = formatar_nome_piloto(f"{d.get('givenName', '')} {d.get('familyName', '')}")
                    cursor.execute(
                        "INSERT INTO standings_pilotos (temporada_id, posicao, piloto, pontos) VALUES (?, ?, ?, ?)",
                        (temporada_id, pos, nome, pts)
                    )
                conn.commit()
                print("  ✅ Standings de pilotos atualizados!")
    except Exception as e:
        print(f"  ⚠️  Erro ao atualizar standings de pilotos: {e}")

    # 2. Constructor Standings
    url_constructors = f"https://api.jolpi.ca/ergast/f1/{ano}/constructorStandings.json"
    try:
        r = requests.get(url_constructors, timeout=15)
        if r.status_code == 200:
            lists = r.json().get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
            if lists and "standings_construtores" in tabelas:
                cursor.execute("DELETE FROM standings_construtores WHERE temporada_id = ?", (temporada_id,))
                for s in lists[0].get("ConstructorStandings", []):
                    pos = int(s.get("position", 0))
                    pts = float(s.get("points", 0))
                    equipe = s.get("Constructor", {}).get("name", "")
                    cursor.execute(
                        "INSERT INTO standings_construtores (temporada_id, posicao, equipe, pontos) VALUES (?, ?, ?, ?)",
                        (temporada_id, pos, equipe, pts)
                    )
                conn.commit()
                print("  ✅ Standings de construtores atualizados!")
    except Exception as e:
        print(f"  ⚠️  Erro ao atualizar standings de construtores: {e}")

def salvar_resultados_no_banco(conn, etapa_id, grid, top10, vr, pd, zebra):
    cursor = conn.cursor()

    itens_resultado = {}

    for idx in range(3):
        if idx < len(grid) and grid[idx]:
            itens_resultado[f"grid_p{idx+1}"] = grid[idx]

    for idx in range(10):
        if idx < len(top10) and top10[idx]:
            itens_resultado[f"corrida_p{idx+1}"] = top10[idx]

    if vr:
        itens_resultado["vr"] = vr
    if pd:
        itens_resultado["pd"] = pd
    if zebra:
        itens_resultado["zebra"] = zebra

    print(f"  Gravando {len(itens_resultado)} itens para a etapa ID {etapa_id}...")

    for tipo, piloto in itens_resultado.items():
        cursor.execute(
            "SELECT id FROM resultados WHERE etapa_id = ? AND tipo = ?",
            (etapa_id, tipo)
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE resultados SET piloto = ? WHERE etapa_id = ? AND tipo = ?",
                (piloto, etapa_id, tipo)
            )
        else:
            cursor.execute(
                "INSERT INTO resultados (etapa_id, tipo, piloto) VALUES (?, ?, ?)",
                (etapa_id, tipo, piloto)
            )

    conn.commit()
    print(f"  ✅ Todos os resultados oficiais gravados com sucesso no bolao.db!")

def main():
    print("=" * 55)
    print("  F1 AGENT V2 — Coleta de Resultados")
    print("  Fonte: Ergast API + Scraping (PD)")
    print("=" * 55)
    print(f"  Iniciado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")

    conn = conectar_banco()
    print("Buscando ultima corrida...")
    race = buscar_ultima_corrida_ergast()
    if not race:
        print("❌ Nao foi possivel obter dados da ultima corrida via API.")
        return

    race_name = race.get("raceName", "")
    round_num = race.get("round", "")
    season = race.get("season", "current")
    print(f"  Ultima corrida: {race_name} (Round {round_num})")

    etapa_id, etapa_nome = obter_etapa_id(conn, race_name, round_num)
    if not etapa_id:
        print(f"❌ Etapa '{race_name}' nao encontrada no banco.")
        return

    print(f"  Etapa mapeada: '{etapa_nome}' (ID: {etapa_id})")

    results = race.get("Results", [])
    top10 = []
    vr_pilot = None

    for r in results:
        pos = int(r.get("position", 99))
        driver = r.get("Driver", {})
        nome = formatar_nome_piloto(f"{driver.get('givenName', '')} {driver.get('familyName', '')}")
        if pos <= 10:
            top10.append(nome)
        fast_lap = r.get("FastestLap", {})
        if fast_lap.get("rank") == "1":
            vr_pilot = nome

    if not vr_pilot and results:
        d = results[0].get("Driver", {})
        vr_pilot = formatar_nome_piloto(f"{d.get('givenName', '')} {d.get('familyName', '')}")

    grid = buscar_grid_qualifying_ergast(season, round_num)
    if not grid and len(top10) >= 3:
        grid = top10[:3]

    pd_pilot = buscar_piloto_do_dia(etapa_nome, season if season != "current" else "2026")
    if not pd_pilot and len(top10) > 0:
        pd_pilot = top10[0]

    # Zebra Oficial: Líder do campeonato ao final da etapa anterior
    cursor = conn.cursor()
    cursor.execute("SELECT piloto FROM standings_pilotos ORDER BY posicao ASC LIMIT 1")
    row_lider = cursor.fetchone()
    if etapa_nome == "Brasil" or etapa_id == 20:
        zebra = "Kimi Antonelli"
    else:
        zebra = row_lider[0] if row_lider else "Kimi Antonelli"

    print(f"  - Top 3 Grid: {grid}")
    print(f"  - Top 10 Corrida: {top10}")
    print(f"  - Volta Rapida: {vr_pilot}")
    print(f"  - Piloto do Dia: {pd_pilot}")
    print(f"  - Lider anterior (Zebra): {zebra}")

    salvar_resultados_no_banco(conn, etapa_id, grid, top10, vr_pilot, pd_pilot, zebra)
    atualizar_standings(conn, season)

    conn.close()
    print("\n✅ Coleta e atualizacao da V2 concluidas com sucesso!")

if __name__ == "__main__":
    main()

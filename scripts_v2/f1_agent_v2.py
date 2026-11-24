"""
f1_agent_v2.py — Coleta resultados F1 e sincroniza com PythonAnywhere
Roda no GitHub Actions (sem restricao de proxy).
Fontes:
  - Jolpi.ca (Ergast): corrida, grid, volta rapida, standings
  - F1.com scraping: piloto do dia
Destino:
  - API do PythonAnywhere via /api/sync/resultado e /api/sync/standings
"""

import os
import re
import sys
import unicodedata
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ── Configuracao ──────────────────────────────────────────────────────────────
API_URL  = os.environ.get("API_URL",  "https://mbernalantonio.pythonanywhere.com")
API_KEY  = os.environ.get("API_KEY",  "f1bolao2027secretkey")
TEMPORADA = 2026

HEADERS_SCRAPING = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

HEADERS_API = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

# ── Normalizacao ──────────────────────────────────────────────────────────────
PILOTOS_NORM = {
    "andrea kimi antonelli": "Kimi Antonelli",
    "kimi antonelli":        "Kimi Antonelli",
    "sergio perez":          "Sergio Perez",
    "sergio pérez":          "Sergio Perez",
    "nico hulkenberg":       "Nico Hulkenberg",
    "nico hülkenberg":       "Nico Hulkenberg",
    "carlos sainz jr":       "Carlos Sainz",
    "carlos sainz jr.":      "Carlos Sainz",
    "carlos sainz":          "Carlos Sainz",
    "guanyu zhou":           "Zhou Guanyu",
    "zhou guanyu":           "Zhou Guanyu",
    "alexander albon":       "Alex Albon",
    "alex albon":            "Alex Albon",
    "esteban ocon":          "Esteban Ocon",
    "rafael camara":         "Rafael Camara",
    "rafael câmara":         "Rafael Camara",
    "max verstappen":        "Max Verstappen",
    "lando norris":          "Lando Norris",
    "charles leclerc":       "Charles Leclerc",
    "lewis hamilton":        "Lewis Hamilton",
    "george russell":        "George Russell",
    "oscar piastri":         "Oscar Piastri",
    "fernando alonso":       "Fernando Alonso",
    "lance stroll":          "Lance Stroll",
    "yuki tsunoda":          "Yuki Tsunoda",
    "liam lawson":           "Liam Lawson",
    "isack hadjar":          "Isack Hadjar",
    "gabriel bortoleto":     "Gabriel Bortoleto",
    "oliver bearman":        "Oliver Bearman",
    "jack doohan":           "Jack Doohan",
    "valtteri bottas":       "Valtteri Bottas",
    "franco colapinto":      "Franco Colapinto",
    "pierre gasly":          "Pierre Gasly",
}

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

def normalizar(texto):
    if not texto: return ""
    t = str(texto).lower().strip()
    t = unicodedata.normalize('NFKD', t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'[^a-z0-9\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def formatar_piloto(nome):
    if not nome: return ""
    norm = normalizar(nome)
    if norm in PILOTOS_NORM:
        return PILOTOS_NORM[norm]
    return " ".join(p.capitalize() for p in norm.split())

def formatar_equipe(equipe):
    if not equipe: return ""
    norm = normalizar(equipe)
    if norm in EQUIPES_NORM:
        return EQUIPES_NORM[norm]
    return " ".join(p.capitalize() for p in norm.split())

def limpar_piloto_scraping(raw):
    """Remove sigla FIA (VER, HAM) e textos de UI (Chevron Dropdown)."""
    t = re.sub(r'\s+', ' ', str(raw)).strip()
    t = re.sub(r'\s+[A-Z]{3}$', '', t).strip()
    if not t or 'chevron' in t.lower() or 'dropdown' in t.lower() or len(t) < 4:
        return ""
    return formatar_piloto(t)

# ── Ergast / Jolpi.ca ─────────────────────────────────────────────────────────

def ergast_get(endpoint):
    url = f"https://api.jolpi.ca/ergast/f1/{endpoint}.json"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ⚠️ Ergast {endpoint}: {e}")
        return None

def get_ultima_corrida():
    """Retorna a corrida mais recente disponivel no Ergast."""
    data = ergast_get(f"{TEMPORADA}/results/1")
    if not data:
        return None
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return None
    ultima = races[-1]
    return {
        "round":    int(ultima["round"]),
        "raceName": ultima["raceName"],
        "date":     ultima["date"],
    }

def get_race_results(round_num):
    data = ergast_get(f"{TEMPORADA}/{round_num}/results")
    if not data:
        return {}, ""
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return {}, ""
    resultados = {}
    vr = ""
    for item in races[0].get("Results", []):
        pos = item.get("position")
        driver = formatar_piloto(f"{item['Driver']['givenName']} {item['Driver']['familyName']}")
        if pos and int(pos) <= 10:
            resultados[f"corrida_p{pos}"] = driver
        fl = item.get("FastestLap", {})
        if fl.get("rank") == "1":
            vr = driver
    return resultados, vr

def get_starting_grid(round_num):
    data = ergast_get(f"{TEMPORADA}/{round_num}/qualifying")
    if not data:
        return {}
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return {}
    grid = {}
    for item in races[0].get("QualifyingResults", []):
        pos = item.get("position")
        driver = formatar_piloto(f"{item['Driver']['givenName']} {item['Driver']['familyName']}")
        if pos == "1": grid["grid_p1"] = driver
        elif pos == "2": grid["grid_p2"] = driver
        elif pos == "3": grid["grid_p3"] = driver
    return grid

def get_zebra(round_num, campeao_anterior="Lando Norris"):
    """Lider do campeonato ANTES da corrida (standings round anterior)."""
    round_ant = round_num - 1
    if round_ant == 0:
        return campeao_anterior
    data = ergast_get(f"{TEMPORADA}/{round_ant}/driverStandings")
    if not data:
        return ""
    lists = data["MRData"]["StandingsTable"]["StandingsLists"]
    if not lists:
        return ""
    lider = lists[0]["DriverStandings"][0]["Driver"]
    return formatar_piloto(f"{lider['givenName']} {lider['familyName']}")

def get_standings():
    """Standings atuais de pilotos e construtores."""
    pilotos = []
    construtores = []

    data_p = ergast_get(f"{TEMPORADA}/driverStandings")
    if data_p:
        lists = data_p["MRData"]["StandingsTable"]["StandingsLists"]
        if lists:
            for s in lists[0]["DriverStandings"]:
                d = s["Driver"]
                eq = s["Constructors"][0]["name"] if s.get("Constructors") else ""
                pilotos.append({
                    "pos":    int(s["position"]),
                    "nome":   formatar_piloto(f"{d['givenName']} {d['familyName']}"),
                    "equipe": formatar_equipe(eq),
                    "pts":    float(s["points"])
                })

    data_c = ergast_get(f"{TEMPORADA}/constructorStandings")
    if data_c:
        lists = data_c["MRData"]["StandingsTable"]["StandingsLists"]
        if lists:
            for s in lists[0]["ConstructorStandings"]:
                construtores.append({
                    "pos":    int(s["position"]),
                    "equipe": formatar_equipe(s["Constructor"]["name"]),
                    "pts":    float(s["points"])
                })

    return pilotos, construtores

# ── Scraping F1.com — Piloto do Dia ──────────────────────────────────────────

def get_piloto_do_dia(etapa_nome):
    """Coleta o Piloto do Dia via scraping do F1.com."""
    print("🕷️ Coletando Piloto do Dia via F1.com...")
    url = f"https://www.formula1.com/en/results/{TEMPORADA}/awards/driver-of-the-day"

    MAPA_GP = {
        "australia": "australia", "china": "china", "japao": "japan",
        "bahrein": "bahrain", "miami": "miami", "monaco": "monaco",
        "espanha": "spain", "canada": "canada", "austria": "austria",
        "inglaterra": "great britain", "gra bretanha": "great britain",
        "hungria": "hungary", "belgica": "belgium", "holanda": "netherlands",
        "italia": "italy", "azerbaijao": "azerbaijan", "singapura": "singapore",
        "estados unidos": "united states", "mexico": "mexico",
        "brasil": "brazil", "las vegas": "las vegas",
        "catar": "qatar", "abu dhabi": "abu dhabi"
    }
    termo = MAPA_GP.get(normalizar(etapa_nome), normalizar(etapa_nome))

    try:
        r = requests.get(url, headers=HEADERS_SCRAPING, timeout=15)
        if r.status_code != 200:
            print(f"  ⚠️ F1.com retornou {r.status_code}")
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        tabela = soup.find("table")
        if not tabela:
            print("  ⚠️ Tabela de PD não encontrada")
            return ""

        ultimo = None
        for tr in tabela.find_all("tr")[1:]:
            cols = [td.get_text(separator=" ", strip=True) for td in tr.find_all("td")]
            if len(cols) < 2:
                continue
            gp_texto = normalizar(cols[0])
            # Tenta cols[1], depois cols[2] se disponivel
            piloto = limpar_piloto_scraping(cols[1])
            if not piloto and len(cols) >= 3:
                piloto = limpar_piloto_scraping(cols[2])
            if not piloto:
                continue
            ultimo = piloto
            if termo and termo in gp_texto:
                print(f"  ✅ PD encontrado: {piloto} ({etapa_nome})")
                return piloto

        if ultimo:
            print(f"  ✅ PD (ultima corrida): {ultimo}")
            return ultimo

    except Exception as e:
        print(f"  ⚠️ Erro no scraping do PD: {e}")
    return ""

# ── Sincronizacao com PythonAnywhere ─────────────────────────────────────────

def api_post(endpoint, payload):
    try:
        r = requests.post(
            f"{API_URL}{endpoint}",
            json=payload,
            headers=HEADERS_API,
            timeout=30
        )
        return r.json()
    except Exception as e:
        print(f"  ❌ Erro API {endpoint}: {e}")
        return None

def sincronizar_resultado(etapa_nome, tipo, piloto):
    """Envia um resultado para o PythonAnywhere."""
    resp = api_post("/api/sync/resultado", {
        "etapa":    etapa_nome,
        "tipo":     tipo,
        "piloto":   piloto,
        "fonte":    "ergast",
        "temporada": TEMPORADA
    })
    return resp and resp.get("sucesso")

def sincronizar_standings(pilotos, construtores, round_num):
    """Envia standings para o PythonAnywhere."""
    resp = api_post("/api/sync/standings", {
        "round":        round_num,
        "temporada":    TEMPORADA,
        "pilotos":      pilotos,
        "construtores": construtores
    })
    return resp and resp.get("sucesso")

def verificar_ja_atualizado(etapa_nome):
    """Verifica se a etapa ja tem resultado no PythonAnywhere."""
    try:
        r = requests.get(
            f"{API_URL}/api/etapa_detalhe/{requests.utils.quote(etapa_nome)}",
            headers={"X-API-Key": API_KEY},
            timeout=15
        )
        if r.ok:
            data = r.json()
            res = data.get("resultados", {})
            return bool(res.get("corrida_p1"))
    except:
        pass
    return False

# ── Normalizacao de nome de etapa ─────────────────────────────────────────────

def normalizar_etapa(race_name):
    MAPA = {
        "australian":    "Australia",
        "chinese":       "China",
        "japanese":      "Japao",
        "miami":         "Miami",
        "canadian":      "Canada",
        "monaco":        "Monaco",
        "barcelona":     "Barcelona",
        "spanish":       "Espanha",
        "austrian":      "Austria",
        "british":       "Inglaterra",
        "belgian":       "Belgica",
        "hungarian":     "Hungria",
        "dutch":         "Holanda",
        "italian":       "Italia",
        "azerbaijan":    "Azerbaijao",
        "bahrain":       "Bahrein",
        "singapore":     "Singapura",
        "united states": "Estados Unidos",
        "mexico city":   "Mexico",
        "são paulo":     "Brasil",
        "sao paulo":     "Brasil",
        "las vegas":     "Las Vegas",
        "qatar":         "Catar",
        "abu dhabi":     "Abu Dhabi",
    }
    nome_lower = race_name.lower()
    for key, val in MAPA.items():
        if key in nome_lower:
            return val
    return race_name

# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("\n" + "="*60)
    print("  F1 AGENT V2 — GitHub Actions")
    print(f"  Iniciado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("="*60 + "\n")

    forcar      = os.environ.get("FORCAR", "false").lower() == "true"
    etapa_manual = os.environ.get("ETAPA_MANUAL", "").strip()

    # 1. Descobre a ultima corrida
    print("🔍 Buscando ultima corrida no Ergast...")
    race_info = get_ultima_corrida()
    if not race_info:
        print("❌ Nenhuma corrida encontrada no Ergast.")
        sys.exit(1)

    round_num  = race_info["round"]
    race_name  = race_info["raceName"]
    etapa_nome = etapa_manual if etapa_manual else normalizar_etapa(race_name)
    print(f"  ✅ Ultima corrida: {race_name} → {etapa_nome} (Round {round_num})")

    # 2. Verifica se ja foi atualizado (a menos que forcado)
    if not forcar and verificar_ja_atualizado(etapa_nome):
        print(f"\n  ℹ️ {etapa_nome} ja tem resultado no banco.")
        print("  Use 'Forçar atualização = true' para sobrescrever.")
        print("\n✅ Nada a fazer.")
        return True

    # 3. Coleta dados
    print("\n📡 Coletando dados via Ergast/Jolpi.ca...")
    corrida, vr = get_race_results(round_num)
    grid        = get_starting_grid(round_num)
    zebra       = get_zebra(round_num)
    pd          = get_piloto_do_dia(etapa_nome)

    print(f"  Corrida Top 10: {list(corrida.values())}")
    print(f"  Grid Top 3:     {list(grid.values())}")
    print(f"  VR:             {vr}")
    print(f"  PD:             {pd}")
    print(f"  Zebra:          {zebra}")

    # 4. Sincroniza resultados com PythonAnywhere
    print("\n🌐 Sincronizando resultados com PythonAnywhere...")
    enviados = 0
    erros    = 0

    todos_resultados = {}
    todos_resultados.update(corrida)
    todos_resultados.update(grid)
    if vr:    todos_resultados["vr"]    = vr
    if pd:    todos_resultados["pd"]    = pd
    if zebra: todos_resultados["zebra"] = zebra

    for tipo, piloto in todos_resultados.items():
        ok = sincronizar_resultado(etapa_nome, tipo, piloto)
        if ok:
            enviados += 1
        else:
            print(f"  ⚠️ Falha ao sincronizar {tipo}: {piloto}")
            erros += 1

    print(f"  ✅ {enviados} resultados sincronizados | ❌ {erros} erros")

    # 5. Sincroniza standings
    print("\n📊 Sincronizando standings...")
    pilotos_st, construtores_st = get_standings()
    if pilotos_st:
        ok = sincronizar_standings(pilotos_st, construtores_st, round_num)
        if ok:
            print(f"  ✅ Standings sincronizados ({len(pilotos_st)} pilotos, {len(construtores_st)} equipes)")
        else:
            print("  ⚠️ Falha ao sincronizar standings")
    else:
        print("  ⚠️ Standings não disponíveis no Ergast ainda")

    print("\n" + "="*60)
    print("  ✅ F1 Agent V2 concluído!")
    print("="*60 + "\n")
    return True

if __name__ == "__main__":
    run()

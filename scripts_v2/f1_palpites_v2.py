"""
F1 Palpites V2 — Le palpites do Google Sheets, grava no bolao.db local e sincroniza via API
Compativel com Windows e Linux (GitHub Actions):
  - Caminho de arquivo relativo portatil (nao trava no Linux)
  - Grava diretamente na tabela 'palpites' do SQLite bolao.db (alimenta o db_calcular.py)
  - Mapeia etapa_id e participante_id/nome no banco
  - Normalizacao canonica de pilotos para garantir pontuacao exata
  - Envia para a API externa caso configurada
"""

import os
import re
import sqlite3
import unicodedata
import requests
import openpyxl
from datetime import datetime, timedelta

# ── Configuracao e Caminhos Portateis ──────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bolao.db")
PALPITES_LOCAL = os.path.join(BASE_DIR, "palpites_f1_v2.xlsx")

API_URL  = "https://mbernalantonio.pythonanywhere.com"
API_KEY  = "f1bolao2027secretkey"
TEMPORADA = 2026

PALPITES_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "11Pan1BXC9flcnBgQD7dQ7Dz6TSVCiZY_Wlt8AlUE5FI"
    "/export?format=xlsx"
)

PARTICIPANTES = {
    "marcelo bernal":    "Bernal",
    "julio cesar":       "Consta",
    "júlio césar":       "Consta",
    "don":                "Donato",
    "alexandre andrade": "Japa",
    "joao otavio":       "Jota",
    "joão otávio":       "Jota",
    "rp":                "Kesper",
    "pierre gibert":     "Pierre",
    "san ribeiro":       "San",
}

ETAPAS_MAP = {
    "australia":        "Australia",
    "china":            "China",
    "japao":            "Japao",
    "japan":            "Japao",
    "miami":            "Miami",
    "canada":           "Canada",
    "monaco":           "Monaco",
    "barcelona":        "Barcelona",
    "austria":          "Austria",
    "inglaterra":       "Inglaterra",
    "gra-bretanha":     "Inglaterra",
    "belgica":          "Belgica",
    "hungria":          "Hungria",
    "holanda":          "Holanda",
    "italia":           "Italia",
    "espanha":          "Espanha",
    "madrid":           "Espanha",
    "azerbaijao":       "Azerbaijao",
    "azerbaijan":       "Azerbaijao",
    "bahrein":          "Bahrein",
    "bahrain":          "Bahrein",
    "singapura":        "Singapura",
    "singapore":        "Singapura",
    "estados unidos":   "Estados Unidos",
    "united states":    "Estados Unidos",
    "eua":              "Estados Unidos",
    "usa":              "Estados Unidos",
    "austin":           "Estados Unidos",
    "mexico":           "Mexico",
    "brasil":           "Brasil",
    "brazil":           "Brasil",
    "sao paulo":        "Brasil",
    "interlagos":       "Brasil",
    "las vegas":        "Las Vegas",
    "catar":            "Catar",
    "qatar":            "Catar",
    "abu dhabi":        "Abu Dhabi",
}

INICIO_BRT = {
    "Australia":      {"classificacao":"2026-03-07 02:00","corrida":"2026-03-08 01:00"},
    "China":          {"classificacao":"2026-03-14 04:00","corrida":"2026-03-15 04:00"},
    "Japao":          {"classificacao":"2026-03-28 03:00","corrida":"2026-03-29 02:00"},
    "Miami":          {"classificacao":"2026-05-02 17:00","corrida":"2026-05-03 17:00"},
    "Canada":         {"classificacao":"2026-05-23 17:00","corrida":"2026-05-24 17:00"},
    "Monaco":         {"classificacao":"2026-06-06 11:00","corrida":"2026-06-07 10:00"},
    "Barcelona":      {"classificacao":"2026-06-13 11:00","corrida":"2026-06-14 10:00"},
    "Austria":        {"classificacao":"2026-06-27 11:00","corrida":"2026-06-28 10:00"},
    "Inglaterra":     {"classificacao":"2026-07-04 12:00","corrida":"2026-07-05 11:00"},
    "Belgica":        {"classificacao":"2026-07-18 11:00","corrida":"2026-07-19 10:00"},
    "Hungria":        {"classificacao":"2026-07-25 11:00","corrida":"2026-07-26 10:00"},
    "Holanda":        {"classificacao":"2026-08-22 11:00","corrida":"2026-08-23 10:00"},
    "Italia":         {"classificacao":"2026-09-05 11:00","corrida":"2026-09-06 10:00"},
    "Espanha":        {"classificacao":"2026-09-12 11:00","corrida":"2026-09-13 10:00"},
    "Azerbaijao":     {"classificacao":"2026-09-25 09:00","corrida":"2026-09-26 08:00"},
    "Bahrein":        {"classificacao":"2026-10-03 05:00","corrida":"2026-10-04 04:00"},
    "Singapura":      {"classificacao":"2026-10-10 10:30","corrida":"2026-10-11 09:00"},
    "Estados Unidos": {"classificacao":"2026-10-24 18:00","corrida":"2026-10-25 17:00"},
    "Mexico":         {"classificacao":"2026-10-31 18:00","corrida":"2026-11-01 17:00"},
    "Brasil":         {"classificacao":"2026-11-07 15:00","corrida":"2026-11-08 14:00"},
    "Las Vegas":      {"classificacao":"2026-11-21 01:00","corrida":"2026-11-22 01:00"},
    "Catar":          {"classificacao":"2026-11-28 15:00","corrida":"2026-11-29 13:00"},
    "Abu Dhabi":      {"classificacao":"2026-12-05 11:00","corrida":"2026-12-06 10:00"},
}

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

ETAPAS_COM_PENALIDADE = {
    "Singapura","Estados Unidos","Mexico","Brasil",
    "Las Vegas","Catar","Abu Dhabi"
}

FMT = "%Y-%m-%d %H:%M"

HEADERS_API = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def normalizar(texto):
    if not texto: return ""
    t = str(texto).lower().strip()
    t = unicodedata.normalize('NFKD', t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'[^a-z0-9\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def normalizar_gp(gp_raw):
    t = normalizar(gp_raw)
    t = re.sub(r"^gp\s+(do|da|de|dos|das)\s+", "", t).strip()
    t = re.sub(r"^gp\s+", "", t).strip()
    return t

def formatar_nome_piloto(nome):
    if not nome: return ""
    norm = normalizar(nome)
    if norm in PILOTOS_NORM:
        return PILOTOS_NORM[norm]
    return " ".join(p.capitalize() for p in norm.split())

def encontrar_etapa(gp_norm):
    for key, val in ETAPAS_MAP.items():
        if key in gp_norm or gp_norm in key:
            return val
    return None

def parse_data(valor):
    if isinstance(valor, datetime): return valor
    if isinstance(valor, str):
        valor = valor.strip()
        for fmt in ["%d/%m/%Y %H:%M:%S","%d/%m/%Y %H:%M",
                    "%Y-%m-%d %H:%M:%S.%f","%Y-%m-%d %H:%M:%S","%Y-%m-%d %H:%M"]:
            try: return datetime.strptime(valor, fmt)
            except: continue
    return None

def get_inicio(etapa_nome, sessao):
    inicio = INICIO_BRT.get(etapa_nome)
    if not inicio: return None
    return datetime.strptime(inicio[sessao], FMT)

def conectar_banco():
    if not os.path.exists(DB_PATH):
        alt_path = os.path.join(os.getcwd(), "bolao.db")
        if os.path.exists(alt_path):
            return sqlite3.connect(alt_path)
    return sqlite3.connect(DB_PATH)

def api_post(endpoint, payload):
    try:
        resp = requests.post(f"{API_URL}{endpoint}", json=payload, headers=HEADERS_API, timeout=10)
        return resp.json()
    except Exception:
        return None

def api_get(endpoint):
    try:
        resp = requests.get(f"{API_URL}{endpoint}", headers={"X-API-Key": API_KEY}, timeout=10)
        return resp.json()
    except Exception:
        return None

# ── Leitura e Processamento ───────────────────────────────────────────────────

def baixar_palpites():
    print("📥 Baixando palpites do Google Sheets...")
    try:
        resp = requests.get(PALPITES_URL, timeout=30)
        resp.raise_for_status()
        with open(PALPITES_LOCAL, "wb") as f:
            f.write(resp.content)
        print("  ✅ Palpites baixados!")
        return True
    except Exception as e:
        print(f"  ⚠️  Erro ao baixar: {e}")
        if os.path.exists(PALPITES_LOCAL):
            print("  ℹ️  Usando versão local.")
            return True
        return False

def ler_respostas():
    wb = openpyxl.load_workbook(PALPITES_LOCAL, data_only=True)
    ws = wb["Respostas"] if "Respostas" in wb.sheetnames else wb.active
    max_row = ws.max_row
    print(f"  📊 Lendo {max_row - 1} respostas...")

    temp = {}
    descartados = 0

    for row in range(2, max_row + 1):
        data_hora = ws.cell(row, 1).value
        usuario   = ws.cell(row, 2).value
        gp_raw    = ws.cell(row, 3).value
        if not usuario or not gp_raw: continue

        usuario_norm = normalizar(str(usuario))
        gp_norm      = normalizar_gp(str(gp_raw))
        part_nome    = PARTICIPANTES.get(usuario_norm)
        if not part_nome: continue

        etapa_nome = encontrar_etapa(gp_norm)
        if not etapa_nome: continue

        p_vals = [ws.cell(row, 3+i).value for i in range(1, 11)]
        pd_val = ws.cell(row, 14).value
        vr_val = ws.cell(row, 15).value
        filled = sum(1 for v in p_vals if v)

        if filled <= 3 and filled > 0:
            sessao = "classificacao"
            palpites = {
                "grid_p1": formatar_nome_piloto(p_vals[0]),
                "grid_p2": formatar_nome_piloto(p_vals[1]),
                "grid_p3": formatar_nome_piloto(p_vals[2]),
                "pd":      formatar_nome_piloto(pd_val),
            }
        elif filled > 3:
            sessao = "corrida"
            palpites = {f"corrida_p{i+1}": formatar_nome_piloto(p_vals[i]) for i in range(10) if p_vals[i]}
            if vr_val:
                palpites["vr"] = formatar_nome_piloto(vr_val)
        else:
            continue

        dt = parse_data(data_hora)
        if dt is None: continue

        inicio = get_inicio(etapa_nome, sessao)
        if inicio and dt >= inicio:
            descartados += 1
            continue

        key = (etapa_nome, part_nome, sessao)
        existing = temp.get(key)
        if existing is None or dt >= existing[0]:
            temp[key] = (dt, palpites)

    if descartados:
        print(f"  🚫 Total descartados por horario de corte: {descartados}")

    return temp

# ── Gravacao Direta no SQLite bolao.db ─────────────────────────────────────────

def gravar_palpites_no_banco(palpites_dict):
    conn = conectar_banco()
    cursor = conn.cursor()

    # Mapeia etapas por nome e id
    cursor.execute("SELECT id, nome FROM etapas")
    etapas_db = {normalizar(row[1]): row[0] for row in cursor.fetchall()}

    # Mapeia participantes caso haja tabela 'participantes'
    participantes_db = {}
    try:
        cursor.execute("SELECT id, nome FROM participantes")
        participantes_db = {normalizar(row[1]): row[0] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        pass

    cursor.execute("PRAGMA table_info(palpites)")
    colunas_palpites = [c[1] for c in cursor.fetchall()]
    usa_part_id = "participante_id" in colunas_palpites

    total_gravados = 0

    for (etapa_nome, part_nome, sessao), (dt, palpites) in palpites_dict.items():
        etapa_id = etapas_db.get(normalizar(etapa_nome))
        if not etapa_id: continue

        part_ref = participantes_db.get(normalizar(part_nome), part_nome) if usa_part_id else part_nome

        for tipo, piloto in palpites.items():
            if not piloto: continue

            if usa_part_id:
                cursor.execute(
                    "SELECT id FROM palpites WHERE etapa_id = ? AND participante_id = ? AND tipo = ?",
                    (etapa_id, part_ref, tipo)
                )
                row = cursor.fetchone()
                if row:
                    cursor.execute(
                        "UPDATE palpites SET piloto = ? WHERE etapa_id = ? AND participante_id = ? AND tipo = ?",
                        (piloto, etapa_id, part_ref, tipo)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO palpites (etapa_id, participante_id, tipo, piloto) VALUES (?, ?, ?, ?)",
                        (etapa_id, part_ref, tipo, piloto)
                    )
            else:
                cursor.execute(
                    "SELECT id FROM palpites WHERE etapa_id = ? AND participante = ? AND tipo = ?",
                    (etapa_id, part_ref, tipo)
                )
                row = cursor.fetchone()
                if row:
                    cursor.execute(
                        "UPDATE palpites SET piloto = ? WHERE etapa_id = ? AND participante = ? AND tipo = ?",
                        (piloto, etapa_id, part_ref, tipo)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO palpites (etapa_id, participante, tipo, piloto) VALUES (?, ?, ?, ?)",
                        (etapa_id, part_ref, tipo, piloto)
                    )
            total_gravados += 1

    conn.commit()
    conn.close()
    print(f"  💾 {total_gravados} registros de palpites gravados no bolao.db local!")

def run():
    print("\n" + "="*60)
    print("  F1 PALPITES V2 — Preenchimento Automatico")
    print("="*60)
    print(f"  Iniciado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")

    if not baixar_palpites():
        return False

    palpites_dict = ler_respostas()
    print(f"  ✅ {len(palpites_dict)} palpites validos lidos")

    # 1. Grava diretamente no bolao.db local (Garante paridade no GitHub Actions)
    gravar_palpites_no_banco(palpites_dict)

    # 2. Envia para a API externa (se disponivel)
    enviados_api = 0
    for (etapa_nome, part_nome, sessao), (dt, palpites) in palpites_dict.items():
        palpites_validos = {k: v for k, v in palpites.items() if v}
        if not palpites_validos: continue

        payload = {
            "participante": part_nome,
            "etapa":        etapa_nome,
            "sessao":       sessao,
            "palpites":     palpites_validos,
        }
        resp = api_post("/api/palpite", payload)
        if resp and resp.get("sucesso"):
            enviados_api += 1

    print(f"  🌐 {enviados_api} palpites sincronizados com a API externa")

    print("\n" + "="*60)
    print("  ✅ Palpites processados e gravados com sucesso!")
    print("="*60 + "\n")
    return True

if __name__ == "__main__":
    run()

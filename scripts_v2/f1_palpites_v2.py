"""
F1 Palpites V2 — Le palpites do Google Sheets e envia para API do PythonAnywhere
Substitui o f1_palpites.py baseado em Excel
Roda no PC do usuario todo domingo apos a corrida
"""

import requests
import openpyxl
import re
import os
import json
from datetime import datetime, timedelta

# ── Configuracao ───────────────────────────────────────────────────────────────
API_URL  = "https://mbernalantonio.pythonanywhere.com"
API_KEY  = "f1bolao2027secretkey"
TEMPORADA = 2027

PALPITES_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "11Pan1BXC9flcnBgQD7dQ7Dz6TSVCiZY_Wlt8AlUE5FI"
    "/export?format=xlsx"
)
PALPITES_LOCAL = r"C:\Users\mbern\OneDrive\F1Agent\palpites_f1_v2.xlsx"

PARTICIPANTES = {
    "marcelo bernal":    "Bernal",
    "julio cesar":       "Consta",
    "júlio césar":       "Consta",
    "don":               "Donato",
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
    "las vegas":        "Las Vegas",
    "catar":            "Catar",
    "qatar":            "Catar",
    "abu dhabi":        "Abu Dhabi",
}

INICIO_BRT = {
    "Australia":      {"classificacao":"2027-03-13 02:00","corrida":"2027-03-14 01:00"},
    "China":          {"classificacao":"2027-03-20 04:00","corrida":"2027-03-21 04:00"},
    "Japao":          {"classificacao":"2027-04-03 03:00","corrida":"2027-04-04 02:00"},
    "Miami":          {"classificacao":"2027-05-01 17:00","corrida":"2027-05-02 17:00"},
    "Canada":         {"classificacao":"2027-05-22 17:00","corrida":"2027-05-23 17:00"},
    "Monaco":         {"classificacao":"2027-06-05 11:00","corrida":"2027-06-06 10:00"},
    "Barcelona":      {"classificacao":"2027-06-12 11:00","corrida":"2027-06-13 10:00"},
    "Austria":        {"classificacao":"2027-06-26 11:00","corrida":"2027-06-27 10:00"},
    "Inglaterra":     {"classificacao":"2027-07-03 12:00","corrida":"2027-07-04 11:00"},
    "Belgica":        {"classificacao":"2027-07-17 11:00","corrida":"2027-07-18 10:00"},
    "Hungria":        {"classificacao":"2027-07-24 11:00","corrida":"2027-07-25 10:00"},
    "Holanda":        {"classificacao":"2027-08-21 11:00","corrida":"2027-08-22 10:00"},
    "Italia":         {"classificacao":"2027-09-04 11:00","corrida":"2027-09-05 10:00"},
    "Espanha":        {"classificacao":"2027-09-11 11:00","corrida":"2027-09-12 10:00"},
    "Azerbaijao":     {"classificacao":"2027-09-24 09:00","corrida":"2027-09-25 08:00"},
    "Bahrein":        {"classificacao":"2027-10-02 05:00","corrida":"2027-10-03 04:00"},
    "Singapura":      {"classificacao":"2027-10-09 10:00","corrida":"2027-10-10 09:00"},
    "Estados Unidos": {"classificacao":"2027-10-23 18:00","corrida":"2027-10-24 17:00"},
    "Mexico":         {"classificacao":"2027-10-30 18:00","corrida":"2027-10-31 17:00"},
    "Brasil":         {"classificacao":"2027-11-06 15:00","corrida":"2027-11-07 14:00"},
    "Las Vegas":      {"classificacao":"2027-11-20 00:00","corrida":"2027-11-21 00:00"},
    "Catar":          {"classificacao":"2027-11-27 15:00","corrida":"2027-11-28 13:00"},
    "Abu Dhabi":      {"classificacao":"2027-12-04 11:00","corrida":"2027-12-05 10:00"},
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
    for a, b in [("á","a"),("à","a"),("ã","a"),("â","a"),("é","e"),("ê","e"),
                 ("è","e"),("í","i"),("ó","o"),("ô","o"),("õ","o"),("ú","u"),
                 ("û","u"),("ç","c"),("ñ","n")]:
        t = t.replace(a, b)
    return t


def normalizar_gp(gp_raw):
    t = normalizar(gp_raw)
    t = re.sub(r"^gp\s+(do|da|de|dos|das)\s+", "", t).strip()
    t = re.sub(r"^gp\s+", "", t).strip()
    return t


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


def api_post(endpoint, payload):
    """Envia dados para a API do PythonAnywhere."""
    try:
        resp = requests.post(
            f"{API_URL}{endpoint}",
            json=payload,
            headers=HEADERS_API,
            timeout=30
        )
        return resp.json()
    except Exception as e:
        print(f"  Erro API {endpoint}: {e}")
        return None


def api_get(endpoint):
    """Busca dados da API do PythonAnywhere."""
    try:
        resp = requests.get(
            f"{API_URL}{endpoint}",
            headers={"X-API-Key": API_KEY},
            timeout=15
        )
        return resp.json()
    except Exception as e:
        print(f"  Erro API GET {endpoint}: {e}")
        return None


# ── Leitura do Google Sheets ───────────────────────────────────────────────────

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
    """Le palpites do Google Sheets e retorna dict organizado."""
    wb = openpyxl.load_workbook(PALPITES_LOCAL, data_only=True)
    ws = wb["Respostas"]
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
                "grid_p1": p_vals[0] or "",
                "grid_p2": p_vals[1] or "",
                "grid_p3": p_vals[2] or "",
                "pd":      pd_val or "",
            }
        elif filled > 3:
            sessao = "corrida"
            palpites = {f"corrida_p{i+1}": p_vals[i] or "" for i in range(10)}
            palpites["vr"] = vr_val or ""
        else:
            continue

        dt = parse_data(data_hora)
        if dt is None: continue

        inicio = get_inicio(etapa_nome, sessao)
        if inicio and dt >= inicio:
            print(f"  🚫 [{part_nome}] {etapa_nome} {sessao}: "
                  f"{dt.strftime('%d/%m %H:%M:%S')} >= {inicio.strftime('%H:%M')} — DESCARTADO")
            descartados += 1
            continue

        key = (etapa_nome, part_nome, sessao)
        existing = temp.get(key)
        if existing is None or dt >= existing[0]:
            temp[key] = (dt, palpites)

    if descartados:
        print(f"  🚫 Total descartados: {descartados}")

    return temp


def calcular_lider_atual():
    """Busca lider atual do bolao via API."""
    dados = api_get("/api/ranking")
    if dados and dados.get("ranking"):
        return dados["ranking"][0]
    return None


def verificar_penalidades(palpites_dict, lider_nome):
    """
    Verifica se o lider enviou palpites dentro do prazo (10min antes).
    Retorna lista de penalidades a aplicar.
    """
    penalidades = []
    if not lider_nome:
        return penalidades

    for (etapa_nome, part_nome, sessao), (dt_palpite, _) in palpites_dict.items():
        if etapa_nome not in ETAPAS_COM_PENALIDADE:
            continue
        if part_nome != lider_nome:
            continue

        inicio = get_inicio(etapa_nome, sessao)
        if not inicio:
            continue

        corte_lider = inicio - timedelta(minutes=10)
        aplicada = dt_palpite >= corte_lider
        tipo = "Treino" if sessao == "classificacao" else "Corrida"

        if aplicada:
            print(f"  🚩 [{lider_nome}] {etapa_nome} — Bandeira Preta {tipo}: "
                  f"enviado {dt_palpite.strftime('%d/%m %H:%M:%S')} "
                  f"(corte: {corte_lider.strftime('%H:%M')})")
        else:
            print(f"  ✅ [{lider_nome}] {etapa_nome} {tipo}: OK "
                  f"({dt_palpite.strftime('%d/%m %H:%M:%S')})")

        penalidades.append({
            "etapa":        etapa_nome,
            "temporada":    TEMPORADA,
            "participante": lider_nome,
            "sessao":       sessao,
            "aplicada":     aplicada,
            "dt_palpite":   dt_palpite.strftime("%Y-%m-%d %H:%M:%S"),
            "dt_corte":     corte_lider.strftime("%Y-%m-%d %H:%M:%S"),
        })

    return penalidades


def run():
    print("\n" + "="*60)
    print("  F1 PALPITES V2 — Preenchimento Automatico")
    print("="*60)
    print(f"  Iniciado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")

    # 1. Baixa palpites
    if not baixar_palpites():
        return False

    # 2. Le respostas
    palpites_dict = ler_respostas()
    print(f"  ✅ {len(palpites_dict)} palpites validos lidos")

    # 3. Busca etapas ja preenchidas na API
    dados_api = api_get("/api/ranking")
    etapas_com_resultado = set()
    if dados_api and dados_api.get("etapas"):
        etapas_com_resultado = set(dados_api["etapas"])

    # 4. Envia palpites para API
    enviados = 0
    erros    = 0
    etapas_processadas = set()

    for (etapa_nome, part_nome, sessao), (dt, palpites) in palpites_dict.items():
        # Filtra palpites vazios
        palpites_validos = {k: v for k, v in palpites.items() if v}
        if not palpites_validos:
            continue

        payload = {
            "participante": part_nome,
            "etapa":        etapa_nome,
            "sessao":       sessao,
            "palpites":     palpites_validos,
        }

        resp = api_post("/api/palpite", payload)
        if resp and resp.get("sucesso"):
            enviados += 1
            etapas_processadas.add(etapa_nome)
        else:
            erro = resp.get("erro", "desconhecido") if resp else "sem resposta"
            # Ignora erro de prazo encerrado (normal para etapas passadas)
            if "Prazo" not in str(erro):
                print(f"  ⚠️  Erro [{part_nome}] {etapa_nome} {sessao}: {erro}")
                erros += 1

    print(f"  ✅ {enviados} palpites enviados para API")
    if erros:
        print(f"  ⚠️  {erros} erros")

    # 5. Verifica penalidades do lider
    print(f"\n{'─'*60}")
    print("  🚩 Verificando penalidades do lider...")
    lider = calcular_lider_atual()
    if lider:
        print(f"  Lider atual: {lider}")
        penalidades = verificar_penalidades(palpites_dict, lider)
        for pen in penalidades:
            resp = api_post("/api/sync/penalidade", pen)
            if resp and resp.get("sucesso"):
                status = "aplicada" if pen["aplicada"] else "OK"
                print(f"  ✅ Penalidade gravada: {pen['participante']} {pen['etapa']} {pen['sessao']} — {status}")
    else:
        print("  ℹ️  Nao foi possivel determinar o lider")

    print("\n" + "="*60)
    print("  ✅ Palpites processados com sucesso!")
    print("="*60 + "\n")
    return True


if __name__ == "__main__":
    run()

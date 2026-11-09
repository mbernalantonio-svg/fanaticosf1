"""
F1 Bolao V2 — Motor de Pontuacao
Calcula pontos de todos os participantes em todas as etapas
e grava na tabela pontuacao do SQLite.
Versao com Matriz de Auditoria Etapa a Etapa.
"""

import sqlite3
import os
import re
import unicodedata
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bolao.db")

# Regras de pontuacao
PONTOS = {
    "grid_p1": 2, "grid_p2": 2, "grid_p3": 2,
    "corrida_p1": 3, "corrida_p2": 3, "corrida_p3": 3,
    "corrida_p4": 3, "corrida_p5": 3,
    "corrida_p6": 4, "corrida_p7": 4, "corrida_p8": 4,
    "corrida_p9": 4, "corrida_p10": 4,
    "pd": 5, "vr": 5,
    "zebra": 10,
    "bp_treino": -2,
    "bp_corrida": -10,
}

RETA_FINAL = {
    "Catar":      2,
    "Abu Dhabi":  3,
}

def normalizar_nome(texto):
    if not texto: return ""
    t = str(texto).strip().lower()
    t = unicodedata.normalize('NFKD', t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'[^a-z0-9\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def sao_iguais(p1, p2):
    if not p1 or not p2: return False
    n1 = normalizar_nome(p1)
    n2 = normalizar_nome(p2)
    if n1 == n2: return True
    sinonimos = [
        ("alex albon", "alexander albon"),
        ("nico hulkenberg", "nico hülkenberg"),
        ("sergio perez", "sergio pérez"),
        ("carlos sainz", "carlos sainz jr"),
        ("zhou guanyu", "guanyu zhou"),
        ("rafael camara", "rafael câmara")
    ]
    for a, b in sinonimos:
        if (n1 == a and n2 == b) or (n1 == b and n2 == a):
            return True
    return False

def calcular_tudo(temporada_id=1, verbose=True):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if verbose:
        print("=" * 55)
        print("  F1 BOLAO V2 — Calculando Pontuacao")
        print("=" * 55)

    cur.execute("SELECT id, nome FROM participantes WHERE ativo = 1 ORDER BY nome")
    participantes = cur.fetchall()

    cur.execute("""
        SELECT DISTINCT e.id, e.nome, e.round, e.multiplicador
        FROM etapas e
        JOIN resultados r ON r.etapa_id = e.id
        WHERE e.temporada_id = ?
        ORDER BY e.round
    """, (temporada_id,))
    etapas = cur.fetchall()

    if verbose:
        print(f"  Etapas com resultado: {len(etapas)}")
        print(f"  Participantes: {len(participantes)}")
        print()

    cur.execute("SELECT campeao_anterior FROM temporadas WHERE id = ?", (temporada_id,))
    row = cur.fetchone()
    campeao_anterior = row[0] if row and row[0] else "Max Verstappen"

    total_calculados = 0

    for etapa in etapas:
        etapa_id    = etapa["id"]
        etapa_nome  = etapa["nome"]
        mult        = etapa["multiplicador"]
        is_primeira = (etapa["round"] == 1)

        cur.execute("SELECT piloto FROM resultados WHERE etapa_id = ? AND tipo = 'corrida_p1'", (etapa_id,))
        row = cur.fetchone()
        vencedor_real = row[0] if row else None

        cur.execute("SELECT piloto FROM resultados WHERE etapa_id = ? AND tipo = 'zebra'", (etapa_id,))
        row = cur.fetchone()
        zebra_banco = row[0] if row and row[0] else None

        if etapa_nome == "Brasil" or etapa_id == 20:
            zebra_ref = "Kimi Antonelli"
        elif zebra_banco and not sao_iguais(zebra_banco, vencedor_real):
            zebra_ref = zebra_banco
        else:
            zebra_ref = campeao_anterior if is_primeira else "Kimi Antonelli"

        cur.execute("SELECT tipo, piloto FROM resultados WHERE etapa_id = ?", (etapa_id,))
        resultados = {row[0]: row[1] for row in cur.fetchall()}

        for part in participantes:
            part_id   = part["id"]
            part_nome = part["nome"]

            cur.execute("""
                SELECT tipo, piloto FROM palpites
                WHERE etapa_id = ? AND participante_id = ?
            """, (etapa_id, part_id))
            palpites = {row[0]: row[1] for row in cur.fetchall()}

            cur.execute("""
                SELECT sessao, aplicada FROM penalidades
                WHERE etapa_id = ? AND participante_id = ?
            """, (etapa_id, part_id))
            penalidades = {row[0]: row[1] for row in cur.fetchall()}

            pts_grid       = 0
            pts_corrida    = 0
            pts_pd         = 0
            pts_vr         = 0
            pts_zebra      = 0
            pts_penalidade = 0

            for tipo in ["grid_p1", "grid_p2", "grid_p3"]:
                palp = palpites.get(tipo)
                real = resultados.get(tipo)
                if sao_iguais(palp, real):
                    pts_grid += PONTOS[tipo]

            for tipo in [f"corrida_p{i}" for i in range(1, 11)]:
                palp = palpites.get(tipo)
                real = resultados.get(tipo)
                if sao_iguais(palp, real):
                    pts_corrida += PONTOS[tipo]

            if sao_iguais(palpites.get("pd"), resultados.get("pd")):
                pts_pd += PONTOS["pd"]

            if sao_iguais(palpites.get("vr"), resultados.get("vr")):
                pts_vr += PONTOS["vr"]

            subtotal = pts_grid + pts_corrida + pts_pd + pts_vr
            pts_grid    *= mult
            pts_corrida *= mult
            pts_pd      *= mult
            pts_vr      *= mult

            palp_p1 = palpites.get("corrida_p1")
            if (palp_p1 and vencedor_real and
                    sao_iguais(palp_p1, vencedor_real) and
                    not sao_iguais(palp_p1, zebra_ref)):
                pts_zebra = PONTOS["zebra"] * mult

            if penalidades.get("treino") == 1:
                pts_penalidade += PONTOS["bp_treino"] * mult
            if penalidades.get("corrida") == 1:
                pts_penalidade += PONTOS["bp_corrida"] * mult

            pts_total = pts_grid + pts_corrida + pts_pd + pts_vr + pts_zebra + pts_penalidade
            pts_bruto = subtotal

            cur.execute("""
                INSERT OR REPLACE INTO pontuacao
                (etapa_id, participante_id, pts_grid, pts_corrida, pts_pd, pts_vr,
                 pts_zebra, pts_penalidade, pts_total, pts_bruto, multiplicador, calculado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (etapa_id, part_id, pts_grid, pts_corrida, pts_pd, pts_vr,
                  pts_zebra, pts_penalidade, pts_total, pts_bruto, mult,
                  datetime.now().isoformat()))
            total_calculados += 1

    conn.commit()
    if verbose:
        print(f"  ✅ {total_calculados} registros de pontuacao calculados\n")
    conn.close()
    return total_calculados


def calcular_capsula(temporada_id=1, verbose=True):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if verbose:
        print("  Calculando Capsula do Tempo...")

    cur.execute("SELECT MAX(round) FROM standings_pilotos WHERE temporada_id = ?", (temporada_id,))
    row = cur.fetchone()
    ultimo_round = row[0] if row and row[0] else None

    if not ultimo_round:
        cur.execute("SELECT MAX(round) FROM etapas WHERE temporada_id = ?", (temporada_id,))
        r = cur.fetchone()
        ultimo_round = r[0] if r and r[0] else 20

    cur.execute("SELECT posicao, piloto FROM standings_pilotos WHERE temporada_id = ? ORDER BY posicao", (temporada_id,))
    stand_pilotos = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("SELECT posicao, equipe FROM standings_construtores WHERE temporada_id = ? ORDER BY posicao", (temporada_id,))
    stand_construtores = {row[0]: row[1] for row in cur.fetchall()}

    QUATRO_GRANDES = {"Mercedes", "Ferrari", "McLaren", "Red Bull", "Red Bull Racing"}
    cur.execute("SELECT piloto, equipe FROM standings_pilotos WHERE temporada_id = ? ORDER BY posicao", (temporada_id,))
    melhor_resto = None
    for row in cur.fetchall():
        if row[1] not in QUATRO_GRANDES:
            melhor_resto = row[0]
            break

    cur.execute("SELECT piloto FROM standings_pilotos WHERE temporada_id = ? ORDER BY posicao DESC LIMIT 1", (temporada_id,))
    row = cur.fetchone()
    gp2 = row[0] if row else None

    cur.execute("SELECT id, nome FROM participantes WHERE ativo = 1")
    participantes = cur.fetchall()

    for part in participantes:
        part_id = part["id"]

        cur.execute("SELECT categoria, valor FROM capsula WHERE temporada_id = ? AND participante_id = ?", (temporada_id, part_id))
        palpites_cap = {row[0]: row[1] for row in cur.fetchall()}

        pts_pilotos_exato   = 0
        pts_pilotos_trocado = 0
        pts_equipes_exato   = 0
        pts_equipes_trocado = 0
        pts_melhor_resto    = 0
        pts_gp2             = 0

        resultado_pilotos = [stand_pilotos.get(i, "") for i in range(1, 7)]
        for i in range(1, 7):
            palp = palpites_cap.get(f"piloto_p{i}", "")
            real = stand_pilotos.get(i, "")
            if palp and real:
                if sao_iguais(palp, real):
                    pts_pilotos_exato += 10
                elif any(sao_iguais(palp, rp) for rp in resultado_pilotos):
                    pts_pilotos_trocado += 5

        resultado_equipes = [stand_construtores.get(i, "") for i in range(1, 4)]
        for i in range(1, 4):
            palp = palpites_cap.get(f"equipe_p{i}", "")
            real = stand_construtores.get(i, "")
            if palp and real:
                if sao_iguais(palp, real):
                    pts_equipes_exato += 10
                elif any(sao_iguais(palp, re) for re in resultado_equipes):
                    pts_equipes_trocado += 5

        palp_mr = palpites_cap.get("melhor_resto", "")
        if palp_mr and melhor_resto and sao_iguais(palp_mr, melhor_resto):
            pts_melhor_resto = 10

        palp_gp2 = palpites_cap.get("gp2", "")
        if palp_gp2 and gp2 and sao_iguais(palp_gp2, gp2):
            pts_gp2 = 10

        pts_total = (pts_pilotos_exato + pts_pilotos_trocado +
                     pts_equipes_exato + pts_equipes_trocado +
                     pts_melhor_resto + pts_gp2)

        cur.execute("""
            INSERT OR REPLACE INTO capsula_pontuacao
            (temporada_id, participante_id, pts_pilotos_exato, pts_pilotos_trocado,
             pts_equipes_exato, pts_equipes_trocado, pts_melhor_resto, pts_gp2,
             pts_total, calculado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (temporada_id, part_id, pts_pilotos_exato, pts_pilotos_trocado,
              pts_equipes_exato, pts_equipes_trocado, pts_melhor_resto, pts_gp2,
              pts_total, datetime.now().isoformat()))

    conn.commit()
    conn.close()
    if verbose:
        print("  ✅ Capsula calculada!")


def imprimir_comparativo_detalhado(temporada_id=1):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT e.round, e.nome as etapa, p.nome as participante, pt.pts_total
        FROM pontuacao pt
        JOIN participantes p ON p.id = pt.participante_id
        JOIN etapas e ON e.id = pt.etapa_id
        WHERE e.temporada_id = ?
        ORDER BY e.round, p.nome
    """, (temporada_id,))
    rows = cur.fetchall()

    matriz = {}
    etapas = []
    participantes = set()
    for r in rows:
        etapa = f"{r['round']:02d}. {r['etapa']}"
        part = r['participante']
        if etapa not in etapas:
            etapas.append(etapa)
        participantes.add(part)
        if part not in matriz:
            matriz[part] = {}
        matriz[part][etapa] = r['pts_total']

    parts_ordenados = sorted(list(participantes))
    print("\n" + "=" * 90)
    print("  MATRIZ DE PONTOS POR ETAPA (V2)")
    print("=" * 90)
    header = f"{'Etapa':18s} | " + " | ".join(f"{p:7s}" for p in parts_ordenados)
    print(header)
    print("-" * len(header))

    totais = {p: 0 for p in parts_ordenados}
    for e in etapas:
        linha = f"{e:18s} | "
        for p in parts_ordenados:
            pts = matriz.get(p, {}).get(e, 0.0)
            totais[p] += pts
            linha += f"{pts:7.1f} | "
        print(linha)

    print("-" * len(header))
    linha_tot = f"{'TOTAL ACUMULADO':18s} | " + " | ".join(f"{totais[p]:7.1f}" for p in parts_ordenados)
    print(linha_tot)
    print("=" * 90 + "\n")
    conn.close()


def get_ranking(temporada_id=1):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT e.id, e.nome, e.round, e.multiplicador
        FROM etapas e
        JOIN pontuacao pt ON pt.etapa_id = e.id
        WHERE e.temporada_id = ?
        GROUP BY e.id
        ORDER BY e.round
    """, (temporada_id,))
    etapas = cur.fetchall()
    n_etapas = len(etapas)

    cur.execute("""
        SELECT p.nome, e.nome as etapa, e.round, pt.pts_total, pt.pts_bruto
        FROM pontuacao pt
        JOIN participantes p ON p.id = pt.participante_id
        JOIN etapas e ON e.id = pt.etapa_id
        WHERE e.temporada_id = ?
        ORDER BY p.nome, e.round
    """, (temporada_id,))
    rows = cur.fetchall()

    dados = {}
    for row in rows:
        nome = row["nome"]
        if nome not in dados:
            dados[nome] = {"pts_por_etapa": {}, "total": 0}
        dados[nome]["pts_por_etapa"][row["etapa"]] = row["pts_total"]
        dados[nome]["total"] += row["pts_total"]

    todas_disputadas = (n_etapas == 23)
    for nome in dados:
        pts_list = [(etapa, pts) for etapa, pts in dados[nome]["pts_por_etapa"].items()]
        if pts_list:
            pior = min(pts_list, key=lambda x: x[1])
            dados[nome]["descarte"] = pior
            if todas_disputadas:
                dados[nome]["total_com_descarte"] = dados[nome]["total"] - pior[1]
            else:
                dados[nome]["total_com_descarte"] = dados[nome]["total"]

    for nome in dados:
        acc = 0
        acumulado = []
        for etapa in etapas:
            pts = dados[nome]["pts_por_etapa"].get(etapa["nome"], 0)
            acc += pts
            acumulado.append(acc)
        dados[nome]["acumulado"] = acumulado

    ranking = sorted(dados.items(),
                     key=lambda x: x[1].get("total_com_descarte", x[1]["total"]),
                     reverse=True)
    conn.close()

    return {
        "ranking":      [r[0] for r in ranking],
        "dados":        dados,
        "etapas":       [e["nome"] for e in etapas],
        "n_etapas":     n_etapas,
        "todas_disp":   todas_disputadas,
        "atualizado":   datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


def run(temporada_id=1):
    calcular_tudo(temporada_id, verbose=True)
    calcular_capsula(temporada_id, verbose=True)
    imprimir_comparativo_detalhado(temporada_id)

    dados = get_ranking(temporada_id)
    print("=== RANKING ATUAL ===")
    medalhas = {1:"🥇", 2:"🥈", 3:"🥉"}
    for i, nome in enumerate(dados["ranking"], 1):
        d = dados["dados"][nome]
        total = d.get("total_com_descarte", d["total"])
        desc  = d.get("descarte", ("N/A", 0))
        m = medalhas.get(i, f"{i}.")
        print(f"  {m} {nome:10} {total:4} pts | descarte: {desc[0]} ({desc[1]}pt)")

    print(f"\n  Etapas: {dados['n_etapas']}/23")
    print(f"  {'Descarte APLICADO' if dados['todas_disp'] else 'Descarte sera aplicado ao final'}")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO log_execucoes (tipo, status, mensagem)
            VALUES ('pontuacao', 'sucesso', ?)
        """, (f"Calculado {dados['n_etapas']} etapas",))
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()


if __name__ == "__main__":
    run()

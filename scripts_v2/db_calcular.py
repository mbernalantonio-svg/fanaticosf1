"""
F1 Bolao V2 — Motor de Pontuacao
Calcula pontos de todos os participantes em todas as etapas
e grava na tabela pontuacao do SQLite.
Substitui completamente o build_dashboard.py baseado em Excel.
"""

import sqlite3
import os
import unicodedata
import re
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bolao.db")

# Normalizacao de nomes para comparacao — remove acentos e padroniza
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
    "zhou guanyu":           "Zhou Guanyu",
    "guanyu zhou":           "Zhou Guanyu",
    "alexander albon":       "Alex Albon",
    "alex albon":            "Alex Albon",
}

def norm(nome):
    if not nome:
        return ""
    chave = nome.strip().lower()
    if chave in PILOTOS_NORM:
        return PILOTOS_NORM[chave].lower()
    txt = unicodedata.normalize('NFKD', nome.strip())
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return txt.lower()

def mesmos_pilotos(a, b):
    """Compara dois nomes de pilotos ignorando acentos e aliases."""
    return bool(a and b and norm(a) == norm(b))

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

# Etapas da Reta Final e seus multiplicadores
RETA_FINAL = {
    "Catar":     2,
    "Abu Dhabi": 3,
}


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
    campeao_anterior = row[0] if row else None

    total_calculados = 0

    for etapa in etapas:
        etapa_id    = etapa["id"]
        etapa_nome  = etapa["nome"]
        mult        = etapa["multiplicador"]
        is_primeira = (etapa["round"] == 1)

        cur.execute("""
            SELECT piloto FROM resultados
            WHERE etapa_id = ? AND tipo = 'zebra'
        """, (etapa_id,))
        row = cur.fetchone()
        zebra_ref = row[0] if row else (campeao_anterior if is_primeira else None)

        cur.execute("""
            SELECT piloto FROM resultados
            WHERE etapa_id = ? AND tipo = 'corrida_p1'
        """, (etapa_id,))
        row = cur.fetchone()
        vencedor_real = row[0] if row else None

        cur.execute("""
            SELECT tipo, piloto FROM resultados WHERE etapa_id = ?
        """, (etapa_id,))
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

            # Grid P1-P3
            for tipo in ["grid_p1", "grid_p2", "grid_p3"]:
                palp = palpites.get(tipo)
                real = resultados.get(tipo)
                if mesmos_pilotos(palp, real):
                    pts_grid += PONTOS[tipo]

            # Corrida P1-P10
            for tipo in [f"corrida_p{i}" for i in range(1, 11)]:
                palp = palpites.get(tipo)
                real = resultados.get(tipo)
                if mesmos_pilotos(palp, real):
                    pts_corrida += PONTOS[tipo]

            # PD
            palp_pd = palpites.get("pd")
            real_pd = resultados.get("pd")
            if mesmos_pilotos(palp_pd, real_pd):
                pts_pd += PONTOS["pd"]

            # VR
            palp_vr = palpites.get("vr")
            real_vr = resultados.get("vr")
            if mesmos_pilotos(palp_vr, real_vr):
                pts_vr += PONTOS["vr"]

            subtotal    = pts_grid + pts_corrida + pts_pd + pts_vr
            pts_grid    *= mult
            pts_corrida *= mult
            pts_pd      *= mult
            pts_vr      *= mult

            # Zebra (tambem multiplicada)
            palp_p1 = palpites.get("corrida_p1")
            if (palp_p1 and vencedor_real and zebra_ref and
                    mesmos_pilotos(palp_p1, vencedor_real) and
                    not mesmos_pilotos(palp_p1, zebra_ref)):
                pts_zebra = PONTOS["zebra"] * mult

            # Penalidades
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
        print(f"  ✅ {total_calculados} registros de pontuacao calculados")
        print()

    conn.close()
    return total_calculados


def calcular_capsula(temporada_id=1, verbose=True):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if verbose:
        print("  Calculando Capsula do Tempo...")

    cur.execute("""
        SELECT MAX(round) FROM standings_pilotos WHERE temporada_id = ?
    """, (temporada_id,))
    row = cur.fetchone()
    ultimo_round = row[0] if row and row[0] else None

    if not ultimo_round:
        if verbose:
            print("  ⚠️  Sem standings no banco — execute f1_agent_v2.py primeiro")
        conn.close()
        return

    cur.execute("""
        SELECT posicao, piloto FROM standings_pilotos
        WHERE temporada_id = ? AND round = ?
        ORDER BY posicao
    """, (temporada_id, ultimo_round))
    stand_pilotos = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("""
        SELECT posicao, equipe FROM standings_construtores
        WHERE temporada_id = ? AND round = ?
        ORDER BY posicao
    """, (temporada_id, ultimo_round))
    stand_construtores = {row[0]: row[1] for row in cur.fetchall()}

    QUATRO_GRANDES = {"Mercedes", "Ferrari", "McLaren", "Red Bull", "Red Bull Racing"}
    cur.execute("""
        SELECT sp.piloto, sp.equipe FROM standings_pilotos sp
        WHERE sp.temporada_id = ? AND sp.round = ?
        ORDER BY sp.posicao
    """, (temporada_id, ultimo_round))
    melhor_resto = None
    for row in cur.fetchall():
        if row[1] not in QUATRO_GRANDES:
            melhor_resto = row[0]
            break

    cur.execute("""
        SELECT piloto FROM standings_pilotos
        WHERE temporada_id = ? AND round = ?
        ORDER BY posicao DESC LIMIT 1
    """, (temporada_id, ultimo_round))
    row = cur.fetchone()
    gp2 = row[0] if row else None

    cur.execute("SELECT id, nome FROM participantes WHERE ativo = 1")
    participantes = cur.fetchall()

    for part in participantes:
        part_id = part["id"]

        cur.execute("""
            SELECT categoria, valor FROM capsula
            WHERE temporada_id = ? AND participante_id = ?
        """, (temporada_id, part_id))
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
                if mesmos_pilotos(palp, real):
                    pts_pilotos_exato += 10
                elif palp in resultado_pilotos:
                    pts_pilotos_trocado += 5

        resultado_equipes = [stand_construtores.get(i, "") for i in range(1, 4)]
        for i in range(1, 4):
            palp = palpites_cap.get(f"equipe_p{i}", "")
            real = stand_construtores.get(i, "")
            if palp and real:
                if palp.strip().lower() == real.strip().lower():
                    pts_equipes_exato += 10
                elif palp in resultado_equipes:
                    pts_equipes_trocado += 5

        palp_mr = palpites_cap.get("melhor_resto", "")
        if palp_mr and melhor_resto and mesmos_pilotos(palp_mr, melhor_resto):
            pts_melhor_resto = 10

        palp_gp2 = palpites_cap.get("gp2", "")
        if palp_gp2 and gp2 and mesmos_pilotos(palp_gp2, gp2):
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
        print(f"  ✅ Capsula calculada (round {ultimo_round})")


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
        "ranking":    [r[0] for r in ranking],
        "dados":      dados,
        "etapas":     [e["nome"] for e in etapas],
        "n_etapas":   n_etapas,
        "todas_disp": todas_disputadas,
        "atualizado": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


def get_ultima_etapa(temporada_id=1):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT e.id, e.nome, e.round, e.multiplicador
        FROM etapas e
        JOIN resultados r ON r.etapa_id = e.id
        WHERE e.temporada_id = ?
        GROUP BY e.id
        ORDER BY e.round DESC LIMIT 1
    """, (temporada_id,))
    etapa = cur.fetchone()
    if not etapa:
        conn.close()
        return None

    etapa_id = etapa["id"]

    cur.execute("""
        SELECT p.nome, pt.pts_total, pt.pts_grid, pt.pts_corrida,
               pt.pts_pd, pt.pts_vr, pt.pts_zebra, pt.pts_penalidade
        FROM pontuacao pt
        JOIN participantes p ON p.id = pt.participante_id
        WHERE pt.etapa_id = ?
        ORDER BY pt.pts_total DESC
    """, (etapa_id,))
    pontuacao = [dict(row) for row in cur.fetchall()]

    cur.execute("""
        SELECT tipo, piloto FROM resultados WHERE etapa_id = ? ORDER BY tipo
    """, (etapa_id,))
    resultados = {row[0]: row[1] for row in cur.fetchall()}

    conn.close()

    return {
        "nome":       etapa["nome"],
        "round":      etapa["round"],
        "mult":       etapa["multiplicador"],
        "pontuacao":  pontuacao,
        "resultados": resultados,
    }


def get_palpites_etapa(etapa_nome, temporada_id=1):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT id, nome, multiplicador FROM etapas
        WHERE temporada_id = ? AND nome = ?
    """, (temporada_id, etapa_nome))
    etapa = cur.fetchone()
    if not etapa:
        conn.close()
        return None

    etapa_id = etapa["id"]

    cur.execute("SELECT tipo, piloto FROM resultados WHERE etapa_id = ?", (etapa_id,))
    resultados = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("""
        SELECT p.nome, pal.tipo, pal.piloto
        FROM palpites pal
        JOIN participantes p ON p.id = pal.participante_id
        WHERE pal.etapa_id = ?
        ORDER BY p.nome, pal.tipo
    """, (etapa_id,))
    palpites_raw = cur.fetchall()

    palpites = {}
    for row in palpites_raw:
        nome = row["nome"]
        if nome not in palpites:
            palpites[nome] = {}
        palpites[nome][row["tipo"]] = row["piloto"]

    cur.execute("""
        SELECT p.nome, pen.sessao, pen.aplicada
        FROM penalidades pen
        JOIN participantes p ON p.id = pen.participante_id
        WHERE pen.etapa_id = ? AND pen.aplicada = 1
    """, (etapa_id,))
    penalidades = {}
    for row in cur.fetchall():
        nome = row["nome"]
        if nome not in penalidades:
            penalidades[nome] = []
        penalidades[nome].append(row["sessao"])

    cur.execute("""
        SELECT p.nome, pt.pts_total
        FROM pontuacao pt
        JOIN participantes p ON p.id = pt.participante_id
        WHERE pt.etapa_id = ?
        ORDER BY pt.pts_total DESC
    """, (etapa_id,))
    pontuacao = {row[0]: row[1] for row in cur.fetchall()}

    conn.close()

    return {
        "nome":        etapa["nome"],
        "mult":        etapa["multiplicador"],
        "resultados":  resultados,
        "palpites":    palpites,
        "penalidades": penalidades,
        "pontuacao":   pontuacao,
    }


def get_capsula(temporada_id=1):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT p.nome, c.categoria, c.valor
        FROM capsula c
        JOIN participantes p ON p.id = c.participante_id
        WHERE c.temporada_id = ?
        ORDER BY p.nome, c.categoria
    """, (temporada_id,))
    palpites_raw = cur.fetchall()

    palpites = {}
    for row in palpites_raw:
        nome = row["nome"]
        if nome not in palpites:
            palpites[nome] = {}
        palpites[nome][row["categoria"]] = row["valor"]

    cur.execute("""
        SELECT p.nome, cp.pts_pilotos_exato, cp.pts_pilotos_trocado,
               cp.pts_equipes_exato, cp.pts_equipes_trocado,
               cp.pts_melhor_resto, cp.pts_gp2, cp.pts_total
        FROM capsula_pontuacao cp
        JOIN participantes p ON p.id = cp.participante_id
        WHERE cp.temporada_id = ?
        ORDER BY cp.pts_total DESC
    """, (temporada_id,))
    pontuacao = {row["nome"]: dict(row) for row in cur.fetchall()}

    cur.execute("""
        SELECT MAX(round) FROM standings_pilotos WHERE temporada_id = ?
    """, (temporada_id,))
    row = cur.fetchone()
    ultimo_round = row[0] if row and row[0] else None

    resultado = {"pilotos": [], "equipes": [], "melhor_resto": "", "gp2": ""}
    if ultimo_round:
        cur.execute("""
            SELECT piloto FROM standings_pilotos
            WHERE temporada_id = ? AND round = ?
            ORDER BY posicao LIMIT 6
        """, (temporada_id, ultimo_round))
        resultado["pilotos"] = [row[0] for row in cur.fetchall()]

        cur.execute("""
            SELECT equipe FROM standings_construtores
            WHERE temporada_id = ? AND round = ?
            ORDER BY posicao LIMIT 3
        """, (temporada_id, ultimo_round))
        resultado["equipes"] = [row[0] for row in cur.fetchall()]

        QUATRO_GRANDES = {"Mercedes", "Ferrari", "McLaren", "Red Bull", "Red Bull Racing"}
        cur.execute("""
            SELECT sp.piloto, sp.equipe FROM standings_pilotos sp
            WHERE sp.temporada_id = ? AND sp.round = ?
            ORDER BY sp.posicao
        """, (temporada_id, ultimo_round))
        for row in cur.fetchall():
            if row[1] not in QUATRO_GRANDES:
                resultado["melhor_resto"] = row[0]
                break

        cur.execute("""
            SELECT piloto FROM standings_pilotos
            WHERE temporada_id = ? AND round = ?
            ORDER BY posicao DESC LIMIT 1
        """, (temporada_id, ultimo_round))
        row = cur.fetchone()
        resultado["gp2"] = row[0] if row else ""

    conn.close()

    return {
        "palpites":  palpites,
        "pontuacao": pontuacao,
        "resultado": resultado,
    }


def run(temporada_id=1):
    """Executa calculo completo de pontuacao."""
    calcular_tudo(temporada_id, verbose=True)
    calcular_capsula(temporada_id, verbose=True)

    dados = get_ranking(temporada_id)
    print()
    print("=== RANKING ATUAL ===")
    medalhas = {1:"🥇", 2:"🥈", 3:"🥉"}
    for i, nome in enumerate(dados["ranking"], 1):
        d = dados["dados"][nome]
        total = d.get("total_com_descarte", d["total"])
        desc  = d.get("descarte", ("N/A", 0))
        m = medalhas.get(i, f"{i}.")
        print(f"  {m} {nome:10} {total:4} pts | descarte: {desc[0]} ({desc[1]}pt)")

    print()
    print(f"  Etapas: {dados['n_etapas']}/23")
    print(f"  {'Descarte APLICADO' if dados['todas_disp'] else 'Descarte sera aplicado ao final'}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO log_execucoes (tipo, status, mensagem)
        VALUES ('pontuacao', 'sucesso', ?)
    """, (f"Calculado {dados['n_etapas']} etapas",))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    run()

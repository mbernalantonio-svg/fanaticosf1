"""
F1 Bolao V2 — Motor de Pontuacao
Calcula pontos de todos os participantes em todas as etapas
e grava na tabela pontuacao do SQLite.
Substitui completamente o build_dashboard.py baseado em Excel.
"""

import sqlite3
import os
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

# Etapas da Reta Final e seus multiplicadores
RETA_FINAL = {
    "Catar":     2,
    "Abu Dhabi": 3,
}


def calcular_tudo(temporada_id=1, verbose=True):
    """
    Calcula pontuacao de todos os participantes em todas as etapas
    e grava na tabela pontuacao.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if verbose:
        print("=" * 55)
        print("  F1 BOLAO V2 — Calculando Pontuacao")
        print("=" * 55)

    # Busca participantes
    cur.execute("SELECT id, nome FROM participantes WHERE ativo = 1 ORDER BY nome")
    participantes = cur.fetchall()

    # Busca etapas com resultado
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

    # Busca campeao anterior (para regra Zebra 1a corrida)
    cur.execute("SELECT campeao_anterior FROM temporadas WHERE id = ?", (temporada_id,))
    row = cur.fetchone()
    campeao_anterior = row[0] if row else None

    total_calculados = 0

    for etapa in etapas:
        etapa_id   = etapa["id"]
        etapa_nome = etapa["nome"]
        mult       = etapa["multiplicador"]
        is_primeira = (etapa["round"] == 1)

        # Busca resultado da zebra (lider do campeonato antes da corrida)
        cur.execute("""
            SELECT piloto FROM resultados
            WHERE etapa_id = ? AND tipo = 'zebra'
        """, (etapa_id,))
        row = cur.fetchone()
        zebra_ref = row[0] if row else (campeao_anterior if is_primeira else None)

        # Busca vencedor da corrida (resultado P1)
        cur.execute("""
            SELECT piloto FROM resultados
            WHERE etapa_id = ? AND tipo = 'corrida_p1'
        """, (etapa_id,))
        row = cur.fetchone()
        vencedor_real = row[0] if row else None

        # Busca todos os resultados da etapa
        cur.execute("""
            SELECT tipo, piloto FROM resultados WHERE etapa_id = ?
        """, (etapa_id,))
        resultados = {row[0]: row[1] for row in cur.fetchall()}

        for part in participantes:
            part_id   = part["id"]
            part_nome = part["nome"]

            # Busca palpites do participante nesta etapa
            cur.execute("""
                SELECT tipo, piloto FROM palpites
                WHERE etapa_id = ? AND participante_id = ?
            """, (etapa_id, part_id))
            palpites = {row[0]: row[1] for row in cur.fetchall()}

            # Busca penalidades
            cur.execute("""
                SELECT sessao, aplicada FROM penalidades
                WHERE etapa_id = ? AND participante_id = ?
            """, (etapa_id, part_id))
            penalidades = {row[0]: row[1] for row in cur.fetchall()}

            # ── Calcula pontos ─────────────────────────────────────────────────

            pts_grid      = 0
            pts_corrida   = 0
            pts_pd        = 0
            pts_vr        = 0
            pts_zebra     = 0
            pts_penalidade = 0

            # Grid P1-P3
            for tipo in ["grid_p1", "grid_p2", "grid_p3"]:
                palp = palpites.get(tipo)
                real = resultados.get(tipo)
                if palp and real and palp == real:
                    pts_grid += PONTOS[tipo]

            # Corrida P1-P10
            for tipo in [f"corrida_p{i}" for i in range(1, 11)]:
                palp = palpites.get(tipo)
                real = resultados.get(tipo)
                if palp and real and palp == real:
                    pts_corrida += PONTOS[tipo]

            # PD
            palp_pd = palpites.get("pd")
            real_pd = resultados.get("pd")
            if palp_pd and real_pd and palp_pd == real_pd:
                pts_pd += PONTOS["pd"]

            # VR
            palp_vr = palpites.get("vr")
            real_vr = resultados.get("vr")
            if palp_vr and real_vr and palp_vr == real_vr:
                pts_vr += PONTOS["vr"]

            # Subtotal antes do multiplicador
            subtotal = pts_grid + pts_corrida + pts_pd + pts_vr

            # Aplica multiplicador da Reta Final
            subtotal_mult = subtotal * mult
            pts_grid    *= mult
            pts_corrida *= mult
            pts_pd      *= mult
            pts_vr      *= mult

            # Zebra (tambem multiplicada)
            palp_p1 = palpites.get("corrida_p1")
            if (palp_p1 and vencedor_real and zebra_ref and
                    palp_p1 == vencedor_real and palp_p1 != zebra_ref):
                pts_zebra = PONTOS["zebra"] * mult

            # Penalidades (tambem multiplicadas)
            if penalidades.get("treino") == 1:
                pts_penalidade += PONTOS["bp_treino"] * mult
            if penalidades.get("corrida") == 1:
                pts_penalidade += PONTOS["bp_corrida"] * mult

            # Total final
            pts_total = pts_grid + pts_corrida + pts_pd + pts_vr + pts_zebra + pts_penalidade
            pts_bruto = subtotal  # sem multiplicador, sem zebra, sem penalidade

            # Grava na tabela pontuacao
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
    """
    Calcula pontuacao da Capsula do Tempo comparando palpites
    com standings atuais do F1.com (tabela standings_pilotos/construtores).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if verbose:
        print("  Calculando Capsula do Tempo...")

    # Busca ultimo round com standings
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

    # Standings atuais de pilotos
    cur.execute("""
        SELECT posicao, piloto FROM standings_pilotos
        WHERE temporada_id = ? AND round = ?
        ORDER BY posicao
    """, (temporada_id, ultimo_round))
    stand_pilotos = {row[0]: row[1] for row in cur.fetchall()}

    # Standings atuais de construtores
    cur.execute("""
        SELECT posicao, equipe FROM standings_construtores
        WHERE temporada_id = ? AND round = ?
        ORDER BY posicao
    """, (temporada_id, ultimo_round))
    stand_construtores = {row[0]: row[1] for row in cur.fetchall()}

    # Melhor do Resto (primeiro piloto fora das 4 grandes)
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

    # GP2 — ultimo piloto no standings
    cur.execute("""
        SELECT piloto FROM standings_pilotos
        WHERE temporada_id = ? AND round = ?
        ORDER BY posicao DESC LIMIT 1
    """, (temporada_id, ultimo_round))
    row = cur.fetchone()
    gp2 = row[0] if row else None

    # Participantes
    cur.execute("SELECT id, nome FROM participantes WHERE ativo = 1")
    participantes = cur.fetchall()

    for part in participantes:
        part_id = part["id"]

        # Palpites da capsula
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

        # Pilotos P1-P6
        resultado_pilotos = [stand_pilotos.get(i, "") for i in range(1, 7)]
        for i in range(1, 7):
            palp = palpites_cap.get(f"piloto_p{i}", "")
            real = stand_pilotos.get(i, "")
            if palp and real:
                if palp == real:
                    pts_pilotos_exato += 10
                elif palp in resultado_pilotos:
                    pts_pilotos_trocado += 5

        # Equipes P1-P3
        resultado_equipes = [stand_construtores.get(i, "") for i in range(1, 4)]
        for i in range(1, 4):
            palp = palpites_cap.get(f"equipe_p{i}", "")
            real = stand_construtores.get(i, "")
            if palp and real:
                if palp == real:
                    pts_equipes_exato += 10
                elif palp in resultado_equipes:
                    pts_equipes_trocado += 5

        # Melhor do Resto
        palp_mr = palpites_cap.get("melhor_resto", "")
        if palp_mr and melhor_resto and palp_mr == melhor_resto:
            pts_melhor_resto = 10

        # GP2
        palp_gp2 = palpites_cap.get("gp2", "")
        if palp_gp2 and gp2 and palp_gp2 == gp2:
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
    """
    Retorna ranking atual com totais, descarte e acumulado.
    Usado pelo dashboard e pelo WhatsApp.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Busca etapas disputadas
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

    # Busca pontuacao por participante por etapa
    cur.execute("""
        SELECT p.nome, e.nome as etapa, e.round, pt.pts_total, pt.pts_bruto
        FROM pontuacao pt
        JOIN participantes p ON p.id = pt.participante_id
        JOIN etapas e ON e.id = pt.etapa_id
        WHERE e.temporada_id = ?
        ORDER BY p.nome, e.round
    """, (temporada_id,))
    rows = cur.fetchall()

    # Organiza por participante
    dados = {}
    for row in rows:
        nome = row["nome"]
        if nome not in dados:
            dados[nome] = {"pts_por_etapa": {}, "total": 0}
        dados[nome]["pts_por_etapa"][row["etapa"]] = row["pts_total"]
        dados[nome]["total"] += row["pts_total"]

    # Descarte — pior FDS (indicativo, aplicado apenas ao final)
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

    # Acumulado por etapa
    for nome in dados:
        acc = 0
        acumulado = []
        for etapa in etapas:
            pts = dados[nome]["pts_por_etapa"].get(etapa["nome"], 0)
            acc += pts
            acumulado.append(acc)
        dados[nome]["acumulado"] = acumulado

    # Ranking ordenado
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


def get_ultima_etapa(temporada_id=1):
    """Retorna dados da ultima etapa disputada."""
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

    # Pontuacao da ultima etapa
    cur.execute("""
        SELECT p.nome, pt.pts_total, pt.pts_grid, pt.pts_corrida,
               pt.pts_pd, pt.pts_vr, pt.pts_zebra, pt.pts_penalidade
        FROM pontuacao pt
        JOIN participantes p ON p.id = pt.participante_id
        WHERE pt.etapa_id = ?
        ORDER BY pt.pts_total DESC
    """, (etapa_id,))
    pontuacao = [dict(row) for row in cur.fetchall()]

    # Resultados da ultima etapa
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
    """Retorna palpites e resultados de uma etapa especifica."""
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

    # Resultados
    cur.execute("SELECT tipo, piloto FROM resultados WHERE etapa_id = ?", (etapa_id,))
    resultados = {row[0]: row[1] for row in cur.fetchall()}

    # Palpites por participante
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

    # Penalidades
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

    # Pontuacao
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
        "nome":       etapa["nome"],
        "mult":       etapa["multiplicador"],
        "resultados": resultados,
        "palpites":   palpites,
        "penalidades":penalidades,
        "pontuacao":  pontuacao,
    }


def get_capsula(temporada_id=1):
    """Retorna dados completos da Capsula do Tempo."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Palpites
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

    # Pontuacao
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

    # Resultado parcial (ultimo round dos standings)
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

    # Exibe ranking
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

    # Registra no log
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO log_execucoes (tipo, status, mensagem)
        VALUES ('pontuacao', 'sucesso', ?)
    """, (f"Calculado {dados['n_etapas']} etapas",))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    run()
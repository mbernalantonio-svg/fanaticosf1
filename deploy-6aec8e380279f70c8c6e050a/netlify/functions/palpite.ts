import type { Config } from "@netlify/functions";

// Servidor de palpites/ranking (mesmo usado pela página).
const BACKEND = "https://mbernalantonio.pythonanywhere.com";

// Horários do backend estão em horário de Brasília (UTC-3, sem horário de verão).
const brt = (s: string) => new Date(s.replace(" ", "T") + (s.length <= 16 ? ":00" : "") + "-03:00");

// Pilotos que não correm em determinada etapa (substituídos).
const SUBSTITUIDOS: Record<string, string[]> = {
  Brasil: ["Esteban Ocon"],
};

// Antecedência mínima exigida do líder do bolão (regulamento: 10 minutos antes do início).
const ANTECEDENCIA_LIDER_MS = 10 * 60 * 1000;
// Punição do líder que não envia com a antecedência mínima.
const PUNICAO_LIDER: Record<string, number> = { classificacao: 2, corrida: 10 };

// Líder(es) do bolão pelo ranking atual (resultado da última etapa disputada). Empate no topo conta como líder.
async function lideres(apiKey: string): Promise<string[]> {
  try {
    const r = await fetch(`${BACKEND}/api/ranking`, { headers: { "X-API-Key": apiKey } });
    if (!r.ok) return [];
    const d = await r.json();
    const nomes: string[] = d.ranking ?? [];
    const pts = (n: string) => Number(d.dados?.[n]?.total_com_descarte ?? d.dados?.[n]?.total ?? 0);
    if (!nomes.length || pts(nomes[0]) <= 0) return [];
    const topo = pts(nomes[0]);
    return nomes.filter((n) => pts(n) === topo);
  } catch {
    return [];
  }
}

const recusa = (erro: string, status = 400) => Response.json({ sucesso: false, erro }, { status });

type Sessao = { sessao: string; inicio?: string; corte?: string };
type Etapa = { etapa: string; sessoes: Sessao[] };

export default async (req: Request) => {
  if (req.method !== "POST") return recusa("Método não permitido", 405);

  const apiKey = req.headers.get("x-api-key") ?? "";
  let body: { participante?: string; etapa?: string; sessao?: string; palpites?: Record<string, string> };
  try {
    body = await req.json();
  } catch {
    return recusa("Requisição inválida");
  }
  // Visitantes (ou envios sem participante) não podem gravar palpites.
  const participante = String(body.participante ?? "").trim();
  if (!participante || participante.toLowerCase() === "visitante") {
    return recusa("Visitantes não podem enviar palpites.", 403);
  }
  const { etapa, sessao } = body;
  if (!etapa || !sessao) return recusa("Selecione uma sessão");

  // Busca o horário oficial de início da sessão.
  let etapas: Etapa[];
  try {
    const r = await fetch(`${BACKEND}/api/etapas_abertas`, { headers: { "X-API-Key": apiKey } });
    if (!r.ok) return recusa("Erro ao consultar horários", 502);
    etapas = ((await r.json()).etapas_abertas ?? []) as Etapa[];
  } catch {
    return recusa("Erro ao consultar horários", 502);
  }

  const s = etapas.find((e) => e.etapa === etapa)?.sessoes.find((x) => x.sessao === sessao);
  const inicio = s?.inicio ?? s?.corte;
  // Palpite aceito até 1 segundo antes do início oficial (ex.: início 14:00:00 → até 13:59:59).
  if (!s || !inicio || Date.now() >= brt(inicio).getTime()) {
    return recusa("Prazo encerrado: a sessão já começou. Palpite não registrado.", 403);
  }

  // Todos os palpites da sessão são obrigatórios.
  const obrigatorios =
    sessao === "classificacao"
      ? ["grid_p1", "grid_p2", "grid_p3", "pd"]
      : [...Array.from({ length: 10 }, (_, i) => `corrida_p${i + 1}`), "vr"];
  const p0 = body.palpites ?? {};
  if (obrigatorios.some((k) => !p0[k])) {
    return recusa("Preencha todos os palpites da sessão antes de enviar.");
  }

  // Mesmo piloto não pode repetir entre P1–P3 (classificação) ou P1–P10 (corrida). PD e VR livres.
  const palpites = body.palpites ?? {};
  const unicos = Object.entries(palpites)
    .filter(([k, v]) => v && /^(grid|corrida)_p\d+$/.test(k))
    .map(([, v]) => v);
  if (new Set(unicos).size !== unicos.length) {
    return recusa("O mesmo piloto não pode ser escolhido em mais de uma posição.");
  }

  // Pilotos substituídos não podem ser escolhidos na etapa.
  const fora = SUBSTITUIDOS[etapa] ?? [];
  if (Object.values(palpites).some((v) => fora.includes(v))) {
    return recusa(`Piloto não participa desta etapa: ${fora.join(", ")}`);
  }

  // O líder que envia com menos de 10 minutos de antecedência sofre a punição do regulamento.
  const atrasoLider =
    brt(inicio).getTime() - Date.now() < ANTECEDENCIA_LIDER_MS && (await lideres(apiKey)).includes(participante);

  const r = await fetch(`${BACKEND}/api/palpite`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify(body),
  });
  const texto = await r.text();
  if (atrasoLider) {
    try {
      const resp = JSON.parse(texto);
      if (resp.sucesso) {
        resp.penalidade_lider = { pontos: PUNICAO_LIDER[sessao] ?? 0, sessao };
        return Response.json(resp, { status: r.status });
      }
    } catch {}
  }
  return new Response(texto, {
    status: r.status,
    headers: { "Content-Type": r.headers.get("content-type") ?? "application/json" },
  });
};

export const config: Config = {
  path: "/api/palpite",
};

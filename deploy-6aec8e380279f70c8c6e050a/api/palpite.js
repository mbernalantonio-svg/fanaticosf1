const BACKEND = "https://mbernalantonio.pythonanywhere.com";
const brt = (s) => new Date(s.replace(" ", "T") + (s.length <= 16 ? ":00" : "") + "-03:00");
const SUBSTITUIDOS = { Brasil: ["Esteban Ocon"] };
const ANTECEDENCIA_LIDER_MS = 10 * 60 * 1000;
const PUNICAO_LIDER = { classificacao: 2, corrida: 10 };

async function lideres(apiKey) {
  try {
    const r = await fetch(`${BACKEND}/api/ranking`, { headers: { "X-API-Key": apiKey } });
    if (!r.ok) return [];
    const d = await r.json();
    const nomes = d.ranking ?? [];
    const pts = (n) => Number(d.dados?.[n]?.total_com_descarte ?? d.dados?.[n]?.total ?? 0);
    if (!nomes.length || pts(nomes[0]) <= 0) return [];
    const topo = pts(nomes[0]);
    return nomes.filter((n) => pts(n) === topo);
  } catch { return []; }
}

export default async function handler(req, res) {
  if (req.method !== "POST")
    return res.status(405).json({ sucesso: false, erro: "Método não permitido" });

  const apiKey = req.headers["x-api-key"] ?? "";
  const body = req.body || {};
  const participante = String(body.participante ?? "").trim();

  if (!participante || participante.toLowerCase() === "visitante")
    return res.status(403).json({ sucesso: false, erro: "Visitantes não podem enviar palpites." });

  const { etapa, sessao, palpites: p0 = {} } = body;
  if (!etapa || !sessao)
    return res.status(400).json({ sucesso: false, erro: "Selecione uma sessão" });

  let etapas;
  try {
    const r = await fetch(`${BACKEND}/api/etapas_abertas`, { headers: { "X-API-Key": apiKey } });
    if (!r.ok) return res.status(502).json({ sucesso: false, erro: "Erro ao consultar horários" });
    etapas = (await r.json()).etapas_abertas ?? [];
  } catch {
    return res.status(502).json({ sucesso: false, erro: "Erro ao consultar horários" });
  }

  const etapaObj = etapas.find((e) => e.etapa === etapa);
  const sessaoObj = etapaObj?.sessoes?.find((x) => x.sessao === sessao);
  const inicio = sessaoObj?.inicio ?? sessaoObj?.corte;

  if (!sessaoObj || !inicio || Date.now() >= brt(inicio).getTime())
    return res.status(403).json({ sucesso: false, erro: "Prazo encerrado: a sessão já começou. Palpite não registrado." });

  const obrigatorios = sessao === "classificacao"
    ? ["grid_p1", "grid_p2", "grid_p3", "pd"]
    : [...Array.from({ length: 10 }, (_, i) => `corrida_p${i + 1}`), "vr"];

  if (obrigatorios.some((k) => !p0[k]))
    return res.status(400).json({ sucesso: false, erro: "Preencha todos os palpites da sessão antes de enviar." });

  const unicos = Object.entries(p0)
    .filter(([k, v]) => v && /^(grid|corrida)_p\d+$/.test(k))
    .map(([, v]) => v);
  if (new Set(unicos).size !== unicos.length)
    return res.status(400).json({ sucesso: false, erro: "O mesmo piloto não pode ser escolhido em mais de uma posição." });

  const fora = SUBSTITUIDOS[etapa] ?? [];
  if (Object.values(p0).some((v) => fora.includes(v)))
    return res.status(400).json({ sucesso: false, erro: `Piloto não participa desta etapa: ${fora.join(", ")}` });

  const atrasoLider =
    brt(inicio).getTime() - Date.now() < ANTECEDENCIA_LIDER_MS &&
    (await lideres(apiKey)).includes(participante);

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
        return res.status(r.status).json(resp);
      }
    } catch {}
  }

  res.setHeader("Content-Type", r.headers.get("content-type") ?? "application/json");
  return res.status(r.status).send(texto);
}

import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";
import { neon } from "@neondatabase/serverless";

const SENHAS_INICIAIS = {
  Bernal: "bernal26", Consta: "consta26", Donato: "donato26",
  Japa: "japa26", Jota: "jota26", Kesper: "kesper26",
  Pierre: "pierre26", San: "san26",
};

function hashSenha(senha) {
  const salt = randomBytes(16).toString("hex");
  return `${salt}:${scryptSync(senha, salt, 64).toString("hex")}`;
}

function confereSenha(senha, guardado) {
  const [salt, h] = guardado.split(":");
  const a = Buffer.from(h, "hex");
  const b = scryptSync(senha, salt, 64);
  return a.length === b.length && timingSafeEqual(a, b);
}

async function verificar(sql, nome, senha) {
  if (!(nome in SENHAS_INICIAIS)) return { ok: false, primeiroAcesso: false };
  const rows = await sql`SELECT senha_hash FROM senhas WHERE nome = ${nome}`;
  if (rows.length > 0) return { ok: confereSenha(senha, rows[0].senha_hash), primeiroAcesso: false };
  return { ok: senha === SENHAS_INICIAIS[nome], primeiroAcesso: true };
}

export default async function handler(req, res) {
  if (req.method !== "POST")
    return res.status(405).json({ ok: false, erro: "Método não permitido" });

  const sql = neon(process.env.DATABASE_URL);
  await sql`CREATE TABLE IF NOT EXISTS senhas (
    nome TEXT PRIMARY KEY,
    senha_hash TEXT NOT NULL,
    atualizado_em TIMESTAMPTZ DEFAULT now()
  )`;

  const { nome, senha, novaSenha } = req.body || {};
  const acao = req.url.split("/").pop();

  if (!nome || !senha)
    return res.status(400).json({ ok: false, erro: "Nome e senha são obrigatórios." });

  const v = await verificar(sql, String(nome), String(senha));
  if (!v.ok)
    return res.status(401).json({ ok: false, erro: "Senha incorreta. Tente novamente." });

  if (acao === "login")
    return res.status(200).json({ ok: true, primeiroAcesso: v.primeiroAcesso });

  if (acao === "trocar-senha") {
    const nova = String(novaSenha || "");
    if (nova.length < 4)
      return res.status(400).json({ ok: false, erro: "A nova senha precisa ter pelo menos 4 caracteres." });
    if (nova === String(senha))
      return res.status(400).json({ ok: false, erro: "A nova senha precisa ser diferente da atual." });
    const senhaHash = hashSenha(nova);
    await sql`INSERT INTO senhas (nome, senha_hash) VALUES (${String(nome)}, ${senhaHash})
      ON CONFLICT (nome) DO UPDATE SET senha_hash = ${senhaHash}, atualizado_em = now()`;
    return res.status(200).json({ ok: true });
  }

  return res.status(404).json({ ok: false, erro: "Ação desconhecida." });
}

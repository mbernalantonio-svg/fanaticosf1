import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";
import { neon } from "@neondatabase/serverless";
import { Resend } from "resend";

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

function gerarCodigo() {
  return Math.floor(100000 + Math.random() * 900000).toString();
}

async function verificar(sql, nome, senha) {
  if (!(nome in SENHAS_INICIAIS)) return { ok: false, primeiroAcesso: false };
  const rows = await sql`SELECT senha_hash FROM senhas WHERE nome = ${nome}`;
  if (rows.length > 0) return { ok: confereSenha(senha, rows[0].senha_hash), primeiroAcesso: false };
  return { ok: senha === SENHAS_INICIAIS[nome], primeiroAcesso: true };
}

export default async function handler(req, res) {
  if (req.method !== "POST")
    return res.status(405).json({ ok: false, erro: "Metodo nao permitido" });

  const sql = neon(process.env.DATABASE_URL);

  // Garante estrutura do banco
  await sql`CREATE TABLE IF NOT EXISTS senhas (
    nome TEXT PRIMARY KEY,
    senha_hash TEXT NOT NULL,
    email TEXT,
    atualizado_em TIMESTAMPTZ DEFAULT now()
  )`;
  // Adiciona coluna email se nao existir
  try {
    await sql`ALTER TABLE senhas ADD COLUMN IF NOT EXISTS email TEXT`;
  } catch(e) {}
  // Tabela de codigos de reset
  await sql`CREATE TABLE IF NOT EXISTS codigos_reset (
    nome TEXT PRIMARY KEY,
    codigo TEXT NOT NULL,
    expira_em TIMESTAMPTZ NOT NULL
  )`;

  const { nome, senha, novaSenha, email, codigo, nomeReset } = req.body || {};
  const acao = req.url.split("/").pop();

  // ── Reset admin ──────────────────────────────────────────────────────────
  if (acao === "reset-senha") {
    const adminKey = req.headers["x-admin-key"] || "";
    if (adminKey !== "f1bolao2027adminreset")
      return res.status(403).json({ ok: false, erro: "Acesso negado." });
    const nr = String(nomeReset || "");
    if (!nr || !(nr in SENHAS_INICIAIS))
      return res.status(400).json({ ok: false, erro: "Participante invalido." });
    await sql`DELETE FROM senhas WHERE nome = ${nr}`;
    await sql`DELETE FROM codigos_reset WHERE nome = ${nr}`;
    return res.status(200).json({ ok: true, mensagem: `Senha de ${nr} resetada.` });
  }

  // ── Esqueci minha senha - envia codigo por email ──────────────────────────
  if (acao === "esqueci-senha") {
    const nomeEsq = String(nome || "").trim();
    if (!nomeEsq || !(nomeEsq in SENHAS_INICIAIS))
      return res.status(400).json({ ok: false, erro: "Participante nao encontrado." });

    // Busca email cadastrado
    const rows = await sql`SELECT email FROM senhas WHERE nome = ${nomeEsq}`;
    const emailCad = rows[0]?.email;
    if (!emailCad)
      return res.status(400).json({ ok: false, erro: "Nenhum email cadastrado para este participante. Entre em contato com o administrador." });

    // Gera codigo de 6 digitos valido por 15 minutos
    const cod = gerarCodigo();
    const expira = new Date(Date.now() + 15 * 60 * 1000).toISOString();
    await sql`INSERT INTO codigos_reset (nome, codigo, expira_em) VALUES (${nomeEsq}, ${cod}, ${expira})
      ON CONFLICT (nome) DO UPDATE SET codigo = ${cod}, expira_em = ${expira}`;

    // Envia email via Resend
    const resend = new Resend(process.env.RESEND_API_KEY);
    const { error } = await resend.emails.send({
      from: "F1 Bolao <onboarding@resend.dev>",
      to: emailCad,
      subject: "Codigo de recuperacao - F1 Bolao 2026",
      html: `
        <div style="font-family:Arial,sans-serif;max-width:400px;margin:0 auto;padding:20px;">
          <h2 style="color:#E10600;">F1 Bolao 2026</h2>
          <p>Ola, <strong>${nomeEsq}</strong>!</p>
          <p>Seu codigo de recuperacao de senha e:</p>
          <div style="background:#f4f4f4;border-radius:8px;padding:20px;text-align:center;margin:20px 0;">
            <span style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#E10600;">${cod}</span>
          </div>
          <p style="color:#666;font-size:14px;">Este codigo expira em <strong>15 minutos</strong>.</p>
          <p style="color:#666;font-size:14px;">Se voce nao solicitou a recuperacao, ignore este email.</p>
          <hr style="border:none;border-top:1px solid #ddd;margin:20px 0;">
          <p style="color:#999;font-size:12px;">Fanaticos por F1 - Bolao 2026</p>
        </div>
      `
    });

    if (error)
      return res.status(500).json({ ok: false, erro: "Erro ao enviar email. Tente novamente." });

    return res.status(200).json({ ok: true, mensagem: `Codigo enviado para ${emailCad.replace(/(.{2}).*(@.*)/, "$1***$2")}` });
  }

  // ── Verificar codigo e trocar senha ──────────────────────────────────────
  if (acao === "verificar-codigo") {
    const nomeV = String(nome || "").trim();
    const codigoV = String(codigo || "").trim();
    const novaSenhaV = String(novaSenha || "").trim();

    if (!nomeV || !codigoV || !novaSenhaV)
      return res.status(400).json({ ok: false, erro: "Dados incompletos." });
    if (novaSenhaV.length < 4)
      return res.status(400).json({ ok: false, erro: "A nova senha precisa ter pelo menos 4 caracteres." });

    const rows = await sql`SELECT codigo, expira_em FROM codigos_reset WHERE nome = ${nomeV}`;
    if (!rows.length)
      return res.status(400).json({ ok: false, erro: "Nenhum codigo solicitado para este participante." });

    const { codigo: codSalvo, expira_em } = rows[0];
    if (new Date() > new Date(expira_em))
      return res.status(400).json({ ok: false, erro: "Codigo expirado. Solicite um novo." });
    if (codigoV !== codSalvo)
      return res.status(400).json({ ok: false, erro: "Codigo incorreto." });

    // Atualiza senha
    const senhaHash = hashSenha(novaSenhaV);
    await sql`INSERT INTO senhas (nome, senha_hash) VALUES (${nomeV}, ${senhaHash})
      ON CONFLICT (nome) DO UPDATE SET senha_hash = ${senhaHash}, atualizado_em = now()`;
    await sql`DELETE FROM codigos_reset WHERE nome = ${nomeV}`;

    return res.status(200).json({ ok: true, mensagem: "Senha alterada com sucesso!" });
  }

  // ── Login ─────────────────────────────────────────────────────────────────
  if (!nome || !senha)
    return res.status(400).json({ ok: false, erro: "Nome e senha sao obrigatorios." });

  const v = await verificar(sql, String(nome), String(senha));
  if (!v.ok)
    return res.status(401).json({ ok: false, erro: "Senha incorreta. Tente novamente." });

  if (acao === "login")
    return res.status(200).json({ ok: true, primeiroAcesso: v.primeiroAcesso });

  // ── Cadastro (primeiro acesso com email) ──────────────────────────────────
  if (acao === "cadastro") {
    const emailV = String(email || "").trim().toLowerCase();
    const novaV  = String(novaSenha || "").trim();

    if (!emailV || !emailV.includes("@"))
      return res.status(400).json({ ok: false, erro: "Email invalido." });
    if (novaV.length < 4)
      return res.status(400).json({ ok: false, erro: "A senha precisa ter pelo menos 4 caracteres." });
    if (novaV === String(senha))
      return res.status(400).json({ ok: false, erro: "A nova senha precisa ser diferente da inicial." });

    const senhaHash = hashSenha(novaV);
    await sql`INSERT INTO senhas (nome, senha_hash, email) VALUES (${String(nome)}, ${senhaHash}, ${emailV})
      ON CONFLICT (nome) DO UPDATE SET senha_hash = ${senhaHash}, email = ${emailV}, atualizado_em = now()`;

    return res.status(200).json({ ok: true });
  }

  // ── Trocar senha (voluntaria) ─────────────────────────────────────────────
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

  return res.status(404).json({ ok: false, erro: "Acao desconhecida." });
}

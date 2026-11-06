import type { Config } from "@netlify/functions";
import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";
import { eq } from "drizzle-orm";
import { db } from "../../db/index.js";
import { senhas } from "../../db/schema.js";

// Senhas iniciais (usadas só até o participante criar a própria senha).
const SENHAS_INICIAIS: Record<string, string> = {
  Bernal: "bernal26",
  Consta: "consta26",
  Donato: "donato26",
  Japa: "japa26",
  Jota: "jota26",
  Kesper: "kesper26",
  Pierre: "pierre26",
  San: "san26",
};

const hash = (senha: string) => {
  const salt = randomBytes(16).toString("hex");
  return `${salt}:${scryptSync(senha, salt, 64).toString("hex")}`;
};

const confere = (senha: string, guardado: string) => {
  const [salt, h] = guardado.split(":");
  const a = Buffer.from(h, "hex");
  const b = scryptSync(senha, salt, 64);
  return a.length === b.length && timingSafeEqual(a, b);
};

// Retorna { ok, primeiroAcesso }
async function verificar(nome: string, senha: string) {
  if (!(nome in SENHAS_INICIAIS)) return { ok: false, primeiroAcesso: false };
  const [linha] = await db.select().from(senhas).where(eq(senhas.nome, nome));
  if (linha) return { ok: confere(senha, linha.senhaHash), primeiroAcesso: false };
  return { ok: senha === SENHAS_INICIAIS[nome], primeiroAcesso: true };
}

const erro = (msg: string, status = 400) => Response.json({ ok: false, erro: msg }, { status });

export default async (req: Request) => {
  if (req.method !== "POST") return erro("Método não permitido", 405);

  let body: any;
  try { body = await req.json(); } catch { return erro("Requisição inválida"); }
  const nome = String(body.nome || "");
  const senha = String(body.senha || "");
  const acao = new URL(req.url).pathname.split("/").pop();

  const v = await verificar(nome, senha);
  if (!v.ok) return erro("Senha incorreta. Tente novamente.", 401);

  if (acao === "login") {
    return Response.json({ ok: true, primeiroAcesso: v.primeiroAcesso });
  }

  if (acao === "trocar-senha") {
    const nova = String(body.novaSenha || "");
    if (nova.length < 4) return erro("A nova senha precisa ter pelo menos 4 caracteres.");
    if (nova === senha) return erro("A nova senha precisa ser diferente da atual.");
    const senhaHash = hash(nova);
    await db
      .insert(senhas)
      .values({ nome, senhaHash })
      .onConflictDoUpdate({ target: senhas.nome, set: { senhaHash, atualizadoEm: new Date() } });
    return Response.json({ ok: true });
  }

  return erro("Ação desconhecida", 404);
};

export const config: Config = {
  path: ["/api/auth/login", "/api/auth/trocar-senha"],
};

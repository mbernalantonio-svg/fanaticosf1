import { pgTable, text, timestamp } from "drizzle-orm/pg-core";

// Participantes que já trocaram a senha inicial.
// Se o participante não tem linha aqui, ainda usa a senha inicial (primeiro acesso).
export const senhas = pgTable("senhas", {
  nome: text().primaryKey(),
  senhaHash: text("senha_hash").notNull(),
  atualizadoEm: timestamp("atualizado_em").defaultNow().notNull(),
});

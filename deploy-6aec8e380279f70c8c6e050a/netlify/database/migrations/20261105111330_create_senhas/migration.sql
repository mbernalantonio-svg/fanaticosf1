CREATE TABLE "senhas" (
	"nome" text PRIMARY KEY,
	"senha_hash" text NOT NULL,
	"atualizado_em" timestamp DEFAULT now() NOT NULL
);

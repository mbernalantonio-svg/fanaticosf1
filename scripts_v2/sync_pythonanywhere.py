"""
sync_pythonanywhere.py - Envia o bolao.db atualizado para o PythonAnywhere
Garante que o backend consumido pelo frontend na Vercel reflita 100% dos dados calculados.
"""

import os
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bolao.db")

API_URL = "https://mbernalantonio.pythonanywhere.com/api/sync/db"
API_KEY = "f1bolao2027secretkey"

def sincronizar_banco():
    if not os.path.exists(DB_PATH):
        print(f"❌ Arquivo {DB_PATH} nao encontrado para sincronizacao.")
        return False

    print(f"🚀 Enviando {DB_PATH} para o PythonAnywhere ({API_URL})...")
    headers = {"X-API-Key": API_KEY}

    with open(DB_PATH, "rb") as f:
        files = {"file": ("bolao.db", f, "application/octet-stream")}
        try:
            resp = requests.post(API_URL, headers=headers, files=files, timeout=30)
            if resp.status_code == 200:
                print(f"  ✅ Sucesso: {resp.json().get('mensagem')}")
                return True
            else:
                print(f"  ❌ Falha no envio: {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            print(f"  ❌ Erro de conexao: {e}")
            return False

if __name__ == "__main__":
    sincronizar_banco()

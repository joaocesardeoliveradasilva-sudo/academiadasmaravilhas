import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BANCO = os.path.join(BASE_DIR, "academia.db")


def conectar():
    conexao = sqlite3.connect(BANCO)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


def _adicionar_coluna(conexao, tabela, coluna, definicao):
    existentes = {linha[1] for linha in conexao.execute(f"PRAGMA table_info({tabela})")}
    if coluna not in existentes:
        conexao.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")


def criar_banco():
    conexao = conectar()
    cursor = conexao.cursor()
    perfil_existia = "perfil" in {
        linha[1] for linha in cursor.execute("PRAGMA table_info(usuarios)")
    }

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            perfil TEXT NOT NULL DEFAULT 'aluno'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alunos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT,
            telefone TEXT,
            idade INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS professores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT,
            telefone TEXT,
            especialidade TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS planos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            preco REAL NOT NULL,
            duracao INTEGER,
            descricao TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id INTEGER NOT NULL,
            valor REAL NOT NULL,
            data TEXT NOT NULL,
            forma TEXT,
            status TEXT NOT NULL DEFAULT 'Pago',
            FOREIGN KEY (aluno_id) REFERENCES alunos(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS treinos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id INTEGER NOT NULL,
            professor_id INTEGER,
            nome TEXT NOT NULL,
            descricao TEXT,
            divisao TEXT,
            FOREIGN KEY (aluno_id) REFERENCES alunos(id) ON DELETE CASCADE,
            FOREIGN KEY (professor_id) REFERENCES professores(id) ON DELETE SET NULL
        )
    """)

    _adicionar_coluna(conexao, "planos", "duracao", "INTEGER")
    _adicionar_coluna(conexao, "usuarios", "perfil", "TEXT NOT NULL DEFAULT 'aluno'")
    if not perfil_existia:
        conexao.execute("UPDATE usuarios SET perfil = 'admin'")
    _adicionar_coluna(conexao, "pagamentos", "forma", "TEXT")
    _adicionar_coluna(conexao, "pagamentos", "plano_id", "INTEGER REFERENCES planos(id)")
    _adicionar_coluna(conexao, "treinos", "professor_id", "INTEGER")
    _adicionar_coluna(conexao, "treinos", "divisao", "TEXT")

    conexao.commit()
    conexao.close()


if __name__ == "__main__":
    criar_banco()
    print("Banco SQLite criado com sucesso!")
    print(f"Local: {BANCO}")
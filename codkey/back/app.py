from pathlib import Path
from functools import wraps
import os
import secrets

from flask import Flask, g, jsonify, redirect, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

from database import conectar, criar_banco

BASE_DIR = Path(__file__).resolve().parent.parent
HTML_DIR = BASE_DIR / "html"
CSS_DIR = BASE_DIR / "css"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
criar_banco()


def acesso(perfis=None):
    def decorar(funcao):
        @wraps(funcao)
        def protegida(*args, **kwargs):
            usuario_id = session.get("usuario_id")
            if not usuario_id:
                return jsonify({"erro": "Faça login para continuar."}), 401

            conexao = conectar()
            try:
                usuario = conexao.execute(
                    "SELECT id, nome, email, perfil FROM usuarios WHERE id = ?",
                    (usuario_id,),
                ).fetchone()
            finally:
                conexao.close()

            if not usuario:
                session.clear()
                return jsonify({"erro": "Faça login para continuar."}), 401
            if perfis and usuario["perfil"] not in perfis:
                return jsonify({"erro": "Você não tem permissão para acessar este recurso."}), 403

            g.usuario = usuario
            return funcao(*args, **kwargs)
        return protegida
    return decorar


PAGINAS_POR_PERFIL = {
    "admin": {
        "paginainicial.html", "aluno.html", "prof.html", "planos.html",
        "pagamentos.html", "treino.html", "usuarios.html",
    },
    "professor": {"aluno.html", "treino.html"},
    "aluno": {"planos.html", "treino.html"},
}


def texto(value):
    return str(value).strip() if value is not None else ""


def inteiro(value, campo):
    try:
        resultado = int(value)
        if resultado < 0:
            raise ValueError
        return resultado
    except (TypeError, ValueError):
        return None


@app.route("/")
def inicio():
    return send_from_directory(str(HTML_DIR), "login.html")


@app.route("/<path:nome>")
def paginas(nome):
    if nome.startswith("api/"):
        return jsonify({"erro": "Endpoint não encontrado."}), 404
    if nome.endswith(".html") and nome not in {"login.html", "cadastroal.html"}:
        usuario_id = session.get("usuario_id")
        if not usuario_id:
            return redirect("/login.html")
        conexao = conectar()
        try:
            usuario = conexao.execute(
                "SELECT perfil FROM usuarios WHERE id = ?", (usuario_id,)
            ).fetchone()
        finally:
            conexao.close()
        if not usuario or nome not in PAGINAS_POR_PERFIL.get(usuario["perfil"], set()):
            return redirect("/treino.html" if usuario and usuario["perfil"] != "admin" else "/login.html")
    return send_from_directory(str(HTML_DIR), nome)


@app.route("/css/<path:nome>")
def arquivos_css(nome):
    return send_from_directory(str(CSS_DIR), nome)


@app.route("/api/cadastro", methods=["POST"])
def cadastro():
    dados = request.get_json(silent=True) or {}
    nome = texto(dados.get("nome"))
    email = texto(dados.get("email")).lower()
    senha = texto(dados.get("senha"))

    if not nome or not email or len(senha) < 6:
        return jsonify({"erro": "Informe nome, e-mail válido e uma senha com pelo menos 6 caracteres."}), 400

    conexao = conectar()
    try:
        conexao.execute("BEGIN IMMEDIATE")
        existente = conexao.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).fetchone()
        if existente:
            return jsonify({"erro": "Este e-mail já está cadastrado."}), 409
        quantidade = conexao.execute("SELECT COUNT(*) AS total FROM usuarios").fetchone()["total"]
        perfil = "admin" if quantidade == 0 else "aluno"
        cursor = conexao.execute(
            "INSERT INTO usuarios (nome, email, senha, perfil) VALUES (?, ?, ?, ?)",
            (nome, email, generate_password_hash(senha), perfil),
        )
        if perfil == "aluno" and not conexao.execute(
            "SELECT id FROM alunos WHERE lower(email) = ?", (email,)
        ).fetchone():
            conexao.execute("INSERT INTO alunos (nome, email) VALUES (?, ?)", (nome, email))
        conexao.commit()
        return jsonify({"mensagem": "Conta criada com sucesso.", "id": cursor.lastrowid, "perfil": perfil}), 201
    finally:
        conexao.close()


@app.route("/api/login", methods=["POST"])
def login():
    dados = request.get_json(silent=True) or {}
    email = texto(dados.get("email")).lower()
    senha = texto(dados.get("senha"))

    if not email or not senha:
        return jsonify({"erro": "Informe e-mail e senha."}), 400

    conexao = conectar()
    try:
        usuario = conexao.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()
        if not usuario or not check_password_hash(usuario["senha"], senha):
            return jsonify({"erro": "E-mail ou senha incorretos."}), 401
        session.clear()
        session["usuario_id"] = usuario["id"]
        return jsonify({"usuario": {
            "id": usuario["id"],
            "nome": usuario["nome"],
            "email": usuario["email"],
            "perfil": usuario["perfil"],
        }})
    finally:
        conexao.close()


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"mensagem": "Sessão encerrada."})


@app.route("/api/sessao")
@acesso()
def sessao_atual():
    return jsonify({"usuario": dict(g.usuario)})


@app.route("/api/usuarios", methods=["GET", "POST", "PATCH"])
@acesso(("admin",))
def usuarios():
    conexao = conectar()
    try:
        if request.method == "GET":
            linhas = conexao.execute(
                "SELECT id, nome, email, perfil FROM usuarios ORDER BY nome"
            ).fetchall()
            return jsonify([dict(linha) for linha in linhas])

        dados = request.get_json(silent=True) or {}
        if request.method == "POST":
            nome = texto(dados.get("nome"))
            email = texto(dados.get("email")).lower()
            senha = texto(dados.get("senha"))
            perfil = texto(dados.get("perfil")).lower()

            if not nome or not email or len(senha) < 6:
                return jsonify({"erro": "Informe nome, e-mail e uma senha com pelo menos 6 caracteres."}), 400
            if perfil not in {"admin", "professor", "aluno"}:
                return jsonify({"erro": "Selecione um cargo válido."}), 400

            conexao.execute("BEGIN IMMEDIATE")
            existente = conexao.execute(
                "SELECT id FROM usuarios WHERE email = ?", (email,)
            ).fetchone()
            if existente:
                return jsonify({"erro": "Este e-mail já está cadastrado."}), 409

            cursor = conexao.execute(
                "INSERT INTO usuarios (nome, email, senha, perfil) VALUES (?, ?, ?, ?)",
                (nome, email, generate_password_hash(senha), perfil),
            )
            if perfil == "aluno":
                aluno = conexao.execute(
                    "SELECT id FROM alunos WHERE lower(email) = ?", (email,)
                ).fetchone()
                if not aluno:
                    conexao.execute(
                        "INSERT INTO alunos (nome, email) VALUES (?, ?)",
                        (nome, email),
                    )
            elif perfil == "professor":
                professor = conexao.execute(
                    "SELECT id FROM professores WHERE lower(email) = ?", (email,)
                ).fetchone()
                if not professor:
                    conexao.execute(
                        "INSERT INTO professores (nome, email) VALUES (?, ?)",
                        (nome, email),
                    )

            conexao.commit()
            return jsonify({
                "mensagem": f"{nome} foi cadastrado como {perfil}.",
                "id": cursor.lastrowid,
                "perfil": perfil,
            }), 201

        usuario_id = inteiro(dados.get("id"), "id")
        perfil = texto(dados.get("perfil")).lower()
        if usuario_id is None:
            return jsonify({"erro": "Selecione um usuário válido."}), 400
        if perfil not in {"admin", "professor", "aluno"}:
            return jsonify({"erro": "O cargo informado é inválido."}), 400

        conexao.execute("BEGIN IMMEDIATE")
        usuario = conexao.execute(
            "SELECT id, nome, email, perfil FROM usuarios WHERE id = ?",
            (usuario_id,),
        ).fetchone()
        if not usuario:
            return jsonify({"erro": "Usuário não encontrado."}), 404

        if usuario["perfil"] == "admin" and perfil != "admin":
            administradores = conexao.execute(
                "SELECT COUNT(*) AS total FROM usuarios WHERE perfil = 'admin'"
            ).fetchone()["total"]
            if administradores <= 1:
                return jsonify({"erro": "É necessário manter pelo menos um administrador."}), 400

        conexao.execute(
            "UPDATE usuarios SET perfil = ? WHERE id = ?",
            (perfil, usuario_id),
        )

        professor = conexao.execute(
            "SELECT id FROM professores WHERE lower(email) = ?",
            (usuario["email"].lower(),),
        ).fetchone()
        if perfil == "professor" and not professor:
            conexao.execute(
                "INSERT INTO professores (nome, email) VALUES (?, ?)",
                (usuario["nome"], usuario["email"]),
            )

        aluno = conexao.execute(
            "SELECT id FROM alunos WHERE lower(email) = ?",
            (usuario["email"].lower(),),
        ).fetchone()
        if perfil == "aluno" and not aluno:
            conexao.execute(
                "INSERT INTO alunos (nome, email) VALUES (?, ?)",
                (usuario["nome"], usuario["email"]),
            )

        conexao.commit()
        return jsonify({
            "mensagem": f"Cargo atualizado para {perfil}.",
            "id": usuario_id,
            "perfil": perfil,
        })
    finally:
        conexao.close()


@app.route("/api/dashboard")
@acesso(("admin",))
def dashboard():
    conexao = conectar()
    try:
        alunos_ativos = conexao.execute("""
            SELECT COUNT(*) AS total FROM alunos
            WHERE email IS NULL OR NOT EXISTS (
                SELECT 1 FROM usuarios
                WHERE lower(usuarios.email) = lower(alunos.email)
                  AND usuarios.perfil != 'aluno'
            )
        """).fetchone()["total"]
        professores_ativos = conexao.execute("""
            SELECT COUNT(*) AS total FROM professores
            WHERE email IS NULL OR NOT EXISTS (
                SELECT 1 FROM usuarios
                WHERE lower(usuarios.email) = lower(professores.email)
                  AND usuarios.perfil != 'professor'
            )
        """).fetchone()["total"]

        def total(tabela):
            return conexao.execute(f"SELECT COUNT(*) AS total FROM {tabela}").fetchone()["total"]
        return jsonify({
            "alunos": alunos_ativos,
            "professores": professores_ativos,
            "planos": total("planos"),
            "pagamentos": total("pagamentos"),
            "treinos": total("treinos"),
        })
    finally:
        conexao.close()


@app.route("/api/alunos", methods=["GET", "POST"])
@acesso(("admin", "professor"))
def alunos():
    conexao = conectar()
    try:
        if request.method == "GET":
            linhas = conexao.execute("""
                SELECT alunos.* FROM alunos
                WHERE alunos.email IS NULL OR NOT EXISTS (
                    SELECT 1 FROM usuarios
                    WHERE lower(usuarios.email) = lower(alunos.email)
                      AND usuarios.perfil != 'aluno'
                )
                ORDER BY alunos.nome
            """).fetchall()
            return jsonify([dict(linha) for linha in linhas])

        if g.usuario["perfil"] != "admin":
            return jsonify({"erro": "Você não tem permissão para cadastrar alunos."}), 403

        dados = request.get_json(silent=True) or {}
        nome = texto(dados.get("nome"))
        email = texto(dados.get("email"))
        telefone = texto(dados.get("telefone"))
        idade = inteiro(dados.get("idade"), "idade")
        if not nome:
            return jsonify({"erro": "O nome do aluno é obrigatório."}), 400
        cursor = conexao.execute(
            "INSERT INTO alunos (nome, email, telefone, idade) VALUES (?, ?, ?, ?)",
            (nome, email or None, telefone or None, idade),
        )
        conexao.commit()
        return jsonify({"mensagem": "Aluno cadastrado com sucesso.", "id": cursor.lastrowid}), 201
    finally:
        conexao.close()


@app.route("/api/professores", methods=["GET", "POST"])
@acesso(("admin",))
def professores():
    conexao = conectar()
    try:
        if request.method == "GET":
            linhas = conexao.execute("""
                SELECT professores.* FROM professores
                WHERE professores.email IS NULL OR NOT EXISTS (
                    SELECT 1 FROM usuarios
                    WHERE lower(usuarios.email) = lower(professores.email)
                      AND usuarios.perfil != 'professor'
                )
                ORDER BY professores.nome
            """).fetchall()
            return jsonify([dict(linha) for linha in linhas])

        dados = request.get_json(silent=True) or {}
        nome = texto(dados.get("nome"))
        email = texto(dados.get("email")).lower()
        senha = texto(dados.get("senha"))
        if not nome or not email or len(senha) < 6:
            return jsonify({"erro": "Informe nome, e-mail e uma senha com pelo menos 6 caracteres."}), 400
        existente = conexao.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).fetchone()
        if existente:
            return jsonify({"erro": "Este e-mail já está cadastrado."}), 409
        cursor = conexao.execute("""
            INSERT INTO professores (nome, email, telefone, especialidade)
            VALUES (?, ?, ?, ?)
        """, (
            nome, email, texto(dados.get("telefone")) or None,
            texto(dados.get("especialidade")) or None,
        ))
        conexao.execute(
            "INSERT INTO usuarios (nome, email, senha, perfil) VALUES (?, ?, ?, 'professor')",
            (nome, email, generate_password_hash(senha)),
        )
        conexao.commit()
        return jsonify({"mensagem": "Professor cadastrado com sucesso.", "id": cursor.lastrowid}), 201
    finally:
        conexao.close()


@app.route("/api/planos", methods=["GET", "POST"])
@acesso(("admin", "aluno"))
def planos():
    conexao = conectar()
    try:
        if request.method == "GET":
            linhas = conexao.execute("SELECT * FROM planos ORDER BY nome").fetchall()
            return jsonify([dict(linha) for linha in linhas])

        if g.usuario["perfil"] != "admin":
            return jsonify({"erro": "Você não tem permissão para cadastrar planos."}), 403

        dados = request.get_json(silent=True) or {}
        nome = texto(dados.get("nome"))
        try:
            preco = float(str(dados.get("preco", "")).replace(",", "."))
        except (TypeError, ValueError):
            preco = -1
        duracao = inteiro(dados.get("duracao"), "duracao")
        if not nome or preco < 0:
            return jsonify({"erro": "Informe nome e um preço válido."}), 400
        cursor = conexao.execute(
            "INSERT INTO planos (nome, preco, duracao, descricao) VALUES (?, ?, ?, ?)",
            (nome, preco, duracao, texto(dados.get("descricao")) or None),
        )
        conexao.commit()
        return jsonify({"mensagem": "Plano cadastrado com sucesso.", "id": cursor.lastrowid}), 201
    finally:
        conexao.close()


@app.route("/api/contratar-plano", methods=["POST"])
@acesso(("aluno",))
def contratar_plano():
    dados = request.get_json(silent=True) or {}
    plano_id = inteiro(dados.get("plano_id"), "plano_id")
    if plano_id is None:
        return jsonify({"erro": "Selecione um plano válido."}), 400

    conexao = conectar()
    try:
        aluno = conexao.execute(
            "SELECT id FROM alunos WHERE email = ?", (g.usuario["email"],)
        ).fetchone()
        plano = conexao.execute(
            "SELECT id, nome, preco FROM planos WHERE id = ?", (plano_id,)
        ).fetchone()
        if not aluno:
            return jsonify({"erro": "Cadastro de aluno não encontrado."}), 404
        if not plano:
            return jsonify({"erro": "Plano não encontrado."}), 404
        cursor = conexao.execute("""
            INSERT INTO pagamentos (aluno_id, plano_id, valor, data, forma, status)
            VALUES (?, ?, ?, date('now', 'localtime'), 'Solicitação de plano', 'Pendente')
        """, (aluno["id"], plano["id"], plano["preco"]))
        conexao.commit()
        return jsonify({
            "mensagem": "Solicitação registrada. O pagamento ainda está pendente.",
            "id": cursor.lastrowid,
        }), 201
    finally:
        conexao.close()


@app.route("/api/pagamentos", methods=["GET", "POST"])
@acesso(("admin",))
def pagamentos():
    conexao = conectar()
    try:
        if request.method == "GET":
            linhas = conexao.execute("""
                SELECT pagamentos.*, alunos.nome AS aluno, planos.nome AS plano
                FROM pagamentos JOIN alunos ON alunos.id = pagamentos.aluno_id
                LEFT JOIN planos ON planos.id = pagamentos.plano_id
                ORDER BY pagamentos.data DESC, pagamentos.id DESC
            """).fetchall()
            return jsonify([dict(linha) for linha in linhas])

        dados = request.get_json(silent=True) or {}
        aluno_id = inteiro(dados.get("aluno_id"), "aluno_id")
        try:
            valor = float(str(dados.get("valor", "")).replace(",", "."))
        except (TypeError, ValueError):
            valor = -1
        data = texto(dados.get("data"))
        forma = texto(dados.get("forma"))
        if aluno_id is None or valor < 0 or not data:
            return jsonify({"erro": "Selecione um aluno e informe valor e data."}), 400
        aluno = conexao.execute("SELECT id FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
        if not aluno:
            return jsonify({"erro": "Aluno não encontrado."}), 404
        cursor = conexao.execute(
            "INSERT INTO pagamentos (aluno_id, valor, data, forma, status) VALUES (?, ?, ?, ?, 'Pago')",
            (aluno_id, valor, data, forma or None),
        )
        conexao.commit()
        return jsonify({"mensagem": "Pagamento registrado com sucesso.", "id": cursor.lastrowid}), 201
    finally:
        conexao.close()


@app.route("/api/treinos", methods=["GET", "POST"])
@acesso(("admin", "professor", "aluno"))
def treinos():
    conexao = conectar()
    try:
        if request.method == "GET":
            consulta = """
                SELECT treinos.*, alunos.nome AS aluno,
                       professores.nome AS professor
                FROM treinos
                JOIN alunos ON alunos.id = treinos.aluno_id
                LEFT JOIN professores ON professores.id = treinos.professor_id
            """
            parametros = ()
            if g.usuario["perfil"] == "aluno":
                consulta += " WHERE lower(alunos.email) = ?"
                parametros = (g.usuario["email"],)
            elif g.usuario["perfil"] == "professor":
                consulta += " WHERE professores.email = ?"
                parametros = (g.usuario["email"],)
            consulta += " ORDER BY treinos.id DESC"
            linhas = conexao.execute(consulta, parametros).fetchall()
            return jsonify([dict(linha) for linha in linhas])

        if g.usuario["perfil"] == "aluno":
            return jsonify({"erro": "Alunos não podem cadastrar treinos."}), 403

        dados = request.get_json(silent=True) or {}
        aluno_id = inteiro(dados.get("aluno_id"), "aluno_id")
        professor_id = inteiro(dados.get("professor_id"), "professor_id")
        nome = texto(dados.get("nome"))
        if aluno_id is None or not nome:
            return jsonify({"erro": "Selecione um aluno e informe o nome do treino."}), 400
        if g.usuario["perfil"] == "professor":
            professor = conexao.execute(
                "SELECT id FROM professores WHERE email = ?", (g.usuario["email"],)
            ).fetchone()
            if not professor:
                return jsonify({"erro": "Cadastro de professor não encontrado."}), 404
            professor_id = professor["id"]
        aluno = conexao.execute("""
            SELECT alunos.id FROM alunos
            WHERE alunos.id = ? AND (
                alunos.email IS NULL OR NOT EXISTS (
                    SELECT 1 FROM usuarios
                    WHERE lower(usuarios.email) = lower(alunos.email)
                      AND usuarios.perfil != 'aluno'
                )
            )
        """, (aluno_id,)).fetchone()
        if not aluno:
            return jsonify({"erro": "Aluno não encontrado."}), 404
        if professor_id:
            professor = conexao.execute("""
                SELECT professores.id FROM professores
                WHERE professores.id = ? AND (
                    professores.email IS NULL OR NOT EXISTS (
                        SELECT 1 FROM usuarios
                        WHERE lower(usuarios.email) = lower(professores.email)
                          AND usuarios.perfil != 'professor'
                    )
                )
            """, (professor_id,)).fetchone()
            if not professor:
                return jsonify({"erro": "Professor não encontrado."}), 404
        cursor = conexao.execute("""
            INSERT INTO treinos (aluno_id, professor_id, nome, descricao, divisao)
            VALUES (?, ?, ?, ?, ?)
        """, (aluno_id, professor_id or None, nome,
              texto(dados.get("descricao")) or None,
              texto(dados.get("divisao")) or None))
        conexao.commit()
        return jsonify({"mensagem": "Treino cadastrado com sucesso.", "id": cursor.lastrowid}), 201
    finally:
        conexao.close()


@app.errorhandler(404)
def nao_encontrado(_erro):
    return jsonify({"erro": "Página ou recurso não encontrado."}), 404


@app.errorhandler(500)
def erro_interno(_erro):
    return jsonify({"erro": "Erro interno do servidor."}), 500



if __name__ == "__main__":
    app.run()
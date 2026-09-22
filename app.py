import os
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import requests
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import URL, select, text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

db = SQLAlchemy()


class Transacao(db.Model):
    __tablename__ = "transacao"
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=False, index=True)
    cliente_email = db.Column(db.String(320), nullable=False)
    codigo_acao = db.Column(db.String(20), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    preco_unitario = db.Column(db.Numeric(18, 2), nullable=False)
    valor_total = db.Column(db.Numeric(18, 2), nullable=False)
    data_transacao = db.Column(db.Date, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "cliente_id": self.cliente_id,
            "cliente_email": self.cliente_email,
            "codigo_acao": self.codigo_acao,
            "quantidade": self.quantidade,
            "preco_unitario": format(self.preco_unitario, ".2f"),
            "valor_total": format(self.valor_total, ".2f"),
            "data_transacao": self.data_transacao.isoformat(),
        }


def positive_integer(value):
    return type(value) is int and 0 < value <= 2147483647


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=16384, USERS_API_TIMEOUT=5)
    if test_config is None:
        app.config.update(
            SQLALCHEMY_DATABASE_URI=URL.create(
                "postgresql+psycopg", username=os.environ["POSTGRES_USER"],
                password=os.environ["POSTGRES_PASSWORD"],
                host=os.environ["POSTGRES_HOST"],
                port=int(os.environ.get("POSTGRES_PORT", "5432")),
                database=os.environ["POSTGRES_DB"],
            ),
            USERS_API_URL=os.environ["USERS_API_URL"].rstrip("/"),
            SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        )
    else:
        app.config.update(test_config)
    db.init_app(app)

    @app.cli.command("init-db")
    def init_db():
        """Cria as tabelas sem apagar dados existentes."""
        db.create_all()

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(erro=error.description), error.code

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        db.session.rollback()
        app.logger.error("Falha ao acessar o banco de dados: %s", type(error).__name__)
        return jsonify(erro="Banco de dados indisponível."), 503

    @app.get("/health")
    def health():
        db.session.execute(text("SELECT 1"))
        return jsonify(status="ok")

    @app.get("/transacao")
    def listar():
        query = select(Transacao).order_by(Transacao.id)
        if "cliente_id" in request.args:
            try:
                cliente_id = int(request.args["cliente_id"])
                if not positive_integer(cliente_id):
                    raise ValueError
            except ValueError:
                return jsonify(erro="cliente_id deve ser um inteiro positivo."), 400
            query = query.where(Transacao.cliente_id == cliente_id)
        return jsonify([item.to_dict() for item in db.session.scalars(query)])

    @app.post("/transacao")
    def criar():
        body = request.get_json()
        if not isinstance(body, dict):
            return jsonify(erro="Envie um objeto JSON."), 400
        required = {"cliente_id", "codigo_acao", "quantidade", "preco_unitario", "data_transacao"}
        if not required.issubset(body):
            return jsonify(erro="Campos obrigatórios ausentes.", campos=sorted(required - body.keys())), 400
        if not positive_integer(body["cliente_id"]) or not positive_integer(body["quantidade"]):
            return jsonify(erro="cliente_id e quantidade devem ser inteiros positivos."), 400
        codigo = body["codigo_acao"]
        if not isinstance(codigo, str) or not 1 <= len(codigo.strip()) <= 20:
            return jsonify(erro="codigo_acao deve conter entre 1 e 20 caracteres."), 400
        try:
            preco = Decimal(str(body["preco_unitario"]))
            if not preco.is_finite() or not 0 < preco < Decimal("10000000000000000"):
                raise ValueError
            arredondado = preco.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if preco != arredondado:
                raise ValueError
            total = arredondado * body["quantidade"]
            if total >= Decimal("10000000000000000"):
                raise ValueError
        except (InvalidOperation, ValueError):
            return jsonify(erro="Preço deve ser positivo, com até duas casas decimais, e total deve caber em 16 dígitos inteiros."), 400
        try:
            data = date.fromisoformat(body["data_transacao"])
            if data.isoformat() != body["data_transacao"]:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify(erro="data_transacao deve ser uma data válida no formato AAAA-MM-DD."), 400

        try:
            response = requests.get(
                f"{app.config['USERS_API_URL'].rstrip('/')}/{body['cliente_id']}",
                timeout=app.config["USERS_API_TIMEOUT"],
            )
            if response.status_code == 404:
                return jsonify(erro="Cliente não encontrado."), 404
            response.raise_for_status()
            usuario = response.json()
            if not isinstance(usuario, dict) or not isinstance(usuario.get("email"), str):
                raise ValueError
            email = usuario["email"].strip()
            if not email or len(email) > 320:
                raise ValueError
        except requests.Timeout:
            return jsonify(erro="Tempo limite ao consultar o serviço de usuários."), 504
        except (requests.RequestException, ValueError):
            return jsonify(erro="Resposta inválida ou falha no serviço de usuários."), 502

        transacao = Transacao(
            cliente_id=body["cliente_id"], cliente_email=email,
            codigo_acao=codigo.strip().upper(), quantidade=body["quantidade"],
            preco_unitario=arredondado, valor_total=total, data_transacao=data,
        )
        db.session.add(transacao)
        db.session.commit()
        return jsonify(transacao.to_dict()), 201

    @app.delete("/transacao/<int:transacao_id>")
    def deletar(transacao_id):
        transacao = db.session.get(Transacao, transacao_id)
        if transacao is None:
            return jsonify(erro="Transação não encontrada."), 404
        db.session.delete(transacao)
        db.session.commit()
        return "", 204

    return app

import sys
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(SCRIPT_DIR))


from flask import Flask, request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from domain import model
from adapters import orm, repository
from service_layer import services


orm.start_mappers()
get_session = sessionmaker(bind=create_engine(config.get_postgres_uri()))
app = Flask(__name__)


@app.route("/allocate", methods=["POST"])
def allocate_endpoint():
    session = get_session()
    repo = repository.SqlAlchemyRepository(session)
    orderid, sku, qty = request.json["orderid"], request.json["sku"], request.json["qty"]

    try:
        batchref = services.allocate(orderid, sku, qty, repo, session)
    except (model.OutOfStock, services.InvalidSku) as e:
        return {"message": str(e)}, 400

    return {"batchref": batchref}, 201


@app.route("/add_batch", methods=["POST"])
def add_batch():
    session = get_session()
    repo = repository.SqlAlchemyRepository(session)
    eta = request.json['eta']

    if eta is not None:
        eta = datetime.fromisoformat(eta).date()
    
    services.add_batch(
        request.json['ref'], request.json['sku'], request.json['qty'], eta, repo, session
    )

    return "OK", 201


if __name__ == "__main__":
    app.run(debug=True, port=config.FLASK_PORT)
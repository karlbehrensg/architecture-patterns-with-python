from datetime import date, timedelta
import uuid

import pytest
import requests

import config
from domain import model
from adapters import repository
from service_layer import services


today = date.today()
tomorrow = today + timedelta(days=1)
later = tomorrow + timedelta(days=10)


def random_suffix():
    return uuid.uuid4().hex[:6]


def random_sku(name=""):
    return f"sku-{name}-{random_suffix()}"


def random_batchref(name=""):
    return f"batch-{name}-{random_suffix()}"


def random_orderid(name=""):
    return f"order-{name}-{random_suffix()}"


class FakeRepository(repository.AbstractRepository):
    def __init__(self, batches):
        self._batches = set(batches)

    def add(self, batch):
        self._batches.add(batch)

    def get(self, reference):
        return next(b for b in self._batches if b.reference == reference)

    def list(self):
        return list(self._batches)

    @staticmethod
    def for_batch(ref, sku, qty, eta=None): 
        return FakeRepository([
            model.Batch(ref, sku, qty, eta),
        ])


class FakeSession:
    committed = False

    def commit(self):
        self.committed = True


def post_to_add_batch(ref, sku, qty, eta):
    url = config.get_api_url()
    r = requests.post(
        f'{url}/add_batch',
        json={'ref': ref, 'sku': sku, 'qty': qty, 'eta': eta},
    )
    assert r.status_code == 201


def test_returns_allocation():
    repo = FakeRepository.for_batch("batch1", "COMPLICATED-LAMP", 100, eta=None) 
    result = services.allocate("o1", "COMPLICATED-LAMP", 10, repo, FakeSession()) 
    assert result == "batch1"


def test_error_for_invalid_sku():
    batch = model.Batch("b1", "AREALSKU", 100, eta=None)
    repo = FakeRepository([batch])

    with pytest.raises(services.InvalidSku, match="Invalid sku NONEXISTENTSKU"):
        services.allocate("o1", "NONEXISTENTSKU", 10, repo, FakeSession())


def test_commits():
    batch = model.Batch("b1", "OMINOUS-MIRROR", 100, eta=None)
    repo = FakeRepository([batch])
    session = FakeSession()

    services.allocate("o1", "OMINOUS-MIRROR", 10, repo, session)
    assert session.committed is True


# domain-layer test:
def test_prefers_current_stock_batches_to_shipments():
    in_stock_batch = model.Batch("in-stock-batch", "RETRO-CLOCK", 100, eta=None) 
    shipment_batch = model.Batch("shipment-batch", "RETRO-CLOCK", 100, eta=tomorrow) 
    line = model.OrderLine("oref", "RETRO-CLOCK", 10)
    model.allocate(line, [in_stock_batch, shipment_batch]) 
    assert in_stock_batch.available_quantity == 90
    assert shipment_batch.available_quantity == 100


# service-layer test:
def test_prefers_warehouse_batches_to_shipments():
    in_stock_batch = model.Batch("in-stock-batch", "RETRO-CLOCK", 100, eta=None) 
    shipment_batch = model.Batch("shipment-batch", "RETRO-CLOCK", 100, eta=tomorrow) 
    repo = FakeRepository([in_stock_batch, shipment_batch])
    session = FakeSession()
    services.allocate('oref', "RETRO-CLOCK", 10, repo, session)
    assert in_stock_batch.available_quantity == 90
    assert shipment_batch.available_quantity == 100


def test_add_batch():
    repo, session = FakeRepository([]), FakeSession() 
    services.add_batch("b1", "CRUNCHY-ARMCHAIR", 100, None, repo, session) 
    assert repo.get("b1") is not None
    assert session.committed


def test_allocate_returns_allocation():
    repo, session = FakeRepository([]), FakeSession() 
    services.add_batch("batch1", "COMPLICATED-LAMP", 100, None, repo, session) 
    result = services.allocate("o1", "COMPLICATED-LAMP", 10, repo, session) 
    assert result == "batch1"


def test_allocate_errors_for_invalid_sku():
    repo, session = FakeRepository([]), FakeSession() 
    services.add_batch("b1", "AREALSKU", 100, None, repo, session)
    
    with pytest.raises(services.InvalidSku, match="Invalid sku NONEXISTENTSKU"): 
        services.allocate("o1", "NONEXISTENTSKU", 10, repo, FakeSession())


@pytest.mark.usefixtures('postgres_db') 
@pytest.mark.usefixtures('restart_api')
def test_happy_path_returns_201_and_allocated_batch():
    sku, othersku = random_sku(), random_sku('other')

    earlybatch = random_batchref(1)
    laterbatch = random_batchref(2)
    otherbatch = random_batchref(3)

    post_to_add_batch(laterbatch, sku, 100, '2011-01-02')
    post_to_add_batch(earlybatch, sku, 100, '2011-01-01')
    post_to_add_batch(otherbatch, othersku, 100, None)

    data = {'orderid': random_orderid(), 'sku': sku, 'qty': 3}
    url = config.get_api_url()
    r = requests.post(f'{url}/allocate', json=data)

    assert r.status_code == 201
    assert r.json()['batchref'] == earlybatch

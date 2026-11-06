"""Tests for proj2/config.py and the places that read it."""
import os

import pytest

import proj2.Flask_app as Flask_app
from proj2 import config


def test_db_path_defaults_to_proj2_db():
    assert config.db_path({}) == config.DEFAULT_DB_PATH
    assert config.DEFAULT_DB_PATH.endswith(os.path.join("proj2", "CSC510_DB.db"))


def test_db_path_env_override_is_absolute(tmp_path):
    target = tmp_path / "other.db"
    assert config.db_path({config.DB_PATH_ENV: str(target)}) == str(target)
    assert os.path.isabs(config.db_path({config.DB_PATH_ENV: "rel.db"}))


def test_blank_db_path_env_uses_default():
    assert config.db_path({config.DB_PATH_ENV: "  "}) == config.DEFAULT_DB_PATH


def test_llm_model_default_and_override():
    assert config.llm_model({}) == config.DEFAULT_LLM_MODEL
    assert config.llm_model({config.LLM_MODEL_ENV: "org/model"}) == "org/model"


def test_seed_password_override_and_random_default():
    assert config.seed_password({config.SEED_PASSWORD_ENV: "chosen"}) == "chosen"
    first, second = config.seed_password({}), config.seed_password({})
    assert first != second and len(first) >= 12


@pytest.mark.parametrize(
    "delivery_type, expected_fee", [("delivery", config.DELIVERY_FEE), ("pickup", 0.0)]
)
def test_order_charges_use_config(delivery_type, expected_fee):
    charges = Flask_app._order_charges(10.00, delivery_type, 2.00)
    assert charges["tax"] == Flask_app._money(10.00 * config.TAX_RATE)
    assert charges["delivery_fee"] == expected_fee
    assert charges["service_fee"] == config.SERVICE_FEE
    assert charges["total"] == Flask_app._money(
        10.00 + charges["tax"] + expected_fee + config.SERVICE_FEE + 2.00
    )


def test_order_charges_follow_config_changes(monkeypatch):
    monkeypatch.setattr(config, "TAX_RATE", 0.10)
    monkeypatch.setattr(config, "SERVICE_FEE", 0.0)
    assert Flask_app._order_charges(10.00, "pickup", 0)["total"] == 11.00


@pytest.mark.parametrize("path", ["/orders", "/restaurants"])
def test_cart_pages_get_fee_schedule_from_server(client, seed_minimal_data, login_session, path,
                                                 monkeypatch):
    """Templates must read fees from the server, so a config change reaches the preview."""
    monkeypatch.setattr(config, "TAX_RATE", 0.0111)
    monkeypatch.setattr(config, "DELIVERY_FEE", 7.77)
    monkeypatch.setattr(config, "SERVICE_FEE", 8.88)
    resp = client.get(path)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for value in ('"tax_rate": 0.0111', '"delivery_fee": 7.77', '"service_fee": 8.88'):
        assert value in html
    # No leftover copies of the default fees in the page's own script.
    for literal in ("0.0725", "3.99", "1.49"):
        assert literal not in html

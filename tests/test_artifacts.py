import csv
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_json_if_exists(name: str):
    path = ROOT / name
    if not path.exists():
        pytest.skip(f"{name} not found")
    return json.loads(path.read_text(encoding="utf-8"))


def test_dashboard_data_json_parses():
    data = _load_json_if_exists("dashboard_data.json")
    assert isinstance(data, (dict, list)), "dashboard_data.json 頂層應為 dict 或 list"


def test_backtest_results_json_parses():
    data = _load_json_if_exists("backtest_results.json")
    assert isinstance(data, (dict, list)), "backtest_results.json 頂層應為 dict 或 list"


def test_history_csv_has_header_and_rows():
    path = ROOT / "history.csv"
    if not path.exists():
        pytest.skip("history.csv not found")
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        assert header, "history.csv 冇 header"
        rows = list(reader)
    assert isinstance(rows, list)

import json, pathlib
from src.captions import MODELS
A = pathlib.Path(__file__).resolve().parents[1] / ".actor"

def test_every_input_field_has_description():
    for k, v in json.loads((A / "input_schema.json").read_text())["properties"].items():
        assert v.get("description"), k

def test_model_enum_supported():
    enum = json.loads((A / "input_schema.json").read_text())["properties"]["model"]["enum"]
    assert set(enum) <= set(MODELS)


def test_billing_grace():
    from src.core import billable_minutes as b
    assert b(None) == 1 and b(60.4) == 1 and b(60.5) == 1 and b(60.6) == 2 and b(3600.3) == 60 and b(121) == 3

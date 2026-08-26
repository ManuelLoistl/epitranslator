from fastapi.testclient import TestClient

from backend.app import app
from backend.prompt import schema_reference

client = TestClient(app)


def test_schema_reference_nonempty():
    text = schema_reference()
    assert "ParameterSchemaBuilder" in text
    assert "add_transmission_parameter" in text


def test_api_docs_returns_schema():
    body = client.get("/api/docs").json()
    assert "schema" in body
    assert "ParameterSchemaBuilder" in body["schema"]

from pathlib import Path


def _read_prod_compose() -> str:
    root = Path(__file__).resolve().parents[2]
    compose_file = root / "docker-compose.prod.yml"
    return compose_file.read_text(encoding="utf-8")


def test_prod_compose_migrate_service_exists_with_expected_command() -> None:
    compose = _read_prod_compose()
    assert "  migrate:\n" in compose
    assert 'command: ["alembic", "upgrade", "head"]' in compose
    assert 'restart: "no"' in compose
    assert "condition: service_healthy" in compose


def test_prod_compose_api_and_worker_depend_on_successful_migration() -> None:
    compose = _read_prod_compose()
    expected_gate = "migrate:\n        condition: service_completed_successfully"
    assert expected_gate in compose
    assert compose.count(expected_gate) >= 2

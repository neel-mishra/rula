"""Integration tests for the experiment CRUD + results API."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_registry_prompts(authenticated_client: AsyncClient):
    response = await authenticated_client.get("/experiments/registry/prompts")
    assert response.status_code == 200
    prompts = response.json()
    names = {p["name"] for p in prompts}
    # Default prompts registered at import time
    assert "triage_classifier" in names
    assert "draft_generator" in names


@pytest.mark.asyncio
async def test_create_experiment_validation(authenticated_client: AsyncClient):
    # Unknown prompt_name
    resp = await authenticated_client.post(
        "/experiments/",
        json={
            "name": "test",
            "prompt_name": "nonexistent_prompt",
            "primary_metric": "triage_correction_rate",
            "variants": [
                {"label": "a", "prompt_version": "v1", "traffic_pct": 50, "is_control": True},
                {"label": "b", "prompt_version": "v1", "traffic_pct": 50, "is_control": False},
            ],
        },
    )
    assert resp.status_code == 400
    assert "Unknown prompt_name" in resp.json()["detail"]

    # Traffic not summing to 100
    resp = await authenticated_client.post(
        "/experiments/",
        json={
            "name": "test",
            "prompt_name": "triage_classifier",
            "primary_metric": "triage_correction_rate",
            "variants": [
                {"label": "a", "prompt_version": "v1", "traffic_pct": 40, "is_control": True},
                {"label": "b", "prompt_version": "v1", "traffic_pct": 40, "is_control": False},
            ],
        },
    )
    assert resp.status_code == 400
    assert "sum to 100" in resp.json()["detail"]

    # No control
    resp = await authenticated_client.post(
        "/experiments/",
        json={
            "name": "test",
            "prompt_name": "triage_classifier",
            "primary_metric": "triage_correction_rate",
            "variants": [
                {"label": "a", "prompt_version": "v1", "traffic_pct": 50, "is_control": False},
                {"label": "b", "prompt_version": "v1", "traffic_pct": 50, "is_control": False},
            ],
        },
    )
    assert resp.status_code == 400
    assert "is_control" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_and_list_experiment(authenticated_client: AsyncClient):
    payload = {
        "name": "triage classifier v1 vs v1",
        "description": "baseline sanity check",
        "prompt_name": "triage_classifier",
        "primary_metric": "triage_correction_rate",
        "variants": [
            {"label": "control", "prompt_version": "v1", "traffic_pct": 50, "is_control": True},
            {"label": "challenger", "prompt_version": "v1", "traffic_pct": 50, "is_control": False},
        ],
    }
    resp = await authenticated_client.post("/experiments/", json=payload)
    assert resp.status_code == 200, resp.text
    created = resp.json()
    assert created["status"] == "draft"
    assert len(created["variants"]) == 2
    exp_id = created["id"]

    # List returns it
    resp = await authenticated_client.get("/experiments/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["experiments"][0]["id"] == exp_id


@pytest.mark.asyncio
async def test_activate_experiment_sets_started_at(authenticated_client: AsyncClient):
    payload = {
        "name": "activation test",
        "prompt_name": "triage_classifier",
        "primary_metric": "triage_correction_rate",
        "variants": [
            {"label": "control", "prompt_version": "v1", "traffic_pct": 50, "is_control": True},
            {"label": "challenger", "prompt_version": "v1", "traffic_pct": 50, "is_control": False},
        ],
    }
    created = (await authenticated_client.post("/experiments/", json=payload)).json()
    exp_id = created["id"]

    resp = await authenticated_client.patch(
        f"/experiments/{exp_id}", json={"status": "active"}
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["status"] == "active"
    assert updated["started_at"] is not None


@pytest.mark.asyncio
async def test_results_empty_experiment(authenticated_client: AsyncClient):
    payload = {
        "name": "empty results",
        "prompt_name": "triage_classifier",
        "primary_metric": "triage_correction_rate",
        "variants": [
            {"label": "control", "prompt_version": "v1", "traffic_pct": 50, "is_control": True},
            {"label": "challenger", "prompt_version": "v1", "traffic_pct": 50, "is_control": False},
        ],
    }
    created = (await authenticated_client.post("/experiments/", json=payload)).json()
    exp_id = created["id"]

    resp = await authenticated_client.get(f"/experiments/{exp_id}/results")
    assert resp.status_code == 200
    rollup = resp.json()
    assert rollup["experiment_id"] == exp_id
    assert len(rollup["variants"]) == 2
    for v in rollup["variants"]:
        assert v["sample_size"] == 0
    assert rollup["winner_variant_id"] is None

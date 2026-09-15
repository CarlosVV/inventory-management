"""
Tests for the task endpoints behind the Tasks modal.
"""
import pytest


def _create(client, **overrides):
    """Create a task with sensible defaults and return the response."""
    payload = {"title": "Review Q4 stock levels", "priority": "high", "dueDate": "2025-10-08"}
    payload.update(overrides)
    return client.post("/api/tasks", json=payload)


class TestTasksEndpoints:
    """Test suite for GET/POST/PATCH/DELETE /api/tasks."""

    def test_get_all_tasks(self, client):
        """Listing tasks returns an array (empty on a fresh process)."""
        response = client.get("/api/tasks")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_create_task(self, client):
        """Creating a task returns 201 with an id, the sent fields and pending status."""
        response = _create(client)
        assert response.status_code == 201

        task = response.json()
        assert isinstance(task["id"], int)
        assert task["id"] >= 1000  # must not collide with mock task ids 1-4
        assert task["title"] == "Review Q4 stock levels"
        assert task["priority"] == "high"
        assert task["dueDate"] == "2025-10-08"
        assert task["status"] == "pending"

    def test_created_task_is_listed_newest_first(self, client):
        """A created task appears at the top of the list."""
        first = _create(client, title="Older task").json()
        second = _create(client, title="Newer task").json()

        ids = [t["id"] for t in client.get("/api/tasks").json()]
        assert ids.index(second["id"]) < ids.index(first["id"])

    def test_task_ids_are_unique(self, client):
        """Two consecutive creates get different ids."""
        a = _create(client).json()["id"]
        b = _create(client).json()["id"]
        assert a != b

    def test_create_task_defaults_priority_to_medium(self, client):
        """Priority is optional and defaults to medium."""
        response = client.post("/api/tasks", json={"title": "Call supplier", "dueDate": "2025-10-10"})
        assert response.status_code == 201
        assert response.json()["priority"] == "medium"

    def test_create_task_strips_title(self, client):
        """Surrounding whitespace in the title is not stored."""
        response = _create(client, title="  Approve Tokyo orders  ")
        assert response.json()["title"] == "Approve Tokyo orders"

    def test_create_task_rejects_empty_title(self, client):
        """An empty title is a validation error."""
        response = _create(client, title="")
        assert response.status_code == 422

    def test_create_task_rejects_missing_due_date(self, client):
        """dueDate is required."""
        response = client.post("/api/tasks", json={"title": "No date", "priority": "low"})
        assert response.status_code == 422

    def test_create_task_rejects_unknown_priority(self, client):
        """Priority must be low, medium or high."""
        response = _create(client, priority="urgent")
        assert response.status_code == 422

    def test_toggle_task_flips_status(self, client):
        """PATCH flips pending to completed and back, returning the task each time."""
        task_id = _create(client).json()["id"]

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.json()["status"] == "pending"

    def test_toggle_nonexistent_task(self, client):
        """PATCH on an unknown id returns 404."""
        response = client.patch("/api/tasks/999999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_task(self, client):
        """DELETE returns 204 and the task is no longer listed."""
        task_id = _create(client).json()["id"]

        response = client.delete(f"/api/tasks/{task_id}")
        assert response.status_code == 204

        ids = [t["id"] for t in client.get("/api/tasks").json()]
        assert task_id not in ids

    def test_delete_nonexistent_task(self, client):
        """DELETE on an unknown id returns 404."""
        response = client.delete("/api/tasks/999999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_mock_task_id_is_not_found(self, client):
        """Mock tasks (ids 1-4) live only in the client; the API does not know them."""
        response = client.delete("/api/tasks/1")
        assert response.status_code == 404

"""
Tests for restocking recommendation and order endpoints.
"""
import pytest
from datetime import datetime, timedelta


class TestRestockingRecommendations:
    """Test suite for GET /api/restocking/recommendations."""

    def test_recommendations_structure(self, client):
        """Recommendations return the expected envelope and item fields."""
        response = client.get("/api/restocking/recommendations?budget=10000")
        assert response.status_code == 200

        data = response.json()
        assert data["budget"] == 10000
        assert isinstance(data["items"], list)
        assert len(data["items"]) > 0

        item = data["items"][0]
        for field in ["sku", "name", "category", "warehouse", "current_demand",
                      "forecasted_demand", "trend", "quantity", "unit_cost",
                      "line_total", "lead_time_days", "recommended"]:
            assert field in item

    def test_only_positive_gaps_are_candidates(self, client):
        """Items whose forecast does not exceed current demand are excluded."""
        response = client.get("/api/restocking/recommendations?budget=1000000")
        for item in response.json()["items"]:
            assert item["forecasted_demand"] > item["current_demand"]
            assert item["quantity"] == item["forecasted_demand"] - item["current_demand"]

    def test_sorted_by_largest_gap_first(self, client):
        """Candidates are ordered by forecast gap, descending."""
        response = client.get("/api/restocking/recommendations?budget=1000000")
        quantities = [item["quantity"] for item in response.json()["items"]]
        assert quantities == sorted(quantities, reverse=True)

    def test_line_total_matches_quantity_times_cost(self, client):
        """Line totals are quantity times unit cost."""
        response = client.get("/api/restocking/recommendations?budget=1000000")
        for item in response.json()["items"]:
            assert item["line_total"] == pytest.approx(item["quantity"] * item["unit_cost"], abs=0.01)

    def test_recommended_total_within_budget(self, client):
        """The sum of recommended lines never exceeds the budget."""
        budget = 8000
        response = client.get(f"/api/restocking/recommendations?budget={budget}")
        data = response.json()

        recommended = [i for i in data["items"] if i["recommended"]]
        total = sum(i["line_total"] for i in recommended)
        assert total <= budget
        assert data["recommended_total"] == pytest.approx(total, abs=0.01)
        assert data["remaining_budget"] == pytest.approx(budget - total, abs=0.01)

    def test_large_budget_recommends_everything(self, client):
        """A budget larger than all candidates recommends every item."""
        response = client.get("/api/restocking/recommendations?budget=1000000")
        data = response.json()
        assert all(i["recommended"] for i in data["items"])

    def test_zero_budget_recommends_nothing(self, client):
        """A zero budget still lists candidates but recommends none."""
        response = client.get("/api/restocking/recommendations?budget=0")
        data = response.json()
        assert len(data["items"]) > 0
        assert not any(i["recommended"] for i in data["items"])
        assert data["recommended_total"] == 0

    def test_negative_budget_rejected(self, client):
        """A negative budget is a validation error."""
        response = client.get("/api/restocking/recommendations?budget=-1")
        assert response.status_code == 422


class TestRestockingOrders:
    """Test suite for POST and GET /api/restocking/orders."""

    def test_place_order_and_list(self, client):
        """A submitted order is returned and then listed."""
        payload = {"items": [{"sku": "TMP-201", "quantity": 70}], "budget": 10000}
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        assert order["status"] == "Submitted"
        assert order["order_number"].startswith("RST-")
        assert order["total_value"] == pytest.approx(70 * 89.5, abs=0.01)
        assert order["budget"] == 10000
        assert len(order["items"]) == 1
        assert order["items"][0]["sku"] == "TMP-201"
        assert order["items"][0]["lead_time_days"] == 10  # Sensors

        listed = client.get("/api/restocking/orders")
        assert listed.status_code == 200
        assert any(o["order_number"] == order["order_number"] for o in listed.json())

    def test_expected_delivery_is_order_date_plus_lead_time(self, client):
        """Expected delivery equals order date plus the slowest line's lead time."""
        payload = {"items": [
            {"sku": "PCB-002", "quantity": 10},   # Circuit Boards: 14 days
            {"sku": "SRV-301", "quantity": 5},    # Actuators: 21 days
        ]}
        order = client.post("/api/restocking/orders", json=payload).json()

        assert order["lead_time_days"] == 21
        order_date = datetime.fromisoformat(order["order_date"])
        expected = datetime.fromisoformat(order["expected_delivery"])
        assert expected - order_date == timedelta(days=21)

    def test_newest_order_listed_first(self, client):
        """Orders are listed newest first."""
        first = client.post("/api/restocking/orders", json={"items": [{"sku": "PRX-204", "quantity": 1}]}).json()
        second = client.post("/api/restocking/orders", json={"items": [{"sku": "PRX-204", "quantity": 2}]}).json()

        listed = client.get("/api/restocking/orders").json()
        numbers = [o["order_number"] for o in listed]
        assert numbers.index(second["order_number"]) < numbers.index(first["order_number"])

    def test_unknown_sku_rejected(self, client):
        """An unknown SKU returns 404."""
        response = client.post("/api/restocking/orders", json={"items": [{"sku": "NOPE-999", "quantity": 1}]})
        assert response.status_code == 404

    def test_empty_items_rejected(self, client):
        """An order with no lines is a validation error."""
        response = client.post("/api/restocking/orders", json={"items": []})
        assert response.status_code == 422

    def test_zero_quantity_rejected(self, client):
        """A non-positive quantity is a validation error."""
        response = client.post("/api/restocking/orders", json={"items": [{"sku": "TMP-201", "quantity": 0}]})
        assert response.status_code == 422

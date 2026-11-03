"""
Tests for restocking API endpoints.
"""
import pytest

import main


@pytest.fixture(autouse=True)
def clear_restocking_orders():
    """Submitted orders live in module-level memory, so isolate each test."""
    main.restocking_orders.clear()
    yield
    main.restocking_orders.clear()


class TestRestockingRecommendations:
    """Test suite for the restocking recommendation endpoint."""

    def test_zero_budget_recommends_nothing(self, client):
        """Test that a zero budget yields no items."""
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total_cost"] == 0
        assert data["lead_time_days"] == 0

    def test_negative_budget_rejected(self, client):
        """Test that a negative budget returns 400."""
        response = client.get("/api/restocking/recommendations?budget=-1")
        assert response.status_code == 400

    def test_recommendations_stay_within_budget(self, client):
        """Test that total cost never exceeds the budget and adds up."""
        for budget in (5000, 20000, 60000, 150000):
            data = client.get(f"/api/restocking/recommendations?budget={budget}").json()
            assert data["total_cost"] <= budget
            assert data["total_cost"] == pytest.approx(sum(i["line_cost"] for i in data["items"]))
            assert data["remaining_budget"] == pytest.approx(budget - data["total_cost"])

    def test_only_items_with_shortfall_recommended(self, client):
        """Test that items with enough stock (e.g. decreasing trend) are never recommended."""
        data = client.get("/api/restocking/recommendations?budget=10000000").json()
        assert len(data["items"]) > 0
        for item in data["items"]:
            assert item["shortfall"] > 0
            assert 0 < item["recommended_quantity"] <= item["shortfall"]
        skus = [i["item_sku"] for i in data["items"]]
        assert "MTR-304" not in skus  # decreasing trend, already overstocked
        assert "PSU-501" not in skus  # on hand exceeds forecast

    def test_increasing_trend_prioritised(self, client):
        """Test that growing-demand items come before stable ones."""
        data = client.get("/api/restocking/recommendations?budget=10000000").json()
        trends = [i["trend"] for i in data["items"]]
        assert trends == sorted(trends, key=lambda t: {"increasing": 0, "stable": 1, "decreasing": 2}[t])

    def test_lead_time_follows_trend(self, client):
        """Test lead time rule and that order lead time is the slowest item."""
        data = client.get("/api/restocking/recommendations?budget=10000000").json()
        expected = {"increasing": 7, "stable": 10, "decreasing": 14}
        for item in data["items"]:
            assert item["lead_time_days"] == expected[item["trend"]]
        assert data["lead_time_days"] == max(i["lead_time_days"] for i in data["items"])

    def test_partial_quantity_when_budget_is_short(self, client):
        """Test that the budget is spent on a partial quantity rather than skipped."""
        data = client.get("/api/restocking/recommendations?budget=20000").json()
        first = data["items"][0]
        assert first["recommended_quantity"] < first["shortfall"]


class TestRestockingOrders:
    """Test suite for submitting and listing restocking orders."""

    ORDER = {"budget": 25000, "items": [
        {"item_sku": "WDG-001", "quantity": 100},
        {"item_sku": "GSK-203", "quantity": 50},
    ]}

    def test_create_order(self, client):
        """Test creating an order prices lines server-side and sets lead time."""
        response = client.post("/api/restocking/orders", json=self.ORDER)
        assert response.status_code == 201

        order = response.json()
        assert order["order_number"].startswith("RST-")
        assert order["status"] == "Submitted"
        assert order["total_cost"] == 100 * 185.0 + 50 * 38.0
        assert order["lead_time_days"] == 7
        assert len(order["items"]) == 2

    def test_created_order_is_listed_newest_first(self, client):
        """Test that submitted orders appear in the list, newest first."""
        assert client.get("/api/restocking/orders").json() == []
        client.post("/api/restocking/orders", json=self.ORDER)
        second = client.post("/api/restocking/orders", json=self.ORDER).json()

        orders = client.get("/api/restocking/orders").json()
        assert len(orders) == 2
        assert orders[0]["id"] == second["id"]

    def test_order_does_not_touch_customer_orders(self, client):
        """Test that restocking orders stay out of the main orders list."""
        before = len(client.get("/api/orders").json())
        client.post("/api/restocking/orders", json=self.ORDER)
        assert len(client.get("/api/orders").json()) == before

    def test_over_budget_rejected(self, client):
        """Test that an order costing more than the budget returns 400."""
        response = client.post("/api/restocking/orders", json={**self.ORDER, "budget": 100})
        assert response.status_code == 400
        assert client.get("/api/restocking/orders").json() == []

    def test_unknown_sku_returns_404(self, client):
        """Test that an unknown SKU returns 404."""
        body = {"budget": 1000, "items": [{"item_sku": "NOPE-000", "quantity": 1}]}
        assert client.post("/api/restocking/orders", json=body).status_code == 404

    def test_empty_order_and_bad_quantity_rejected(self, client):
        """Test that empty orders and non-positive quantities return 400."""
        assert client.post("/api/restocking/orders", json={"budget": 1000, "items": []}).status_code == 400
        body = {"budget": 1000, "items": [{"item_sku": "WDG-001", "quantity": 0}]}
        assert client.post("/api/restocking/orders", json=body).status_code == 400

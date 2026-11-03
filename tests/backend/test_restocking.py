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


class TestRestockingReviewFixes:
    """Regression tests for the bugs found in code review."""

    def _first_line(self, client):
        """First recommended line, using a budget large enough to include every candidate."""
        return client.get("/api/restocking/recommendations?budget=10000000").json()["items"][0]

    @pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
    def test_non_finite_budget_rejected_on_recommendations(self, client, value):
        """nan passes a plain `< 0` check and inf overflows, so both must return 400, not 200/500."""
        response = client.get(f"/api/restocking/recommendations?budget={value}")
        assert response.status_code == 400

    def test_non_finite_budget_rejected_on_order(self, client):
        """A nan budget would make `total > budget` False and let any order through.

        Raw bodies are sent because the test client refuses to encode NaN/Infinity, while
        Python's JSON parser on the server accepts them.
        """
        sku = self._first_line(client)["item_sku"]
        for token in ("NaN", "Infinity"):
            response = client.post(
                "/api/restocking/orders",
                content=f'{{"budget": {token}, "items": [{{"item_sku": "{sku}", "quantity": 1}}]}}',
                headers={"Content-Type": "application/json"},
            )
            assert response.status_code in (400, 422), token
        assert main.restocking_orders == []

    def test_duplicate_sku_rejected(self, client):
        """The same SKU twice would create duplicate v-for keys in the Orders view."""
        sku = self._first_line(client)["item_sku"]
        response = client.post("/api/restocking/orders", json={
            "budget": 10000000,
            "items": [{"item_sku": sku, "quantity": 1}, {"item_sku": sku, "quantity": 1}],
        })
        assert response.status_code == 400
        assert main.restocking_orders == []

    def test_quantity_above_shortfall_rejected(self, client):
        """Ordering more than the shortfall is over-ordering, however large the budget."""
        line = self._first_line(client)
        response = client.post("/api/restocking/orders", json={
            "budget": 1e12,
            "items": [{"item_sku": line["item_sku"], "quantity": line["shortfall"] + 1}],
        })
        assert response.status_code == 400
        assert main.restocking_orders == []

    def test_sku_without_shortfall_rejected(self, client):
        """A forecast item with enough stock has shortfall 0, so any quantity exceeds it."""
        in_shortfall = {c["item_sku"] for c in main.restocking_candidates()}
        sku = next(f["item_sku"] for f in main.demand_forecasts
                   if f["item_sku"] not in in_shortfall and f.get("unit_cost"))
        response = client.post("/api/restocking/orders", json={
            "budget": 1e12, "items": [{"item_sku": sku, "quantity": 1}]
        })
        assert response.status_code == 400

    def test_missing_quantity_on_hand_treated_as_zero(self, client, monkeypatch):
        """A forecast without quantity_on_hand used to pass the filter then KeyError in the endpoint."""
        monkeypatch.setattr(main, "demand_forecasts", [
            {"id": "x", "item_sku": "NEW-1", "item_name": "New", "current_demand": 5,
             "forecasted_demand": 10, "trend": "stable", "period": "2025-Q1", "unit_cost": 2.0},
        ])
        response = client.get("/api/restocking/recommendations?budget=1000")
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["quantity_on_hand"] == 0
        assert item["recommended_quantity"] == 10

    def test_order_numbers_unique_and_sequential(self, client):
        """Consecutive orders get distinct ids and numbers."""
        sku = self._first_line(client)["item_sku"]
        numbers = []
        for _ in range(3):
            response = client.post("/api/restocking/orders", json={
                "budget": 10000000, "items": [{"item_sku": sku, "quantity": 1}]
            })
            assert response.status_code == 201
            numbers.append(response.json()["order_number"])
        assert len(set(numbers)) == 3
        assert [n.rsplit("-", 1)[1] for n in numbers] == ["0001", "0002", "0003"]

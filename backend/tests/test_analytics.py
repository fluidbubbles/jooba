import pytest
from httpx import AsyncClient


class TestDashboardAPI:
    @pytest.mark.asyncio
    async def test_dashboard_returns_zero_stats_and_expected_shape_when_empty(
        self, client: AsyncClient
    ) -> None:
        """Empty dashboard returns zeroed metrics with expected response types."""
        response = await client.get("/api/analytics/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["total_candidates"], int)
        assert isinstance(data["total_sent"], int)
        assert isinstance(data["total_replies"], int)
        assert isinstance(data["total_interested"], int)
        assert isinstance(data["unreplied_count"], int)
        assert isinstance(data["reply_rate"], float)
        assert isinstance(data["sequences"], list)
        assert data["total_candidates"] == 0
        assert data["total_sent"] == 0
        assert data["total_replies"] == 0
        assert data["total_interested"] == 0
        assert data["unreplied_count"] == 0
        assert data["reply_rate"] == 0
        assert data["sequences"] == []

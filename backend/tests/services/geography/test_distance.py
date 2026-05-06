from app.entities.geography.distance import haversine_distance_km


class TestHaversineDistanceKm:
    def test_paris_lyon(self):
        # Paris : 48.8566° N, 2.3522° E
        # Lyon  : 45.7640° N, 4.8357° E
        distance = haversine_distance_km(48.8566, 2.3522, 45.7640, 4.8357)
        assert 390 < distance < 400

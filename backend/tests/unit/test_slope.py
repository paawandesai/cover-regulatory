import numpy as np

from app.ingest.slope import band_areas, slope_percent


def test_uniform_slope_lands_in_one_band():
    # A plane rising 20 ft per 100 ft: 20% everywhere, so all cells fall in the 15-29.99% band.
    cell = 3.0
    xs = np.arange(20) * cell
    elev = np.tile(xs * 0.20, (10, 1))
    s = slope_percent(elev, cell)
    assert np.allclose(s, 20.0)
    inside = np.ones_like(s, dtype=bool)
    inside[0, 0] = False
    bands = band_areas(s, inside, cell)
    assert bands["15-29.99"] == (s.size - 1) * cell * cell
    assert sum(bands.values()) == bands["15-29.99"]


def test_steep_and_flat_cells_are_split():
    cell = 1.0
    s = np.array([[5.0, 14.99, 15.0, 59.99, 60.0, 100.0]])
    bands = band_areas(s, np.ones_like(s, dtype=bool), cell)
    assert bands == {"0-14.99": 2.0, "15-29.99": 1.0, "30-44.99": 0.0, "45-59.99": 1.0, "60-99.99": 1.0, "100+": 1.0}

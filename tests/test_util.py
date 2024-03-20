import numpy as np
import pytest

from syfop.util import (
    const_time_series,
    constraints_to_str,
    print_constraints,
    random_time_series,
)


def test_const_time_series():
    time_series = const_time_series(value=23, time_coords=42, time_coords_year=2020)
    assert time_series.sizes["time"] == 42
    assert (time_series == 23).all()
    assert (time_series.time[0].dt.year == 2020).all()
    assert (time_series.time[1] - time_series.time[0]) == np.timedelta64(1, "h")


@pytest.mark.parametrize("time_coords", [42, range(42)])
def test_random_time_series(time_coords):
    time_series = random_time_series(time_coords)
    assert time_series.sizes["time"] == 42
    assert ((0 <= time_series) & (time_series < 1)).all()


@pytest.fixture(scope="session")
def some_model():
    from tests.test_network import simple_demand_network

    return simple_demand_network(time_coords=3).model


def test_print_constraints(some_model):
    # won't check stdout here, test test_constraints_to_str checks also output, should be fine
    print_constraints(some_model)


def test_constraints_to_str(some_model):
    constraints_as_str = constraints_to_str(some_model)
    expected_output = """
inout_flow_balance_wind0:
-0.500000 * size_wind0
+1.000000 * flow_wind_demand1
=
-0.000000

inout_flow_balance_wind1:
-0.500000 * size_wind0
+1.000000 * flow_wind_demand2
=
-0.000000

inout_flow_balance_wind2:
-0.500000 * size_wind0
+1.000000 * flow_wind_demand3
=
-0.000000

inout_flow_balance_demand3:
+1.000000 * flow_wind_demand1
=
5.000000

inout_flow_balance_demand4:
+1.000000 * flow_wind_demand2
=
5.000000

inout_flow_balance_demand5:
+1.000000 * flow_wind_demand3
=
5.000000
"""
    assert constraints_as_str == expected_output

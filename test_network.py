# %%

import pytest
from unittest import skip
import numpy as np
import xarray as xr
from network import Storage, System
from network import Node
from network import NodeFixInput
from network import Storage
from network import NUM_TIME_STEPS

# %%


def test_expensive_solar_pv():
    """If PV is more expensive than wind, the model should choose only wind (for constant wind/PV
     profiles)."""
    def const_time_series(value):
        return xr.DataArray(
            value * np.ones(NUM_TIME_STEPS),
            dims="time",
            coords={"time": np.arange(NUM_TIME_STEPS)},
        )

    wind = NodeFixInput(name="wind", input_flow=const_time_series(0.5), costs=1)
    solar_pv = NodeFixInput(
        name="solar_pv", input_flow=const_time_series(0.5), costs=20.0
    )

    electricity = Node(name="electricity", inputs=[solar_pv, wind], costs=0)

    co2 = NodeFixInput(name="co2", input_flow=const_time_series(5))

    methanol_synthesis = Node(
        name="methanol_synthesis",
        inputs=[co2, electricity],
        costs=8e-6,
        input_proportions={"co2": 0.25, "electricity": 0.75},
    )

    system = System([wind, solar_pv, electricity, co2, methanol_synthesis])
    system.optimize("gurobi")

    assert system.model.solution.size_wind == 30.0
    assert system.model.solution.size_solar_pv == 0.0


@pytest.mark.parametrize("with_storage", [False, True])
def test_simple_co2_storage(with_storage):
    """A simple methanol synthesis network with wind only to produce hydrogen.

    The optimum should be identical in both scenarios:
     - there is a constant 0.5 CO2 input flow (no storage)
     - CO2 input flow is alternating between 0 and 1 and there is a CO2 storage
    """

    wind_flow = xr.DataArray(
        0.5 * np.ones(NUM_TIME_STEPS),
        dims="time",
        coords={"time": np.arange(NUM_TIME_STEPS)},
    )
    co2_flow = xr.DataArray(
        np.ones(NUM_TIME_STEPS), dims="time", coords={"time": np.arange(NUM_TIME_STEPS)}
    )
    if with_storage:
        co2_flow[1::2] = 0
        storage = Storage(
            costs=1000, max_charging_speed=1.0, storage_loss=0.0, charging_loss=0.0
        )
    else:
        co2_flow = 0.5 * co2_flow
        storage = None

    wind = NodeFixInput(name="wind", input_flow=wind_flow, costs=1)
    hydrogen = Node(name="hydrogen", inputs=[wind], costs=3)
    co2 = NodeFixInput(name="co2", input_flow=co2_flow, storage=storage)

    methanol_synthesis = Node(
        name="methanol_synthesis",
        inputs=[co2, hydrogen],
        costs=1,
        input_proportions={"co2": 0.25, "hydrogen": 0.75},
    )

    system = System([wind, hydrogen, co2, methanol_synthesis])
    system.optimize("gurobi")

    np.testing.assert_almost_equal(system.model.solution.size_wind, 3.0)
    np.testing.assert_almost_equal(system.model.solution.size_hydrogen, 1.5)
    np.testing.assert_almost_equal(system.model.solution.size_methanol_synthesis, 2.0)
    np.testing.assert_array_almost_equal(system.model.solution.flow_wind_hydrogen, 1.5)
    np.testing.assert_array_almost_equal(system.model.solution.flow_co2_methanol_synthesis, 0.5)
    np.testing.assert_array_almost_equal(system.model.solution.flow_hydrogen_methanol_synthesis, 1.5)
    np.testing.assert_array_almost_equal(system.model.solution.flow_methanol_synthesis, 2.0)
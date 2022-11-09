import pytest
from unittest import skip
import numpy as np
import xarray as xr
from syfop.network import Network
from syfop.node import Node, NodeFixOutputProfile
from syfop.node import Storage
from syfop.node import NodeFixInputProfile
from syfop.node import NodeScalableInputProfile
from syfop.util import NUM_TIME_STEPS
from syfop.util import NUM_LOCATIONS


all_solvers = pytest.mark.parametrize("solver", ["gurobi", "highs"])


def const_time_series(value):
    return xr.DataArray(
        value * np.ones((NUM_TIME_STEPS, NUM_LOCATIONS)),
        dims=("time", "locations"),
        coords={
            "time": np.arange(NUM_TIME_STEPS),
            "locations": np.arange(NUM_LOCATIONS),
        },
    )


@all_solvers
def test_expensive_solar_pv(solver):
    """If PV is more expensive than wind, the model should choose only wind (for constant wind/PV
    profiles)."""

    wind = NodeScalableInputProfile(
        name="wind", input_flow=const_time_series(0.5), costs=1, output_unit="MW"
    )
    solar_pv = NodeScalableInputProfile(
        name="solar_pv", input_flow=const_time_series(0.5), costs=20.0, output_unit="MW"
    )

    electricity = Node(
        name="electricity",
        inputs=[solar_pv, wind],
        costs=0,
        output_unit="MW",
    )

    co2 = NodeFixInputProfile(
        name="co2", input_flow=const_time_series(5), costs=0, output_unit="t"
    )

    methanol_synthesis = Node(
        name="methanol_synthesis",
        inputs=[co2, electricity],
        costs=8e-6,
        convert_factor=1.0,  # this is not a realistic value probably
        output_unit="t",
        input_proportions={"co2": 0.25, "electricity": 0.75},
    )

    network = Network([wind, solar_pv, electricity, co2, methanol_synthesis])
    network.optimize(solver)

    assert network.model.solution.size_wind == 30.0
    assert network.model.solution.size_solar_pv == 0.0


@pytest.mark.parametrize("with_storage", [False, True])
def test_simple_co2_storage(with_storage):
    """A simple methanol synthesis network with wind only to produce hydrogen.

    The optimum should be identical in both scenarios:
     - there is a constant 0.5 CO2 input flow (no storage)
     - CO2 input flow is alternating between 0 and 1 and there is a CO2 storage
    """

    wind_flow = const_time_series(0.5)
    co2_flow = const_time_series(1.0)
    if with_storage:
        co2_flow[1::2] = 0
        storage = Storage(costs=1000, max_charging_speed=1.0, storage_loss=0.0, charging_loss=0.0)
    else:
        co2_flow = 0.5 * co2_flow
        storage = None

    wind = NodeScalableInputProfile(name="wind", input_flow=wind_flow, costs=1, output_unit="MW")
    hydrogen = Node(name="hydrogen", inputs=[wind], costs=3, output_unit="t")
    co2 = NodeFixInputProfile(
        name="co2", input_flow=co2_flow, storage=storage, costs=0, output_unit="t"
    )

    methanol_synthesis = Node(
        name="methanol_synthesis",
        inputs=[co2, hydrogen],
        costs=1,
        output_unit="t",
        input_proportions={"co2": 0.25, "hydrogen": 0.75},
    )

    network = Network([wind, hydrogen, co2, methanol_synthesis])
    network.optimize("gurobi")

    np.testing.assert_almost_equal(network.model.solution.size_wind, 3.0)
    np.testing.assert_almost_equal(network.model.solution.size_hydrogen, 1.5)
    np.testing.assert_almost_equal(network.model.solution.size_methanol_synthesis, 2.0)
    np.testing.assert_array_almost_equal(network.model.solution.flow_wind_hydrogen, 1.5)
    np.testing.assert_array_almost_equal(network.model.solution.flow_co2_methanol_synthesis, 0.5)
    np.testing.assert_array_almost_equal(
        network.model.solution.flow_hydrogen_methanol_synthesis, 1.5
    )
    np.testing.assert_array_almost_equal(network.model.solution.flow_methanol_synthesis, 2.0)


def test_missing_node():
    """If a node is used as input but not passed to the Network constructor, this is an error.
    This might change in future."""
    wind = Node(name="wind", inputs=[], costs=10, output_unit="MW")
    electricity = Node(name="electricity", inputs=[wind], costs=0, output_unit="MW")

    with pytest.raises(ValueError, match="missing in list of nodes.* wind"):
        network = Network([electricity])


def test_model_simple_demand():
    """Just two nodes, constant wind and constant demand."""
    wind = NodeScalableInputProfile(
        name="wind", input_flow=const_time_series(0.5), costs=1, output_unit="MW"
    )
    demand = NodeFixOutputProfile(
        name="demand", inputs=[wind], output_flow=const_time_series(5.0), costs=0, output_unit="MW"
    )

    network = Network([wind, demand])
    network.optimize("gurobi")
    np.testing.assert_almost_equal(network.model.solution.size_wind, 10.0)

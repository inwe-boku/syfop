import numpy as np
import pytest

from syfop.network import Network
from syfop.node import (
    Node,
    NodeFixInputProfile,
    NodeFixOutputProfile,
    NodeScalableInputProfile,
    Storage,
)
from syfop.util import DEFAULT_NUM_TIME_STEPS, const_time_series

all_solvers = pytest.mark.parametrize("solver", ["gurobi", "highs"])
default_solver = "highs"


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
        input_commodities="electricity",
        costs=0,
        output_unit="MW",
    )

    co2 = NodeFixInputProfile(
        name="co2", input_flow=const_time_series(5), costs=0, output_unit="t"
    )

    methanol_synthesis = Node(
        name="methanol_synthesis",
        inputs=[co2, electricity],
        input_commodities=["co2", "electricity"],
        costs=8e-6,
        convert_factor=1.0,  # this is not a realistic value probably
        output_unit="t",
        input_proportions={"co2": 0.25, "electricity": 0.75},
    )

    network = Network([wind, solar_pv, electricity, co2, methanol_synthesis])
    network.optimize(solver)

    assert network.model.solution.size_wind == 30.0
    assert network.model.solution.size_solar_pv == 0.0

    co2 = network.model.solution.flow_co2_methanol_synthesis
    electricity = network.model.solution.flow_electricity_methanol_synthesis
    np.testing.assert_array_almost_equal(0.25 * (co2 + electricity), co2)
    np.testing.assert_array_almost_equal(0.75 * (co2 + electricity), electricity)


@pytest.mark.parametrize(
    "storage_type",
    [
        "no_storage",
        "co2_storage",
        "electricity_storage",
        "hydrogen_storage",
    ],
)
def test_simple_co2_storage(storage_type):
    """A simple methanol synthesis network with wind only to produce hydrogen.

    The optimum should be (almost) identical in all scenarios:
     - there is a constant 0.5 CO2 input flow (no storage)
     - CO2 input flow is alternating between 0 and 1 and there is a CO2 storage (co2_storage)
     - wind capacity factors are alternating between 0 and 1 and there is a battery, note that
       this won't effect the size of the wind node (electricity_storage)
     - wind is alternating again between 0 and 1, but instead of storing electricity, we store
       hydrogen - note that here we need a larger electrolyzer (hydrogen_storage)

    """

    wind_flow = const_time_series(0.5)
    co2_flow = const_time_series(0.5)
    co2_storage = None
    electricity_storage = None
    hydrogen_storage = None
    expected_size_hydrogen = 1.5

    # note: there is no curtailment, so we need to invest into storage for non-constant input flow
    # even if it's expensive, so storage price is not relevant.

    if storage_type == "co2_storage":
        co2_flow = 2 * co2_flow
        co2_flow[1::2] = 0
        co2_storage = Storage(
            costs=1000,  # price not relevant, see comment above
            max_charging_speed=1.0,
            storage_loss=0.0,
            charging_loss=0.0,
        )
    elif storage_type == "electricity_storage":
        electricity_storage = Storage(
            costs=100,  # price not relevant, see comment above
            max_charging_speed=1.0,
            storage_loss=0.0,
            charging_loss=0.0,
        )
        wind_flow = 2 * wind_flow
        wind_flow[1::2] = 0
    elif storage_type == "hydrogen_storage":
        hydrogen_storage = Storage(
            costs=30,  # price not relevant, see comment above
            max_charging_speed=1.0,
            storage_loss=0.0,
            charging_loss=0.0,
        )
        wind_flow = 2 * wind_flow
        wind_flow[1::2] = 0
        expected_size_hydrogen = 3.0
    elif storage_type == "no_storage":
        # nothing to do here
        ...
    else:
        raise ValueError(f"invalid storage_type: {storage_type}")

    wind = NodeScalableInputProfile(
        name="wind",
        input_flow=wind_flow,
        costs=1.3,
        output_unit="MW",
        storage=electricity_storage,
    )
    hydrogen = Node(
        name="hydrogen",
        inputs=[wind],
        input_commodities="electricity",
        costs=3,
        output_unit="t",
        storage=hydrogen_storage,
    )
    co2 = NodeFixInputProfile(
        name="co2", input_flow=co2_flow, storage=co2_storage, costs=0, output_unit="t"
    )

    methanol_synthesis = Node(
        name="methanol_synthesis",
        inputs=[co2, hydrogen],
        input_commodities=["co2", "hydrogen"],
        costs=1.2,
        output_unit="t",
        input_proportions={"co2": 0.25, "hydrogen": 0.75},
    )

    network = Network([wind, hydrogen, co2, methanol_synthesis])
    network.optimize(default_solver)

    np.testing.assert_almost_equal(network.model.solution.size_wind, 3.0)

    np.testing.assert_almost_equal(network.model.solution.size_hydrogen, expected_size_hydrogen)
    np.testing.assert_almost_equal(network.model.solution.size_methanol_synthesis, 2.0)
    if storage_type == "hydrogen_storage":
        np.testing.assert_array_almost_equal(
            network.model.solution.flow_wind_hydrogen,
            wind_flow * network.model.solution.size_wind,
        )
    else:
        np.testing.assert_array_almost_equal(network.model.solution.flow_wind_hydrogen, 1.5)
    np.testing.assert_array_almost_equal(network.model.solution.flow_co2_methanol_synthesis, 0.5)
    np.testing.assert_array_almost_equal(
        network.model.solution.flow_hydrogen_methanol_synthesis, 1.5
    )
    np.testing.assert_array_almost_equal(network.model.solution.flow_methanol_synthesis, 2.0)


def test_missing_node():
    """If a node is used as input but not passed to the Network constructor, this is an error.
    This might change in future."""
    wind = Node(name="wind", inputs=[], input_commodities=[], costs=10, output_unit="MW")
    electricity = Node(
        name="electricity",
        inputs=[wind],
        input_commodities="electricity",
        costs=0,
        output_unit="MW",
    )

    with pytest.raises(ValueError, match="missing in list of nodes.* wind"):
        Network([electricity])


def simple_demand_network(time_coords=DEFAULT_NUM_TIME_STEPS):
    wind = NodeScalableInputProfile(
        name="wind",
        input_flow=const_time_series(0.5, time_coords=time_coords),
        costs=1,
        output_unit="MW",
    )
    demand = NodeFixOutputProfile(
        name="demand",
        inputs=[wind],
        input_commodities="electricity",
        output_flow=const_time_series(5.0, time_coords=time_coords),
        costs=0,
        output_unit="MW",
    )

    network = Network([wind, demand], time_coords=time_coords)
    return network


def test_model_simple_demand():
    """Just two nodes, constant wind and constant demand. Wind capacity needs to be scaled to
    meet demand."""
    network = simple_demand_network()
    network.optimize(default_solver)
    np.testing.assert_almost_equal(network.model.solution.size_wind, 10.0)


@pytest.mark.parametrize("wrong_length", [False, True])
def test_incosistent_time_coords(wrong_length):
    """If a node is used as input but not passed to the Network constructor, this is an error.
    This might change in future."""
    if wrong_length:
        time_coords_params = {"time_coords": 42}
        error_msg_pattern = "has an input flow with length"
    else:
        time_coords_params = {"time_coords_year": 2019}
        error_msg_pattern = "wind has an input flow with time_coords different from the Network"

    wind = NodeScalableInputProfile(
        name="wind",
        input_flow=const_time_series(42.0, **time_coords_params),
        costs=1,
        output_unit="MW",
    )
    electricity = Node(
        name="electricity",
        inputs=[wind],
        input_commodities="electricity",
        costs=0,
        output_unit="MW",
    )

    with pytest.raises(ValueError, match=error_msg_pattern):
        Network([wind, electricity])

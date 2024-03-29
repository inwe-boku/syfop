import numpy as np
import pytest

from syfop.network import Network, SolverError
from syfop.node import Node, NodeFixInput, NodeFixOutput, NodeScalableInput, Storage
from syfop.util import DEFAULT_NUM_TIME_STEPS, const_time_series

all_solvers = pytest.mark.parametrize("solver", ["gurobi", "highs", "cplex"])
default_solver = "highs"


@all_solvers
def test_expensive_solar_pv(solver):
    """If PV is more expensive than wind, the model should choose only wind (for constant wind/PV
    profiles)."""

    wind = NodeScalableInput(
        name="wind", input_profile=const_time_series(0.5), costs=1, output_unit="MW"
    )
    solar_pv = NodeScalableInput(
        name="solar_pv", input_profile=const_time_series(0.5), costs=20.0, output_unit="MW"
    )

    electricity = Node(
        name="electricity",
        inputs=[solar_pv, wind],
        input_commodities="electricity",
        costs=0,
        output_unit="MW",
    )

    co2 = NodeFixInput(name="co2", input_flow=const_time_series(5), costs=0, output_unit="t")

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
    expected_storage_costs = 0

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
        # optimal storage size is 0.5
        expected_storage_costs = 1000 * 0.5
    elif storage_type == "electricity_storage":
        electricity_storage = Storage(
            costs=100,  # price not relevant, see comment above
            max_charging_speed=1.0,
            storage_loss=0.0,
            charging_loss=0.0,
        )
        wind_flow = 2 * wind_flow
        wind_flow[1::2] = 0
        # optimal storage size is 3.0 * 0.5
        expected_storage_costs = 100 * 3.0 * 0.5
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
        # optimal storage size is 3.0 * 0.5
        expected_storage_costs = 30 * 3 * 0.5
    elif storage_type == "no_storage":
        # nothing to do here
        ...
    else:
        raise ValueError(f"invalid storage_type: {storage_type}")

    wind = NodeScalableInput(
        name="wind",
        input_profile=wind_flow,
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
    co2 = NodeFixInput(
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

    expect_size_methanol_synthesis = 2.0
    expected_size_wind = 3.0
    np.testing.assert_almost_equal(network.model.solution.size_wind, expected_size_wind)
    np.testing.assert_almost_equal(network.model.solution.size_hydrogen, expected_size_hydrogen)
    np.testing.assert_almost_equal(
        network.model.solution.size_methanol_synthesis, expect_size_methanol_synthesis
    )
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
    np.testing.assert_array_almost_equal(
        network.model.solution.output_flow_methanol_synthesis, 2.0
    )

    expected_objective = (
        1.3 * expected_size_wind
        + 3 * expected_size_hydrogen
        + 1.2 * expect_size_methanol_synthesis
        + expected_storage_costs
    )
    np.testing.assert_almost_equal(network.model.objective.value, expected_objective)


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


@pytest.mark.parametrize("input_flow_costs", [True, False])
def test_no_input_node(input_flow_costs):
    extra_kwrgs = {}
    expected_input_flow_costs = 0

    if input_flow_costs:
        extra_kwrgs["input_flow_costs"] = 42  # EUR/MWh

        # 42 EUR/MWh * 10h * 5 MWh/h
        expected_input_flow_costs = 42 * 10 * 5

    time_coords = 10
    gas = Node(
        name="gas", inputs=[], input_commodities="gas", costs=1, output_unit="MW", **extra_kwrgs
    )
    demand = NodeFixOutput(
        name="demand",
        inputs=[gas],
        input_commodities="electricity",
        output_flow=const_time_series(5.0, time_coords=time_coords),
        costs=0,
        output_unit="MW",
    )
    network = Network([gas, demand], time_coords=time_coords)
    network.optimize(default_solver)

    np.testing.assert_array_almost_equal(network.model.solution.input_flow_gas, 5.0)
    np.testing.assert_array_almost_equal(network.model.solution.flow_gas_demand, 5.0)
    assert network.model.solution.size_gas == 5.0

    assert network.model.objective.value == 5.0 + expected_input_flow_costs


def test_no_output_node():
    time_coords = 10
    wind = NodeFixInput(
        name="wind",
        input_flow=const_time_series(5, time_coords=time_coords),
        costs=0,  # FIXME NodeFixInput is not usable if we don't set the size to 0
        output_unit="t",
    )
    hydrogen = Node(
        name="hydrogen",
        inputs=[wind],
        input_commodities="electricity",
        costs=3,
        output_unit="t",
    )
    network = Network([wind, hydrogen], time_coords=time_coords)
    network.optimize(default_solver)
    np.testing.assert_array_almost_equal(network.model.solution.output_flow_hydrogen, 5.0)
    np.testing.assert_array_almost_equal(network.model.solution.flow_wind_hydrogen, 5.0)
    assert network.model.solution.size_hydrogen == 5.0


def simple_demand_network(time_coords=DEFAULT_NUM_TIME_STEPS, wind_input_flow=0.5):
    wind = NodeScalableInput(
        name="wind",
        input_profile=const_time_series(wind_input_flow, time_coords=time_coords),
        costs=1,
        output_unit="MW",
    )
    demand = NodeFixOutput(
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
@pytest.mark.parametrize("input_output", ["input", "output"])
def test_inconsistent_time_coords(input_output, wrong_length):
    """If a node is used as input but not passed to the Network constructor, this is an error.
    This might change in future."""
    time_coords_params = {"input": {}, "output": {}}
    if wrong_length:
        time_coords_params[input_output] = {"time_coords": 42}
        error_msg_pattern = f"has an .*{input_output}.* with length"
    else:
        time_coords_params[input_output] = {"time_coords_year": 2019}
        error_msg_pattern = f" has an .*{input_output}.* with time_coords different from the"

    wind = NodeScalableInput(
        name="wind",
        input_profile=const_time_series(0.42, **time_coords_params["input"]),
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
    demand = NodeFixOutput(
        name="demand",
        inputs=[electricity],
        output_flow=const_time_series(0.42, **time_coords_params["output"]),
        input_commodities="electricity",
        costs=0,
        output_unit="MW",
    )

    with pytest.raises(ValueError, match=error_msg_pattern):
        Network([wind, electricity, demand])


@pytest.mark.parametrize("with_curtailment", [False, True])
def test_hot_chocolate(with_curtailment):
    """A quite synthetic example, to test whether parameters and units are intuitive. A cow
    produces milk which is mixed cacao powder to produce hot chocolate."""
    time_coords = 3

    # we will need 2l of cow capacity, because we have a constant capacity factor of 120ml per
    # liter of cow capacity
    milk_flow = const_time_series(120e-3, time_coords=time_coords)

    if with_curtailment:
        # let's assume we have too much milk in the first time stamp, there is no storage and we
        # don't have enough cacao powder, so we need to curtail some milk
        milk_flow[0] = 1.0

    # we will need size = 8 to get 8g per time stamp
    cacao_delivery_flow = const_time_series(1.0, time_coords=time_coords)

    cow = NodeScalableInput(
        name="cow",
        input_profile=milk_flow,
        # this is a weird workaround, because we know only the milk price, but costs here is
        # relative to the cow size not to the amount of milk
        costs=1.49 * milk_flow[0],  # in EUR/l
        output_unit="l",
    )

    # 1g of cacao powder is 1.67ml if desolved in milk
    cacao_delivery = NodeScalableInput(
        name="cacao_delivery",
        input_profile=cacao_delivery_flow,
        # workaround, same as for cow costs
        costs=3.2e-3 * cacao_delivery_flow[0],  # in EUR/g
        output_unit="g",
    )

    hot_chocolate = Node(
        name="hot_chocolate",
        inputs=[cow, cacao_delivery],
        input_commodities=["milk", "cacao"],
        # 240ml of milk, 8g of cacao
        input_proportions={"cacao_delivery": 8 / (240e-3 + 8), "cow": 240e-3 / (240e-3 + 8)},
        convert_factor=(240e-3 + 8 * 1.67e-3) / (240e-3 + 8),
        costs=0,
        output_unit="l",
    )

    # the consumer drinks 1 cup of cocao per time stamp, which is 240ml of milk and 8g of cacao
    hot_chocolate_consumer = NodeFixOutput(
        name="hot_chocolate_consumer",
        inputs=[hot_chocolate],
        input_commodities="hot_chocolate",
        output_flow=const_time_series(240e-3 + 8 * 1.67e-3, time_coords=time_coords),
        costs=0,
        output_unit="l",
    )

    nodes = [cow, cacao_delivery, hot_chocolate, hot_chocolate_consumer]

    if with_curtailment:
        milk_curtailment = Node(
            name="milk_curtailment",
            inputs=[cow],
            input_commodities="milk",
            costs=0,
            output_unit="l",
        )

        nodes.append(milk_curtailment)

    network = Network(nodes, time_coords=time_coords)

    network.optimize(default_solver)

    assert network.model.solution.size_cacao_delivery == 8
    assert abs(network.model.solution.size_cow - 2.0) < 1e-14
    np.testing.assert_array_almost_equal(
        network.model.solution.flow_cacao_delivery_hot_chocolate, 8.0
    )
    np.testing.assert_array_almost_equal(network.model.solution.flow_cow_hot_chocolate, 240e-3)
    np.testing.assert_array_almost_equal(
        network.model.solution.flow_hot_chocolate_hot_chocolate_consumer, 240e-3 + 8 * 1.67e-3
    )

    if with_curtailment:
        np.testing.assert_almost_equal(
            network.model.solution.output_flow_milk_curtailment[0], 2.0 - 240e-3
        )
        np.testing.assert_array_almost_equal(
            network.model.solution.output_flow_milk_curtailment[1:], 0
        )

    # test keys of output_flows
    if with_curtailment:
        assert {"milk_curtailment", "hot_chocolate"} == set(cow.output_flows.keys())
    else:
        assert {"hot_chocolate"} == set(cow.output_flows.keys())
    assert {"hot_chocolate"} == set(cacao_delivery.output_flows.keys())
    assert {"hot_chocolate_consumer"} == set(hot_chocolate.output_flows.keys())


@pytest.mark.parametrize("mode", ["netgraph", "graphviz"])
def test_draw_network(mode):
    # does not really test output, only increases coverage and check if any error is raised
    network = simple_demand_network()
    network.draw(mode=mode)


def test_draw_network_invalid_mode():
    network = simple_demand_network()
    with pytest.raises(ValueError, match="invalid draw mode: INVALID"):
        network.draw(mode="INVALID_MODE")


def test_infeasible_network():
    network = simple_demand_network(wind_input_flow=0.0)
    error_msg = (
        "unable to solve optimization, solver status=warning, termination condition=infeasible"
    )
    with pytest.raises(SolverError, match=error_msg):
        network.optimize(default_solver)


def test_network_add_constraints():
    """Test adding custom constraints."""
    wind = NodeScalableInput(
        name="wind",
        input_profile=const_time_series(0.5),
        costs=1,
        output_unit="MW",
    )
    demand = NodeFixOutput(
        name="demand",
        inputs=[wind],
        input_commodities="electricity",
        output_flow=const_time_series(5.0),
        costs=0,
        output_unit="MW",
    )
    curtailment = Node(
        name="curtailment",
        inputs=[wind],
        input_commodities="electricity",
        costs=0,
        output_unit="MW",
    )
    network = Network([wind, demand, curtailment])

    # Let's make Sebastian happy and force the system to have at least 15MW of wind :)
    network.add_constraints(wind.size >= 15)
    network.optimize()

    assert network.model.solution.size_wind == 15.0
    np.testing.assert_array_almost_equal(network.model.solution.output_flow_curtailment, 2.5)


def test_network_add_variables():
    """Test adding custom variables."""
    network = simple_demand_network()
    total_energy = network.add_variables(name="total_energy")
    network.add_constraints(total_energy == network.nodes_dict["wind"].input_flows[""].sum())
    network.optimize()

    # we need 5 MW constant demand
    assert network.model.solution.total_energy == DEFAULT_NUM_TIME_STEPS * 5.0


def test_empty_network():
    """Empty network should raise an error."""
    with pytest.raises(ValueError, match="empty network not allowed"):
        Network([])


def test_node_with_same_name():
    """Nodes with the same name should raise an error."""
    wind = NodeScalableInput(
        name="wind",
        input_profile=const_time_series(0.5),
        costs=1,
        output_unit="MW",
    )
    demand = NodeFixOutput(
        name="wind",  # here is a simulated bug! should be "demand"
        inputs=[wind],
        input_commodities="electricity",
        output_flow=const_time_series(5.0),
        costs=0,
        output_unit="MW",
    )

    with pytest.raises(ValueError, match="node names are not unique: wind, wind"):
        Network([wind, demand])

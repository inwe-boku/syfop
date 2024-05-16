import re

import pytest

from syfop.node import (
    Node,
    NodeFixOutput,
    NodeScalableInput,
    NodeScalableOutput,
    Storage,
)
from syfop.units import ureg
from syfop.util import const_time_series


@pytest.fixture
def three_example_nodes():
    wind = NodeScalableInput(
        name="wind",
        input_profile=const_time_series(0.5),
        costs=1,
    )
    solar_pv = NodeScalableInput(
        name="solar_pv",
        input_profile=const_time_series(0.5),
        costs=20.0,
    )
    electricity = Node(
        name="electricity",
        inputs=[solar_pv, wind],
        input_commodities="electricity",
        costs=0,
    )
    return wind, solar_pv, electricity


def test_input_commodities_as_str(three_example_nodes):
    _, _, electricity = three_example_nodes
    assert electricity.input_commodities == ["electricity", "electricity"]


def test_wrong_input_proportions_commodities(three_example_nodes):
    wind, solar_pv, _ = three_example_nodes

    error_msg = (
        "wrong parameter for node electricity: input_proportions needs to be a dict "
        "with keys matching names of input_commodities: {'electricity'}"
    )
    with pytest.raises(AssertionError, match=error_msg):
        _ = Node(
            name="electricity",
            inputs=[solar_pv, wind],
            input_commodities=["electricity", "electricity"],
            costs=0,
            # correct would be key: "electricity"
            input_proportions={"wind": 0.8 * ureg.MW, "solar_pv": 1.42 * ureg.MW},
        )


def test_invalid_num_input_commodities1(three_example_nodes):
    wind, solar_pv, _ = three_example_nodes

    error_msg = (
        "invalid number of input_commodities provided for node 'electricity': "
        "['electricity'], does not match number of inputs: ['solar_pv', 'wind']"
    )
    error_msg = re.escape(error_msg)

    with pytest.raises(ValueError, match=error_msg):
        _ = Node(
            name="electricity",
            inputs=[solar_pv, wind],
            # there are two input nodes, but only one commodity: a string would work or a list with
            # two strings "electricity", but a list with one string is not allowed
            input_commodities=["electricity"],
            costs=0,
            input_proportions={"wind": 0.8, "solar_pv": 0.2},
        )


def test_invalid_num_input_commodities2():
    error_msg = (
        "invalid number of input_commodities provided for node 'gas': "
        "[], does not match number of inputs: []"
    )
    with pytest.raises(ValueError, match=error_msg):
        _ = Node(
            name="gas",
            inputs=[],
            input_commodities=[],
            costs=0,
        )


def test_input_profile_not_capacity_factor():
    error_msg = "invalid values in input_profile: must be capacity factors"

    with pytest.raises(ValueError, match=error_msg):
        _ = NodeScalableInput(
            name="wind",
            input_profile=const_time_series(1.5),
            costs=1,
        )

    with pytest.raises(ValueError, match=error_msg):
        _ = NodeScalableInput(
            name="wind",
            input_profile=const_time_series(-0.5),
            costs=1,
        )


def test_wrong_node_input():
    error_msg = "inputs must be of type NodeBase or some subclass"
    with pytest.raises(ValueError, match=error_msg):
        _ = Node(
            name="electricity",
            inputs=["solar_pv", "wind"],
            input_commodities="electricity",
            costs=0,
        )


def test_scalable_output_not_implemented():
    # this unit test is a bit useless, but it increases coverage
    error_msg = "NodeScalableOutput is not implemented yet"
    with pytest.raises(NotImplementedError, match=error_msg):
        NodeScalableOutput()


def test_storage_forbidden_for_output_nodes():
    storage = Storage(
        costs=10 * ureg.EUR / ureg.MWh,
        max_charging_speed=1.0,
        storage_loss=0.0,
        charging_loss=0.0,
    )

    error_msg = "storage is not supported for output nodes"
    with pytest.raises(NotImplementedError, match=error_msg):
        _ = NodeFixOutput(
            name="demand",
            inputs=[],
            input_commodities="electricity",
            output_flow=const_time_series(5.0) * ureg.kW,
            storage=storage,
        )

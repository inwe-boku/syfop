import pytest

from syfop.node import Node, NodeScalableInput
from syfop.units import ureg
from syfop.util import const_time_series


@pytest.fixture
def three_example_nodes():
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
            output_unit="MW",
            # correct would be key: "electricity"
            input_proportions={"wind": 0.8 * ureg.MW, "solar_pv": 1.42 * ureg.MW},
        )


def test_wrong_number_of_commodities(three_example_nodes):
    wind, solar_pv, _ = three_example_nodes

    error_msg = (
        "invalid number of input_commodities provided for node 'electricity': "
        "\\['electricity'\\], does not match number of inputs: solar_pv, wind"
    )
    with pytest.raises(ValueError, match=error_msg):
        _ = Node(
            name="electricity",
            inputs=[solar_pv, wind],
            input_commodities=["electricity"],
            costs=0,
            output_unit="MW",
            input_proportions={"wind": 0.8, "solar_pv": 0.2},
        )


def test_input_profile_not_capacity_factor():
    error_msg = "invalid values in input_profile: must be capacity factors"

    with pytest.raises(ValueError, match=error_msg):
        _ = NodeScalableInput(
            name="wind",
            input_profile=const_time_series(1.5),
            costs=1,
            output_unit="MW",
        )

    with pytest.raises(ValueError, match=error_msg):
        _ = NodeScalableInput(
            name="wind",
            input_profile=const_time_series(-0.5),
            costs=1,
            output_unit="MW",
        )


def test_wrong_node_input():
    error_msg = "inputs must be of type NodeBase or some subclass"
    with pytest.raises(ValueError, match=error_msg):
        _ = Node(
            name="electricity",
            inputs=["solar_pv", "wind"],
            input_commodities="electricity",
            costs=0,
            output_unit="MW",
        )

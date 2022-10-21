import os

os.environ["PATH"] = f"{os.environ['PATH']}:/home/p/HiGHS/build/bin"
os.environ["GRB_LICENSE_FILE"] = "/opt/gurobi810/gurobi.lic"

import numpy as np
import xarray as xr
import pandas as pd
import linopy
import networkx as nx
import matplotlib.pyplot as plt
from networkx.drawing.nx_pydot import graphviz_layout


class Node:
    def __init__(self, name, inputs, costs, input_proportions=None, storage=None):
        self.name = name
        self.inputs = inputs
        self.outputs = None

        self.input_flows = None
        self.output_flows = None

        self.storage = storage

        # TODO some nodes do not need size/costs, e.g. curtailing etc, but setting costs=0 is doing
        # the job, but it creates some unnecessary variables
        self.size = None
        self.costs = costs

        if input_proportions is not None:
            assert input_proportions.keys() == {input_.name for input_ in inputs}, (
                f"wrong parameter for node {name}: input_proportions needs to be a "
                "dict with keys matching names of inputs"
            )
            # is this check too strict due to numerical errors?
            assert (
                sum(input_proportions.values()) == 1.0
            ), f"wrong parameter for node {name}: input_proportions needs to sum up to 1."

        self.input_proportions = input_proportions


class NodeFixInput(Node):
    # input is a fixed constant with dims location/time
    # this is use for input time series at the top of the tree
    #
    # size is determined by optimization model, if costs is not None, otherwise input is not scaled!
    # this might limit flexibility a bit
    def __init__(self, name, input_flow, costs=None, storage=None):
        self.name = name
        self.inputs = []
        self.outputs = None

        self.storage = storage

        # TODO input_flow should be <1.? (i.e. dimensionless capacity factors)
        # but note: this is wrong for co2 (costs=0), i.e. only for scalable fixed input

        self.input_flows = {"": input_flow}
        self.output_flows = None

        assert (
            costs != 0.0
        ), "costs equal zero, this does not make sense here I guess? maybe use different node type?"

        self.size = None
        self.costs = costs


class Storage:
    def __init__(self, costs, max_charging_speed, storage_loss, charging_loss):
        self.costs = costs  # per size
        self.max_charging_speed = (
            max_charging_speed
        )  # unit: share of total size per timestamp
        self.storage_loss = storage_loss
        self.charging_loss = charging_loss

        assert storage_loss < 1
        assert charging_loss < 1
        assert max_charging_speed <= 1

    # usage examples:
    #  - h2 storage
    #  - co2 storage
    #  - battery


class NodeFixOutput(Node):
    # output is fixed with dims location/time
    # usage example is to fix demand by use of a time series

    # TODO not yet implemented
    ...


# TODO this should be an input for Flow and maybe use a datetime range as coords
NUM_TIME_STEPS = 8760
time = pd.date_range(2020, freq="h", periods=NUM_TIME_STEPS)


def timeseries_variable(model, name):
    return model.add_variables(
        name=name,
        lower=xr.DataArray(
            np.zeros(NUM_TIME_STEPS), coords={"time": np.arange(NUM_TIME_STEPS)}
        ),
    )


class System:
    # basically a list of all technologies
    def __init__(self, nodes):
        self.nodes = nodes
        self.nodes_dict = {node.name: node for node in nodes}
        self.graph = self._create_graph(nodes)
        self.model = self._generate_optimization_model(nodes)

    def _create_graph(self, nodes):
        graph = nx.DiGraph()
        for node in nodes:
            if isinstance(node, NodeFixInput):
                color = "red"
            else:
                color = "blue"

            graph.add_node(node.name, color=color)

            if hasattr(node, "storage") and node.storage is not None:
                # XXX hopefully this name is unique
                graph.add_node(f"{node.name}_storage", color="green")
                graph.add_edge(f"{node.name}_storage", node.name)
                graph.add_edge(node.name, f"{node.name}_storage")

            for input_ in node.inputs:
                graph.add_edge(input_.name, node.name)
        return graph

    def _generate_optimization_model(self, nodes):
        model = linopy.Model()

        for node in nodes:
            # TODO atm some nodes should not have variables, but setting costs to 0 does the
            # job too
            if node.costs:  # None or 0 means that we don't need a size variable
                node.size = model.add_variables(name=f"size_{node.name}", lower=0)

        # XXX not sure if we really need this backward connection, also in won't work as soon as 
        # we add demand
        for node in nodes:
            for input_ in node.inputs:
                if input_.outputs is None:
                    input_.outputs = []
                input_.outputs.append(node)

        # each input_flow is a variable (representing the amount of energy in the edge coming from
        # input to self)
        for node in nodes:
            if node.input_flows is None:
                # FIXME we need a check for uniqueness of name somewhere
                node.input_flows = {
                    input_.name: timeseries_variable(
                        model, f"flow_{input_.name}_{node.name}"
                    )
                    for input_ in node.inputs
                }
            else:
                # if input_flows is not None, we have a FixedInput, which we need to scale only
                # if there is a size defined, otherwise it will stay as scalar
                if node.size is not None:
                    node.input_flows[""] = node.size * node.input_flows[""]

        # this is a bit weird: we want a variable or constant for each edge, but we store it as
        # dict for all input connections and as list for all output connections
        for node in nodes:
            if node.output_flows is None:
                if node.outputs is None:
                    # this is a variable for leaves, i.e. final output, not really needed, but
                    # nice to have and used in size constraints
                    node.output_flows = [
                        timeseries_variable(model, f"flow_{node.name}")
                    ]
                else:
                    node.output_flows = [
                        output.input_flows[node.name] for output in node.outputs
                    ]

        # constraint: size of technology
        for node in nodes:
            if node.output_flows is not None and node.size:
                # FIXME this is probably wrong for FixedInput?!
                model.add_constraints(
                    1 * sum(node.output_flows) - node.size <= 0,
                    name=f"limit_outflow_by_size_{node.name}",
                )

        # constraint: proportion of inputs
        for node in nodes:
            if (
                hasattr(node, "input_proportions")
                and node.input_proportions is not None
            ):
                for name, proportion in node.input_proportions.items():
                    total_input = sum(
                        input_flow
                        for n, input_flow in node.input_flows.items()
                        if n != name
                    )
                    model.add_constraints(
                        proportion * total_input
                        + (proportion - 1) * node.input_flows[name]
                        == 0.0,
                        name=f"proportion_{node.name}_{name}"
                    )

        # storage
        for node in nodes:
            if node.storage is not None:
                node.storage.size = size = model.add_variables(
                    name=f"size_storage_{node.name}", lower=0
                )
                node.storage.level = level = timeseries_variable(
                    model, f"storage_level_{node.name}"
                )
                node.storage.charge = charge = timeseries_variable(
                    model, f"storage_charge_{node.name}"
                )
                node.storage.discharge = discharge = timeseries_variable(
                    model, f"storage_discharge_{node.name}"
                )

                model.add_constraints(
                    charge - size * node.storage.max_charging_speed <= 0,
                    name=f"max_charging_speed_{node.name}"
                )
                model.add_constraints(
                    discharge - size * node.storage.max_charging_speed <= 0,
                    name=f"max_discharging_speed_{node.name}"
                )
                model.add_constraints(level - size <= 0,
                    name=f'storage_max_level_{node.name}'
                )
                model.add_constraints(
                    level.isel(time=0)
                    - (1 - node.storage.charging_loss) * charge.isel(time=0)
                    + discharge.isel(time=0)
                    == 0,
                    name=f'storage_level_balance_t0_{node.name}'
                )
                model.add_constraints(
                    (level
                    - (1 - node.storage.storage_loss)
                    * level.shift(time=1)
                    - (1 - node.storage.charging_loss) * charge
                    + discharge).isel(time=slice(1, None))
                    == 0,
                    name=f'storage_level_balance_{node.name}'
                )
                # XXX should we start with empty storage?
                # model.add_constraints(level.isel(time=0) == 0)

                # storage[0] == 0  # XXX is this correct to start with empty storage?
                # storage[t] - storage[t-1] < charging_speed
                # storage[t-1] - storage[t] < discharging_speed
                # storage[t] < size

                # for all time stamps t:
                # sum(input_flows)[t] == sum(output_flows)[t] + eff * (storage[t] - 
                #   storage[t-1]) + storage_loss * storage[t]

                # storage_loss: share of lost storage per time stamp
                # eff: charge and discharge efficiency

        # constraint: sum of inputs = sum of outputs
        for node in nodes:
            if node.output_flows is not None:
                if isinstance(node, NodeFixInput) and isinstance(
                    node.input_flows[""], xr.DataArray
                ):
                    # this if is needed because linopy wants all variables on one side and the 
                    # constants on the other side...
                    # XXX this is super weird... without multiplying by 1, the left-hand-side is of
                    # wrong type, probably because there is only one thing in the summation!

                    if node.storage is None:  # wow this is an ugly nested if!
                        model.add_constraints(
                            1.0 * sum(node.output_flows)
                            == sum(node.input_flows.values()),
                            name=f'input_output_flow_balance_{node.name}'
                        )
                    else:
                        model.add_constraints(
                            1.0 * sum(node.output_flows)
                            + node.storage.charge
                            - node.storage.discharge
                            == sum(node.input_flows.values()),
                            name=f'input_output_flow_balance_{node.name}'
                        )
                else:
                    if node.storage is None:  # wow this is an ugly nested if!
                        model.add_constraints(
                            1.0 * sum(node.output_flows)
                            - sum(node.input_flows.values())
                            == 0,
                            name=f'input_output_flow_balance_{node.name}'
                        )
                    else:
                        model.add_constraints(
                            1.0 * sum(node.output_flows)
                            + node.storage.charge
                            - node.storage.discharge
                            - sum(node.input_flows.values())
                            == 0,
                            name=f'input_output_flow_balance_{node.name}'
                        )

        model.add_objective(self.total_costs())

        return model

    def optimize(self, solver="glpk"):
        # TODO infeasible should raise?
        self.model.solve(solver_name=solver, keep_files=True)

    def total_costs(self):
        technology_costs = sum(
            node.size * node.costs for node in self.nodes if node.costs
        )
        storage_costs = sum(
            node.storage.size * node.storage.costs
            for node in self.nodes
            if hasattr(node, "storage") and node.storage is not None
        )

        if storage_costs != 0:
            # if there is no technology, storage costs is simply an int and this is not 
            # combinable with a linopy expression uargh... :-/
            return technology_costs + storage_costs
        else:
            return technology_costs

    def draw(self):
        nx.draw(
            self.graph,
            pos=graphviz_layout(self.graph, prog="dot"),  # , args='concentrate=false'),
            node_color=[
                node_attrs["color"] for _, node_attrs in self.graph.nodes(data=True)
            ],
            # node_size=5000,
            with_labels=True,
        )


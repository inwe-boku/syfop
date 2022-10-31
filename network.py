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


class NodeBase:
    def __init__(self, name, storage, costs):
        self.name = name
        self.storage = storage
        self.costs = costs

        # this needs to be filled later
        self.outputs = None  
        self.output_flows = None

    def _create_storage_variables(self, model):
        self.storage.size = model.add_variables(name=f"size_storage_{self.name}", lower=0)
        self.storage.level = timeseries_variable(model, f"storage_level_{self.name}")
        self.storage.charge = timeseries_variable(model, f"storage_charge_{self.name}")
        self.storage.discharge = timeseries_variable(model, f"storage_discharge_{self.name}")

    def _create_storage_constraints(self, model):
        size = self.storage.size
        level = self.storage.level
        charge = self.storage.charge
        discharge = self.storage.discharge

        model.add_constraints(
            charge - size * self.storage.max_charging_speed <= 0,
            name=f"max_charging_speed_{self.name}",
        )
        model.add_constraints(
            discharge - size * self.storage.max_charging_speed <= 0,
            name=f"max_discharging_speed_{self.name}",
        )
        model.add_constraints(level - size <= 0, name=f"storage_max_level_{self.name}")
        model.add_constraints(
            level.isel(time=0)
            - (1 - self.storage.charging_loss) * charge.isel(time=0)
            + discharge.isel(time=0)
            == 0,
            name=f"storage_level_balance_t0_{self.name}",
        )
        model.add_constraints(
            (
                level
                - (1 - self.storage.storage_loss) * level.shift(time=1)
                - (1 - self.storage.charging_loss) * charge
                + discharge
            ).isel(time=slice(1, None))
            == 0,
            name=f"storage_level_balance_{self.name}",
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

    def _create_constraint_inout_flow_balance(self, model):
        """Add constraint: sum of inputs == sum of outputs."""
        lhs = sum(self.output_flows)
        # this if is needed because linopy wants all variables on one side and the constants on
        # the other side...
        if isinstance(self, NodeInputProfileBase) and isinstance(
            self.input_flows[""], xr.DataArray
        ):
            rhs = sum(self.input_flows.values())
        else:
            lhs = lhs - sum(self.input_flows.values())
            rhs = 0

        if self.storage is not None:
            lhs = lhs + self.storage.charge - self.storage.discharge

        model.add_constraints(lhs == rhs, name=f"inout_flow_balance_{self.name}")

    def create_variables(self, model):
        if self.storage is not None:
            self._create_storage_variables(model)

    def create_constraints(self, model):
        self._create_constraint_inout_flow_balance(model)

        if self.storage is not None:
            self._create_storage_constraints(model)


class NodeScalableBase(NodeBase):
    def create_variables(self, model):
        super().create_variables(model)

        # TODO atm some nodes should not have variables, but setting costs to 0 does the
        # job too
        # FIXME is this correct to not have size when costs are 0?
        if self.costs:  # None or 0 means that we don't need a size variable
            self.size = model.add_variables(name=f"size_{self.name}", lower=0)

        # each input_flow is a variable (representing the amount of energy in the edge coming from
        # input to self)
        if not isinstance(self, NodeInputProfileBase):
            self.input_flows = {
                input_.name: timeseries_variable(model, f"flow_{input_.name}_{self.name}")
                for input_ in self.inputs
            }

    def create_constraints(self, model):
        super().create_constraints(model)

        # constraint: size of technology
        # if node.output_flows is not None and node.size:
        # FIXME this is probably wrong for FixedInput?!
        if self.output_flows is not None and self.size:
            model.add_constraints(
                sum(self.output_flows) - self.size <= 0,
                name=f"limit_outflow_by_size_{self.name}",
            )

        # constraint: proportion of inputs
        if hasattr(self, "input_proportions") and self.input_proportions is not None:
            for name, proportion in self.input_proportions.items():
                total_input = sum(
                    input_flow for n, input_flow in self.input_flows.items() if n != name
                )
                model.add_constraints(
                    proportion * total_input + (proportion - 1) * self.input_flows[name] == 0.0,
                    name=f"proportion_{self.name}_{name}",
                )


class NodeInputProfileBase(NodeBase):
    def __init__(self, name, input_flow, costs, storage=None):
        super().__init__(name, storage, costs)

        self.inputs = []

        # TODO input_flow should be <1.? (i.e. dimensionless capacity factors)
        # but note: this is wrong for co2 (costs=0), i.e. only for scalable fixed input
        self.input_flows = {"": input_flow}


class NodeOutputProfileBase(NodeBase):
    ...


class NodeFixInputProfile(NodeInputProfileBase):
    # CO2
    ...


class NodeFixOutputProfile(NodeOutputProfileBase):
    # Demand
    ...


class NodeScalableInputProfile(NodeScalableBase, NodeInputProfileBase):
    # Wind, PV, ...
    def create_variables(self, model):
        super().create_variables(model)
        # if input_flows is not None, we have a FixedInput, which we need to scale only
        # if there is a size defined, otherwise it will stay as scalar
        self.input_flows[""] = self.size * self.input_flows[""]


class NodeScalableOutputProfile(NodeScalableBase, NodeOutputProfileBase):
    # ?!
    ...


class Node(NodeScalableBase):
    """This node consists of a size """
    # examples:
    #  - electricity
    #  - hydrogen (with costs > 0)
    #  - curtailing
    def __init__(self, name, inputs, costs, input_proportions=None, storage=None):
        super().__init__(name, storage, costs)

        self.inputs = inputs
        self.input_flows = None

        # TODO some nodes do not need size/costs, e.g. curtailing etc, but setting costs=0 is doing
        # the job, but it creates some unnecessary variables
        self.size = None

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


class Storage:
    # note: atm this is not a node
    def __init__(self, costs, max_charging_speed, storage_loss, charging_loss):
        self.costs = costs  # per size
        self.max_charging_speed = max_charging_speed  # unit: share of total size per timestamp
        self.storage_loss = storage_loss
        self.charging_loss = charging_loss

        assert storage_loss < 1
        assert charging_loss < 1
        assert max_charging_speed <= 1

    # usage examples:
    #  - h2 storage
    #  - co2 storage
    #  - battery


# TODO this should be an input for Flow and maybe use a datetime range as coords
NUM_TIME_STEPS = 8760
time = pd.date_range(2020, freq="h", periods=NUM_TIME_STEPS)


def timeseries_variable(model, name):
    return model.add_variables(
        name=name,
        lower=xr.DataArray(np.zeros(NUM_TIME_STEPS), coords={"time": np.arange(NUM_TIME_STEPS)}),
    )


class Network:
    # basically a list of all technologies
    def __init__(self, nodes):

        all_input_nodes = {input_node for node in nodes for input_node in node.inputs}
        if not (all_input_nodes <= set(nodes)):
            raise ValueError(
                "nodes used as input node, but missing in list of nodes passed to "
                f"Network(): {', '.join(node.name for node in (all_input_nodes - set(nodes)))}"
            )

        self.nodes = nodes
        self.nodes_dict = {node.name: node for node in nodes}
        self.graph = self._create_graph(nodes)
        self.model = self._generate_optimization_model(nodes)

    def _create_graph(self, nodes):
        graph = nx.DiGraph()
        for node in nodes:
            if isinstance(node, NodeInputProfileBase):
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
            node.create_variables(model)

        # XXX not sure if we really need this backward connection, also it won't work as soon as
        # we add demand
        for node in nodes:
            for input_ in node.inputs:
                if input_.outputs is None:
                    input_.outputs = []
                input_.outputs.append(node)

        # this is a bit weird: we want a variable or constant for each edge, but we store it as
        # dict for all input connections and as list for all output connections
        for node in nodes:
            if node.output_flows is None:
                if node.outputs is None:
                    # this is a variable for leaves, i.e. final output, not really needed, but
                    # nice to have and used in size constraints
                    node.output_flows = [timeseries_variable(model, f"flow_{node.name}")]
                else:
                    node.output_flows = [output.input_flows[node.name] for output in node.outputs]

        for node in nodes:
            node.create_constraints(model)

        model.add_objective(self.total_costs())

        return model

    def optimize(self, solver="glpk"):
        # TODO infeasible should raise?
        self.model.solve(solver_name=solver, keep_files=True)

    def total_costs(self):
        technology_costs = sum(node.size * node.costs for node in self.nodes if node.costs)
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
            node_color=[node_attrs["color"] for _, node_attrs in self.graph.nodes(data=True)],
            # node_size=5000,
            with_labels=True,
        )


# %%
def print_constraints(m):
    """
    Print equations of model `m` in a more or less readable form.
    """

    from linopy.io import fill_by, float_to_str, int_to_str, concatenate, asarray

    m.constraints.sanitize_missings()
    kwargs = dict(broadcast_like="vars", filter_missings=True)
    vars = m.constraints.iter_ravel("vars", **kwargs)
    coeffs = m.constraints.iter_ravel("coeffs", **kwargs)
    labels = m.constraints.iter_ravel("labels", **kwargs)

    labels_ = m.constraints.iter_ravel("labels", filter_missings=True)
    sign_ = m.constraints.iter_ravel("sign", filter_missings=True)
    rhs_ = m.constraints.iter_ravel("rhs", filter_missings=True)

    names = m.constraints.labels.data_vars

    iterate = zip(names, labels, vars, coeffs, labels_, sign_, rhs_)

    for (n, l, v, c, l_, s_, r_) in iterate:
        if not c.size:
            continue

        diff_con = l[:-1] != l[1:]
        new_con_b = concatenate([asarray([True]), diff_con])
        end_of_con_b = concatenate([diff_con, asarray([True])])

        l = fill_by(v.shape, new_con_b, "\n" + n + int_to_str(l_) + ":\n")
        s = fill_by(v.shape, end_of_con_b, "\n" + s_.astype(object) + "\n")
        r = fill_by(v.shape, end_of_con_b, float_to_str(r_, ensure_sign=False))

        varname = np.frompyfunc(lambda i: m.variables.get_name_by_label(i) + "%i" % i, 1, 1)

        constraints = l + float_to_str(c) + " * " + varname(v) + s + r

        print("\n".join(constraints))
        print()


# %%

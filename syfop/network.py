import time

import linopy
import networkx as nx
import pandas as pd
from networkx.drawing.nx_pydot import graphviz_layout

from syfop.node import NodeInputProfileBase, NodeOutputProfileBase
from syfop.util import DEFAULT_NUM_TIME_STEPS, timeseries_variable


class Network:
    def __init__(self, nodes, time_coords=DEFAULT_NUM_TIME_STEPS, time_coords_year=2020):
        all_input_nodes = {input_node for node in nodes for input_node in node.inputs}
        if not (all_input_nodes <= set(nodes)):
            raise ValueError(
                "nodes used as input node, but missing in list of nodes passed to "
                f"Network(): {', '.join(node.name for node in (all_input_nodes - set(nodes)))}"
            )

        # XXX minor code duplication with util.const_time_series()
        if isinstance(time_coords, int):
            time_coords = pd.date_range(time_coords_year, freq="h", periods=time_coords)
        self.time_coords = time_coords

        self._check_consistent_time_coords(nodes, time_coords)

        self.nodes = nodes
        self.nodes_dict = {node.name: node for node in nodes}
        self.graph = self._create_graph(nodes)
        self.model = self._generate_optimization_model(nodes)

    def _check_consistent_time_coords(self, nodes, time_coords):
        for node in nodes:
            if not hasattr(node, "input_flows") or node.input_flows is None:
                continue
            for input_flow in node.input_flows.values():
                #
                if len(input_flow.time) != len(time_coords):
                    raise ValueError(
                        f"inconsistent time_coords: node {node.name} has an input flow with "
                        f"length {len(input_flow.time)}, but the network has time_coords with "
                        f"length {len(time_coords)}"
                    )
                if (input_flow.time != time_coords).any():
                    raise ValueError(
                        f"inconsistent time_coords: node {node.name} has an input flow with "
                        "time_coords different from the Network's time_coords"
                    )

    def _create_graph(self, nodes):
        graph = nx.DiGraph()
        for node in nodes:
            if isinstance(node, NodeInputProfileBase):
                color = "red"
            elif isinstance(node, NodeOutputProfileBase):
                color = "black"
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
            node.create_variables(model, self.time_coords)

        # XXX not sure if we really need this backward connection, also it won't work as soon as
        # we add demand
        for node in nodes:
            node.outputs = []
        for node in nodes:
            for input_ in node.inputs:
                input_.outputs.append(node)

        # output connections are not known when Node objects are created, so we add
        # it to the Node objects here, except for nodes which are NodeOutputProfileBase
        for node in nodes:
            if node.output_flows is None:
                if not node.outputs:
                    # this is a variable for leaves, i.e. final output, not really needed, but
                    # nice to have and used in size constraints
                    node.output_flows = {
                        node.name: timeseries_variable(
                            model, self.time_coords, f"flow_{node.name}"
                        )
                    }
                else:
                    node.output_flows = {
                        node.name: output.input_flows[node.name] for output in node.outputs
                    }

                    # TODO this has quadratic performance and is very ugly, but having dicts
                    # everywhere also not nice, maybe switch to some adjacency matrix thingy, where
                    # one can select all input edges or output edges by choosing a column or a row?
                    node.output_commodities = [
                        output.input_commodities[output.inputs.index(node)]
                        for output in node.outputs
                        if output.input_commodities is not None  # FIXME this line is stupid
                    ]

                    # check whether output_proportions are valid and not missing if required
                    # note that the first part could be checked already in the constructor of the
                    # node classes which take output_proportions as parameter
                    node._check_proportions_valid_or_missing(
                        node.outputs, node.output_proportions, node.output_commodities, "output"
                    )

        for node in nodes:
            node.create_constraints(model)

        model.add_objective(self.total_costs())

        return model

    def _check_storage_level_zero(self):
        """This is a basic plausibility check. A storage which is never full or never empty
        could be replaced by a smaller storage, which would be advantageous if costs are
        positive. So something is fishy if this check fails."""
        for node in self.nodes:
            if hasattr(node, "storage") and node.storage is not None and node.storage.costs > 0:
                storage_level = self.model.solution[f"storage_level_{node.name}"]
                storage_size = self.model.solution[f"size_storage_{node.name}"]
                assert storage_level.min() == 0.0, f"storage for {node.name} never empty"
                assert storage_level.max() == storage_size, f"storage for {node.name} never full"

    def optimize(self, solver_name="highs", **kwargs):
        """Optimize all node sizes: minimize total costs (sum of all (scaled) node costs) with
        subject to all constraints induced by the network.

        Parameters
        ----------
        solver_name : str, optional
            all solvers supported by
            [linopy](https://linopy.readthedocs.io/en/latest/solvers.html), by default "highs"

        """
        # TODO infeasible should raise?

        t0 = time.time()

        io_api = "direct" if solver_name in ("gurobi", "highs") else "lp"
        self.model.solve(solver_name=solver_name, keep_files=True, io_api=io_api, **kwargs)

        self._check_storage_level_zero()

        print("Solving time: ", time.time() - t0)

    def total_costs(self):
        technology_costs = sum(node.size * node.costs for node in self.nodes if node.costs)
        storage_costs = sum(
            node.storage.size * node.storage.costs
            for node in self.nodes
            if hasattr(node, "storage") and node.storage is not None
        )

        if isinstance(storage_costs, int):
            # if there is no technology, storage costs is simply an int and this is not
            # combinable with a linopy expression uargh... :-/
            # https://github.com/PyPSA/linopy/issues/60
            return technology_costs
        else:
            return technology_costs + storage_costs

    def draw(self):
        """Draw a graphic representation of the network of all nodes and edges."""
        nx.draw(
            self.graph,
            pos=graphviz_layout(self.graph, prog="dot"),  # , args='concentrate=false'),
            node_color=[node_attrs["color"] for _, node_attrs in self.graph.nodes(data=True)],
            # node_size=5000,
            with_labels=True,
        )

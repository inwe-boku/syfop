import time

import linopy
import networkx as nx
import pandas as pd
from networkx.drawing.nx_agraph import graphviz_layout

from syfop.node import NodeInputProfileBase, NodeOutputProfileBase
from syfop.util import DEFAULT_NUM_TIME_STEPS, timeseries_variable


class SolverError(Exception):
    ...


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
                color = "#c72321"
            elif isinstance(node, NodeOutputProfileBase):
                color = "#f0c220"
            else:
                color = "#000000"

            graph.add_node(node.name, color=color)

            if hasattr(node, "storage") and node.storage is not None:
                # XXX hopefully this name is unique
                graph.add_node(f"{node.name}_storage", color="#0d8085")
                graph.add_edge(f"{node.name}_storage", node.name)
                graph.add_edge(node.name, f"{node.name}_storage")

            for input_ in node.inputs:
                graph.add_edge(input_.name, node.name)
        return graph

    def _add_leaf_flow_variables(self, model, nodes):
        # Add a variable for nodes, which do not have input flows or output flows. This variable
        # should be simply the sum of output flows (for the input flow variable) or sum of input
        # flows (for the output flow variable).
        # This is not really needed but nice to have to see the values in the solution and
        # output_flow comes in handy in to be in the size constraints.
        for node in nodes:
            if len(node.input_flows) == 0:
                node.input_flows[node.name] = timeseries_variable(
                    model, self.time_coords, f"input_flow_{node.name}"
                )
            if len(node.output_flows) == 0:
                node.output_flows[node.name] = timeseries_variable(
                    model, self.time_coords, f"output_flow_{node.name}"
                )

    def _generate_optimization_model(self, nodes):
        model = linopy.Model()

        for node in nodes:
            node.create_variables(model, self.time_coords)

        for node in nodes:
            node.outputs = []
        for node in nodes:
            for input_ in node.inputs:
                input_.outputs.append(node)

        # output connections are not known when Node objects are created, so we add
        # it to the Node objects here, except for nodes which are NodeOutputProfileBase
        for node in nodes:
            if node.output_flows is None:
                node.output_flows = {
                    output.name: output.input_flows[node.name] for output in node.outputs
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

                if (
                    len(set(node.output_commodities)) > 1
                    and hasattr(node, "storage")
                    and node.storage is not None
                ):
                    # we have one storage per node, so it is not clear what should be stored
                    raise ValueError("storage not supported for multiple output commodities (yet)")

        self._add_leaf_flow_variables(model, nodes)

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
                # XXX not sure what to use as epsilon here
                assert (
                    storage_level.min() < 1e-12
                ), f"storage for {node.name} never empty (min value: {storage_level.min()}"
                assert (
                    storage_level.max() > storage_size - 1e-12
                ), f"storage for {node.name} never full (max value: {storage_level.max()}"

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

        if linopy.constants.SolverStatus[self.model.status] != linopy.constants.SolverStatus.ok:
            raise SolverError(
                f"unable to solve optimization, solver status={self.model.status}, "
                f"termination condition={self.model.termination_condition}"
            )

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

    def draw(self, mode="netgraph"):
        """Draw a graphic representation of the network of all nodes and edges.

        Parameters
        ----------
        mode : str
            choice of plotting library used to draw the graph, one of: netgraph, graphviz


        """
        # this requires python >=3.7, otherwise order of values() is not guaranteed
        node_color = {
            node: node_attrs["color"] for node, node_attrs in self.graph.nodes(data=True)
        }

        if mode == "graphviz":
            nx.draw(
                self.graph,
                pos=graphviz_layout(self.graph, prog="dot"),
                node_color=node_color.values(),
                # node_size=5000,
                with_labels=True,
            )
        elif mode == "netgraph":
            # netgraph is used only here, let's keep it an optional dependency
            import netgraph

            # TODO we could do some fancy stuff here to make plotting nicer:
            #   shape = input_proportions
            #   color = output node
            #   scalable or fixed size?
            #   display results?
            #   display commodities / units?
            # TODO allow custom args to be passed to netgraph?
            netgraph.Graph(
                self.graph,
                node_labels=True,
                node_layout="dot",
                node_label_offset=0.09,
                node_color=node_color,
                arrows=True,
                edge_width=1.2,
                node_edge_width=0.0,
            )
        else:
            raise ValueError(f"invalid draw mode: {mode} (valid modes: netgraph, graphviz)")

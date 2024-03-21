import logging
import time

import linopy
import networkx as nx
import pandas as pd
from networkx.drawing.nx_agraph import graphviz_layout

from syfop.node_base import NodeInputBase, NodeOutputBase
from syfop.util import DEFAULT_NUM_TIME_STEPS, timeseries_variable


class SolverError(Exception):
    """Raised when the solver fails to find an optimal solution."""

    ...


class Network:
    """A network is a directed acyclic graph of nodes, which represents the flow of commodities
    between nodes. Nodes are represented by objects of classes defined in ``syfop.node``. The
    connections between nodes are defined by the parameter ``inputs`` when creating node objects.

    The network is used to optimize the sizes of the nodes, such that the total costs are
    minimized.

    Attributes of this class are not supposed to be modified outside of this class - use the
    methods instead.

    Attributes
    ----------
    nodes : list of subclasses of syfop.node.NodeBase
        List of nodes to be included in the network. All nodes used as input nodes need to be
        included in this list.
    time_coords : pandas.DatetimeIndex
        time coordinates for the optimization problem
    nodes_dict : dict
        dictionary of nodes with node names as keys
    graph : networkx.DiGraph
        used for drawing the network
    model : linopy.Model
        optimization model for the network

    """

    def __init__(
        self,
        nodes,
        time_coords=DEFAULT_NUM_TIME_STEPS,
        time_coords_year=2020,
        solver_dir=None,
    ):
        """Create a network of nodes.

        Parameters
        ----------
        nodes : list of subclasses of syfop.node.NodeBase
            List of nodes to be included in the network. All nodes used as input nodes need to be
            included in this list otherwise a ValueError is raised.
        time_coords : int or pandas.DatetimeIndex
            time coordinates used for all time series in the network, typically hourly time steps
            for a year
        time_coords_year : int
            used only if time_coords is an int
        solver_dir : str
            Path where temporary files for the lp file, see
            [``linopy.model.Model``](https://linopy.readthedocs.io/en/latest/generated/linopy.model.Model.html#linopy.model.Model.__init__).
            This is used as workaround on the VSC [VSC](https://vsc.ac.at), because the defaut temp
            folder is on a partition with very limited space and deleting the files after the
            optimization does not work (always?).


        """
        if len(nodes) == 0:
            raise ValueError("empty network not allowed, provide a non empty list of nodes!")

        all_input_nodes = {input_node for node in nodes for input_node in node.inputs}
        if not (all_input_nodes <= set(nodes)):
            raise ValueError(
                "nodes used as input node, but missing in list of nodes passed to "
                f"Network(): {', '.join(node.name for node in (all_input_nodes - set(nodes)))}"
            )

        # check if names of nodes are unique
        node_names = [node.name for node in nodes]
        if len(set(node_names)) != len(nodes):
            raise ValueError(f"node names are not unique: {', '.join(node_names)}")

        # minor code duplication with util.const_time_series(), but should not matter too much
        if isinstance(time_coords, int):
            time_coords = pd.date_range(str(time_coords_year), freq="h", periods=time_coords)
        self.time_coords = time_coords

        self._check_consistent_time_coords(nodes, time_coords)

        self.nodes = nodes
        self.nodes_dict = {node.name: node for node in nodes}
        self.graph = self._create_graph(nodes)

        self.model = self._generate_optimization_model(nodes, solver_dir)

    def _check_consistent_time_coords(self, nodes, time_coords):
        # all time series need to be defined on the same coordinates otherwise vector comparison
        # will lead to empty constraints
        for field in ("input_flows", "output_flows", "input_profile", "output_profile"):
            for node in nodes:
                if not hasattr(node, field) or getattr(node, field) is None:
                    # don't need to check flows created later than this check, because these are
                    # filled with flows using self.time_coords
                    continue

                flows = getattr(node, field)
                if isinstance(flows, dict):
                    flows = flows.values()
                    field_title = "an item in"
                else:
                    flows = [flows]
                    field_title = "an"

                for flow in flows:
                    if len(flow.time) != len(time_coords):
                        raise ValueError(
                            f"inconsistent time_coords: node {node.name} has {field_title} {field} "
                            f"with length {len(flow.time)}, but the network has time_coords "
                            f"with length {len(time_coords)}"
                        )
                    if (flow.time != time_coords).any():
                        raise ValueError(
                            f"inconsistent time_coords: node {node.name} has {field_title} {field} "
                            "with time_coords different from the Network's time_coords"
                        )

    def _create_graph(self, nodes):
        """Create a nx.DiGraph object to plot the network."""
        graph = nx.DiGraph()
        for node in nodes:
            if isinstance(node, NodeInputBase):
                color = "#c72321"
            elif isinstance(node, NodeOutputBase):
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
        # In most cases this is not really needed but nice to have to see the values in the
        # solution and output_flow comes in handy in to be in the size constraints.
        # When input_flow_costs is set on nodes which do not have any other inputs set (fixed,
        # profile or other nodes), this is used to determine the total input_flow_costs. Also it
        # makes the constraints easier because we never have empty sums.
        for node in nodes:
            if len(node.input_flows) == 0:
                node.input_flows[""] = timeseries_variable(
                    model, self.time_coords, f"input_flow_{node.name}"
                )
            if len(node.output_flows) == 0:
                node.output_flows[""] = timeseries_variable(
                    model, self.time_coords, f"output_flow_{node.name}"
                )

    def _generate_optimization_model(self, nodes, solver_dir):
        """Create the linopy optimization model for the network."""
        model = linopy.Model(solver_dir=solver_dir)

        for node in nodes:
            node.create_variables(model, self.time_coords)

        for node in nodes:
            node.outputs = []
        for node in nodes:
            for input_ in node.inputs:
                input_.outputs.append(node)

        # output connections are not known when Node objects are created, so we add
        # it to the Node objects here, except for nodes which are NodeOutputeBase
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

    def add_variables(self, *args, **kwargs):
        """Add custom variables to the linopy optimization model. See
        ``linopy.Model.add_variables()`` for a documentation of the parameters.

        This method must be called before ``Network.optimize()`` is called.

        """
        return self.model.add_variables(*args, **kwargs)

    def add_constraints(self, *args, **kwargs):
        """Add custom constraints to the linopy optimization model. See
        ``linopy.Model.add_constraints()`` for a documentation of the parameters.

        To create the constraint, variables can be accessed via ``Network.model.variables`` or by
        node attributes, e.g. in `Network.nodes_dict['wind'].size` for a node with name "wind".

        This method must be called before ``Network.optimize()`` is called.

        """
        return self.model.add_constraints(*args, **kwargs)

    def _check_storage_level_zero(self):
        """This is a basic plausibility check. A storage which is never full or never empty
        could be replaced by a smaller storage, which would be advantageous if costs are
        positive. So something is fishy if this check fails.

        """
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
            all solvers supported by `linopy
            <https://linopy.readthedocs.io/en/latest/prerequisites.html#install-a-solver>`__, by
            default "highs"
        **kwargs
            additional parameters passed to the solver via ``linopy.Model.solve()``.

        """
        # TODO infeasible should raise?

        t0 = time.time()

        io_api = "direct" if solver_name in ("gurobi", "highs") else "lp"
        self.model.solve(solver_name=solver_name, io_api=io_api, **kwargs)

        if linopy.constants.SolverStatus[self.model.status] != linopy.constants.SolverStatus.ok:
            raise SolverError(
                f"unable to solve optimization, solver status={self.model.status}, "
                f"termination condition={self.model.termination_condition}"
            )

        self._check_storage_level_zero()

        logging.info("Solving time: %s", time.time() - t0)

    def total_costs(self):
        """Return the total costs of the network as a linopy expression: this is the sum of all
        node costs (size of the node times the cost per unit) and input flow costs (sum of all
        input flows of the complete time span times the cost per unit).

        This is used as objective in the optimization problem.

        The result of the solved optimization can be found in the attribute
        ``Network.model.objective.value``.

        """
        technology_costs = sum(node.size * node.costs for node in self.nodes if node.costs)
        storage_costs = sum(
            node.storage.size * node.storage.costs
            for node in self.nodes
            if hasattr(node, "storage") and node.storage is not None
        )

        costs = technology_costs

        # add costs for input_flows (e.g. fuel costs) if defined
        for node in self.nodes:
            if not hasattr(node, "input_flow_costs") or node.input_flow_costs == 0.0:
                continue
            input_flows = list(node.input_flows.values())
            assert len(input_flows) == 1, "only one input flow is supported for now"
            costs = costs + node.input_flow_costs * input_flows[0].sum()

        costs = costs + storage_costs

        return costs

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

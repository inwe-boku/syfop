import logging
import time

import linopy
import networkx as nx
import pandas as pd
from networkx.drawing.nx_agraph import graphviz_layout

from syfop.node_base import NodeInputBase, NodeOutputBase
from syfop.units import default_units, interval_length_h, ureg
from syfop.util import DEFAULT_NUM_TIME_STEPS, timeseries_variable


class SolverError(Exception):
    """Raised when the solver fails to find an optimal solution."""

    ...


class Network:
    """A network is a directed acyclic graph of nodes, which represents the flow of commodities
    between nodes. Nodes are represented by objects of classes defined in :py:mod:`syfop.node`.
    The connections between nodes are defined by the parameter ``inputs`` when creating node
    objects.

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
    model : linopy.model.Model
        optimization model for the network

    """

    def __init__(
        self,
        nodes,
        time_coords=None,
        time_coords_freq="h",
        time_coords_num=DEFAULT_NUM_TIME_STEPS,
        time_coords_year=2020,
        total_cost_unit=ureg.EUR,
        solver_dir=None,
        units={},
    ):
        """
        Parameters
        ----------
        nodes : list of subclasses of syfop.node.NodeBase
            List of nodes to be included in the network. All nodes used as input nodes need to be
            included in this list otherwise a ``ValueError`` is raised.
        time_coords : pandas.DatetimeIndex
            time coordinates used for all time series in the network, typically hourly time steps
            for a year. If ``None``, ``time_coords`` are generated using the parameters
            ``time_coords_freq``, ``time_coords_num`` and ``time_coords_year``.
        time_coords_freq : str
            used only if ``time_coords`` is ``None``, frequency of the time coordinates
        time_coords_num : int
            used only if ``time_coords`` is ``None``, number of time stamps generated. Note that
            the default value might be wrong in case of a leap year.
        time_coords_year : int
            used only if ``time_coords`` is ``None``, year used for generating time stamps (first
            hour of this year will be used for the first time stamp)
        total_cost_unit : pint.Unit
            unit of the objective function, needs to be a currency
        solver_dir : str
            Path where temporary files for the lp file, see :py:class:`linopy.model.Model`. This is
            used as workaround on the `VSC <https://vsc.ac.at>`__, because the default temp folder
            is on a partition with very limited space and deleting the files after the optimization
            does not work (always?).
        units : dict
            A mapping from commodity to unit, e.g. ``{"electricity": ureg.MW}``. This overwrites
            the default units in :py:mod:`syfop.units.default_units`. Required for commodities,
            which are not defined in :py:mod:`syfop.units.default_units`.

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
        # TODO we might run into troubles if constraints or variables are not unique, e.g. because
        # the name contains underscores
        node_names = [node.name for node in nodes]
        if len(set(node_names)) != len(nodes):
            raise ValueError(f"node names are not unique: {', '.join(node_names)}")

        # minor code duplication with util.const_time_series(), but should not matter too much
        if time_coords is None:
            time_coords = pd.date_range(
                str(time_coords_year),
                freq=time_coords_freq,
                periods=time_coords_num,
            )
        self.time_coords = time_coords

        self.nodes = nodes
        self.nodes_dict = {node.name: node for node in nodes}

        self.total_cost_unit = total_cost_unit

        self._set_units(units)

        self._check_consistent_time_coords(nodes, time_coords)
        self._check_all_nodes_connected(nodes)

        self.model = self._generate_optimization_model(nodes, solver_dir)

    def _set_units(self, units):
        self.units = default_units.copy()
        self.units.update(units)

        # if units is never modified later on, this should be okay to allow nodes to access units
        for node in self.nodes:
            node.units = self.units

    def _check_all_nodes_connected(self, nodes):
        """Check if graph of node forms a connected network."""
        graph = self._create_graph(nodes)
        components = list(nx.weakly_connected_components(graph))
        if len(components) > 1:
            raise ValueError(
                "network is not connected, there are multiple components: "
                f"{', '.join(str(component) for component in components)}"
            )

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

    def _set_missing_input_commodities(self, nodes):
        # set input commodities for input nodes, i.e. NodeScaleableInput and NodeFixedInput:
        # Input nodes have only one input commodity, which is the same as the output commodity,
        # therefore it does not need to be set explicitly by the user, but can be infered from the
        # node(s) it is connected to.
        # We need to disallow multiple output_commodities for input nodes anyhow, because there is
        # no convert factor.
        for node in nodes:
            if node.input_commodities is None:
                assert (
                    len(set(node.output_commodities)) == 1
                ), f"unexpected number of output_commodities for node '{node.name}'"

                # all other node types should have input_commmodities set at this point
                assert isinstance(
                    node, NodeInputBase
                ), f" unexpected type for node '{node.name}': {type(node)}"
                node.input_commodities = [node.output_commodities[0]]

    def _set_output_connections(self, nodes):
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

                if len(node.output_commodities) == 0:
                    # here we have no ouputs of a Node, so there is only the leaf output flow
                    node.output_commodities = [node.size_commodity]

                if (
                    len(set(node.output_commodities)) > 1
                    and hasattr(node, "storage")
                    and node.storage is not None
                ):
                    # we have one storage per node, so it is not clear what should be stored
                    raise ValueError("storage not supported for multiple output commodities")

    def _generate_optimization_model(self, nodes, solver_dir):
        """Create the linopy optimization model for the network."""
        model = linopy.Model(solver_dir=solver_dir)

        for node in nodes:
            node.create_variables(model, self.time_coords)

        self._set_output_connections(nodes)

        self._set_missing_input_commodities(nodes)

        self._add_leaf_flow_variables(model, nodes)

        for node in nodes:
            node.create_constraints(model, self.time_coords)

        model.add_objective(self.total_costs())

        return model

    def add_variables(self, *args, **kwargs):
        """Add custom variables to the linopy optimization model. See
        :py:meth:`linopy.model.Model.add_variables()` for a documentation of the parameters.

        This method must be called before :py:class:`Network.optimize()` is called.

        """
        return self.model.add_variables(*args, **kwargs)

    def add_constraints(self, *args, **kwargs):
        """Add custom constraints to the linopy optimization model. See
        :py:meth:`linopy.model.Model.add_constraints()` for a documentation of the parameters.

        To create the constraint, variables can be accessed via ``Network.model.variables`` or by
        node attributes, e.g. in ``Network.nodes_dict['wind'].size`` for a node with name *wind*.

        This method must be called before :py:meth:`Network.optimize()` is called.

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
            <https://linopy.readthedocs.io/en/latest/prerequisites.html#install-a-solver>`__
        **kwargs
            additional parameters passed to the solver via :py:meth:`linopy.model.Model.solve()`.

        """
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
        technology_costs = sum(
            node.size * node.costs_magnitude(self.total_cost_unit)
            for node in self.nodes
            if node.has_costs()
        )
        storage_costs = sum(
            node.storage.size * node.storage_cost_magnitude(self.total_cost_unit)
            for node in self.nodes
            if hasattr(node, "storage") and node.storage is not None
        )

        costs = technology_costs

        # add costs for input_flows (e.g. fuel costs) if defined
        for node in self.nodes:
            if not hasattr(node, "input_flow_costs") or not node.input_flow_costs:
                continue
            input_flows = list(node.input_flows.values())
            assert len(input_flows) == 1, "only one input_flow is supported"
            input_flow = input_flows[0]

            # this is just a check: atm we support only Node, so input_flows should be plain linopy
            # variables without units, but in case of a NodeScalableInput or a NodeFixInput we
            # would need to strip units here and use the magnitude.
            assert isinstance(input_flows[0], linopy.Variable), "unexpected input_flow type"

            interval_length_h_ = interval_length_h(self.time_coords)

            input_flow_unit = self.units[node.input_commodities[0]]  # something like MW
            input_flow_costs_mag = node.input_flow_costs.to(
                self.total_cost_unit / (input_flow_unit * ureg.h)
            ).magnitude

            # something like: EUR/MWh * x h * MW
            costs = costs + input_flow_costs_mag * interval_length_h_ * input_flow.sum()

        costs = costs + storage_costs

        return costs

    @staticmethod
    def _create_graph(nodes):
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

    def draw(self, mode="netgraph"):
        """Draw a graphic representation of the network of all nodes and edges.

        Parameters
        ----------
        mode : str
            choice of plotting library used to draw the graph, one of: netgraph, graphviz

        """
        graph = self._create_graph(self.nodes)

        # this requires python >=3.7, otherwise order of values() is not guaranteed
        node_color = {node: node_attrs["color"] for node, node_attrs in graph.nodes(data=True)}

        if mode == "graphviz":
            nx.draw(
                graph,
                pos=graphviz_layout(graph, prog="dot"),
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
                graph,
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

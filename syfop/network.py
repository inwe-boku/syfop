import linopy
import networkx as nx
import matplotlib.pyplot as plt
from networkx.drawing.nx_pydot import graphviz_layout

from syfop.node import NodeInputProfileBase
from syfop.util import timeseries_variable


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
            # TODO why is this a list and not a dict?!
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

    def optimize(self, solver_name="glpk", **kwargs):
        # TODO infeasible should raise?
        self.model.solve(solver_name=solver_name, keep_files=True, io_api="direct", **kwargs)

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

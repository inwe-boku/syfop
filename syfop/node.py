from syfop.node_base import NodeInputBase, NodeOutputBase, NodeScalableBase


class NodeFixInput(NodeInputBase):
    """A node with a fixed input profile, i.e. input flow for each time stamp is given. There is no
    size variable and no scaling.

    Example
    -------

    **CO2 stream:** A node representing the CO2 stream from a ethanol refineries, which can be used
    to produce methanol. The CO2 stream is given as a fixed time series, which involves the
    seasonality of the ethanol production (e.g. given by fermentation of sugar cane).

    See also:
    https://doi.org/10.1038/s41467-022-30850-2

    """

    # FIXME does it make sense that this class supports costs? they won't be scaled...
    ...


class NodeFixOutput(NodeOutputBase):
    """A node with a fixed output profile, i.e. output flow for each time stamp is given.

    Example
    -------

    **Demand:** A node representing the demand of a certain commodity. The demand is given as a
    fixed time series. Imagine the demand of electricity in a certain region for each hour over a
    year.

    """

    # FIXME does it make sense that this class supports costs?
    # TODO do we need to support input_proportions here?
    # FIXME if this has no size, but costs, would it fail?
    ...


class NodeScalableInput(NodeScalableBase, NodeInputBase):
    """A given input profile is scaled by a size variable.

    Use cases: wind or PV time series as capacity factors and size is the installed capacity.

    Note that 0 <= input_flow <= 1 needs to be given otherwise size wouldn't be maximum total
    output of the node because input_flow is multiplied with the size variable.

    Attributes
    ----------
    size: linopy.Variable
        The size of the node.

    """

    def __init__(
        self,
        name,
        input_flow,
        costs,
        output_unit,
        output_proportions=None,
        storage=None,
    ):
        """
        Parameters
        ----------
        name : str
            Name of the node, must be unique in the network
        input_flow : xr.DataArray
            Time series of the input flow. Must be capacity factors, i.e. between 0 and 1.
        costs : float
            Costs per unit of size.
        output_unit : list of str or str
            Unit of the output commodity.
        output_proportions : dict
            Proportions of the output flows. The keys are the names of the output flows and the
            values are the proportions. The proportions must sum up to 1. If not given, all output
            commodities must be equal.
        storage : Storage, optional
            Storage attached to the node.

        """
        if not ((0 <= input_flow) & (input_flow <= 1)).all():
            raise ValueError(
                "invalid values in input_flow: must be capacity factors, i.e. between 0 and 1"
            )

        super().__init__(
            name,
            input_flow,
            costs,
            output_unit,
            output_proportions=output_proportions,
            storage=storage,
        )

    def create_variables(self, model, time_coords):
        super().create_variables(model, time_coords)
        self.input_flows[""] = self.size * self.input_flows[""]


class NodeScalableOutput(NodeScalableBase, NodeOutputBase):
    """Represents a node which has a size variable and a given output profile."""

    # TODO what would be the usecase of such a node?!
    # TODO do we need to check if output_flow <= 1? How does scaling work here?
    # TODO do we need the size limit constraint here?
    def __init__(self):
        raise NotImplementedError("NodeScalableOutput is not implemented yet")


class Node(NodeScalableBase):
    """Represents a node which has no preset input or output flows or profiles. That means, that
    input and output flows are determined by the nodes connected to it.

    If `costs` is given, the node has a size variable:

    Attributes
    ----------
    size: linopy.Variable
        The size of the node.

    Examples
    --------

    **Electrolyzer:** In a network where hydrogen is generated using renewable electricity, the
    electrolyzer can be modeled to be of type `Node`. It has a size variable, which represents the
    capacity of the electrolyzer. The input flow is the electricity and the output flow is the
    hydrogen. The costs are the costs per per unit of capacity.

    **Electricity:** In a network where electricity is produced from different renewable sources,
    a virtual electricity node, which does not represent real technology, can be used to implement
    a combined storage.The costs should be set to zero, because the node does not represent a real
    technology.

    **Curtailment:** In a network with renewable electricity sources, a curtailment node can be
    used to consume electric energy which cannot be stored or used otherwise. The costs should be
    set to zero.

    """

    def __init__(
        self,
        name,
        inputs,
        input_commodities,
        costs,
        output_unit,
        convert_factor=1.0,
        input_proportions=None,
        output_proportions=None,
        storage=None,
        input_flow_costs=0.0,
    ):
        """
        Parameters
        ----------
        name : str
            Name of the node, must be unique in the network
        inputs : list of subclasses of syfob.nodes.NodeBase
            node objects that are inputs to this node, i.e. from each input node there is a
            connection to this node
        input_commodities : list of str
            List of input commodities. If all inputs have the same commodity, a single string can
            be given.
        costs : float
            Costs per size.
        output_unit : str
            Unit of the output commodity.
        convert_factor : float, optional
            Conversion factor for the output commodity. Default is 1.0.
        input_proportions : dict
            Proportions of the input flows. The keys are the names of the input flows and the
            values are the proportions. The proportions must sum up to 1. If not given, all input
            commodities must be equal.
        output_proportions : dict
            Proportions of the output flows. The keys are the names of the output flows and the
            values are the proportions. The proportions must sum up to 1. If not given, all output
            commodities must be equal.
        storage : Storage
            Storage attached to the node.
        input_flow_costs : float
            Costs per input flow.

        """
        super().__init__(name, storage, costs, output_unit, convert_factor)

        # TODO add check that inputs does not contain nodes of type NodeOutputBase?
        self.inputs = inputs

        # str = equal for each input
        self.input_commodities = self._preprocess_input_commodities(inputs, input_commodities)

        self.input_flows = None

        # TODO some nodes do not need size/costs, e.g. curtailing etc, but setting costs=0 is doing
        # the job, but it creates some unnecessary variables
        self.size = None

        self._check_proportions_valid_or_missing(
            self.inputs, input_proportions, self.input_commodities, "input"
        )
        self.input_proportions = input_proportions
        self.output_proportions = output_proportions

        self.input_flow_costs = input_flow_costs

    def create_constraints(self, model):
        super().create_constraints(model)

        # XXX why is this not needed in scalable classes?
        # constraint: size of technology
        if self.size is not None:
            lhs = sum(self.output_flows.values()) - self.size

            if self.storage is not None:
                lhs = lhs + self.storage.charge

            model.add_constraints(
                lhs <= 0,
                name=f"limit_outflow_by_size_{self.name}",
            )


class Storage:
    """A ``Storage`` can be attached to a node to store a certain amount of the output commodity
    for later time stamps. A storage has a size variable, which is measured in units of the output
    commodity of its node. Storage for nodes with multiple output commodities are not supported at
    the moment.

    """

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

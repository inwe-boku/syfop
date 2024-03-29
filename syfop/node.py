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

    Attributes
    ----------
    size: linopy.Variable
        The size of the node.


    Example
    -------

    The node represents wind or PV electricity generation. Capacity factor time series are given
    and multiplied with a size variable to create the input flow.

    """

    def __init__(
        self,
        name,
        input_profile,
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
        input_profile : xr.DataArray
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
        if not ((0 <= input_profile) & (input_profile <= 1)).all():
            raise ValueError(
                "invalid values in input_profile: must be capacity factors, i.e. between 0 and 1"
            )

        self.input_profile = input_profile

        super().__init__(
            name=name,
            input_flow=None,  # overwritten by create_variables()
            costs=costs,
            output_unit=output_unit,
            output_proportions=output_proportions,
            storage=storage,
        )
        self.input_flows = None

    def create_variables(self, model, time_coords):
        super().create_variables(model, time_coords)
        self.input_flows = {"": self.size * self.input_profile}


class NodeScalableOutput(NodeScalableBase, NodeOutputBase):
    """Represents a node which has a size variable and a given output profile."""

    # TODO what would be the usecase of such a node?!
    # TODO do we need to check if output_flow <= 1? How does scaling work here?
    # TODO do we need the size limit constraint here?
    def __init__(self):
        """Note: This is not implemented yet!"""
        # this would be probably more less the same as NodeScalableInput, right?
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
            Costs per unit of input flow. Use this to add fuel costs. At the moment this is not
            available for oder node types: NodeFixInput would add constant input flow costs, which
            does not change the optimation result and NodeScalableInput would add costs which are
            proportional to its size, which could be added to the ``costs`` parameter.
            At maximum one input node is allowed if ``input_flow_costs>0``.

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

    **Examples:** hydrogen storage, CO2 storage, battery.

    Attributes
    ----------
    size : linopy.Variable
        The size of the storage.
    level : linopy.Variable
        The level of the storage for each time stamp, i.e. the amount of the stored commodity.
    charge : linopy.Variable
        The amount of the commodity that is charged into the storage for each time stamp.
    discharge : linopy.Variable
        The amount of the commodity that is discharged from the storage for each time stamp. A
        positive value for ``charge`` and ``discharge`` in the same time stamp does not make sense,
        but it is not forbidden in any way. However, such a case will not be optimal if
        ``charging_loss>0``.

    """

    # Note: atm this is not implemented as node class. Probably could be done, but might be more
    # complicated to be implemented
    def __init__(self, costs, max_charging_speed, storage_loss, charging_loss):
        """
        Parameters
        ----------
        costs : float
            Storage costs per unit of size
        max_charging_speed : float
            Maximum charging speed, i.e. the share of the total size that can be charged per time
            stamp. For example, if the maximum charging speed is 0.5, two time stamps are needed to
            charge the storage completely.
        storage_loss : float
            Loss of stored commodity per time stamp as share of the stored commodity. For example,
            if the storage loss for a battery is 0.01 and the battery is half full, 0.5% of the
            battery capacity is lost in the next time stamp.
        charging_loss : float
            Loss of charged commodity per time stamp as share of the charged commodity. For
            example, if ``charging_loss`` is 0.01 and there is 100kg of excess hydrogen to be
            stored in a certain timestamp, only 99kg will end up in the storage.

        """
        self.costs = costs  # per size
        self.max_charging_speed = max_charging_speed  # unit: share of total size per timestamp
        self.storage_loss = storage_loss
        self.charging_loss = charging_loss

        # a loss which equals to 1 does not make sense, because everything would be lost
        # if charging_loss == 0. solutions might be indeterministic because charging and
        # discharging might be done in the same time stamp
        assert 0 <= storage_loss < 1, "storage_loss must be smaller than 1"
        assert 0 <= charging_loss < 1, "charging_loss must be smaller than 1"
        assert 0 < max_charging_speed <= 1, "max_charging_speed must not be greater than 1"

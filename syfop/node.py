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
    size: linopy.variables.Variable
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
        costs : pint.Quantity
            Costs per unit of size.
        output_proportions : dict
            Proportions of the output flows. The keys are the names of the output commodities and
            the values are a quantity of the type of the output commodity, all multiples of these
            values are allowed.
            Example: ``{"electricity": 0.3 * ureg.MW, "heat": 2.3 * ureg.kW}``.
        storage : Storage
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
    size: linopy.variables.Variable
        The size of the node: sum of the output flows are less or equal to the size. If there are
        multiple output commodities, only output flows for ``size_commodity`` are used for the sum
        of output flows.

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
        convert_factor=1.0,
        convert_factors=None,
        size_commodity=None,
        input_proportions=None,
        output_proportions=None,
        storage=None,
        input_flow_costs=None,
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
        costs : pint.Quantity
            Costs per size. See also ``size_commodity``. Can be set to zero, e.g. for curtailing
            nodes: in this case no size variable will be created.
        convert_factor : float or pint.Quantity
            Conversion factor for the output commodity. If this node has multiple different input
            comodities, the parameter ``convert_factors`` needs to be used.
        convert_factors : dict
            a dictionary where each output commodity maps to a tuple of a input commodity to a
            convert factor, example: ``{'hydrogen': ('electricity', 42 * ureg.t / ureg.MW}``
        size_commodity : str
            Which commodity is used to define the size of the Node. This parameter is only
            required, if there is more than one output commodity or if there are no output nodes
            connected, otherwise it is defined automatically.
        input_proportions : dict
            Proportions of the input flows. The keys are the names of the input commodities and the
            values are a quantity of the type of the input commodity, all multiples of these values
            are allowed. Example: ``{"electricity": 0.3 * ureg.MW, "co2": 2.3 * ureg.t/ureg.h}``.
        output_proportions : dict
            Proportions of the output flows. The keys are the names of the output commodities and
            the values are a quantity of the type of the output commodity, all multiples of these
            values are allowed.
            Example: ``{"electricity": 0.3 * ureg.MW, "heat": 2.3 * ureg.kW}``.
        storage : Storage
            Storage attached to the node.
        input_flow_costs : pint.Quantity
            Costs per unit of input flow. Use this to add fuel costs. This is not available for
            oder node types: NodeFixInput would add constant input flow costs, which does not
            change the optimation result and NodeScalableInput would add costs which are
            proportional to its size, which could be added to the ``costs`` parameter. At maximum
            one input node is allowed if ``input_flow_costs`` is given.

        """
        super().__init__(name, storage, costs, convert_factor, convert_factors)

        # TODO add check that inputs does not contain nodes of type NodeOutputBase?
        self.inputs = inputs

        # str = equal for each input
        self.input_commodities = self._preprocess_input_commodities(inputs, input_commodities)

        self.input_flows = None

        self.size = None

        # output_proportions are checked in Network.__init__, when we know the output commodities
        self._check_proportions_valid(input_proportions, self.input_commodities, "input")

        self._size_commodity = size_commodity
        self.input_proportions = input_proportions
        self.output_proportions = output_proportions

        self.input_flow_costs = input_flow_costs

    def create_constraints(self, model):
        super().create_constraints(model)

        # constraint: output_flows are limited by the size of technology in each timestamp
        # Note: this is not needed for NodeScalableInput and NodeScalableOutput because there the
        # input_profile and output_profile are checked to be between 0 and 1.
        if self.size is not None:
            output_flows = self._get_output_flows(self.size_commodity)
            lhs = sum(output_flows) - self.size

            # FIXME this is probably probably missing for NodeScalableInput
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

    The storage for one node does not support multiple different output commodities at the moment.
    If you need a storage for different output commodities, create a separate nodes for each
    commodity and attach a separate storage there.

    **Examples:** hydrogen storage, CO2 storage, battery.

    Attributes
    ----------
    size : linopy.variables.Variable
        The size of the storage.
    level : linopy.variables.Variable
        The level of the storage for each time stamp, i.e. the amount of the stored commodity.
    charge : linopy.variables.Variable
        The amount of the commodity that is charged into the storage for each time stamp.
    discharge : linopy.variables.Variable
        The amount of the commodity that is discharged from the storage for each time stamp. A
        positive value for ``charge`` and ``discharge`` in the same time stamp does not make sense,
        but it is not forbidden in any way. However, such a case will not be optimal if
        ``charging_loss>0``.

    **Note:** The units of the variables ``size``, ``level``, ``charge`` and ``discharge`` are
    given by the unit of the commodity times hours (independently of the interval size between time
    stamps). This means for a battery, the variables will be given in `MWh` if the unit for
    'electricity' is set to `MW`. This means that the values in ``charge`` and ``discharge`` depend
    on the interval of time stamps.

    """

    # Note: atm this is not implemented as node class. Probably could be done, but might be more
    # complicated to be implemented
    def __init__(self, costs, max_charging_speed, storage_loss, charging_loss):
        """
        Parameters
        ----------
        costs : pint.Quantity
            Storage costs per unit of size, e.g. ``1000 * ureg.EUR/ureg.kWh``.
        max_charging_speed : float
            Maximum charging speed, i.e. the share of the total size that can be charged per hour
            (indepenent of the length of the interval between time stamps). For example, if the
            maximum charging speed is 0.5, two hours are needed to charge the storage completely.
            The same limit is applied for discharging speed.
        storage_loss : float
            Loss of stored commodity per hour (indepenent of the length of the interval between
            time stamps) as share of the stored commodity. For example, if the storage loss for a
            battery is 0.01 and the battery is half full, 0.5% of the battery capacity is lost in
            the next hour.
        charging_loss : float
            Loss of charged commodity as share of the charged commodity. For example, if
            ``charging_loss`` is 0.01 and there is 100kg of excess hydrogen to be stored in a
            certain timestamp, only 99kg will end up in the storage.

        """
        self.costs = costs  # per size
        self.max_charging_speed = max_charging_speed  # unit: share of total size per timestamp
        self.storage_loss = storage_loss
        self.charging_loss = charging_loss

        # a loss which equals to 1 does not make sense, because everything would be lost
        # if charging_loss == 0. solutions might be indeterministic because charging and
        # discharging might be done in the same time stamp
        assert 0 <= storage_loss < 1, "storage_loss must be non-negative and smaller than 1"
        assert 0 <= charging_loss < 1, "charging_loss must be non-negative and smaller than 1"
        assert (
            0 < max_charging_speed <= 1
        ), "max_charging_speed must be positive and not be greater than 1"

import linopy

from syfop.util import timeseries_variable


class NodeBase:
    """A Base class for all node types. Do not initialize directly, use sub classes."""

    def __init__(self, name, storage, costs, output_unit, convert_factor=1.0):
        self.name = name
        self.storage = storage
        self.costs = costs
        self.output_unit = output_unit
        self.convert_factor = convert_factor

        # this needs to be filled later
        self.outputs = None
        self.output_flows = None

        # overwritten in some subclasses
        self.input_commodities = None
        self.output_commodities = None
        self.input_proportions = None
        self.output_proportions = None

    def _preprocess_input_commodities(self, inputs, input_commodities):
        if not all(isinstance(node, NodeBase) for node in inputs):
            raise ValueError("inputs must be of type NodeBase or some subclass")

        if isinstance(input_commodities, str):
            input_commodities = len(inputs) * [input_commodities]
        elif len(inputs) != len(input_commodities):
            raise ValueError(
                f"invalid number of input_commodities provided for node '{self.name}': "
                f"{input_commodities}, does not match number of inputs: "
                f"{', '.join(input_.name for input_ in inputs)}"
            )

        return input_commodities

    def _check_proportions_valid_or_missing(
        self, nodes, proportions, commodities, input_or_output
    ):
        """Raise an error if invalid proportions are provided or if no proportions are provided,
        but required due to different commodities."""
        if proportions is not None:
            # TODO maybe skip one input/output, because equality maybe be hard due
            # to numerical errors, see comment below
            assert proportions.keys() == {node.name for node in nodes}, (
                f"wrong parameter for node {self.name}: {input_or_output}_proportions needs to be"
                f" a dict with keys matching names of {input_or_output}s"
            )
            # TODO is this check too strict due to numerical errors?
            assert sum(proportions.values()) == 1.0, (
                f"wrong parameter for node {self.name}: {input_or_output}_proportions needs to "
                "sum up to 1."
            )
        elif len(set(commodities)) > 1:
            raise ValueError(
                f"node {self.name} has different {input_or_output}_commodities, "
                f"but no {input_or_output}_proportions provided"
            )

    def _create_input_flows_variables(self, model, time_coords):
        """Each input flow is a variable (representing the amount of energy in the edge coming from
        input to self). Later we will store the same variables also as output_flows in the nodes in
        self.inputs."""
        self.input_flows = {
            input_.name: timeseries_variable(model, time_coords, f"flow_{input_.name}_{self.name}")
            for input_ in self.inputs
        }

    def _create_storage_variables(self, model, time_coords):
        """This method is not supposed to be called if the node does not have a storage."""
        self.storage.size = model.add_variables(name=f"size_storage_{self.name}", lower=0)
        self.storage.level = timeseries_variable(model, time_coords, f"storage_level_{self.name}")
        self.storage.charge = timeseries_variable(
            model, time_coords, f"storage_charge_{self.name}"
        )
        self.storage.discharge = timeseries_variable(
            model, time_coords, f"storage_discharge_{self.name}"
        )

    def _create_proportion_constraints(self, model, proportions, flows):
        for name, proportion in proportions.items():
            # this is more complicated than it has to be because we need to avoid using the
            # same variable multiple times in a constraint
            # https://github.com/PyPSA/linopy/issues/54
            total_input = sum(flow for n, flow in flows.items() if n != name)
            model.add_constraints(
                proportion * total_input + (proportion - 1) * flows[name] == 0.0,
                name=f"proportion_{self.name}_{name}",
            )

    def _create_storage_constraints(self, model):
        """This method is not supposed to be called if the node does not have a storage."""
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

        # Using roll(time=1) we use the last level as base level for the first time stamp. This is
        # probably the most reasonable thing to do, because leaving start/end level completely free
        # can lead to undesired results, such as starting with a huge filled storage but ending
        # with an empty one.
        # We can assume that at some point the storage should be empty, otherwise it could be built
        # smaller. But the time stamp when storage is empty is not known at this point, therefore
        # connecting start and end level is a better solution.
        model.add_constraints(
            (
                level
                - (1 - self.storage.storage_loss) * level.roll(time=1)
                - (1 - self.storage.charging_loss) * charge
                + discharge
            )
            == 0,
            name=f"storage_level_balance_{self.name}",
        )

    def _create_constraint_inout_flow_balance(self, model):
        """Add constraint: sum of inputs == sum of outputs for this node for each time step."""

        # No input/output flows should never happen because we create extra variables for such
        # nodes in Network(). Hence, this is just a paranoia check to avoid an empty sum to
        # evaluate to 0 which would cause an infeasible network. (We define "no input nodes" as
        # arbitrary input, i.e. to match the sum of outputs and not zero input. Same for no
        # output nodes.)
        assert len(list(self.input_flows.values())) > 0, "node {self.name} has no input flows"
        assert len(list(self.output_flows.values())) > 0, "node {self.name} has no output flows"

        lhs = sum(self.output_flows.values())
        rhs = self.convert_factor * sum(self.input_flows.values())

        # linopy wants all variables on one side and the constants on the other side: this is a
        # workaround if rhs is not a constant.
        # will be obsolete as soon as this is implemented:
        #   https://github.com/PyPSA/linopy/issues/60
        # Note that rhs is only a constant if self is an instance of NodeInputProfileBase with
        # only one input, which is an xr.DataArray.
        #
        # Update 2024-03-11: with linopy 0.3.8 this should be obsolete, but it works only by adding
        # the constraint as rhs == lhs, but lhs == rhs fails:
        #    FAILED tests/test_network.py::test_no_input_node[True] - ValueError: dimensions
        #    ('time',) must have the same length as the number of data dimensions, ndim=0
        #
        # Is issue #60 properly implemented? Is it possible to do the overloading of the equality
        # operator properly in linopy if lhs is an xarray object in lhs == rhs?
        #
        if not isinstance(lhs, linopy.Variable) and not isinstance(lhs, linopy.LinearExpression):
            if self.storage is not None:
                # lhs means that sum of output flow nodes is not a variable, which means that we
                # have a self is of type NodeFixOutputProfile. then storage doesn't really make
                # sense, so we can simply forbid this case.
                # If we want to support it, we need to take care of a wrong sign when adding charge
                # and discharge below to lhs.
                raise RuntimeError("NodeFixOutputProfile with Storage not supported")
            lhs, rhs = rhs, lhs
        if isinstance(rhs, linopy.Variable) or isinstance(rhs, linopy.LinearExpression):
            lhs = lhs - rhs
            rhs = 0

        if self.storage is not None:
            lhs = lhs + self.storage.charge - self.storage.discharge

        model.add_constraints(lhs == rhs, name=f"inout_flow_balance_{self.name}")

    def create_variables(self, model, time_coords):
        self._create_input_flows_variables(model, time_coords)

        if self.storage is not None:
            self._create_storage_variables(model, time_coords)

    def create_constraints(self, model):
        self._create_constraint_inout_flow_balance(model)

        if self.storage is not None:
            self._create_storage_constraints(model)

        # constraint: proportion of inputs
        if self.input_proportions is not None:
            self._create_proportion_constraints(model, self.input_proportions, self.input_flows)

        # constraint: proportion of outputs
        if self.output_proportions is not None:
            self._create_proportion_constraints(model, self.output_proportions, self.output_flows)


class NodeScalableBase(NodeBase):
    """A Base class for all node types, which have a size variable. Do not initialize directly, use
    sub classes."""

    def create_variables(self, model, time_coords):
        super().create_variables(model, time_coords)

        # TODO atm some nodes should not have variables, but setting costs to 0 does the
        # job too
        # FIXME is this correct to not have size when costs are 0?
        if self.costs:  # None or 0 means that we don't need a size variable
            self.size = model.add_variables(name=f"size_{self.name}", lower=0)


class NodeInputProfileBase(NodeBase):
    """A Base class for all node types with a given input time series (profile or fixed
    input_flow).

    Do not initialize directly, use sub classes."""

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
            Time series of the input flow.
        costs : float
            Node costs per size.
        output_unit : str
            Unit of the output commodity.
        output_proportions : dict
            Proportions of the output flows. The keys are the names of the output flows and the
            values are the proportions. The proportions must sum up to 1. If not given, all output
            commodities must be equal.
        storage : Storage
            Storage attached to the node.

        """
        super().__init__(name, storage, costs, output_unit)

        self.inputs = []

        # validated in class Network, when every node knows it's outputs
        self.output_proportions = output_proportions

        self.input_flows = {"": input_flow}

    def _create_input_flows_variables(self, model, time_coords):
        # nothing to do here, input is given via profile
        ...


class NodeOutputProfileBase(NodeBase):
    """A Base class for all node types with a given output time series (profile or fixed
    output_flow).

    Do not initialize directly, use sub classes."""

    def __init__(
        self,
        name,
        inputs,
        input_commodities,
        output_flow,
        costs,
        output_unit,
        input_proportions=None,
        storage=None,
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
        output_flow : xr.DataArray
            Time series of the output flow.
        costs : float
            Costs per size.
        output_unit : str
            Unit of the output commodity.
        input_proportions : dict
            Proportions of the input flows. The keys are the names of the input flows and the
            values are the proportions. The proportions must sum up to 1. If not given, all input
            commodities must be equal.
        storage : Storage
            Storage attached to the node

        """
        super().__init__(name, storage, costs, output_unit)

        # TODO add check that inputs does not contain nodes of type NodeOutputProfileBase?
        self.inputs = inputs

        # str = equal for each input
        self.input_commodities = self._preprocess_input_commodities(inputs, input_commodities)

        self.output_flows = {name: output_flow}

        self._check_proportions_valid_or_missing(
            self.inputs, input_proportions, self.input_commodities, "input"
        )
        self.input_proportions = input_proportions

        if storage is not None:
            # what would be the meaning of a storage in an output node?
            # if we want to support it, check the comment above, see RuntimeError when creating the
            # in _create_constraint_inout_flow_balance()
            raise NotImplementedError("storage is not supported for output nodes")


class NodeFixInputProfile(NodeInputProfileBase):
    # CO2
    # FIXME does it make sense that this class supports costs? they won't be scaled...
    ...


class NodeFixOutputProfile(NodeOutputProfileBase):
    """A node with a fixed output profile, i.e. output flow for each time stamp is given."""

    # Demand
    # FIXME does it make sense that this class supports costs?
    # TODO do we need to support input_proportions here?
    ...


class NodeScalableInputProfile(NodeScalableBase, NodeInputProfileBase):
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


class NodeScalableOutputProfile(NodeScalableBase, NodeOutputProfileBase):
    """Represents a node which has a size variable and a given output profile."""

    # TODO what would be the usecase of such a node?!
    # TODO do we need to check if output_flow <= 1? How does scaling work here?
    # TODO do we need the size limit constraint here?
    def __init__(self):
        raise NotImplementedError("NodeScalableOutputProfile is not implemented yet")


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

        # TODO add check that inputs does not contain nodes of type NodeOutputProfileBase?
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

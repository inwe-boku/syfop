import linopy

from syfop.units import default_units, strip_unit, ureg
from syfop.util import timeseries_variable


class NodeBase:
    """A Base class for all node types. Do not initialize directly, use sub classes."""

    def __init__(
        self,
        name,
        storage,
        costs,
        output_unit,
        convert_factor=1.0,
        convert_factors=None,
    ):
        self.name = name
        self.storage = storage
        self.costs = costs
        self.output_unit = output_unit
        self.convert_factor = convert_factor
        self.convert_factors = convert_factors

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
            input_commodities = max(1, len(inputs)) * [input_commodities]
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

    def _get_flows(self, direction, flows, attached_nodes, commodities, commodity):
        if len(attached_nodes) == 0:
            if commodities != [commodity]:
                raise ValueError(
                    f"node '{self.name}' has no {direction} nodes, therefore "
                    f"{direction}_commidities should be set to '{[commodity]}', "
                    f"but it is: {commodities} "
                )
            return flows.values()
        else:
            return (
                flows[attached_node.name]
                for attached_node, commodity_ in zip(attached_nodes, commodities, strict=True)
                if commodity == commodity_
            )

    def _get_input_flows(self, input_commodity):
        """Return a generator of all input flows for a given commodity. This method does not work
        before Network.__init__ is called, because self.input_commodities is filled there.
        """
        return self._get_flows(
            "input", self.input_flows, self.inputs, self.input_commodities, input_commodity
        )

    def _get_output_flows(self, output_commodity):
        """Return a generator of all output flows for a given commodity. This method does not work
        before Network.__init__ is called, because self.output_commodities is filled there."""
        return self._get_flows(
            "output", self.output_flows, self.outputs, self.output_commodities, output_commodity
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

    def _get_convertion_factors(self):
        # note that convert_factors is supported only by Node, but not by node classes for
        # input/output, therefore we implicitely dissallow multiple different commodities for the
        # classes NodeScalableInput, NodeFixedInput, NodeScalableOutput, NodeFixedOutput
        if self.convert_factors is None:
            if len(set(self.input_commodities)) > 1 or len(set(self.output_commodities)) > 1:
                raise ValueError(
                    "convert_factors is required for multiple input or output commodities"
                )
            input_commodity = self.input_commodities[0]  # FIXME could this be None?
            output_commodity = self.output_commodities[
                0
            ]  # FIXME could this be None at this point?
            convert_factors = {output_commodity: (input_commodity, self.convert_factor)}
        else:
            if self.convert_factor != 1.0 or self.convert_factor is not None:
                raise ValueError(
                    "convert_factors is only allowed if convert_factor is 1.0 or None"
                )
            convert_factors = self.convert_factors

        return convert_factors

    def _create_constraint_inout_flow_balance(self, model):
        """Add a constraint for each output commodity:

            sum of input flows == convert_factor * sum of output flows

        in each time step."""
        # No input/output flows: should never happen because we create extra variables for such
        # nodes in Network(). Hence, this is just a paranoia check to avoid an empty sum to
        # evaluate to 0 which would cause an infeasible network. (We define "no input nodes" as
        # arbitrary input, i.e. to match the sum of outputs and not zero input. Same for no
        # output nodes.)
        assert len(list(self.input_flows.values())) > 0, f"node '{self.name}' has no input flows"
        assert len(list(self.output_flows.values())) > 0, f"node '{self.name}' has no output flows"

        convert_factors = self._get_convertion_factors()

        # every commodity which goes out of this node
        ouptut_commodities = set(self.output_commodities)

        for output_commodity in ouptut_commodities:
            input_commodity, convert_factor = convert_factors[output_commodity]

            # converts from float to pint.Quantity or from pint.Quantity to pint.Quantity
            convert_factor = convert_factor * ureg.dimensionless * 1.0

            # by passing it to ureg.Unit() we allow strings as input for default_units
            convert_factor_mag = convert_factor.to(
                ureg.Unit(default_units[output_commodity])
                / ureg.Unit(default_units[input_commodity])
            ).magnitude

            # TODO we should support commodities not defined in units.default_units and maybe also
            # allow the user to overwrite the default units. Should this be done via a parameter
            # for Node or Network?

            # strip unit from fixed time series and leave linopy variables unchanged: since linopy
            # does not support pint objects, we need to strip the unit, i.e. pass the magnitude
            # only to linopy. It would be a bit nicer if linopy would support pint objects, but
            # adding this is beyond the scope of this project and it is unclear if it would be
            # accepted upstream in linopy.
            input_flows_mag = [
                strip_unit(input_flow, input_commodity)
                for input_flow in self._get_input_flows(input_commodity)
            ]
            output_flows_mag = [
                strip_unit(output_flow, output_commodity)
                for output_flow in self._get_output_flows(output_commodity)
            ]

            self._create_constraint_inout_flow_balance_commodity(
                model,
                input_flows_mag,
                output_flows_mag,
                convert_factor_mag,
            )

    def _create_constraint_inout_flow_balance_commodity(
        self,
        model,
        input_flows_mag,
        output_flows_mag,
        convert_factor_mag,
    ):
        """Add a constraint to the model:

            sum of input flows == convert_factor * sum of output flows

        in each time step for a list of input and output flows and a certain convert_factor. This
        method is intended to be used for all input and output flows of one input and one output
        commodity. Parameters here are expected to have no units, i.e. magnitude needs to be
        passed.

        ``input_flows_mag`` and ``ouptut_flows_mag`` are either xr.DataArray without units or
        linopy.Variable objects.
        """
        lhs = sum(output_flows_mag)
        rhs = convert_factor_mag * sum(input_flows_mag)

        # linopy wants all variables on one side and the constants on the other side: this is a
        # workaround if rhs is not a constant.
        # will be obsolete as soon as this is implemented:
        #   https://github.com/PyPSA/linopy/issues/60
        # Note that rhs is only a constant if self is an instance of NodeInputBase with
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
                # have a self is of type NodeFixOutput. then storage doesn't really make
                # sense, so we can simply forbid this case.
                # If we want to support it, we need to take care of a wrong sign when adding charge
                # and discharge below to lhs.
                raise RuntimeError("NodeFixOutput with Storage not supported")
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

    def storage_cost_magnitude(self, currency_unit):
        assert hasattr(self, "storage") and self.storage is not None, "node has no storage"
        storage_unit = default_units[self._get_size_commodity(self)]
        return self.storage.costs.to(currency_unit / storage_unit).magnitude


class NodeScalableBase(NodeBase):
    """A Base class for all node types, which have a size variable. Do not initialize directly, use
    sub classes."""

    def costs_magnitude(self, currency_unit):
        """Returns the costs scaled to ``currency_unit`` / ``size_unit``, where ``size_unit`` is
        the unit of the output commodity."""
        size_unit = default_units[self._get_size_commodity()]
        costs_mag = self.costs.to(currency_unit / size_unit).magnitude
        return costs_mag

    def create_variables(self, model, time_coords):
        super().create_variables(model, time_coords)

        # TODO atm some nodes should not have variables, but setting costs to 0 does the
        # job too
        # FIXME is this correct to not have size when costs are 0?
        if self.costs:  # None or 0 means that we don't need a size variable
            self.size = model.add_variables(name=f"size_{self.name}", lower=0)


class NodeInputBase(NodeBase):
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
        costs : pint.Quantity
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


class NodeOutputBase(NodeBase):
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
            be given. Only one input commodity is supported, i.e. if ``input_commodities`` is of
            type ``list`` all elements should be equal.
        output_flow : xr.DataArray
            Time series of the output flow.
        costs : pint.Quantity
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

        # TODO add check that inputs does not contain nodes of type NodeOutputBase?
        self.inputs = inputs

        # str = equal for each input
        self.input_commodities = self._preprocess_input_commodities(inputs, input_commodities)

        # something similar is done in Network.__init__ for input nodes and the input_commodities
        assert (
            len(set(self.input_commodities)) == 1
        ), f"unexpected number of input_commodities for node '{self.name}'"
        self.output_commodities = [self.input_commodities[0]]

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

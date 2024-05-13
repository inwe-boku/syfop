import linopy

from syfop.units import interval_length_h, strip_unit, ureg
from syfop.util import timeseries_variable


class NodeBase:
    """A Base class for all node types. Do not initialize directly, use sub classes."""

    def __init__(
        self,
        name,
        storage,
        costs,
        convert_factor=1.0,
        convert_factors=None,
    ):
        self.name = name
        self.storage = storage
        self.costs = costs
        self.convert_factor = convert_factor
        self.convert_factors = convert_factors

        # this needs to be filled later
        self.outputs = None
        self.output_flows = None
        self._size_commodity = None
        self.units = None

        # overwritten in some subclasses
        self.input_commodities = None
        self.output_commodities = None
        self.input_proportions = None
        self.output_proportions = None

    def _preprocess_input_commodities(self, inputs, input_commodities):
        if not all(isinstance(node, NodeBase) for node in inputs):
            raise ValueError("inputs must be of type NodeBase or some subclass")

        if isinstance(input_commodities, str):
            # some nodes don't have inputs, because nothing is connected to it, but we still need
            # an input commodity (and an input flow)
            input_commodities = max(1, len(inputs)) * [input_commodities]
        elif len(inputs) != len(input_commodities) and not (
            len(inputs) == 0 and len(input_commodities) == 1
        ):
            raise ValueError(
                f"invalid number of input_commodities provided for node '{self.name}': "
                f"{input_commodities}, does not match number of inputs: "
                f"{', '.join(input_.name for input_ in inputs)}"
            )

        return input_commodities

    def _check_proportions_valid(self, proportions, commodities, input_or_output):
        """Raise an error if invalid proportions are provided."""
        if proportions is not None:
            assert proportions.keys() == set(commodities), (
                f"wrong parameter for node {self.name}: {input_or_output}_proportions needs to be"
                f" a dict with keys matching names of {input_or_output}_commodities: "
                f"{set(commodities)}"
            )

    @property
    def size_commodity(self):
        """Which commodity is used to define the size of the Node."""
        # self._size_commodity can be not None only for type Node. All other types should have
        # exactly one output commodity set - either directly in __init__ or by Network.__init__().
        if self._size_commodity is None:
            if len(set(self.output_commodities)) == 0:
                raise ValueError(
                    f"node '{self.name}' has no output nodes defined, so "
                    "size_commmodity must be set"
                )
            if len(set(self.output_commodities)) > 1:
                raise ValueError(
                    "size_commodity not provided, but required for multiple "
                    "different output commodities"
                )
            return self.output_commodities[0]
        else:
            return self._size_commodity

    def has_costs(self):
        return not (self.costs == 0.0 or self.costs is None)

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

    def _create_proportion_constraints(self, model, proportions, get_flows):
        proportions = proportions.copy()
        reference_commodity, reference_proportion = proportions.popitem()

        flows_reference_mag = [
            strip_unit(flow, reference_commodity, self.units)
            for flow in get_flows(reference_commodity)
        ]

        for commodity, proportion in proportions.items():
            # XXX minor code duplication, search for strip_unit() in this file
            flows_mag = [strip_unit(flow, commodity, self.units) for flow in get_flows(commodity)]

            model.add_constraints(
                1
                / strip_unit(reference_proportion, reference_commodity, self.units)
                * sum(flows_reference_mag)
                == 1 / strip_unit(proportion, commodity, self.units) * sum(flows_mag),
                name=f"proportion_{self.name}_{commodity}",
            )

    def _create_storage_constraints(self, model, time_coords):
        """This method is not supposed to be called if the node does not have a storage."""
        size = self.storage.size
        level = self.storage.level
        charge = self.storage.charge
        discharge = self.storage.discharge

        max_charging_per_timestamp = (
            size * interval_length_h(time_coords) * self.storage.max_charging_speed
        )
        model.add_constraints(
            charge - max_charging_per_timestamp <= 0,
            name=f"max_charging_speed_{self.name}",
        )
        model.add_constraints(
            discharge - max_charging_per_timestamp <= 0,
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
                    f"node '{self.name}': convert_factors is required for "
                    "multiple input or output commodities"
                )
            input_commodity = self.input_commodities[0]
            output_commodity = self.output_commodities[0]
            convert_factors = {output_commodity: (input_commodity, self.convert_factor)}
        else:
            if self.convert_factor != 1.0 and self.convert_factor is not None:
                raise ValueError(
                    f"node '{self.name}': convert_factors is only allowed "
                    "if convert_factor is 1.0 or None"
                )
            convert_factors = self.convert_factors

        return convert_factors

    def _create_constraint_inout_flow_balance(self, model, time_coords):
        """Add a constraint for each output commodity:

            sum of input flows == convert_factor * sum of output flows

        in each time step. Input flows are here only for the input commodity for which the
        convert_factor is defined in convert_factors"""
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

            # by passing it to ureg.Unit() we allow strings as input for units
            convert_factor_mag = convert_factor.to(
                ureg.Unit(self.units[output_commodity]) / ureg.Unit(self.units[input_commodity])
            ).magnitude

            # strip unit from fixed time series and leave linopy variables unchanged: since linopy
            # does not support pint objects, we need to strip the unit, i.e. pass the magnitude
            # only to linopy. It would be a bit nicer if linopy would support pint objects, but
            # adding this is beyond the scope of this project and it is unclear if it would be
            # accepted upstream in linopy.
            input_flows_mag = [
                strip_unit(input_flow, input_commodity, self.units)
                for input_flow in self._get_input_flows(input_commodity)
            ]
            output_flows_mag = [
                strip_unit(output_flow, output_commodity, self.units)
                for output_flow in self._get_output_flows(output_commodity)
            ]

            self._create_constraint_inout_flow_balance_commodity(
                model,
                input_flows_mag,
                output_flows_mag,
                convert_factor_mag,
                time_coords,
            )

    def _create_constraint_inout_flow_balance_commodity(
        self,
        model,
        input_flows_mag,
        output_flows_mag,
        convert_factor_mag,
        time_coords,
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
            # no need for unit conversion, Example: charge and discharge are MWh and lhs in MW
            lhs = lhs + 1 / interval_length_h(time_coords) * (
                self.storage.charge - self.storage.discharge
            )

        model.add_constraints(lhs == rhs, name=f"inout_flow_balance_{self.name}")

    def create_variables(self, model, time_coords):
        self._create_input_flows_variables(model, time_coords)

        if self.storage is not None:
            self._create_storage_variables(model, time_coords)

    def create_constraints(self, model, time_coords):
        self._create_constraint_inout_flow_balance(model, time_coords)

        if self.storage is not None:
            self._create_storage_constraints(model, time_coords)

        # constraint: proportion of inputs
        if self.input_proportions is not None:
            self._create_proportion_constraints(
                model, self.input_proportions, self._get_input_flows
            )

        # constraint: proportion of outputs
        if self.output_proportions is not None:
            self._create_proportion_constraints(
                model, self.output_proportions, self._get_output_flows
            )

    def storage_cost_magnitude(self, currency_unit):
        assert hasattr(self, "storage") and self.storage is not None, "node has no storage"
        storage_unit = self.units[self.size_commodity]
        return self.storage.costs.to(currency_unit / (storage_unit * ureg.h)).magnitude


class NodeScalableBase(NodeBase):
    """A Base class for all node types, which have a size variable. Do not initialize directly, use
    sub classes."""

    def costs_magnitude(self, currency_unit):
        """Returns the costs scaled to ``currency_unit`` / ``size_unit``, where ``size_unit`` is
        the unit of the output commodity."""
        size_unit = self.units[self.size_commodity]
        costs_mag = self.costs.to(currency_unit / size_unit).magnitude
        return costs_mag

    def create_variables(self, model, time_coords):
        super().create_variables(model, time_coords)

        if self.has_costs():
            self.size = model.add_variables(name=f"size_{self.name}", lower=0)


class NodeInputBase(NodeBase):
    """A Base class for all node types with a given input time series (profile or fixed
    input_flow).

    Do not initialize directly, use sub classes."""

    def __init__(self, name, input_flow, costs, output_proportions=None, storage=None):
        super().__init__(name, storage, costs)

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
        input_proportions=None,
        storage=None,
    ):
        super().__init__(name, storage, costs)

        # TODO add check that inputs does not contain nodes of type NodeOutputBase?
        self.inputs = inputs

        # str = equal for each input
        self.input_commodities = self._preprocess_input_commodities(inputs, input_commodities)

        # something similar is done in Network.__init__ for input nodes and the input_commodities
        assert (
            len(set(self.input_commodities)) == 1
        ), f"unexpected number of input_commodities for node '{self.name}'"
        self.output_commodities = [self.input_commodities[0]]

        self.output_flows = {"": output_flow}

        self._check_proportions_valid(input_proportions, self.input_commodities, "input")
        self.input_proportions = input_proportions

        if storage is not None:
            # what would be the meaning of a storage in an output node?
            # if we want to support it, check the comment above, see RuntimeError when creating the
            # in _create_constraint_inout_flow_balance()
            raise NotImplementedError("storage is not supported for output nodes")

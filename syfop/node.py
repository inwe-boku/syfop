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
                f"wrong parameter for node {self.name}: {input_or_output}_proportions needs to sum "
                "up to 1."
            )
        elif len(set(commodities)) > 1:
            raise ValueError(
                f"node {self.name} has different {input_or_output}_commodities, "
                f"but no {input_or_output}_proportions provided"
            )

    def _create_input_flows_variables(self, model):
        # each input_flow is a variable (representing the amount of energy in the edge coming from
        # input to self)
        self.input_flows = {
            input_.name: timeseries_variable(model, f"flow_{input_.name}_{self.name}")
            for input_ in self.inputs
        }

    def _create_storage_variables(self, model):
        """This method is not supposed to be called if the node does not have a storage."""
        self.storage.size = model.add_variables(name=f"size_storage_{self.name}", lower=0)
        self.storage.level = timeseries_variable(model, f"storage_level_{self.name}")
        self.storage.charge = timeseries_variable(model, f"storage_charge_{self.name}")
        self.storage.discharge = timeseries_variable(model, f"storage_discharge_{self.name}")

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
        model.add_constraints(
            level.isel(time=0)
            - (1 - self.storage.charging_loss) * charge.isel(time=0)
            + discharge.isel(time=0)
            == 0,
            name=f"storage_level_balance_t0_{self.name}",
        )
        model.add_constraints(
            (
                level
                - (1 - self.storage.storage_loss) * level.shift(time=1)
                - (1 - self.storage.charging_loss) * charge
                + discharge
            ).isel(time=slice(1, None))
            == 0,
            name=f"storage_level_balance_{self.name}",
        )
        # XXX should we start with empty storage?
        # model.add_constraints(level.isel(time=0) == 0)

        # storage[0] == 0  # XXX is this correct to start with empty storage?
        # storage[t] - storage[t-1] < charging_speed
        # storage[t-1] - storage[t] < discharging_speed
        # storage[t] < size

        # for all time stamps t:
        # sum(input_flows)[t] == sum(output_flows.items())[t] + eff * (storage[t] -
        #   storage[t-1]) + storage_loss * storage[t]

        # storage_loss: share of lost storage per time stamp
        # eff: charge and discharge efficiency

    def _create_constraint_inout_flow_balance(self, model):
        """Add constraint: sum of inputs == sum of outputs."""
        # sum of output flows (left-hand-side of equation) and inputs must be equal:
        lhs = sum(self.output_flows.values())
        rhs = self.convert_factor * sum(self.input_flows.values())

        # linopy wants all variables on one side and the constants on the other side: this is a
        # workaround if rhs is not a constant.
        # will be obsolete as soon as this is implemented: https://github.com/PyPSA/linopy/issues/60
        # Note that rhs is only a constant if self is an instance of NodeInputProfileBase with
        # only one input, which is an xr.DataArray.
        if not isinstance(lhs, linopy.Variable) and not isinstance(lhs, linopy.LinearExpression):
            lhs, rhs = rhs, lhs
        if isinstance(rhs, linopy.Variable) or isinstance(rhs, linopy.LinearExpression):
            lhs = lhs - rhs
            rhs = 0

        if self.storage is not None:
            lhs = lhs + self.storage.charge - self.storage.discharge

        model.add_constraints(lhs == rhs, name=f"inout_flow_balance_{self.name}")

    def create_variables(self, model):
        self._create_input_flows_variables(model)

        if self.storage is not None:
            self._create_storage_variables(model)

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
    def create_variables(self, model):
        super().create_variables(model)

        # TODO atm some nodes should not have variables, but setting costs to 0 does the
        # job too
        # FIXME is this correct to not have size when costs are 0?
        if self.costs:  # None or 0 means that we don't need a size variable
            self.size = model.add_variables(name=f"size_{self.name}", lower=0)

    def create_constraints(self, model):
        super().create_constraints(model)

        # constraint: size of technology
        # FIXME this is probably wrong for FixedInput?!
        if self.output_flows is not None and self.size:
            model.add_constraints(
                sum(self.output_flows.values()) - self.size <= 0,
                name=f"limit_outflow_by_size_{self.name}",
            )


class NodeInputProfileBase(NodeBase):
    def __init__(
        self,
        name,
        input_flow,
        costs,
        output_unit,
        output_proportions=None,
        storage=None,
    ):
        super().__init__(name, storage, costs, output_unit)

        self.inputs = []

        # validated in class Network, when every node knows it's outputs
        self.output_proportions = output_proportions

        # TODO input_flow should be <1.? (i.e. dimensionless capacity factors)
        # but note: this is wrong for co2 (costs=0), i.e. only for scalable fixed input
        self.input_flows = {"": input_flow}

    def _create_input_flows_variables(self, model):
        # nothing to do here, input is given via profile
        ...


class NodeOutputProfileBase(NodeBase):
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


class NodeFixInputProfile(NodeInputProfileBase):
    # CO2
    # FIXME does it make sense that this class supports costs? they won't be scaled...
    ...


class NodeFixOutputProfile(NodeOutputProfileBase):
    # Demand
    # FIXME does it make sense that this class supports costs?
    # TODO do we need to support input_proportions here?
    ...


class NodeScalableInputProfile(NodeScalableBase, NodeInputProfileBase):
    # Wind, PV, ...
    def create_variables(self, model):
        super().create_variables(model)
        # if input_flows is not None, we have a FixedInput, which we need to scale only
        # if there is a size defined, otherwise it will stay as scalar
        self.input_flows[""] = self.size * self.input_flows[""]


class NodeScalableOutputProfile(NodeScalableBase, NodeOutputProfileBase):
    # TODO what would be the usecase of such a node?!
    # not implemented yet!
    ...


class Node(NodeScalableBase):
    """This node has a size."""

    # examples:
    #  - electricity
    #  - hydrogen (with costs > 0)
    #  - curtailing
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
    ):
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


class Storage:
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

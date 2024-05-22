Optimization model
==================

Each network generates a linear optimization model which is defined by the following equations:

inout_flow constraints
----------------------

For each node $n$ in the network $N$, the sum of all input flows and all output flows are equal in
each time step $t$:

$$
    \sum_{o} \mbox{output_flow}_o(t) = C \cdot \sum_{i} \mbox{input_flow}_i(t)
    \quad \forall t \in T
$$

In the most simple case, there is only one input commodity and one output commodity. In this case,
The left hand side of the equation is the sum of all output flows, and the right hand side is the
sum of all input flows multiplied by the `convert_factor` $C$. That means,
$\mbox{output_flow}_o(t)$ is the amount of the commodity which flows from $n$ to node $o$ for all
output nodes $o$ attached to $n$. The same way, $\mbox{input_flow}_i(t)$ is the amount of the
commodity which flows from node $i$ to $n$ for all input nodes $i$ attached to $n$.

If there are more than one input or output commodity, the equation is extended to

$$
    \sum_{o \in O\left(c^\text{out}\right)} \text{output_flow}_o(t)
        = C_{c^\text{out}} \cdot \sum_{i \in I\left(c^\text{in}\right)}
            \mbox{input_flow}_i(t)
    \quad \forall t \in T,
$$

where `convert_factors` maps each output commodity to a certain input commodity and a conversion
factor:

$$
    c^\text{out} \mapsto \left(c^\text{in}, C_{c^\text{out}} \right)
$$

Here, $I\left(c^\text{in}\right)$ is used to denote the set of all input nodes for commodity
$c^\text{in}$ and $O\left(c^\text{out}\right)$ is used to denote the set of all output nodes for
commodity $c^\text{out}$, respectively. For each output commodity $c^\text{out}$, constraints as
describe above are added to the optimization model. Input commodities which do not appear in `convert_factors` are not considered for this set of constraints.


If there is a storage, we do not allow multiple output commodities. However the charge and
discharge needs to be added to the equation. That means, in this case, the equation is extended to:

$$
    \sum_{o} \mbox{output_flow}_o(t) + \frac{1}{l} \cdot
            \left(\text{charge}(t) - \text{discharge}(t)\right)
        = C \cdot \sum_{i} \mbox{input_flow}_i(t)   \quad \forall t \in T
$$

Here, $l$ is the interval length between two consecutive time stamps.

Size constraints
----------------


The sum of all output flows to a node $n$ is limited by the size of the node:

$$
    \sum_{o \in O\left(\text{size_commodity}\right)}
        \mbox{output_flow}_o(t) \leq \mbox{size} \quad \forall t \in T
$$

Here, the sum is over all output nodes $o$, where the commodity from $n$ to $o$ equals the
`size_commodity`. All other output flows are not considered for the size constraint.


Input proportion constraints
----------------------------

For a node with multiple input commodities $c_1, \ldots, c_n$, a list of input proportions $p_1,
\ldots, p_n$ can be defined to specify fixed proportions of each input commodity for each time
stamp. The optimization model then has the following additional constraints for $k = 2, \ldots, n$:

$$
    \frac{1}{p_1} \sum_{i \in I\left(c_1\right)} \mbox{input_flow}_i(t) =
    \frac{1}{p_k} \sum_{i \in I\left(c_k\right)} \mbox{input_flow}_i(t) \quad \forall t \in T
$$

Note that output proportions are defined implicitly by `convert_factors`.


Storage constraints
-------------------

For each node with a storage, there are the following constraints:

$$
    \text{storage_charge} \leq \text{storage_size} \cdot l \cdot \text{max_charging_speed}  \\
    \text{storage_discharge} \leq \text{storage_size} \cdot l \cdot \text{max_charging_speed}  \\
    \text{level} \leq \text{storage_size} \\
    \text{level}(t) = (1 - \text{storage_loss}) \cdot \text{level}(t-1)
        + (1 - \text{charging_loss}) \cdot \text{charge}(t)
        - \text{discharge}(t)
$$

Here, $l$ is the interval length between two consecutive time stamps.


Variables
---------

The optimization model consists of the following variables:

 - `size` for each node which has positive costs defined
 - `output_flow`: a variable for each time stamp for each output connection of every node (except `NodeFixOutput`)
 - `input_flows` a variable for each time stamp for each input connection of every node (except `NodeFixInput` and `NodeScalableInput`)
 - `storage_size` the size of each storage
 - `storage_level`: a variable for each time stamp and each storage
 - `storage_charge`: a variable for each time stamp and each storage indicating the increase in storage level in this time stamp
 - `storage_discharge`: a variable for each time stamp and each storage indicating the increase in storage level in this time stamp

Note that the unit for each variable is defined by its commodity and the `units` attribute of the
network object. The variables `size`, `output_flow` and `input_flows` are in the unit of the
commodity per time (e.g. MW or t/h). The variables `storage_size`, `storage_level`,
`storage_charge` and `storage_discharge` are in the unit of the storage commodity (e.g. MWh or t).


Objective function
------------------

The objective function is to minimize the total costs of the network:

$$
    \min
    \left(
        \begin{aligned}
            &   \sum_{n \in N} \mbox{costs}_n \cdot \mbox{size}_n  \\
            +&  \sum_{n \in N} \mbox{storage_costs}_n \cdot \mbox{storage_size}_n \\
            +&  \sum_{n \in N} \mbox{input_flow_costs}_n \cdot \left|t\right|
                \cdot \sum_{t \in T} \mbox{input_flow}_n(t) \\
        \end{aligned}
    \right)
$$

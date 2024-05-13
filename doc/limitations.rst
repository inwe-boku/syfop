Limitations
===========


Spatially explicit models
-------------------------

At the moment there is no specif functionality implmented to track or use geographic location of
infrastructure or consumption. The current imlementation focuses on modeling indivudal pixels: each
tile in a grid of reanalysis data is used as input to generate time series for renewables which is
then used for methanol production. In this case, spatial information is not needed as each network
operates only in one location.

However, if one wanted to model the spatial distribution of infrastructure, one could of course
generate a separate node for each location. Adding new dimensions for longitude, latitude or
lcocation to all xarray objects used in *syfop* might be helpful (similar to ``time_coords``).


Time delay
----------

To model shipping of synthetic fules, one would need to introduce a time delay between the
production of the synthetic fuel and the consumption of the fuel. This is not supported in the
current version of *syfop*.


CHP power plants
----------------

The node parameters ``input_proportions`` and ``convert_factors`` are predefined and fixed
values. However, to model a CHP power plant the proportions between heat and electricity output
need to be modeled as optimization variables. This is not supported in the current version of
*syfop*. (One might be able to implment such a model using custom constraints and variables without
modifying the *syfop* code.)


Initial capacity
----------------

There is no functionality to set an initial capacity for a node or a storage, which is already in
operation at the beginning of the simulation.


Fix costs
---------

At the moment there are only costs for installing new infrastructure and inflow costs (i.e. fuel
costs). But there are no fix costs implemented. This might be relevant for existing infrastructure
to create an incentive to reduce existing capacity.


Maximum capacity
----------------

There is no built-in functionality to limit the maximum capacity of a node or a storage. It can be
done using custom constraint, but probably a better way would be to add it as built-in
functionality.


Equidistant time steps
----------------------

At the moment only equidistant time steps are supported. Note that the pandas convention of using
the starting point of time steps to define the intervals, does not allow to infer the length of the
last interval. This would need to be handled, e.g. by asking the user to pass the length of the
last interval.

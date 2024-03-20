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

The node parameters ``input_proportions`` and ``output_proportions`` are predefined and fixed
values. However, to model a CHP power plant the proportions between heat and electricity output
need to be modeled as optimization variables. This is not supported in the current version of
*syfop*. (One might be able to implment such a model using custom constraints and variables without
modifying the *syfop* code.)

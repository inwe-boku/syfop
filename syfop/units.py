import pint
import pint_xarray  # noqa: F401

ureg = pint.UnitRegistry()

# users might want to add their own currencies, e.g. EUR for a certain year
ureg.define("EUR = [currency]")

# per commodity
# FIXME either we need t/h or MWh here!! weird that tests pass?! probably because we test
# input_flow_costs only with electrictiy until now, but as soon as we add the storage for units
# we will have a problem...
default_units = {
    "electricity": ureg.MW,
    "co2": ureg.t / ureg.h,
    "hydrogen": ureg.t / ureg.h,
    "gas": ureg.MW,
    "methanol": ureg.t / ureg.h,
    # TODO heat? coal?
}


def is_pintxarray(x):
    # this seems to work if pint_xarray is imported before, no idea if there is a better way
    # for some unknown reason a quantified xarray object is still of type xarray.DataArray:
    #    xr.DataArray([1, 2, 3]) * ureg.m   # of type xr.DataArray
    return hasattr(x, "pint")


def strip_unit(x, commodity):
    """Strip unit from x and return magnitude scaled to the default unit for magnitude.

    Parameters
    ----------
    x : xarray.DataArray, xarray.Dataset or other
        xarray object with unit or any other object.
    commodity : str
        Commodity name.

    Returns
    -------
    any
        Magnitude of x in default unit for commodity.

    """
    if is_pintxarray(x):
        commodity_unit = default_units[commodity]
        return x.pint.to(commodity_unit).pint.magnitude
    elif isinstance(x, pint.Quantity):
        return x.to(default_units[commodity]).magnitude
    else:
        return x

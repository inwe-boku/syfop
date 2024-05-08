import numpy as np
import pint
import pint_xarray  # noqa: F401

ureg = pint.UnitRegistry()

# users might want to add their own currencies, e.g. EUR for a certain year
ureg.define("EUR = [currency]")

# per commodity
default_units = {
    "electricity": ureg.MW,
    "co2": ureg.t / ureg.h,
    "hydrogen": ureg.t / ureg.h,
    "gas": ureg.MW,
    "methanol": ureg.t / ureg.h,
}


def is_pintxarray(x):
    # this seems to work if pint_xarray is imported before, no idea if there is a better way
    # for some unknown reason a quantified xarray object is still of type xarray.DataArray:
    #    xr.DataArray([1, 2, 3]) * ureg.m   # of type xr.DataArray
    return hasattr(x, "pint")


def strip_unit(x, commodity, units):
    """Strip unit from x and return magnitude scaled to the default unit for magnitude.

    Parameters
    ----------
    x : xarray.DataArray, xarray.Dataset or other
        xarray object with unit or any other object.
    commodity : str
        Commodity name.
    units : dict
        A mapping of commodity names to units.

    Returns
    -------
    any
        Magnitude of x in default unit for commodity.

    """
    if is_pintxarray(x):
        commodity_unit = units[commodity]
        return x.pint.to(commodity_unit).pint.magnitude
    elif isinstance(x, pint.Quantity):
        return x.to(units[commodity]).magnitude
    else:
        return x


def interval_length_h(time_coords):
    # see also https://stackoverflow.com/a/78373992/859591
    interval_lengths = np.diff(time_coords)
    # this works only if equidistant... should have been checked before already.
    assert (interval_lengths == interval_lengths[0]).all(), "timestes are not equidistant"
    interval_length_h = interval_lengths[0] / np.timedelta64(1, "h")

    return interval_length_h

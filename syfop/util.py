import numpy as np
import pandas as pd
import xarray as xr

DEFAULT_NUM_TIME_STEPS = 8760


def const_time_series(value, time_coords=DEFAULT_NUM_TIME_STEPS, time_coords_year=2020):
    """Creates a constant time series as DataArray.

    Parameters
    ----------

    value : float
        constant value used for each time stamp
    time_coords : int or array-like
        Number of hourly time stamps generated or array used as time coordinates. Does not need to
        be of a date time type, but probably makes sense.
    time_coords_year : int
        Year used for generating hourly time stamps. This is ignored if ``time_coords`` is not of
        type int.

    """
    if isinstance(time_coords, int):
        time_coords = pd.date_range(time_coords_year, freq="h", periods=time_coords)

    return xr.DataArray(
        value * np.ones(len(time_coords)),
        dims=("time",),
        coords={"time": time_coords},
    )


def timeseries_variable(model, time_coords, name):
    return model.add_variables(
        name=name,
        lower=const_time_series(0.0, time_coords),
    )


def random_time_series(time_coords=DEFAULT_NUM_TIME_STEPS):
    np.random.seed(42)
    if isinstance(time_coords, int):
        len_time_coords = time_coords
    else:
        len_time_coords = len(time_coords)
    return const_time_series(np.random.rand(len_time_coords), time_coords)


def print_constraints(m):
    """
    Print equations of model `m` in a more or less readable form.
    """
    print(constraints_to_str(m))


def constraints_to_str(m):
    from linopy.io import asarray, concatenate, fill_by, float_to_str, int_to_str

    m.constraints.sanitize_missings()
    kwargs = dict(broadcast_like="vars", filter_missings=True)
    vars = m.constraints.iter_ravel("vars", **kwargs)
    coeffs = m.constraints.iter_ravel("coeffs", **kwargs)
    labels = m.constraints.iter_ravel("labels", **kwargs)

    labels_ = m.constraints.iter_ravel("labels", filter_missings=True)
    sign_ = m.constraints.iter_ravel("sign", filter_missings=True)
    rhs_ = m.constraints.iter_ravel("rhs", filter_missings=True)

    names = m.constraints.labels.data_vars

    iterate = zip(names, labels, vars, coeffs, labels_, sign_, rhs_)

    out_str = ""

    for (n, l, v, c, l_, s_, r_) in iterate:
        if not c.size:
            continue

        diff_con = l[:-1] != l[1:]
        new_con_b = concatenate([asarray([True]), diff_con])
        end_of_con_b = concatenate([diff_con, asarray([True])])

        l_filled = fill_by(v.shape, new_con_b, "\n" + n + int_to_str(l_) + ":\n")
        s = fill_by(v.shape, end_of_con_b, "\n" + s_.astype(object) + "\n")
        r = fill_by(v.shape, end_of_con_b, float_to_str(r_, ensure_sign=False))

        varname = np.frompyfunc(lambda i: m.variables.get_name_by_label(i) + "%i" % i, 1, 1)

        constraints = l_filled + float_to_str(c) + " * " + varname(v) + s + r

        out_str += "\n".join(constraints) + "\n"

    return out_str

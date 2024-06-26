import numpy as np
import pandas as pd
import xarray as xr

DEFAULT_NUM_TIME_STEPS = 8760


def const_time_series(
    value,
    time_coords=None,
    time_coords_freq="h",
    time_coords_num=DEFAULT_NUM_TIME_STEPS,
    time_coords_year=2020,
):
    """Creates a constant time series as :py:class:`xarray.DataArray`. The time coordinates will be
    created from parameters if not given.

    Parameters
    ----------

    value : float
        constant value used for each time stamp
    time_coords : pandas.DatetimeIndex
        time coordinates for the time series. If None, time_coords are generated using
        ``time_coords_freq``, ``time_coords_num`` and ``time_coords_year``.
    time_coords_freq : str
        used only if ``time_coords`` is ``None``, frequency of the time coordinates
    time_coords_num : int
        used only if ``time_coords`` is ``None``, number of time stamps generated
    time_coords_year : int
        used only if ``time_coords`` is ``None``, year used for generating time stamps (first hour
        of this year will be used for the first time stamp)

    Returns
    -------
    xarray.DataArray

    """
    if time_coords is None:
        time_coords = pd.date_range(
            str(time_coords_year),
            freq=time_coords_freq,
            periods=time_coords_num,
        )

    return xr.DataArray(
        value * np.ones(len(time_coords)),
        dims=("time",),
        coords={"time": time_coords},
    )


def timeseries_variable(model, time_coords, name):
    """Create a non-negative variable for a :py:class:`linopy.model.Model` with time coordinates.

    Parameters
    ----------
    model : linopy.Model
        The model to which the variable should be added.
    time_coords : pandas.DatetimeIndex
        see ``const_time_series()``
    name : str
        Name of the variable.

    Returns
    -------
    linopy.variables.Variable
        The created variable.

    """
    return model.add_variables(
        name=name,
        lower=const_time_series(0.0, time_coords),
    )


def random_time_series(
    time_coords_freq="h",
    time_coords_num=DEFAULT_NUM_TIME_STEPS,
    time_coords_year=2020,
):
    """Create a random time series.

    Parameters
    ----------
    time_coords_freq : str
        used only if ``time_coords`` is ``None``, frequency of the time coordinates
    time_coords_num : int
        used only if ``time_coords`` is ``None``, number of time stamps generated
    time_coords_year : int
        used only if ``time_coords`` is ``None``, year used for generating time stamps (first hour
        of this year will be used for the first time stamp)

    Returns
    -------
    xarray.DataArray
        A random time series between 0 and 1 with given time coordinates.
    """
    # let's make it deterministic, way better for debugging test cases!
    np.random.seed(42)

    # this is a bit of a hack, because value is documented as float, but a time series here
    return const_time_series(
        np.random.rand(time_coords_num),
        time_coords_freq=time_coords_freq,
        time_coords_num=time_coords_num,
        time_coords_year=time_coords_year,
    )


def print_constraints(m):
    """Print equations of model `m` in a more or less readable form.

    Use with caution: see comment in `constraints_to_str()`.

    Parameters
    ----------
    m : linopy.Model
        The model to be printed.

    """
    print(constraints_to_str(m))


def constraints_to_str(m):
    """Lists all constraints with their names and with the variable names in a more or less
    readable form.

    This function has been copy and pasted from `linopy.io.constraints_to_file()` (linopy version
    0.3.8) and then modified. The original function writes to a file and simply numbers all
    constraints and variables, but does not use their real names. The original function is intended
    to be used to write a model to an lpfile, but this function is intended to be used for
    debugging and testing.

    Use with caution: this function uses inter data structures of linopy and therefore might break
    with new versions of linopy.

    Parameters
    ----------
    m : linopy.Model
        The model to be printed.

    Returns
    -------
    str
        A string with the constraints.

    """
    if not len(m.constraints):
        return ""

    names = m.constraints
    batch = []
    for name in names:
        df = m.constraints[name].flat

        labels = df.labels.values
        vars = df.vars.values
        coeffs = df.coeffs.values
        rhs = df.rhs.values
        sign = df.sign.values

        len_df = len(df)  # compute length once
        if not len_df:
            continue

        # write out the start to enable a fast loop afterwards
        idx = 0
        label = labels[idx]
        coeff = coeffs[idx]
        var = vars[idx]
        varname = m.variables.get_name_by_label(var)
        batch.append(f"\n{name}{label}:\n{coeff:+.6f} * {varname}{var}\n")
        prev_label = label
        prev_sign = sign[idx]
        prev_rhs = rhs[idx]

        for idx in range(1, len_df):
            label = labels[idx]
            varname = m.variables.get_name_by_label(vars[idx])
            coeff = coeffs[idx]
            var = vars[idx]

            if label != prev_label:
                batch.append(
                    f"{prev_sign}\n{prev_rhs:.6f}\n\n{name}{label}:\n"
                    f"{coeff:+.6f} * {varname}{var}\n"
                )
                prev_sign = sign[idx]
                prev_rhs = rhs[idx]
            else:
                batch.append(f"{coeff:+.6f} * {varname}{var}\n")

            prev_label = label

        batch.append(f"{prev_sign}\n{prev_rhs:.6f}\n")

    return "".join(batch)

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
        time_coords = pd.date_range(str(time_coords_year), freq="h", periods=time_coords)

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
    """Print equations of model `m` in a more or less readable form.

    Use with caution: see comment in `constraints_to_str()`.

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

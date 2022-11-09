import numpy as np
import xarray as xr
import pandas as pd


# TODO this should be an input for Flow and maybe use a datetime range as coords
NUM_TIME_STEPS = 8760
NUM_LOCATIONS = 3
time = pd.date_range(2020, freq="h", periods=NUM_TIME_STEPS)


def timeseries_variable(model, name):
    return model.add_variables(
        name=name,
        lower=xr.DataArray(
            np.zeros((NUM_TIME_STEPS, NUM_LOCATIONS)),
            dims=("time", "locations"),
            coords={
                "time": np.arange(NUM_TIME_STEPS),
                "locations": np.arange(NUM_LOCATIONS),
            },
        ),
    )


def random_time_series():
    np.random.seed(42)
    return xr.DataArray(
        np.random.rand(NUM_TIME_STEPS, NUM_LOCATIONS),
        dims=("time", "locations"),
        coords={
            "time": np.arange(NUM_TIME_STEPS),
            "locations": np.arange(NUM_LOCATIONS),
        },
    )


def const_time_series(value):
    return xr.DataArray(
        value * np.ones((NUM_TIME_STEPS, NUM_LOCATIONS)),
        dims=("time", "locations"),
        coords={
            "time": np.arange(NUM_TIME_STEPS),
            "locations": np.arange(NUM_LOCATIONS),
        },
    )


# %%
def print_constraints(m):
    """
    Print equations of model `m` in a more or less readable form.
    """

    from linopy.io import fill_by, float_to_str, int_to_str, concatenate, asarray

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

    for (n, l, v, c, l_, s_, r_) in iterate:
        if not c.size:
            continue

        diff_con = l[:-1] != l[1:]
        new_con_b = concatenate([asarray([True]), diff_con])
        end_of_con_b = concatenate([diff_con, asarray([True])])

        l = fill_by(v.shape, new_con_b, "\n" + n + int_to_str(l_) + ":\n")
        s = fill_by(v.shape, end_of_con_b, "\n" + s_.astype(object) + "\n")
        r = fill_by(v.shape, end_of_con_b, float_to_str(r_, ensure_sign=False))

        varname = np.frompyfunc(lambda i: m.variables.get_name_by_label(i) + "%i" % i, 1, 1)

        constraints = l + float_to_str(c) + " * " + varname(v) + s + r

        print("\n".join(constraints))
        print()


# %%

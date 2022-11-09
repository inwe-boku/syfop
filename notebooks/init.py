"""Common imports and workarounds for Jupyter notebooks

This module avoids copy & pasting 30-50 lines of imports and Jupyter workarounds. This way it will
be possible to avoid setting PYTHONPATH before running the Jupyter server.

Usage:
    Add the following line to the first cell of your notebook and have fun!

>>> from init import *

It is recommend to place this line in the second cell:

>>> matplotlib.rc('figure', figsize=(15, 10))

"""


# Jupyter setup & workarounds
# ===========================

# This is not nice :(
# But couldn't find a better solution, which allows imports in notebooks and
# separates code from notebooks in different folders.
# See also: https://github.com/jupyter/notebook/issues/1566
import sys as _sys

if ".." not in _sys.path:
    import os as _os

    if not _os.path.isdir("../.git"):
        raise RuntimeError("")
    _sys.path.insert(0, "..")

# autoreload prints a warning if enabled a second time
if "autoreload" not in _sys.path:
    from IPython import get_ipython

    get_ipython().magic("matplotlib inline")
    get_ipython().magic("load_ext autoreload")
    get_ipython().magic("autoreload 2")


# Standard Scientific Imports
# ===========================
import numpy as np  # noqa: F401
import pandas as pd  # noqa: F401
import xarray as xr  # noqa: F401

import matplotlib  # noqa: F401
import matplotlib.pyplot as plt  # noqa: F401

# from dask.diagnostics import ProgressBar  # noqa: F401

import numpy as np
import xarray as xr
import pandas as pd
import linopy
import networkx as nx
import matplotlib.pyplot as plt
from networkx.drawing.nx_pydot import graphviz_layout

# This command is useful too, but does not work in the same cell, where matplotlib is imported:
# matplotlib.rc('figure', figsize=(15, 10))


# Custom & Project Specific Imports
# =================================
from syfop.network import *
from syfop.node import *
from syfop.util import random_time_series
from syfop.util import const_time_series

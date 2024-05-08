# syfop - Synthetic fuel optimizer


[![MIT License](https://img.shields.io/github/license/inwe-boku/syfop.svg)](https://choosealicense.com/licenses/mit/)
[![Tests on GH Actions](https://github.com/inwe-boku/syfop/actions/workflows/tests.yml/badge.svg)](https://github.com/inwe-boku/syfop/actions/workflows/tests.yml)
[![Coverage Status](https://coveralls.io/repos/github/inwe-boku/syfop/badge.svg)](https://coveralls.io/github/inwe-boku/syfop)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![DOI](https://zenodo.org/badge/550867861.svg)](https://zenodo.org/doi/10.5281/zenodo.10869438)
[![Documentation Status](https://readthedocs.org/projects/syfop/badge/?version=latest)](https://syfop.readthedocs.io/)


`syfop` allows the user to model a network, where commodities run through nodes representing
certain types of technologies. In a second step, sizes of the nodes are optimized to be cost
optimal with respect to constraints introduced by the network. The optimization uses discrete time
series for all nodes on as pre-specified time interval.

A simple example for such a network consists of only two nodes. The first node represents a wind
park, where an hourly electricity generation profile is pre-specified (e.g. for one year). The
second node defines the demand for each hour in the same time interval. The nodes are connected
with an edge, which represents the commodity _electricity_. `syfop` then determines the optimal
size of the wind park, such that demand is satisfied in each hour of the year, assuming that costs
and electricity generation are scaled linearly by its size.

In more detail, this is described as follows. We define a network of nodes, which are connected
using directed edges (cycles are not allowed here, which means that the network is a [directed
acyclic graph](https://en.wikipedia.org/wiki/Directed_acyclic_graph)). Each node has several
attributes, such as size and costs per unit of size. Each edge represents the transmission of a
certain commodity between two nodes. The commodity is then either entirely used in the second node,
which means that it does not have any other outgoing edges to other nodes, or it is converted to
other commodities and transmitted to other nodes. This means that the sum of all inputs needs to
equal all outputs in every time step. The conversion is defined linearly using a conversion factor.


Example(s)
----------

see [demo.ipynb](notebooks/demo.ipynb)


How to install
--------------

At the moment there is no package built for syfop, but it can be installed via pip directly from the
repository:

    pip install git+https://github.com/inwe-boku/syfop

The solver HiGHs is installed automatically . Other [solvers](https://linopy.readthedocs.io/en/latest/solvers.html) are supported too, but not installed automatically.

To install development requirements run:

    pip install -e 'syfop[test,dev] @ git+https://github.com/inwe-boku/syfop'
    pre-commit install

<!--
To install Gurobiy:

Download from:
https://www.gurobi.com/downloads/gurobi-software/


    tar tar -zxf gurobi10.0.1_linux64.tar.gz
    cd bla
    python setup.py install

    /opt/gurobi1001/linux64/bin/grbgetkey XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX

    export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/gurobi1000/linux64/lib
    export GRB_LICENSE_FILE="/opt/gurobi810/gurobi.lic"

-->


How to use
----------


```python
node1 = NodeScalableInput(
    name="node1",
    input_profile=random_time_series(),
    costs=10,
)
```

```python
node2 = NodeFixInput(
    name="node2",
    costs=0,
    input_flow=random_time_series(),
)

```

```python
node3 = Node(
    name="node3",
    inputs=[node1, node2],
    input_commodities="electricity",
    costs=42,
)

```

```python
node4 = Node(
    name="node4",
    inputs=[node1, node2],
    input_commodities=["co2", "hydrogen"],
    costs=8,
    input_proportions={"node1": 0.25, "node2": 0.75},
)
```

```python
node5 = Node(
    name="node5",
    inputs=[node2, node3],
    input_commodities="electricity",
    costs=7,
    storage=Storage(
        costs=200,
        max_charging_speed=0.2,
        storage_loss=0.0,
        charging_loss=0.001
    ),
)
```

```python
network = Network(
    [
        node1,
        node2,
        node3,
        node4,
        node5,
    ]
)
```


Acknowledgements
----------------

We gratefully acknowledge support from the European Research Council ("reFUEL" ERC2017-STG 758149).

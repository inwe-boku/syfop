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



How to install
--------------

Via pip:

    pip install git+https://github.com/inwe-boku/syfop

See [documentation](https://syfop.readthedocs.io/latest/how-to-install.html) for more details.


How to use
----------




Acknowledgements
----------------

We gratefully acknowledge support from the European Research Council ("reFUEL" ERC2017-STG 758149).

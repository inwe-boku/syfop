# syfop

<!--
 [![Version](http://img.shields.io/pypi/v/ppw?color=brightgreen)](https://pypi.python.org/pypi/ppw)
[![CI Status](https://github.com/zillionare/python-project-wizard/actions/workflows/release.yml/badge.svg)](https://github.com/zillionare/python-project-wizard)
[![Dowloads](https://img.shields.io/pypi/dm/ppw)](https://pypi.org/project/ppw/)
![Python Versions](https://img.shields.io/pypi/pyversions/ppw)
[![Style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
-->

<!--
<p align="center">
<a href="https://pypi.python.org/pypi/syfop">
    <img src="https://img.shields.io/pypi/v/syfop.svg"
        alt = "Release Status">
</a>
-->

[![MIT License](https://img.shields.io/github/license/inwe-boku/syfop.svg)](https://choosealicense.com/licenses/mit/)


<a href="https://github.com/inwe-boku/syfop/actions">
    <img src="https://github.com/inwe-boku/syfop/actions/workflows/dev.yml/badge.svg" alt="Tests">
</a>

<!--
<a href="https://inwe-boku.github.io/syfop/">
    <img src="https://img.shields.io/website/https/inwe-boku.github.io/syfop/index.html.svg?label=docs&down_message=unavailable&up_message=available" alt="Documentation Status">
</a>

<a href="https://pyup.io/repos/github/lumbric/syfop/">
<img src="https://pyup.io/repos/github/lumbric/syfop/shield.svg" alt="Updates">
</a>

-->
</p>


Synthetic fuel optimizer

<!--
 * Documentation: <https://inwe-boku.github.io/syfop/>
-->


Example(s)
----------

see [demo.ipynb](notebooks/demo.ipynb)


Short introduction
------------------

`syfop` models a network where commodities run through nodes representing certain types of technologies. In a second step, sizes of the nodes are optimized to be cost optimal with respect to constraints introduced by the network. The optimization uses discrete time series for all nodes on as pre-specified time interval. One can think of a node being a wind park, where hourly electricity is given for one year, a second node defines the demand for each hour. `syfop` then determines the optimal size of the wind park, such that demand is satisfied in each hour of the year.

In more detail, this is described as follows. We define a network of nodes, which are connected using directed edges. Each node has

a size and costs, which are scaled linearly by its size.

Nodes

Nodes are connected with direct egdes


each edge represents the transmission off a certain commodity

sum of all inputs of a node equals the sum of all outputs. (respecting the convertion factor)

input / output profiles

input proportions

some nodes have a size, some a cost

total cost is minimize respecting all constraints


How to install
--------------


    pre-commit install
    conda update -f env.yml


install gurobipy


How to use
----------



    node1 = Node(
        name="node1",
    )

    network = Network([node1])

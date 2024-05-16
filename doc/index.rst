syfop - Synthetic fuel optimizer
================================

.. toctree::
    :maxdepth: 2
    :hidden:
    :titlesonly:

    how-to-install
    how-to-use
    limitations
    api_reference/index

..
    usage



`syfop` allows the user to model a network, where commodities run through nodes representing
certain types of technologies. Such a network is used to generate a linear optimization problem,
which is solved to find the optimal sizes of the nodes such that the total cost of the network is
minimized. The optimization uses discrete time series for all nodes on as pre-specified time
interval.

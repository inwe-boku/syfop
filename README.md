# syfop - Synthetic fuel optimizer


[![MIT License](https://img.shields.io/github/license/inwe-boku/syfop.svg)](https://choosealicense.com/licenses/mit/)
[![Tests on GH Actions](https://github.com/inwe-boku/syfop/actions/workflows/tests.yml/badge.svg)](https://github.com/inwe-boku/syfop/actions/workflows/tests.yml)
[![Coverage Status](https://coveralls.io/repos/github/inwe-boku/syfop/badge.svg)](https://coveralls.io/github/inwe-boku/syfop)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![DOI](https://zenodo.org/badge/550867861.svg)](https://zenodo.org/doi/10.5281/zenodo.10869438)
[![Documentation Status](https://readthedocs.org/projects/syfop/badge/?version=latest)](https://syfop.readthedocs.io/)


*syfop* allows the user to model a network, where commodities run through nodes representing
certain types of technologies. Such a network is used to generate a linear optimization problem,
which is solved to find the optimal sizes of the nodes such that the total cost of the network is
minimized. The optimization uses discrete time series for all nodes on as pre-specified time
interval.



How to install
--------------

Via pip:

    pip install git+https://github.com/inwe-boku/syfop

See [documentation](https://syfop.readthedocs.io/latest/how-to-install.html) for more details.


How to use
----------

A simple network which satisfies the demand for electricity using wind and solar PV, and uses
excess electricity to produce hydrogen with an electrolyzer, can be defined as follows:

```python
from syfop.network import Network
from syfop.nodes import Node, NodeFixOutput, NodeScalableInput, Storage

# values here are a bit arbitrary but close to real values

wind = NodeScalableInput(
    name="wind",
    input_profile=random_time_series(),
    costs=128 * ureg.EUR / ureg.kW,
)
solar_pv = NodeScalableInput(
    name="solar_pv",
    input_profile=random_time_series(),
    costs=53 * ureg.EUR / ureg.kW,
)
battery = Storage(
    costs=33 * ureg.EUR / ureg.kWh,
    max_charging_speed=0.2,
    storage_loss=0,
    charging_loss=0,
)
electricity = Node(
    name="electricity",
    inputs=[wind, solar_pv],
    input_commodities="electricity",
    costs=0,
    storage=battery,
)
electrolyzer_convert_factor = 0.019 * ureg.kg / ureg.kWh
electrolyzer = Node(
    name="electrolyzer",
    inputs=[electricity],
    input_commodities="electricity",
    size_commodity="hydrogen",
    costs=1 / electrolyzer_convert_factor * 30 * ureg.EUR / ureg.kW,
    convert_factor=electrolyzer_convert_factor,
)
demand = NodeFixOutput(
    name="demand",
    inputs=[electricity],
    input_commodities="electricity",
    output_flow=random_time_series() * ureg.MW,
)

network = Network([wind, solar_pv, electricity, electrolyzer, demand])

network.optimize()
```

![Simple network](docs/source/_static/simple_network.png)

More details can be found in [the documentation](https://syfop.readthedocs.io/latest/how-to-use.html).

Acknowledgements
----------------

We gratefully acknowledge support from the European Research Council ("reFUEL" ERC2017-STG 758149).

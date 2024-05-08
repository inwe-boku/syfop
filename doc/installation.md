Installation
============

At the moment there is no package built for syfop, but it can be installed via pip directly from the
repository:

    pip install git+https://github.com/inwe-boku/syfop

The opensource solver [HiGHs](https://highs.dev/) is installed automatically . Other
[solvers](https://linopy.readthedocs.io/en/latest/solvers.html) are supported too, but not
installed automatically.

For development we recommend to run:

    pip install -e 'syfop[test,dev] @ git+https://github.com/inwe-boku/syfop'
    pre-commit install


Precise versions of all dependencies, which have been tested, can be found in the
[conda-env.yml](https://github.com/inwe-boku/syfop-global-costs/blob/main/conda-env.yml) file in
the [syfop-global-costs](https://github.com/inwe-boku/syfop-global-costs/) repository.


Solvers
-------

### Installation of Gurobi

Gurobi can be installed via conda or mamba/micromamba from the [gurobi
channel](https://anaconda.org/Gurobi/gurobi):

    conda install gurobi::gurobi

Gurobi is already included in the
[conda-env.yml](https://github.com/inwe-boku/syfop-global-costs/blob/main/conda-env.yml) of the
[syfop-global-costs](https://github.com/inwe-boku/syfop-global-costs/) repository.

You still need to retreive an [(academic) licence](https://www.gurobi.com/features/academic-named-user-license/) and place the licence file in one of the standard folders or set the `GRB_LICENSE_FILE` environment variable:

    # create the licence file using the key from grubi.com:
    /opt/gurobi1001/linux64/bin/grbgetkey XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
    export GRB_LICENSE_FILE="/opt/gurobi810/gurobi.lic"


Alternativly, Gurobi can be installed manually:

Download the binary from [guobi.com](https://www.gurobi.com/downloads/gurobi-software/):

    wget https://packages.gurobi.com/10.0/gurobi10.0.1_linux64.tar.gz
    tar -zxf gurobi10.0.1_linux64.tar.gz
    cd gurobi1001/linux64/
    python setup.py install   # run this in the conda environment

    # create the licence file using the key from grubi.com:
    /opt/gurobi1001/linux64/bin/grbgetkey XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX

    export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/gurobi1001/linux64/lib
    export GRB_LICENSE_FILE="/opt/gurobi810/gurobi.lic"


### Installation of CPLEX

To install cplex follow [these instructions](https://community.ibm.com/community/user/ai-datascience/blogs/xavier-nodet1/2020/07/09/cplex-free-for-students):

> For quick access to CPLEX Optimization Studio through this program, go to
http://ibm.biz/CPLEXonAI. Click on Software, then you'll find, in the ILOG CPLEX Optimization
Studio card, a link to register. Once your registration is accepted, you will see a link to
download of the AI version.

Note that after clicking the download link, you need to select "HTTP" as download method if you
don't want to use the *Download director*. Select the version of the CPLEX Optimization Studio
which suits your OS and then click download.

Make the file executable, run it and follow the instructions of the installer:

```
chmod +x ~/Downloads/cplex_studio2211.linux_x86_64.bin
~/Downloads/cplex_studio2211.linux_x86_64.bin
```

It does not seem to make a difference if a conda environment is activated before running the
installer.

Note that you don't need root permissions if you install it to your home folder, e.g.
`/home/YOUR_USER/cplex_studio2211`.

The installer will print out a command to install the Python package to access CPLEX via a Python
API. Activate the conda environment and then install the cplex package:

```
micromamba activate syfop-global-costs
python /home/YOUR_USER/cplex_studio2211/python/setup.py install
```

CPLEX is not compiled to be used in a conda environment and therefore he library search path needs
to be adjusted for CPLEX to avoid the following error:

```
libstdc++.so.6: version `GLIBCXX_3.4.29' not found
```

A detailed explanation of the problem can be found in [this stackoverflow
answer](https://stackoverflow.com/a/77940023/859591).

To fix the search path, run the following commands:

```
micromamba activate syfop-global-costs

# patchelf can also be used from the system, if already installed or if you have root access
# do something like: sudo apt get install patchelf
micromamba install -c conda-forge patchelf

patchelf --set-rpath '$ORIGIN/../../../..'  $CONDA_PREFIX/lib/python3.10/site-packages/cplex/_internal/libcplex2211.so
```

Note that there is an alternative workaround in
[run.sh](https://github.com/inwe-boku/syfop-global-costs/blob/7d5b9c685c0d61a63ce258d76cad424e83a7cd31/run.sh#L23),
which is not necessary if the patching procedure above was successful.

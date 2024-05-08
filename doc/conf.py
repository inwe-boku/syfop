import os
import sys

from sphinxawesome_theme.postprocess import Icons

sys.path.insert(0, os.path.abspath(".."))

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "syfop"
copyright = "2024, BOKU University"
author = "BOKU University"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",  # support for automatic documentation of docstrings
    "sphinx.ext.napoleon",  # support for numpy and google docstrings
    "sphinx.ext.viewcode",  # show source code in documentation
    "sphinx.ext.intersphinx",  # link to other projects
    "myst_parser",
]

myst_enable_extensions = ["dollarmath", "amsmath"]

source_suffix = {
    ".rst": "restructuredtext",
    ".txt": "markdown",
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# This defines how to handle the class docstring and the one in the __init__ method
autoclass_content = "both"
# autodoc_class_signature = "separated"

# this fixes the anchor links to sections, quite ugly otherwise
html_permalinks_icon = Icons.permalinks_icon

# no idea what this does
# autosummary_generate = True
# autodoc_typehints = "none"

napoleon_google_docstring = False
napoleon_numpy_docstring = True

# no idea what this does
# napoleon_use_param = False
# napoleon_use_rtype = False
# napoleon_preprocess_types = True

intersphinx_mapping = {
    "linopy": ("https://linopy.readthedocs.io/en/latest/", None),
    "pint": ("https://pint.readthedocs.io/en/stable/", None),
    "python": ("https://docs.python.org/3", None),
    # 'numpy': ('http://docs.scipy.org/doc/numpy/', None),
    "pandas": ("http://pandas.pydata.org/pandas-docs/dev", None),
    "xarray": ("https://docs.xarray.dev/en/latest/", None),
}


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# Theme choice:
#  - awesome is the most beautiful, but has some scrolling issues
#  - furo is the cleanest, but I don't like the colors that much
#  - sphinx_book_theme is used by pypsa
#
# html_theme = "sphinx_book_theme"
# html_theme = "furo"


html_theme = "sphinxawesome_theme"
extensions += ["sphinxawesome_theme.highlighting"]

html_title = "syfop"

html_logo = "_static/logo.svg"
html_favicon = "_static/logo.png"

# TODO somehow the headerlinks look ugly, it looks better on the webpage and  on sphinx-themes.org
html_theme_options = {
    "show_breadcrumbs": True,
    "awesome_external_links": True,
    "awesome_headerlinks": True,
    "extra_header_link_icons": {
        "repository on GitHub": {
            "link": "https://github.com/inwe-boku/syfop",
            "icon": (
                '<svg height="26px" style="margin-top:-2px;display:inline" '
                'viewBox="0 0 45 44" '
                'fill="currentColor" xmlns="http://www.w3.org/2000/svg">'
                '<path fill-rule="evenodd" clip-rule="evenodd" '
                'd="M22.477.927C10.485.927.76 10.65.76 22.647c0 9.596 6.223 17.736 '
                "14.853 20.608 1.087.2 1.483-.47 1.483-1.047 "
                "0-.516-.019-1.881-.03-3.693-6.04 "
                "1.312-7.315-2.912-7.315-2.912-.988-2.51-2.412-3.178-2.412-3.178-1.972-1.346.149-1.32.149-1.32 "  # noqa
                "2.18.154 3.327 2.24 3.327 2.24 1.937 3.318 5.084 2.36 6.321 "
                "1.803.197-1.403.759-2.36 "
                "1.379-2.903-4.823-.548-9.894-2.412-9.894-10.734 "
                "0-2.37.847-4.31 2.236-5.828-.224-.55-.969-2.759.214-5.748 0 0 "
                "1.822-.584 5.972 2.226 "
                "1.732-.482 3.59-.722 5.437-.732 1.845.01 3.703.25 5.437.732 "
                "4.147-2.81 5.967-2.226 "
                "5.967-2.226 1.185 2.99.44 5.198.217 5.748 1.392 1.517 2.232 3.457 "
                "2.232 5.828 0 "
                "8.344-5.078 10.18-9.916 10.717.779.67 1.474 1.996 1.474 4.021 0 "
                "2.904-.027 5.247-.027 "
                "5.96 0 .58.392 1.256 1.493 1.044C37.981 40.375 44.2 32.24 44.2 "
                '22.647c0-11.996-9.726-21.72-21.722-21.72" '
                'fill="currentColor"/></svg>'
            ),
        },
    },
}


html_static_path = ["_static"]

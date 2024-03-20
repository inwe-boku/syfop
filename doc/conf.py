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
]

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


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

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
}


html_static_path = ["_static"]

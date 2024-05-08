API reference
=============

..
   Files in here have been generated with the following command:

   PYTHONPATH=.. sphinx-apidoc ../syfop -o api_reference -e

.. toctree::
   :maxdepth: 1
   :glob:

   ./*

..
   This picture will not be updated automatically, but you can do it manually by running the
   following command in the root of the project:

   pyreverse -o png -p syfop syfop
   mv classes_syfop.png doc/_static
   rm packages_syfop.png

.. figure:: /_static/classes_syfop.png
   :scale: 50 %
   :alt: Overview of the classes in the syfop package

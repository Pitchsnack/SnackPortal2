"""Operator tooling. Never imported by a service; never part of the installed distribution.

``[tool.setuptools.packages.find]`` does not enumerate ``tools*``, so nothing here is packaged,
and ``[tool.importlinter].root_packages`` does not list it, so nothing here can become a
back-channel between two services — a tool that imported two services would still be unable to
make them import each other.
"""

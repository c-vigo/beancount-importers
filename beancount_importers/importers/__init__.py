"""Beancount Importers - Module with importers."""

from .n26 import Importer as n26_importer

__all__ = ["n26_importer"]

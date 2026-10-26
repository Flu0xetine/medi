"""A–E临床分级规则引擎。"""

from .engine import classify
from .parser import FIELD_SPECS

__all__ = ["FIELD_SPECS", "classify"]

import re
import logging
from typing import Optional
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


class EhpCompat:
    def __init__(self, html: str):
        self.soup = BeautifulSoup(html, "lxml")

    def find_once(self, tag: str = None, select: tuple = None, order: int = 1):
        return EhpNode(self.soup, tag=tag, select=select, order=order, mode="once")

    def find_all(self, tag: str = None, select: tuple = None, start: int = 1, order: int = None):
        return EhpNode(self.soup, tag=tag, select=select, order=order, mode="all", start=start).resolve_list()


class EhpNode:
    def __init__(self, element, tag=None, select=None, order=1, mode="once", start=1):
        self._element = element
        self._tag = tag
        self._select = select
        self._order = order
        self._mode = mode
        self._start = start
        self._resolved = None

    def _get_resolved(self):
        if self._resolved is not None:
            return self._resolved
        if self._element is None:
            self._resolved = None
            return None
        self._resolved = self._do_resolve()
        return self._resolved

    def _do_resolve(self):
        el = self._element
        if isinstance(el, EhpNode):
            el = el._get_resolved()
        if el is None:
            return None

        kwargs = {}
        if self._tag:
            kwargs["name"] = self._tag

        if self._select:
            attr_name, attr_val = self._select
            if attr_name == "class":
                kwargs["class_"] = attr_val
            else:
                kwargs["attrs"] = {attr_name: attr_val}

        if self._mode == "once":
            results = el.find_all(**kwargs, recursive=True)
            idx = (self._order or 1) - 1
            if idx < len(results):
                return results[idx]
            return None
        else:
            results = el.find_all(**kwargs, recursive=True if not self._tag else False)
            if not results and self._tag:
                results = el.find_all(**kwargs, recursive=True)
            start_idx = (self._start or 1) - 1
            return results[start_idx:]

    def resolve_list(self):
        resolved = self._get_resolved()
        if resolved is None:
            return []
        if isinstance(resolved, list):
            return [EhpItem(r) for r in resolved]
        return [EhpItem(resolved)]

    def find_once(self, tag=None, select=None, order=1):
        resolved = self._get_resolved()
        if resolved is None:
            return EhpNode(None)
        if isinstance(resolved, list):
            resolved = resolved[0] if resolved else None
        return EhpNode(resolved, tag=tag, select=select, order=order, mode="once")

    def find_all(self, tag=None, select=None, start=1, order=None):
        resolved = self._get_resolved()
        if resolved is None:
            return []
        if isinstance(resolved, list):
            resolved = resolved[0] if resolved else None
        return EhpNode(resolved, tag=tag, select=select, order=order, mode="all", start=start).resolve_list()


class EhpItem:
    def __init__(self, element):
        self._element = element

    def __call__(self, tag=None, attribute=None, select=None, order=1, divider=None):
        return self.item(tag=tag, attribute=attribute, select=select, order=order, divider=divider)

    def __str__(self):
        if self._element is None:
            return ""
        return self._element.get_text(strip=True)

    def item(self, tag=None, attribute=None, select=None, order=1, divider=None):
        if self._element is None:
            return ""

        kwargs = {}
        if tag:
            kwargs["name"] = tag

        if select:
            attr_name, attr_val = select
            if attr_name == "class":
                kwargs["class_"] = attr_val
            else:
                kwargs["attrs"] = {attr_name: attr_val}

        results = self._element.find_all(**kwargs, recursive=True)
        idx = (order or 1) - 1
        if idx >= len(results):
            return ""

        el = results[idx]

        if attribute:
            val = el.get(attribute, "")
            if isinstance(val, list):
                val = " ".join(val)
        else:
            val = el.get_text(strip=True)

        if divider and val:
            sep, part_idx = divider
            parts = val.split(sep)
            if part_idx < len(parts):
                val = parts[part_idx]
            else:
                val = ""

        return val.strip() if val else ""

    def find_once(self, tag=None, select=None, order=1):
        if self._element is None:
            return EhpItem(None)
        kwargs = {}
        if tag:
            kwargs["name"] = tag
        if select:
            attr_name, attr_val = select
            if attr_name == "class":
                kwargs["class_"] = attr_val
            else:
                kwargs["attrs"] = {attr_name: attr_val}
        results = self._element.find_all(**kwargs, recursive=True)
        idx = (order or 1) - 1
        if idx < len(results):
            return EhpItem(results[idx])
        return EhpItem(None)

    def find_all(self, tag=None, select=None, start=1):
        if self._element is None:
            return []
        kwargs = {}
        if tag:
            kwargs["name"] = tag
        if select:
            attr_name, attr_val = select
            if attr_name == "class":
                kwargs["class_"] = attr_val
            else:
                kwargs["attrs"] = {attr_name: attr_val}
        results = self._element.find_all(**kwargs, recursive=True)
        start_idx = (start or 1) - 1
        return [EhpItem(r) for r in results[start_idx:]]


def execute_parser_rule(rule: str, dom=None, item=None, key=None) -> Optional[str]:
    if not rule:
        return ""
    try:
        local_ctx = {}
        if dom is not None:
            local_ctx["find_once"] = dom.find_once
            local_ctx["find_all"] = dom.find_all
        if item is not None:
            local_ctx["item"] = item
        if key is not None:
            local_ctx["key"] = key

        result = eval(rule, {"__builtins__": {}}, local_ctx)

        if isinstance(result, EhpNode):
            resolved = result._get_resolved()
            if resolved is None:
                return ""
            if isinstance(resolved, Tag):
                return resolved.get_text(strip=True)
            return str(resolved)
        if isinstance(result, EhpItem):
            return str(result)
        if isinstance(result, list):
            return result
        return str(result) if result else ""
    except Exception as e:
        logger.debug("Parser rule failed: %s -> %s", rule, e)
        return ""

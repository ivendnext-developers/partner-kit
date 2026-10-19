"""The extension-point library's own contracts, read from this repository's ``contracts/`` folder — copies of the
product's files at a pinned commit (see ``contracts/README.md`` and ``EXPORT_SOURCES.md``), so a check runs for anyone with
this repository alone: no product clone, no skipped test. The checker is the product's own
``extension_contract_check.py`` (it checks the draft 2020-12 keywords the contracts use; ``jsonschema`` is not needed).

    from check import errors          # errors("desk_action", "answer", value) -> [] when the value holds

``available()`` stays for the callers that still ask; it is True whenever the contracts folder is there.
"""

from __future__ import annotations

import functools
import importlib.util
import pathlib

CONTRACTS = pathlib.Path(__file__).resolve().parents[2] / "contracts"


def available() -> bool:
    return (CONTRACTS / "extension_contract_check.py").is_file() and (CONTRACTS / "extension_contracts").is_dir()


@functools.lru_cache(maxsize=1)
def _checker():
    spec = importlib.util.spec_from_file_location("extension_contract_check", CONTRACTS / "extension_contract_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def errors(contract: str, definition: str, value) -> list[str]:
    """The product checker's errors for ``value`` against ``<contract>.v1.schema.json#/$defs/<definition>``."""
    mod = _checker()
    schema = mod._schema(contract)
    return mod._errors(schema["$defs"][definition], value, schema)

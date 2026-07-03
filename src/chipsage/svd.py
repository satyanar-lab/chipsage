"""CMSIS-SVD → domain-model adapter.

This is the *only* module that imports ``cmsis_svd``. It translates a parsed SVD device into
chipsage's vendor-agnostic :mod:`chipsage.models` types and computes each field's slice of
the register reset value. It does not validate — that is the loader's job — and it never
originates a value: everything here comes straight from the SVD.

The ``cmsis-svd`` 0.6 parser already resolves ``derivedFrom`` peripherals (a derived
peripheral yields its parent's registers) and expands register arrays, so iterating
``device.peripherals`` / ``peripheral.registers`` / ``register.fields`` gives concrete
entities with concrete offsets.
"""

from __future__ import annotations

from pathlib import Path

from cmsis_svd import SVDParser

from .models import AddressBlock, Chip, Field, Peripheral, Register


def _access_str(access: object) -> str | None:
    """Normalise an ``SVDAccessType`` enum (or ``None``) to its canonical SVD string."""
    if access is None:
        return None
    return getattr(access, "value", str(access))


def _field_reset(register_reset: int | None, bit_offset: int, bit_width: int) -> int | None:
    """Extract a field's slice of the register reset value (``None`` if none is defined)."""
    if register_reset is None:
        return None
    return (register_reset >> bit_offset) & ((1 << bit_width) - 1)


def _build_field(svd_field: object, register_reset: int | None) -> Field:
    bit_offset = svd_field.bit_offset
    bit_width = svd_field.bit_width
    return Field(
        name=svd_field.name,
        bit_offset=bit_offset,
        bit_width=bit_width,
        description=_clean(svd_field.description),
        access=_access_str(svd_field.access),
        reset_value=_field_reset(register_reset, bit_offset, bit_width),
    )


def _build_register(svd_register: object, default_width: int) -> Register:
    size = svd_register.size or default_width
    reset_value = svd_register.reset_value
    return Register(
        name=svd_register.name,
        address_offset=svd_register.address_offset,
        size=size,
        description=_clean(svd_register.description),
        reset_value=reset_value,
        reset_mask=svd_register.reset_mask,
        access=_access_str(svd_register.access),
        fields=tuple(_build_field(f, reset_value) for f in svd_register.fields),
    )


def _build_peripheral(svd_peripheral: object, default_width: int) -> Peripheral:
    blocks = tuple(
        AddressBlock(offset=ab.offset, size=ab.size)
        for ab in (svd_peripheral.address_blocks or ())
    )
    return Peripheral(
        name=svd_peripheral.name,
        base_address=svd_peripheral.base_address,
        description=_clean(svd_peripheral.description),
        derived_from=svd_peripheral.derived_from,
        address_blocks=blocks,
        registers=tuple(_build_register(r, default_width) for r in svd_peripheral.registers),
    )


def _clean(text: str | None) -> str | None:
    """Collapse the whitespace SVD descriptions wrap across lines; keep ``None`` as ``None``."""
    if text is None:
        return None
    collapsed = " ".join(text.split())
    return collapsed or None


def parse_svd(path: str | Path) -> Chip:
    """Parse an SVD file into a :class:`~chipsage.models.Chip` domain object."""
    device = SVDParser.for_xml_file(str(path)).get_device()
    default_width = device.size or 32
    return Chip(
        vendor=(device.vendor or "unknown").strip(),
        name=device.name,
        svd_version=device.version,
        svd_source=Path(path).name,
        width=default_width,
        peripherals=tuple(_build_peripheral(p, default_width) for p in device.peripherals),
    )

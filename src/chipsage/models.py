"""Vendor-agnostic domain model for chipsage's Tier-1 register data.

These dataclasses are deliberately decoupled from the ``cmsis_svd`` parser: only
:mod:`chipsage.svd` imports the parser and adapts it into these types. Everything downstream
(validation, loading, and — in later phases — the MCP tools) speaks this model, honouring
the Constitution's rule that "vendors are data, not code".

The types are frozen (immutable) so that a parsed chip cannot be silently mutated between
validation and insertion — the loader may reject, never repair.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class AddressBlock:
    """A contiguous span of a peripheral's address space, relative to its base address."""

    offset: int  # bytes from the peripheral base address
    size: int  # length of the block in bytes


@dataclass(frozen=True)
class EnumeratedValue:
    """A symbolic name for one value of a field, from the SVD's enumeratedValues.

    ``value`` is ``None`` only for a catch-all "default" entry (``is_default``), which names
    every value not otherwise listed.
    """

    name: str
    value: int | None
    description: str | None = None
    is_default: bool = False


@dataclass(frozen=True)
class Field:
    """A named bit-slice within a register."""

    name: str
    bit_offset: int  # least-significant bit position within the register
    bit_width: int  # number of bits
    description: str | None = None
    access: str | None = None  # SVD access string, e.g. "read-write"
    reset_value: int | None = None  # the field's slice of the register reset value
    enumerated_values: tuple[EnumeratedValue, ...] = ()  # symbolic value names, if any

    @property
    def msb(self) -> int:
        """Most-significant bit position occupied by the field."""
        return self.bit_offset + self.bit_width - 1

    @property
    def mask(self) -> int:
        """Bit mask of the field within the register word."""
        return ((1 << self.bit_width) - 1) << self.bit_offset


@dataclass(frozen=True)
class Register:
    """A single hardware register at ``address_offset`` within its peripheral."""

    name: str
    address_offset: int  # bytes from the peripheral base address
    size: int  # register width in bits
    description: str | None = None
    reset_value: int | None = None
    reset_mask: int | None = None
    access: str | None = None
    fields: tuple[Field, ...] = ()

    @property
    def size_bytes(self) -> int:
        """Register width rounded up to whole bytes."""
        return ceil(self.size / 8)


@dataclass(frozen=True)
class Peripheral:
    """A peripheral instance mapped at ``base_address``."""

    name: str
    base_address: int
    description: str | None = None
    derived_from: str | None = None  # source peripheral name if this instance is derived
    address_blocks: tuple[AddressBlock, ...] = ()
    registers: tuple[Register, ...] = ()

    @property
    def size(self) -> int | None:
        """Extent in bytes from the base address to the end of the furthest address block.

        ``None`` when the peripheral declares no address blocks (range cannot be verified).
        """
        if not self.address_blocks:
            return None
        return max(ab.offset + ab.size for ab in self.address_blocks)


@dataclass(frozen=True)
class Chip:
    """A microcontroller device parsed from one SVD file."""

    vendor: str
    name: str
    svd_version: str | None = None
    svd_source: str | None = None  # provenance: the SVD filename it was parsed from
    width: int = 32  # default register width in bits
    peripherals: tuple[Peripheral, ...] = ()


# --- Tier-3 documentation (prose / errata) ------------------------------------------------
#
# These types carry text extracted verbatim from a vendored datasheet PDF, page-anchored for
# citation. Only :mod:`chipsage.pdf` imports PyMuPDF and produces them — the rest of the code
# speaks this model, exactly as it does for the SVD-derived Tier-1 types above.


@dataclass(frozen=True)
class PageText:
    """The verbatim text of one datasheet page, anchored to its page number."""

    pdf_page: int  # 1-based physical page index in the PDF
    label: str  # the datasheet's own printed page label (used in citations)
    text: str  # verbatim extracted page text


@dataclass(frozen=True)
class Erratum:
    """One erratum extracted verbatim from a datasheet's errata appendix.

    ``peripheral`` is the datasheet's own hardware-block heading the erratum is listed under
    (e.g. "Clocks", "USB") — the grouping that lets a peripheral query surface its errata.
    """

    code: str  # e.g. "RP2040-E7"
    peripheral: str | None  # the block heading this erratum is grouped under
    title: str | None  # the erratum's Summary line
    label: str  # printed page label where the erratum is documented
    pdf_page: int  # 1-based physical page index
    text: str  # verbatim body (Summary / Description / Workaround / Affects / …)

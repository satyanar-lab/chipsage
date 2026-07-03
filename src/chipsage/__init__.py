"""chipsage — local, citation-backed microcontroller documentation for AI coding tools.

Phase 1 exposes the Tier-1 pipeline: parse vendor CMSIS-SVD into a vendor-agnostic domain
model, validate it at ingest, and load the valid rows into a single SQLite index. Nothing
enters the index without ground truth; every stored chip carries provenance.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]

"""Deterministic source reconciliation policy for provider NAV observations."""

from decimal import Decimal

NAV_RECONCILIATION_TOLERANCE = Decimal("0.0001")
SOURCE_PRIORITY = ("amfi", "mfapi")


def build_reconciliation(
    source_values: dict[str, Decimal],
    tolerance: Decimal = NAV_RECONCILIATION_TOLERANCE,
) -> dict[str, Decimal | str | None]:
    """Select canonical NAV and classify cross-provider disagreement.

    AMFI is preferred as the official industry publication source. MFAPI is
    retained as an independent convenience mirror. Other sources follow
    in stable lexical order.
    """
    normalized = {
        source.strip().lower(): Decimal(value)
        for source, value in source_values.items()
        if source.strip()
    }
    if not normalized:
        raise ValueError("At least one source NAV is required.")
    if any(not value.is_finite() or value <= 0 for value in normalized.values()):
        raise ValueError("All source NAV values must be finite and greater than zero.")
    if not tolerance.is_finite() or tolerance < 0:
        raise ValueError("tolerance must be a finite, non-negative decimal.")

    canonical_source = next(
        (source for source in SOURCE_PRIORITY if source in normalized),
        sorted(normalized)[0],
    )
    canonical_nav = normalized[canonical_source]
    difference = max(normalized.values()) - min(normalized.values())
    relative_difference = difference / canonical_nav if len(normalized) > 1 else None
    status = (
        "single_source"
        if len(normalized) == 1
        else "matched"
        if difference <= tolerance
        else "conflict"
    )
    return {
        "source_values": {key: str(value) for key, value in sorted(normalized.items())},
        "canonical_nav": canonical_nav,
        "canonical_source": canonical_source,
        "absolute_difference": difference if len(normalized) > 1 else None,
        "relative_difference": relative_difference,
        "status": status,
        "tolerance": tolerance,
    }

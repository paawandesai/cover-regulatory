from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

Label = Literal["verified", "mock", "derived", "interpretive", "uncited"]


@dataclass(frozen=True)
class Sourced:
    """A value plus where it came from. Parcel attributes are 'verified' only when the source is real data."""

    value: Any
    source_id: str | None
    fetched_at: datetime | None
    label: Label = "verified"

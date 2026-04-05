from __future__ import annotations
from typing import Iterator, TypeVar

try:
    from tqdm import tqdm
except Exception:
    tqdm = None

T = TypeVar("T")


def iter_with_progress(items: list[T], desc: str, unit: str = "item") -> Iterator[T]:
    if tqdm is not None:
        yield from tqdm(items, desc=desc, unit=unit)
        return
    total = len(items)
    for idx, item in enumerate(items, start=1):
        print(f"{desc} [{idx}/{total}]")
        yield item

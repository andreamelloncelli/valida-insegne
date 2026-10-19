"""Tabella di taratura barometrica del registratore (SC3 §2.4.3a, §4.4.2e)."""

from __future__ import annotations

import bisect
import csv
import io
import logging
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class CalibrationError(ValueError):
    """La tabella di taratura non e' leggibile."""


@dataclass(frozen=True)
class CalibrationTable:
    """Coppie (quota indicata, quota vera) in metri, ordinate per quota indicata."""

    points: tuple[tuple[float, float], ...]

    @property
    def low_m(self) -> float:
        return self.points[0][0]

    @property
    def high_m(self) -> float:
        return self.points[-1][0]

    def correct(self, indicated_m: float) -> float:
        """Quota vera per interpolazione lineare fra i punti della tabella.

        Fuori dall'intervallo si prolunga il primo o l'ultimo tratto: il
        certificato copre di norma tutto il campo del sensore.
        """
        indicated = [p[0] for p in self.points]
        position = bisect.bisect_left(indicated, indicated_m)
        position = min(max(position, 1), len(self.points) - 1)
        (x0, y0), (x1, y1) = self.points[position - 1], self.points[position]
        return y0 + (y1 - y0) * (indicated_m - x0) / (x1 - x0)


def parse_calibration(text: str) -> CalibrationTable:
    """Legge una tabella CSV a due colonne: quota indicata e quota vera, in metri.

    Accetta virgola o punto e virgola come separatore e una riga d'intestazione
    facoltativa.
    """
    started = time.perf_counter()
    dialect = ";" if text.count(";") > text.count(",") else ","
    points: list[tuple[float, float]] = []
    for number, row in enumerate(csv.reader(io.StringIO(text), delimiter=dialect), start=1):
        cells = [cell.strip() for cell in row if cell.strip()]
        if not cells:
            continue
        if len(cells) < 2:
            raise CalibrationError(f"Riga {number}: servono due colonne, quota indicata e vera.")
        try:
            points.append((float(cells[0]), float(cells[1])))
        except ValueError:
            if number == 1 and not points:
                continue  # intestazione
            raise CalibrationError(f"Riga {number}: valori non numerici.") from None
    points.sort()
    if len(points) < 2:
        raise CalibrationError("La tabella di taratura deve avere almeno due punti.")
    if any(a[0] == b[0] for a, b in zip(points, points[1:])):
        raise CalibrationError("La tabella di taratura ripete la stessa quota indicata.")
    table = CalibrationTable(tuple(points))
    logger.debug(
        "Tabella di taratura letta: separatore=%r | %.1fms | %d punti, %.0f-%.0f m",
        dialect,
        (time.perf_counter() - started) * 1000,
        len(points),
        table.low_m,
        table.high_m,
    )
    return table


def load_calibration(path: str | Path) -> CalibrationTable:
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise CalibrationError(f"Tabella di taratura non leggibile: {exc}") from exc
    return parse_calibration(text)

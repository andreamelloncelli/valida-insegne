"""Parsing dei file IGC (FAI Sporting Code Section 3, Annex A)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from silverc.rules import PARAMS

logger = logging.getLogger(__name__)

_B_RECORD_MIN_LEN = 35


class IGCParseError(ValueError):
    """Il file non e' un IGC utilizzabile."""


@dataclass(frozen=True)
class Fix:
    time: datetime
    lat: float
    lon: float
    valid: bool
    pressure_alt: int | None
    gnss_alt: int | None
    enl: int | None = None


@dataclass(frozen=True)
class Waypoint:
    lat: float
    lon: float
    name: str


@dataclass
class DeclaredTask:
    """Percorso dichiarato prima del volo (record C)."""

    declared_at: datetime | None
    start: Waypoint
    turnpoints: list[Waypoint]
    finish: Waypoint
    takeoff: Waypoint | None = None
    landing: Waypoint | None = None

    @property
    def points(self) -> list[Waypoint]:
        """Punti che concorrono alla distanza: partenza, virate, arrivo."""
        return [self.start, *self.turnpoints, self.finish]


@dataclass
class Flight:
    fixes: list[Fix]
    flight_date: date | None
    headers: dict[str, str] = field(default_factory=dict)
    task: DeclaredTask | None = None
    rejected: list[tuple[int, str]] = field(default_factory=list)
    has_g_record: bool = False
    has_enl: bool = False
    source: str = ""
    a_record: str = ""

    @property
    def glider(self) -> str:
        gid = self.headers.get("GID", "").strip()
        gty = self.headers.get("GTY", "").strip()
        return " / ".join(p for p in (gty, gid) if p) or "n/d"

    @property
    def pilot(self) -> str:
        return self.headers.get("PLT", "").strip() or "n/d"

    @property
    def glider_type(self) -> str:
        return self.headers.get("GTY", "").strip()

    @property
    def registration(self) -> str:
        return self.headers.get("GID", "").strip()

    @property
    def competition_id(self) -> str:
        return self.headers.get("CID", "").strip()

    @property
    def recorder(self) -> str:
        fty = self.headers.get("FTY", "").strip()
        return fty or "n/d"

    @property
    def recorder_hardware(self) -> str:
        """Versione hardware del registratore (HFRHW), utile a riconoscerne il modello."""
        return self.headers.get("RHW", "").strip() or "n/d"

    @property
    def manufacturer_code(self) -> str:
        """Codice costruttore a 3 caratteri del record A (es. LXV, FLA, XCS)."""
        return self.a_record[1:4].upper() if len(self.a_record) >= 4 else ""


def _parse_header_date(line: str) -> date | None:
    # Formato storico: HFDTE DDMMYY ; formato nuovo: HFDTEDATE:DDMMYY,NN
    body = line[5:].strip()
    if body.upper().startswith("DATE:"):
        body = body[5:]
    digits = "".join(c for c in body.split(",")[0] if c.isdigit())
    if len(digits) < 6:
        return None
    dd, mm, yy = int(digits[0:2]), int(digits[2:4]), int(digits[4:6])
    year = 2000 + yy if yy < 80 else 1900 + yy
    try:
        return date(year, mm, dd)
    except ValueError:
        return None


def _parse_i_record(line: str) -> dict[str, tuple[int, int]]:
    """Restituisce {codice: (start, end)} con indici 0-based, end esclusivo."""
    try:
        count = int(line[1:3])
    except ValueError:
        return {}
    ext: dict[str, tuple[int, int]] = {}
    for i in range(count):
        chunk = line[3 + i * 7 : 10 + i * 7]
        if len(chunk) < 7:
            break
        try:
            start, end = int(chunk[0:2]), int(chunk[2:4])
        except ValueError:
            continue
        ext[chunk[4:7].upper()] = (start - 1, end)
    return ext


def _parse_c_records(lines: list[str], flight_date: date | None) -> DeclaredTask | None:
    """Ricostruisce il percorso dichiarato dalla sequenza di record C.

    Il primo record C e' l'intestazione (data/ora di dichiarazione e numero di
    punti di virata); seguono decollo, partenza, le virate, arrivo, atterraggio.
    """
    if not lines:
        return None
    header = lines[0]
    declared_at: datetime | None = None
    try:
        dd, mm, yy = int(header[1:3]), int(header[3:5]), int(header[5:7])
        hh, mi, ss = int(header[7:9]), int(header[9:11]), int(header[11:13])
        declared_at = datetime(
            2000 + yy if yy < 80 else 1900 + yy, mm, dd, hh, mi, ss, tzinfo=timezone.utc
        )
    except ValueError:
        logger.debug("Record C: intestazione senza data/ora di dichiarazione valida")

    try:
        num_turnpoints = int(header[23:25])
    except ValueError:
        logger.debug("Record C: numero di punti di virata illeggibile")
        return None

    waypoints: list[Waypoint] = []
    for line in lines[1:]:
        if len(line) < 18:
            continue
        try:
            waypoints.append(
                Waypoint(
                    lat=_parse_latitude(line[1:9]),
                    lon=_parse_longitude(line[9:18]),
                    name=line[18:].strip() or "senza nome",
                )
            )
        except (ValueError, IndexError):
            logger.debug("Record C: punto malformato ignorato")

    # decollo + partenza + virate + arrivo + atterraggio
    if len(waypoints) < num_turnpoints + 4:
        logger.debug(
            "Record C: attesi %d punti, trovati %d", num_turnpoints + 4, len(waypoints)
        )
        return None

    return DeclaredTask(
        declared_at=declared_at,
        takeoff=waypoints[0],
        start=waypoints[1],
        turnpoints=waypoints[2 : 2 + num_turnpoints],
        finish=waypoints[2 + num_turnpoints],
        landing=waypoints[3 + num_turnpoints],
    )


def _parse_latitude(raw: str) -> float:
    deg = int(raw[0:2])
    minutes = int(raw[2:7]) / 1000.0
    value = deg + minutes / 60.0
    return -value if raw[7].upper() == "S" else value


def _parse_longitude(raw: str) -> float:
    deg = int(raw[0:3])
    minutes = int(raw[3:8]) / 1000.0
    value = deg + minutes / 60.0
    return -value if raw[8].upper() == "W" else value


def _parse_altitude(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def parse_igc(path: str | Path) -> Flight:
    """Legge un file IGC e restituisce i fix ordinati e ripuliti."""
    started = time.perf_counter()
    path = Path(path)
    try:
        raw_lines = path.read_text(encoding="latin-1").splitlines()
    except OSError as exc:
        raise IGCParseError(f"Impossibile leggere {path}: {exc}") from exc

    headers: dict[str, str] = {}
    extensions: dict[str, tuple[int, int]] = {}
    flight_date: date | None = None
    has_g_record = False
    a_record = ""
    c_records: list[str] = []
    fixes: list[Fix] = []
    rejected: list[tuple[int, str]] = []
    day_offset = 0
    previous_seconds = -1

    for lineno, line in enumerate(raw_lines, start=1):
        if not line:
            continue
        rec = line[0].upper()
        if rec == "A" and not a_record:
            a_record = line.strip()
        elif rec == "H":
            if line[1:5].upper() == "FDTE":
                flight_date = _parse_header_date(line)
            code = line[2:5].upper()
            headers[code] = line.split(":", 1)[1] if ":" in line else line[5:]
        elif rec == "I":
            extensions = _parse_i_record(line)
        elif rec == "C":
            c_records.append(line)
        elif rec == "G":
            has_g_record = True
        elif rec == "B":
            fix = _parse_b_record(line, lineno, extensions, flight_date, day_offset, rejected)
            if fix is None:
                continue
            seconds = fix.time.hour * 3600 + fix.time.minute * 60 + fix.time.second
            if seconds < previous_seconds:
                day_offset += 1
                fix = Fix(
                    time=fix.time + timedelta(days=1),
                    lat=fix.lat,
                    lon=fix.lon,
                    valid=fix.valid,
                    pressure_alt=fix.pressure_alt,
                    gnss_alt=fix.gnss_alt,
                    enl=fix.enl,
                )
                logger.debug("Rollover di mezzanotte alla riga %d | offset giorni: %d", lineno, day_offset)
            previous_seconds = seconds
            fixes.append(fix)

    if not fixes:
        raise IGCParseError(f"Nessun B-record valido trovato in {path}")

    kept = _filter_altitude_spikes(fixes, rejected)
    task = _parse_c_records(c_records, flight_date)
    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.debug(
        "Parsed IGC: file=%s, logger=%s | fixes=%d, scartati=%d, data=%s, ENL=%s, G-record=%s | %.1fms",
        path.name,
        a_record[1:4] or "n/d",
        len(kept),
        len(rejected),
        flight_date,
        "ENL" in extensions,
        has_g_record,
        elapsed_ms,
    )
    return Flight(
        fixes=kept,
        flight_date=flight_date,
        headers=headers,
        task=task,
        rejected=rejected,
        has_g_record=has_g_record,
        has_enl="ENL" in extensions,
        source=str(path),
        a_record=a_record,
    )


def _parse_b_record(
    line: str,
    lineno: int,
    extensions: dict[str, tuple[int, int]],
    flight_date: date | None,
    day_offset: int,
    rejected: list[tuple[int, str]],
) -> Fix | None:
    if len(line) < _B_RECORD_MIN_LEN:
        rejected.append((lineno, "B-record troncato"))
        return None
    try:
        hh, mm, ss = int(line[1:3]), int(line[3:5]), int(line[5:7])
        lat = _parse_latitude(line[7:15])
        lon = _parse_longitude(line[15:24])
    except (ValueError, IndexError):
        rejected.append((lineno, "B-record malformato"))
        return None

    if not (0 <= hh < 24 and 0 <= mm < 60 and 0 <= ss < 60):
        rejected.append((lineno, "orario fuori range"))
        return None

    base = flight_date or date(1970, 1, 1)
    stamp = datetime(base.year, base.month, base.day, hh, mm, ss, tzinfo=timezone.utc)
    stamp += timedelta(days=day_offset)

    enl: int | None = None
    if "ENL" in extensions:
        start, end = extensions["ENL"]
        chunk = line[start:end].strip()
        if chunk.isdigit():
            enl = int(chunk)

    return Fix(
        time=stamp,
        lat=lat,
        lon=lon,
        valid=line[24].upper() == "A",
        pressure_alt=_parse_altitude(line[25:30]),
        gnss_alt=_parse_altitude(line[30:35]),
        enl=enl,
    )


def _filter_altitude_spikes(fixes: list[Fix], rejected: list[tuple[int, str]]) -> list[Fix]:
    """Scarta i fix con variazione di quota barometrica fisicamente impossibile."""
    kept: list[Fix] = []
    last_ref: Fix | None = None
    for index, fix in enumerate(fixes):
        if fix.pressure_alt is None or last_ref is None or last_ref.pressure_alt is None:
            kept.append(fix)
            if fix.pressure_alt is not None:
                last_ref = fix
            continue
        dt = (fix.time - last_ref.time).total_seconds()
        if dt <= 0:
            rejected.append((index, "timestamp non crescente"))
            continue
        rate = abs(fix.pressure_alt - last_ref.pressure_alt) / dt
        if rate > PARAMS.max_plausible_vertical_speed_ms:
            rejected.append(
                (index, f"spike di quota: {rate:.0f} m/s a {fix.time:%H:%M:%S}")
            )
            continue
        kept.append(fix)
        last_ref = fix
    return kept

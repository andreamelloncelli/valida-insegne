"""Generatore di tracce IGC sintetiche per i test."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def _lat_field(lat: float) -> str:
    hemi = "N" if lat >= 0 else "S"
    lat = abs(lat)
    deg = int(lat)
    minutes = round((lat - deg) * 60 * 1000)
    return f"{deg:02d}{minutes:05d}{hemi}"


def _lon_field(lon: float) -> str:
    hemi = "E" if lon >= 0 else "W"
    lon = abs(lon)
    deg = int(lon)
    minutes = round((lon - deg) * 60 * 1000)
    return f"{deg:03d}{minutes:05d}{hemi}"


@dataclass
class IGCBuilder:
    """Costruisce un file IGC minimale ma valido, fix per fix."""

    date_ddmmyy: str = "150625"
    with_enl: bool = False
    with_g_record: bool = True
    a_record: str = "ALXV001"
    pilot: str = "Mario Rossi"
    glider_type: str = "ASK 21"
    registration: str = "I-ABCD"
    fr_type: str = "LXNAV,LX9000"
    competition_id: str = ""
    lines: list[str] = field(default_factory=list)
    task: list[str] = field(default_factory=list)

    def declare(
        self,
        points: list[tuple[float, float, str]],
        declared_hhmmss: str = "090000",
    ) -> "IGCBuilder":
        """Dichiara un percorso: decollo, partenza, virate..., arrivo, atterraggio."""
        turnpoints = max(0, len(points) - 4)
        self.task = [
            f"C{self.date_ddmmyy}{declared_hhmmss}{self.date_ddmmyy}0001{turnpoints:02d}TASK"
        ]
        self.task += [f"C{_lat_field(lat)}{_lon_field(lon)}{name}" for lat, lon, name in points]
        return self

    def fix(
        self,
        seconds: int,
        lat: float,
        lon: float,
        pressure_alt: int,
        gnss_alt: int | None = None,
        valid: bool = True,
        enl: int = 0,
    ) -> "IGCBuilder":
        seconds %= 86400
        hh, mm, ss = seconds // 3600, seconds % 3600 // 60, seconds % 60
        gnss = pressure_alt if gnss_alt is None else gnss_alt
        line = (
            f"B{hh:02d}{mm:02d}{ss:02d}{_lat_field(lat)}{_lon_field(lon)}"
            f"{'A' if valid else 'V'}{pressure_alt:05d}{gnss:05d}"
        )
        if self.with_enl:
            line += f"{enl:03d}"
        self.lines.append(line)
        return self

    def render(self) -> str:
        head = [
            self.a_record,
            f"HFDTEDATE:{self.date_ddmmyy},01",
            f"HFPLTPILOTINCHARGE:{self.pilot}",
            f"HFGTYGLIDERTYPE:{self.glider_type}",
            f"HFGIDGLIDERID:{self.registration}",
            f"HFFTYFRTYPE:{self.fr_type}",
        ]
        if self.competition_id:
            head.append(f"HFCIDCOMPETITIONID:{self.competition_id}")
        if self.with_enl:
            head.append("I013638ENL")
        tail = ["GDEADBEEF"] if self.with_g_record else []
        return "\n".join(head + self.task + self.lines + tail) + "\n"

    def write(self, path) -> str:
        path = str(path)
        with open(path, "w", encoding="latin-1") as handle:
            handle.write(self.render())
        return path


def offset_lat(lat: float, metres: float) -> float:
    return lat + metres / 111_320.0


def offset_lon(lon: float, lat: float, metres: float) -> float:
    return lon + metres / (111_320.0 * math.cos(math.radians(lat)))

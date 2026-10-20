"""Catalogo dei voli reali di `data/VoliTest` e caricamento con cache.

Le aspettative vengono da tre fonti, dichiarate in `FlightCase.source`:

- `perizia`: analisi scritte dall'esaminatore (i .txt e .docx nelle cartelle);
- `cartella`: la prova tentata secondo il nome della cartella. E' l'obiettivo,
  non l'esito omologato: dove il validatore oggi da' altro il caso e' un
  `xfail` da verificare, non un'aspettativa invertita;
- `cartella fallita`: la cartella dichiara il volo fallito.

La cartella non e' versionata (contiene i nomi dei piloti): se manca, i test
che la usano vengono saltati.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from silverc.analysis import FlightAnalysis, analyse
from silverc.igc import Flight, parse_igc
from silverc.rules import BADGES
from silverc.validator import Requirement, ValidationReport, Verdict, validate_badge

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "VoliTest"
ALL_IGC: list[str] = (
    sorted(str(p.relative_to(DATA_DIR)) for p in DATA_DIR.glob("*/*.[iI][gG][cC]"))
    if DATA_DIR.is_dir()
    else []
)

# Voli con perizia scritta.
ZARA_50 = "Jonathan Zara 50km C argento/846_JonathanZara.igc"
SQUADRITO_50 = "Domenico Squadrito 50 km/2019-08-03-XCS-AAA-01.igc"
GUGGIARI_50 = "Tommaso Guggiari 50 km/2019-08-03-XCS-AAA-01.igc"
ZARA_300 = "Jonathan Zara 300 km/2019-08-03-XLK-JOD-01.IGC"
GUGGIARI_500 = "Tommaso Guggiari 500 km/2026-03-20-LXV-261-03.igc"

# Stesso volo in piu' file.
LORO_GAIN = ("Danilo Loro prove C Argento/461VPMY1.igc",
             "Danilo Loro prove C Argento/461VPMY1 - guadagno quota.igc")
LORO_5H = ("Danilo Loro prove C Argento/46MVEZ31.igc",
           "Danilo Loro prove C Argento/46MVEZ31 - 5h.igc")
GHIRINGHELLI_500 = ("Ghiringhelli 500km/2024-03-25-NAV-9D2-01.igc",
                    "Ghiringhelli 500km/43P_StefanoGhiringhelli.igc")
LOCURCIO = ("50km Giuseppe Locurcio/951_.igc", "50km Giuseppe Locurcio/951_Giuseppe.igc")
GUGGIARI_750 = ("Guggiari 750/44KLGMN1.IGC", "Guggiari 750/2004-09-04-XCS-SEA-01.igc")
AMIDEO = ("Volo 50km argento Giuseppe Amideo/1999-09-11-XLK-GIA-01.IGC",
          "Volo 50km argento Giuseppe Amideo/94RX9LR1.IGC")

MATTEI_FRAGMENT = "Andrea Mattei 300 km/55IV21N2.igc"
ORLANDI_300 = "Daniele Orlandi oro e diamanti/249V2KH1.igc"
GORNI_5H = "Gorni volo 50km fallito/2014-04-17 - Volo delle 5 ore.IGC"
GORNI_50 = "Gorni volo 50km fallito/2014-05-23 - Ripetizione 50 Km + Lema.IGC"
ZERO_DECLARATIONS = (GORNI_5H, GORNI_50, GUGGIARI_750[0])

SILVER_COMPLETE = (
    "Venturini 50 km/2025-04-06 Andrea Venturini 540674.igc",
    "50 km 5h 1000m Melloncelli/2026-05-17-XNA-1409B957E7726CF203A91CD01389F783-01.igc",
    AMIDEO[1],
    SQUADRITO_50,
)
SILVER_INCOMPLETE = (GORNI_50, "1000 m Certa/2025-06-28-NAV-180186-01.igc")


@lru_cache(maxsize=None)
def load(rel_path: str) -> tuple[Flight, FlightAnalysis]:
    """Parse e analisi di un volo, una sola volta per sessione."""
    flight = parse_igc(DATA_DIR / rel_path)
    return flight, analyse(flight)


@lru_cache(maxsize=None)
def report(rel_path: str, badge: str) -> ValidationReport:
    flight, analysis = load(rel_path)
    return validate_badge(flight, analysis, BADGES[badge])


def requirement(rep: ValidationReport, code: str) -> Requirement:
    return next(r for r in rep.requirements if r.code == code)


def km(measured: str) -> float:
    """'51.99 km' -> 51.99"""
    return float(measured.split()[0])


@dataclass(frozen=True)
class FlightCase:
    path: str
    badge: str
    code: str
    expected: Verdict
    source: str
    xfail: str | None = None

    @property
    def id(self) -> str:
        return f"{self.path.split('/')[0]}|{Path(self.path).name}|{self.badge}-{self.code}"


def _claim(path: str, badge: str, code: str, xfail: str | None = None) -> FlightCase:
    return FlightCase(path, badge, code, Verdict.PASS, "cartella", xfail)


_SILVER_ALL = [
    _claim(path, "argento", code)
    for path in SILVER_COMPLETE[:3]
    for code in ("durata", "distanza", "quota")
]

CLAIMS: list[FlightCase] = _SILVER_ALL + [
    # Argento, una prova per cartella.
    _claim("Silvia Marinoni 50 km/55HVPN61.igc", "argento", "distanza"),
    _claim("Silvia Marinoni 50 km/55hx4941.igc", "argento", "distanza"),
    _claim("Silvia Marinoni 5h 19-6-2024/2024-06-19-XNA-49427F5597785BCE36CD8547DC018987-01.igc",
           "argento", "durata"),
    _claim("Silvia Marinoni +1000m 24-3-2024/2024-03-24-XNA-ABEF3A7D40B5FFF6-01.igc",
           "argento", "quota"),
    _claim("Meloncelli guadagno di quota +1000 26-4-2025/"
           "2025-04-26-cdargento-guadagno-quota-melloncelli.igc", "argento", "quota"),
    _claim("1000 m Certa/2025-06-28-NAV-180186-01.igc", "argento", "quota"),
    _claim(LORO_GAIN[1], "argento", "quota"),
    _claim("Daniele Bossari 50 km + 5h/2025-04-09-NAV-200912-01.igc", "argento", "distanza"),
    _claim("Daniele Bossari 50 km + 5h/2025-04-30-NAV-200912-01.igc", "argento", "durata"),
    _claim("Davide Cescato 50km n° 2/94KVPNB2.igc", "argento", "distanza"),
    _claim("50 Alessandro Malnati/111_AlessandroMalnati.igc", "argento", "distanza"),
    _claim("50 km Andrea Melloncelli/2026-05-02-XNA-1409B957E7726CF203A91CD01389F783-01.igc",
           "argento", "distanza"),
    _claim(GORNI_5H, "argento", "durata"),
    FlightCase(GORNI_50, "argento", "distanza", Verdict.FAIL, "cartella fallita"),
    # Argento, discordanze da verificare.
    _claim(LORO_5H[1], "argento", "durata",
           "da verificare: 4h32m dopo lo sgancio, i B-record coprono solo 4h42m"),
    _claim("De Mercato guadagno di quota 1000m 2025/2025-04-26-NAV-200746-01.igc",
           "argento", "quota", "da verificare: 984 m GNSS contro 1100 m (971 m barometrici)"),
    _claim(LOCURCIO[0], "argento", "distanza", "da verificare: 45.2 km dallo sgancio"),
    _claim(LOCURCIO[1], "argento", "distanza", "da verificare: 45.2 km dallo sgancio"),
    _claim("Ema 50km/2018-06-23-XLK-EMD-01.IGC", "argento", "distanza",
           "da verificare: 45.1 km dallo sgancio"),
    _claim("50 km Christian Certa/2026-05-01-NAV-180186-01.igc", "argento", "distanza",
           "da verificare: 48.6 km dallo sgancio"),
    # Oro, guadagno di 3000 m.
    _claim("Daniele Bossari +3000m/2026-07-05-NAV-200912-01.igc", "oro", "quota"),
    _claim("Matteo +3000/97DG8291.IGC", "oro", "quota"),
    _claim("Daniele Orlandi oro e diamanti/24AV2KH1.igc", "oro", "quota"),
    _claim("Luca Platini insegne 300 500 5000/2021-05-07-XCS-AAA-01.igc", "oro", "quota"),
    _claim(GUGGIARI_750[0], "oro", "quota"),
    _claim(GUGGIARI_750[1], "oro", "quota"),
    _claim("Bassalti +3000m/1.igc", "oro", "quota",
           "da verificare: 3088 m GNSS contro 3100 m, AL LIMITE"),
    _claim("Enrico +3000/2022-03-26-XLK-END-01.igc", "oro", "quota",
           "da verificare: 2890 m GNSS contro 3100 m"),
    # Oro, distanza di 300 km e oltre.
    _claim("300 diamante Enrico/2018-04-17-XLK-END-01.IGC", "oro", "distanza"),
    _claim("300km Enrico/75HLNQ61.IGC", "oro", "distanza"),
    _claim("300km Matteo Neri/94KG8291.IGC", "oro", "distanza"),
    _claim("Adrien Kiss 300 km/55hxaaa1.igc", "oro", "distanza"),
    _claim("Daniele Bossari 300 km/2026-04-16-NAV-200912-01.igc", "oro", "distanza"),
    _claim("Ghiringhelli 300 km/2021-04-02-NAV-8U3-01.igc", "oro", "distanza"),
    _claim("Loris 300/44HLQSC1.IGC", "oro", "distanza"),
    _claim("Mattei 300 km/2026-04-16-XLK-AND-02.IGC", "oro", "distanza"),
    _claim("Platini 300 km/44JVJH71.igc", "oro", "distanza"),
    _claim("Domenico Squadrito 500 km/2026-07-03-NAV-180405-01.igc", "oro", "distanza"),
    _claim(GHIRINGHELLI_500[0], "oro", "distanza"),
    _claim(GHIRINGHELLI_500[1], "oro", "distanza"),
    _claim("Tommaso 500/2025-05-18-FLA-4CS-03.igc", "oro", "distanza"),
    _claim("Luca Platini insegne 300 500 5000/2021-05-18-XCS-AAA-01.igc", "oro", "distanza"),
    _claim(GUGGIARI_750[1], "oro", "distanza"),
    _claim("Andrea Mattei 300 km/55IV21N1.igc", "oro", "distanza",
           "da verificare: virate dichiarate non raggiunte (percorso non completato)"),
    _claim("Cimini 300 km/73av28s1.igc", "oro", "distanza",
           "da verificare: dichiarazione del 30/11/2016, percorso valutato 88 km"),
    _claim("Bassalti +3000m/1.igc", "oro", "distanza",
           "da verificare: percorso dichiarato di 503 km non completato"),
    _claim("Luca Platini insegne 300 500 5000/2021-04-23-XCS-AAA-01.igc", "oro", "distanza",
           "da verificare: percorso dichiarato di 517 km non completato, 2h53m di volo"),
]

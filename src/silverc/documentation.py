"""Controlli documentali sul file IGC: intestazione e tipo di registratore."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum

from silverc.igc import Flight
from silverc.rules import RECORDERS

logger = logging.getLogger(__name__)

_PLACEHOLDERS = {"", "N/D", "NKN", "UNKNOWN", "NONE", "NIL", "PILOT", "GLIDER", "-", "?"}
# Marche civili: prefisso di nazionalita' e sigla separati da un trattino
# (I-ABCD, D-1234, HB-3122) o, per gli Stati Uniti, N seguito da cifre.
_REGISTRATION = re.compile(r"^[A-Z0-9]{1,3}-[A-Z0-9]{2,5}$|^N[1-9][0-9A-Z]{0,4}$")


class RecorderKind(str, Enum):
    FLIGHT_RECORDER = "Flight Recorder approvato IGC"
    POSITION_RECORDER = "Position Recorder"


@dataclass
class RecorderInfo:
    kind: RecorderKind
    manufacturer: str
    model: str
    source: str
    reasons: list[str] = field(default_factory=list)

    @property
    def is_flight_recorder(self) -> bool:
        return self.kind is RecorderKind.FLIGHT_RECORDER


@dataclass
class DocumentCheck:
    """Esito di un controllo sull'intestazione; `ok=None` vuol dire da verificare."""

    label: str
    value: str
    ok: bool | None
    reason: str


def _is_placeholder(value: str) -> bool:
    return value.strip().upper() in _PLACEHOLDERS


def classify_recorder(flight: Flight, override: RecorderKind | None = None) -> RecorderInfo:
    """Distingue un Flight Recorder approvato da un semplice Position Recorder.

    La descrizione nel file puo' essere vaga: si considera FR solo un logger
    con codice costruttore approvato, G-record presente e tipo dichiarato. In
    ogni altro caso si ricade sul PR, che e' l'ipotesi piu' severa.
    """
    started = time.perf_counter()
    code = flight.manufacturer_code
    model = flight.recorder
    if override is not None:
        info = RecorderInfo(
            kind=override,
            manufacturer=code or "n/d",
            model=model,
            source="indicato dall'utente",
            reasons=[f"Tipo di registratore indicato dall'utente: {override.value}."],
        )
    else:
        reasons: list[str] = []
        if not code:
            reasons.append("Record A assente: costruttore del logger non identificabile.")
        elif code.startswith(RECORDERS.unapproved_prefix):
            reasons.append(
                f"Codice costruttore '{code}': la X iniziale identifica un "
                "produttore non approvato IGC."
            )
        elif code not in RECORDERS.approved_manufacturers:
            reasons.append(
                f"Codice costruttore '{code}' non presente fra i produttori di "
                "Flight Recorder approvati IGC."
            )
        if not flight.has_g_record:
            reasons.append("G-record assente: il file non e' firmato dal logger.")
        if model.upper() in RECORDERS.placeholder_types:
            reasons.append("Tipo di logger (HFFTY) non dichiarato.")

        if reasons:
            kind = RecorderKind.POSITION_RECORDER
            reasons.append(
                "Trattato come Position Recorder, l'ipotesi piu' severa. Se il "
                "logger e' nella lista FAI dei Flight Recorder approvati, indicarlo "
                "esplicitamente (opzione --recorder fr o selettore dell'interfaccia)."
            )
        else:
            kind = RecorderKind.FLIGHT_RECORDER
            reasons.append(
                f"Codice costruttore '{code}' approvato IGC, G-record presente, "
                f"modello '{model}': Flight Recorder dichiarato. La firma non e' "
                "verificata e il modello va confrontato con la lista FAI dei "
                "dispositivi approvati."
            )
        info = RecorderInfo(
            kind=kind, manufacturer=code or "n/d", model=model, source="dal file", reasons=reasons
        )

    logger.debug(
        "Classificazione registratore: costruttore=%s, modello=%s, G-record=%s, override=%s "
        "| %.1fms | esito: %s",
        code or "n/d",
        model,
        flight.has_g_record,
        override.name if override else None,
        (time.perf_counter() - started) * 1000,
        info.kind.name,
    )
    return info


def check_pilot(flight: Flight) -> DocumentCheck:
    value = flight.headers.get("PLT", "").strip()
    if _is_placeholder(value):
        return DocumentCheck("Pilota", value or "n/d", False, "Nome del pilota assente (HFPLT).")
    words = [w for w in re.split(r"[\s_.,]+", value) if any(c.isalpha() for c in w)]
    if len(words) < 2:
        return DocumentCheck(
            "Pilota",
            value,
            False,
            "Il campo pilota deve contenere nome e cognome: trovata una sola parola.",
        )
    return DocumentCheck("Pilota", value, True, "Nome e cognome presenti.")


def check_glider_type(flight: Flight) -> DocumentCheck:
    value = flight.glider_type
    if _is_placeholder(value) or not any(c.isalpha() for c in value):
        # Il tipo non fa parte della dichiarazione (§1.1.3): lo verifica l'OO.
        return DocumentCheck(
            "Tipo di aliante",
            value or "n/d",
            None,
            "Tipo di aliante assente o non riconoscibile (HFGTY): non e' richiesto "
            "nella dichiarazione, lo conferma l'OO al decollo (§4.3.1).",
        )
    return DocumentCheck(
        "Tipo di aliante", value, True, "Tipo di aliante dichiarato: va confrontato con l'aliante usato."
    )


def check_registration(flight: Flight) -> DocumentCheck:
    value = flight.registration
    if _is_placeholder(value):
        if not _is_placeholder(flight.competition_id):
            return DocumentCheck(
                "Marche",
                "n/d",
                True,
                "Marche assenti (HFGID), ma basta la sigla di gara come identificativo "
                "dell'aliante (§1.1.3).",
            )
        return DocumentCheck(
            "Marche",
            "n/d",
            False,
            "Identificativo dell'aliante assente: servono le marche (HFGID) o la sigla "
            "di gara (HFCID) (§1.1.3).",
        )
    if not _REGISTRATION.match(value.upper().replace(" ", "")):
        return DocumentCheck(
            "Marche",
            value,
            None,
            "Formato insolito per delle marche civili (atteso es. I-ABCD): verificare.",
        )
    return DocumentCheck("Marche", value, True, "Marche civili nel formato atteso.")


def check_competition_id(flight: Flight) -> DocumentCheck:
    value = flight.competition_id
    if _is_placeholder(value):
        return DocumentCheck(
            "Sigla di gara", "n/d", True, "Non indicata: facoltativa se ci sono le marche."
        )
    return DocumentCheck("Sigla di gara", value, True, "Presente.")


def check_headers(flight: Flight) -> list[DocumentCheck]:
    """Controlli sui dati del pilota e dell'aliante nell'intestazione IGC."""
    return [
        check_pilot(flight),
        check_glider_type(flight),
        check_registration(flight),
        check_competition_id(flight),
    ]

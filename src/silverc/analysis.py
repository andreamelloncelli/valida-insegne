"""Estrazione dei punti notevoli del volo dalla traccia IGC."""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from silverc.calibration import CalibrationTable
from silverc.course import TaskCheck, verify_declared_task
from silverc.documentation import RecorderInfo, RecorderKind, classify_recorder
from silverc.geo import (
    Point,
    altitude,
    fast_distance_ll,
    fast_distance_m,
    geodesic_distance_ll,
    geodesic_distance_m,
    loss_of_height,
)
from silverc.igc import Fix, Flight
from silverc.rules import PARAMS, RULES

logger = logging.getLogger(__name__)

RELEASE_SOURCE_MANUAL = "dichiarato dall'utente"
RELEASE_SOURCE_HEURISTIC = "euristica sulla traccia"
RELEASE_SOURCE_ENGINE = "spegnimento del motore (§1.2.8)"


@dataclass
class HeightGain:
    low: Point | None
    high: Point | None
    gain_m: float


@dataclass
class FinishFix:
    """Fix d'arrivo candidato con le distanze dai due punti di riferimento."""

    point: Point
    distance_m: float
    from_takeoff_m: float
    loss_of_height_m: float


@dataclass
class FlightAnalysis:
    takeoff: Point
    landing: Point
    release: Point
    release_source: str
    release_confidence: str
    tow_climb_m: float
    height_gain: HeightGain
    farthest: Point
    distance_m: float
    distance_from_takeoff_m: float
    geodesic_model: str
    loss_of_height_m: float
    altitude_source: str
    engine_suspected: bool
    max_enl: int | None
    notes: list[str]
    task_check: TaskCheck | None = None
    recorder: RecorderInfo | None = None
    altitude_usable: bool = True
    calibrated: bool = False
    silver_finish: FinishFix | None = None
    straight_finish: FinishFix | None = None
    median_fix_interval_s: float = 0.0
    gaps: list[tuple[Point, float]] = field(default_factory=list)
    intermediate_stops: list[tuple[Point, Point]] = field(default_factory=list)
    motorglider: bool = False
    engine_start: Point | None = None

    @property
    def finish(self) -> Point:
        """Fine delle prove: l'avvio del motore se precede l'atterraggio (§1.3.2c)."""
        return self.engine_start or self.landing

    @property
    def duration_s(self) -> float:
        return (self.finish.time - self.release.time).total_seconds()


def _sampling_stride(fixes: list[Fix], window_s: int) -> int:
    span = (fixes[-1].time - fixes[0].time).total_seconds()
    if span <= 0 or len(fixes) < 2:
        return 1
    interval = span / (len(fixes) - 1)
    per_window = window_s / max(interval, 1e-6)
    return max(1, int(per_window // 12))


def _moving_flags(fixes: list[Fix]) -> list[bool]:
    """Per ogni fix: l'aliante si allontana dalla posizione entro la finestra?"""
    stride = _sampling_stride(fixes, PARAMS.stationary_window_s)
    flags = [False] * len(fixes)
    for i, fix in enumerate(fixes):
        limit = fix.time.timestamp() + PARAMS.stationary_window_s
        j = i + 1
        while j < len(fixes) and fixes[j].time.timestamp() <= limit:
            if fast_distance_m(fix, fixes[j]) >= PARAMS.stationary_radius_m:
                flags[i] = True
                break
            j += stride
        # Con fix piu' radi della finestra nessun fix cade al suo interno: si
        # guarda allora lo spostamento fino al fix successivo.
        if (
            not flags[i]
            and i + 1 < len(fixes)
            and fixes[i + 1].time.timestamp() > limit
            and fast_distance_m(fix, fixes[i + 1]) >= PARAMS.stationary_radius_m
        ):
            flags[i] = True
    return flags


def detect_takeoff(fixes: list[Fix], moving: list[bool] | None = None) -> Point:
    """Primo fix a partire dal quale l'aliante lascia la posizione di sosta."""
    flags = moving if moving is not None else _moving_flags(fixes)
    for i, flag in enumerate(flags):
        if flag:
            return Point(i, fixes[i])
    return Point(0, fixes[0])


def detect_landing(fixes: list[Fix], moving: list[bool] | None = None) -> Point:
    """Primo fix della sosta finale: i successivi sono registrazione a terra."""
    flags = moving if moving is not None else _moving_flags(fixes)
    last = len(fixes) - 1
    for i in range(last, -1, -1):
        if flags[i]:
            return Point(min(i + 1, last), fixes[min(i + 1, last)])
    return Point(last, fixes[last])


def detect_release(fixes: list[Fix], takeoff: Point, use_gnss: bool) -> tuple[Point, str, float]:
    """Euristica di sgancio: fine della salita continua iniziale.

    Cerca il primo massimo di quota dopo il decollo seguito, entro una breve
    finestra, da una discesa significativa. Funziona sul traino aereo e sul
    verricello; non distingue un decollo autonomo a motore.
    """
    peak_alt: int | None = None
    peak_point: Point | None = None
    takeoff_alt = altitude(takeoff.fix, use_gnss)
    for i in range(takeoff.index, len(fixes)):
        alt = altitude(fixes[i], use_gnss)
        if alt is None:
            continue
        if peak_alt is None or alt > peak_alt:
            peak_alt, peak_point = alt, Point(i, fixes[i])
            continue
        if peak_point is None or peak_alt - alt < PARAMS.release_drop_m:
            continue
        climb = peak_alt - (takeoff_alt if takeoff_alt is not None else peak_alt)
        confidence = "alta" if climb >= PARAMS.min_tow_climb_m else "bassa"
        logger.debug(
            "Sgancio euristico: t=%s, quota=%dm, salita al traino=%dm, confidenza=%s",
            peak_point.time.strftime("%H:%M:%S"),
            peak_alt,
            climb,
            confidence,
        )
        return peak_point, confidence, float(climb)
    return takeoff, "nulla", 0.0


def find_farthest_point(fixes: list[Fix], origin: Fix, start_index: int, end_index: int) -> Point:
    """Punto della traccia piu' lontano dall'origine, fra due indici inclusi.

    Il candidato si sceglie con la distanza approssimata (una passata su tutti
    i fix); la distanza definitiva sul candidato si calcola poi in geodetica.
    """
    best_index = start_index
    best_distance = -1.0
    for i in range(start_index, min(end_index + 1, len(fixes))):
        distance = fast_distance_m(origin, fixes[i])
        if distance > best_distance:
            best_distance, best_index = distance, i
    return Point(best_index, fixes[best_index])


def choose_finish_fix(
    fixes: list[Fix],
    release: Point,
    takeoff: Point,
    end_index: int,
    use_gnss: bool,
    from_takeoff: bool,
) -> Point:
    """Fix d'arrivo scelto dopo il volo (§1.2.10c) col miglior esito ufficiale.

    Il fix piu' lontano non e' sempre il migliore: una planata finale bassa
    puo' superare il limite di perdita di quota, mentre un fix precedente piu'
    alto lo rispetta. Si scarta ogni fix che invalida la prova (§2.4.4) e fra
    gli altri si massimizza la distanza ufficiale o, con `from_takeoff`
    (argento, §2.2.1a), la minore fra quella e la distanza dal decollo.
    """
    started = time.perf_counter()
    release_alt = altitude(release.fix, use_gnss)
    best_key: tuple[bool, float] | None = None
    best_index = release.index
    for i in range(release.index, min(end_index + 1, len(fixes))):
        alt = altitude(fixes[i], use_gnss)
        loss = float(release_alt - alt) if release_alt is not None and alt is not None else 0.0
        check = loss_of_height(fast_distance_m(release.fix, fixes[i]), loss, use_gnss)
        metric = check.official_m
        if from_takeoff:
            metric = min(metric, fast_distance_m(takeoff.fix, fixes[i]))
        key = (not check.invalid, metric)
        if best_key is None or key > best_key:
            best_key, best_index = key, i
    logger.debug(
        "Scelta del fix d'arrivo: fix=%d-%d, gnss=%s, dal decollo=%s | %.1fms | "
        "scelto indice %d, valido=%s, metrica=%.0fm",
        release.index,
        end_index,
        use_gnss,
        from_takeoff,
        (time.perf_counter() - started) * 1000,
        best_index,
        best_key[0] if best_key else None,
        best_key[1] if best_key else 0.0,
    )
    return Point(best_index, fixes[best_index])


def finish_fix(
    point: Point, release: Point, takeoff: Point, use_gnss: bool
) -> FinishFix:
    """Distanze geodetiche e perdita di quota di un fix d'arrivo."""
    release_alt = altitude(release.fix, use_gnss)
    alt = altitude(point.fix, use_gnss)
    return FinishFix(
        point=point,
        distance_m=geodesic_distance_m(release.fix, point.fix)[0],
        from_takeoff_m=geodesic_distance_m(takeoff.fix, point.fix)[0],
        loss_of_height_m=(
            float(release_alt - alt) if release_alt is not None and alt is not None else 0.0
        ),
    )


def median_fix_interval_s(fixes: list[Fix], start_index: int, end_index: int) -> float:
    """Intervallo mediano fra fix consecutivi: la cadenza impostata sul registratore."""
    window = fixes[start_index : end_index + 1]
    intervals = [(b.time - a.time).total_seconds() for a, b in zip(window, window[1:])]
    return statistics.median(intervals) if intervals else 0.0


def engine_running(fix: Fix) -> bool:
    """Il fix registra il motore acceso (ENL o MOP oltre soglia)?"""
    return (fix.enl is not None and fix.enl >= PARAMS.enl_running_threshold) or (
        fix.mop is not None and fix.mop >= PARAMS.mop_running_threshold
    )


def find_engine_run(fixes: list[Fix], start_index: int, end_index: int) -> Point | None:
    """Primo fix col motore acceso fra due indici inclusi."""
    for i in range(start_index, min(end_index + 1, len(fixes))):
        if engine_running(fixes[i]):
            return Point(i, fixes[i])
    return None


def find_gaps(
    fixes: list[Fix], start_index: int, end_index: int, max_interval_s: float
) -> list[tuple[Point, float]]:
    """Intervalli fra fix consecutivi oltre `max_interval_s`: (fix che chiude il buco, durata)."""
    gaps: list[tuple[Point, float]] = []
    for i in range(start_index + 1, min(end_index + 1, len(fixes))):
        interval = (fixes[i].time - fixes[i - 1].time).total_seconds()
        if interval > max_interval_s:
            gaps.append((Point(i, fixes[i]), interval))
    return gaps


def _stationary_runs(
    fixes: list[Fix], moving: list[bool], start_index: int, end_index: int
) -> list[tuple[Point, Point]]:
    runs: list[tuple[Point, Point]] = []
    run_start: int | None = None
    for i in range(start_index, min(end_index, len(fixes))):
        if not moving[i]:
            if run_start is None:
                run_start = i
        elif run_start is not None:
            runs.append((Point(run_start, fixes[run_start]), Point(i, fixes[i])))
            run_start = None
    if run_start is not None:
        last = min(end_index, len(fixes) - 1)
        runs.append((Point(run_start, fixes[run_start]), Point(last, fixes[last])))
    return runs


def find_ground_stops(
    fixes: list[Fix], moving: list[bool], start_index: int, end_index: int, use_gnss: bool
) -> list[tuple[Point, Point]]:
    """Soste a terra fra due indici: tratti lunghi in cui l'aliante non si sposta.

    In volo un aliante non resta fermo, ma il GPS di un logger puo' bloccare
    la posizione per qualche decina di secondi: si scartano i tratti brevi e
    quelli in cui la quota cambia.
    """
    stops: list[tuple[Point, Point]] = []
    for start, end in _stationary_runs(fixes, moving, start_index, end_index):
        if (end.time - start.time).total_seconds() < PARAMS.stationary_window_s:
            continue
        heights = [
            a for a in (altitude(f, use_gnss) for f in fixes[start.index : end.index + 1])
            if a is not None
        ]
        if heights and max(heights) - min(heights) > PARAMS.ground_altitude_spread_m:
            continue
        stops.append((start, end))
    return stops


def _relaunched(fixes: list[Fix], stop: Point, use_gnss: bool) -> bool:
    """Dopo la sosta l'aliante risale, cioe' riparte in volo?"""
    base = altitude(stop.fix, use_gnss)
    if base is None:
        return False
    after = [a for a in (altitude(f, use_gnss) for f in fixes[stop.index :]) if a is not None]
    return bool(after) and max(after) - base >= PARAMS.relaunch_climb_m


def refine_landing(
    fixes: list[Fix], moving: list[bool], release: Point, landing: Point, use_gnss: bool
) -> Point:
    """Anticipa l'atterraggio alla prima sosta a terra dopo cui non si vola piu'.

    Dopo l'atterraggio l'aliante viene spesso spostato a terra: la sosta
    finale rilevata e' allora quella al parcheggio e la durata risulterebbe
    piu' lunga del vero.
    """
    for start, _ in find_ground_stops(fixes, moving, release.index, landing.index, use_gnss):
        if not _relaunched(fixes, start, use_gnss):
            return start
    return landing


def find_intermediate_stops(
    fixes: list[Fix], moving: list[bool], start_index: int, end_index: int, use_gnss: bool
) -> list[tuple[Point, Point]]:
    """Atterraggi intermedi: soste a terra dopo cui l'aliante riparte (§2.4.5)."""
    return [
        (start, end)
        for start, end in find_ground_stops(fixes, moving, start_index, end_index, use_gnss)
        if _relaunched(fixes, start, use_gnss)
    ]


def parse_release_time(value: str, flight: Flight) -> datetime:
    """Orario di sgancio HH:MM[:SS] UTC indicato dall'utente, alla data del volo."""
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
        moment = parsed.replace(tzinfo=timezone.utc)
        day = flight.flight_date or (flight.fixes[0].time.date() if flight.fixes else None)
        if day is not None:
            moment = moment.replace(year=day.year, month=day.month, day=day.day)
        return moment
    raise ValueError("orario di sgancio atteso come HH:MM:SS (UTC)")


def find_point_at(fixes: list[Fix], moment: datetime) -> Point:
    """Fix piu' vicino a un istante dato."""
    best = min(range(len(fixes)), key=lambda i: abs((fixes[i].time - moment).total_seconds()))
    return Point(best, fixes[best])


def compute_height_gain(
    fixes: list[Fix], start_index: int, use_gnss: bool, end_index: int | None = None
) -> HeightGain:
    """Massimo guadagno di quota con punto basso precedente al punto alto."""
    low: Point | None = None
    running_low: Point | None = None
    high: Point | None = None
    best = 0.0
    stop = len(fixes) if end_index is None else min(end_index + 1, len(fixes))
    for i in range(start_index, stop):
        alt = altitude(fixes[i], use_gnss)
        if alt is None:
            continue
        current = Point(i, fixes[i])
        running_alt = altitude(running_low.fix, use_gnss) if running_low else None
        if running_alt is None or alt < running_alt:
            running_low = current
            running_alt = alt
        gain = alt - running_alt
        if gain > best:
            best, low, high = float(gain), running_low, current
    return HeightGain(low=low, high=high, gain_m=best)


def analyse(
    flight: Flight,
    release_time: datetime | None = None,
    use_gnss_altitude: bool = False,
    recorder_kind: RecorderKind | None = None,
    calibrated: bool = False,
    motorglider: bool = False,
    calibration: CalibrationTable | None = None,
) -> FlightAnalysis:
    """Calcola tutte le grandezze necessarie alla validazione.

    `recorder_kind` forza il tipo di registratore; se assente si ricava dal file.
    `calibrated` indica che il registratore ha dati di taratura barometrica:
    solo allora si usa la quota barometrica senza margine (§2.4.6).
    `calibration` e' la tabella del certificato di taratura: la quota
    barometrica viene corretta (§2.4.3a) e il registratore si considera tarato.
    `motorglider` indica un aliante con motore: lo sgancio puo' essere lo
    spegnimento del motore e le prove finiscono al suo avvio (§1.2.8, §1.3.2c).
    """
    started = time.perf_counter()
    notes: list[str] = []
    fixes = flight.fixes
    if calibration is not None:
        calibrated = True
        fixes = [
            replace(f, pressure_alt=round(calibration.correct(f.pressure_alt)))
            if f.pressure_alt is not None
            else f
            for f in fixes
        ]
        recorded = [f.pressure_alt for f in flight.fixes if f.pressure_alt is not None]
        if recorded and (min(recorded) < calibration.low_m or max(recorded) > calibration.high_m):
            notes.append(
                f"Quote registrate fra {min(recorded)} e {max(recorded)} m, oltre la tabella "
                f"di taratura ({calibration.low_m:.0f}-{calibration.high_m:.0f} m): la "
                "correzione e' estrapolata, da verificare."
            )
    recorder = classify_recorder(flight, recorder_kind)

    baro = [f.pressure_alt for f in fixes if f.pressure_alt is not None]
    gnss = [f.gnss_alt for f in fixes if f.gnss_alt is not None]
    altitude_usable = True
    if not use_gnss_altitude and not calibrated:
        # §2.4.6a: senza dati di taratura, FR o PR che sia, vale il §2.4.3c:
        # quota GNSS con un margine di 100 m su tutti i requisiti di quota.
        use_gnss_altitude = True
        notes.append(
            "Nessun dato di taratura barometrica dichiarato: usata la quota GNSS "
            "con il margine di 100 m sui requisiti di quota (§2.4.6a, §2.4.3c)."
        )
    elif not use_gnss_altitude and (
        not baro or max(baro) - min(baro) < PARAMS.min_barometric_spread_m
    ):
        use_gnss_altitude = True
        notes.append(
            "Quota barometrica assente o costante (campo non compilato dal "
            "logger): usata la quota GNSS con il margine di 100 m (§2.4.3c)."
        )
    if use_gnss_altitude and (not gnss or max(gnss) - min(gnss) < PARAMS.min_barometric_spread_m):
        altitude_usable = False
        notes.append(
            "Quota GNSS assente o costante: senza una quota barometrica tarata "
            "i requisiti di quota non sono determinabili."
        )
    altitude_source = (
        "GNSS"
        if use_gnss_altitude
        else "barometrica corretta con la tabella di taratura (§2.4.3a)"
        if calibration is not None
        else "barometrica (ISA 1013.25 hPa)"
    )

    moving = _moving_flags(fixes)
    takeoff = detect_takeoff(fixes, moving)
    landing = detect_landing(fixes, moving)

    if release_time is not None:
        release = find_point_at(fixes, release_time)
        release_source, confidence, tow_climb = RELEASE_SOURCE_MANUAL, "alta", 0.0
        delta = abs((release.time - release_time).total_seconds())
        if delta > PARAMS.max_release_time_mismatch_s:
            confidence = "bassa"
            notes.append(
                f"L'orario di sgancio indicato dista {delta:.0f}s dal fix piu' "
                "vicino: verificare che si riferisca a questo volo."
            )
        if release.index < takeoff.index:
            confidence = "bassa"
            notes.append(
                "L'orario di sgancio indicato precede il decollo rilevato "
                f"({takeoff.time:%H:%M:%S} UTC)."
            )
    else:
        release, confidence, tow_climb = detect_release(fixes, takeoff, use_gnss_altitude)
        release_source = RELEASE_SOURCE_HEURISTIC
        launch_run = (
            find_engine_run(fixes, takeoff.index, release.index) if motorglider else None
        )
        if launch_run is not None:
            # Decollo autonomo: la prova parte allo spegnimento del motore (§1.2.8).
            stop = launch_run.index
            while stop < landing.index and engine_running(fixes[stop]):
                stop += 1
            release, confidence, tow_climb = Point(stop, fixes[stop]), "alta", 0.0
            release_source = RELEASE_SOURCE_ENGINE

    # Per riconoscere una sosta serve una quota che non si blocca col GPS: la
    # barometrica quando il logger la registra.
    ground_gnss = not baro or max(baro) - min(baro) < PARAMS.min_barometric_spread_m
    landing = refine_landing(fixes, moving, release, landing, ground_gnss)

    engine_start: Point | None = None
    if motorglider:
        if not (flight.has_enl or flight.has_mop):
            notes.append(
                "Motoaliante senza registrazione ENL o MOP: l'uso del motore non e' "
                "verificabile dalla traccia, l'OO deve certificare il mezzo usato per "
                "escluderlo (§2.4.5, §2.4.7)."
            )
        engine_start = find_engine_run(fixes, release.index + 1, landing.index)
        if engine_start is not None:
            notes.append(
                f"Avvio del motore alle {engine_start.time:%H:%M:%S} UTC: le prove "
                "finiscono li' (§1.3.2c, §2.4.5)."
            )
    finish = engine_start or landing

    gain = compute_height_gain(fixes, release.index, use_gnss_altitude, finish.index)

    farthest = find_farthest_point(fixes, release.fix, release.index, finish.index)
    distance, model = geodesic_distance_m(release.fix, farthest.fix)
    distance_from_takeoff, _ = geodesic_distance_m(takeoff.fix, farthest.fix)

    release_alt = altitude(release.fix, use_gnss_altitude)
    far_alt = altitude(farthest.fix, use_gnss_altitude)
    loss = float(release_alt - far_alt) if release_alt is not None and far_alt is not None else 0.0

    silver_finish = finish_fix(
        choose_finish_fix(fixes, release, takeoff, finish.index, use_gnss_altitude, True),
        release,
        takeoff,
        use_gnss_altitude,
    )
    straight_finish = finish_fix(
        choose_finish_fix(fixes, release, takeoff, finish.index, use_gnss_altitude, False),
        release,
        takeoff,
        use_gnss_altitude,
    )

    cadence = median_fix_interval_s(fixes, release.index, finish.index)
    if cadence > RULES.max_fix_interval_s:
        notes.append(
            f"Cadenza di registrazione di un fix ogni {cadence:.0f} s: lo SC3 chiede "
            f"almeno un fix ogni {RULES.max_fix_interval_s:.0f} s (§2.4.1). La traccia "
            "non e' una prova sufficiente per la richiesta."
        )

    # Con cadenza gia' oltre il minuto ogni intervallo sarebbe un buco: basta
    # l'avvertenza sulla cadenza.
    gaps = (
        find_gaps(fixes, release.index, finish.index, RULES.max_fix_interval_s)
        if cadence <= RULES.max_fix_interval_s
        else []
    )
    if gaps:
        longest = max(gaps, key=lambda gap: gap[1])
        notes.append(
            f"{len(gaps)} buchi di registrazione oltre {RULES.max_fix_interval_s:.0f} s "
            f"(il piu' lungo di {longest[1]:.0f} s, chiuso alle "
            f"{longest[0].time:%H:%M:%S} UTC): la continuita' del volo va confermata "
            "dall'OO o con la traccia di un secondo registratore (§2.4a, §2.4.5, §4.3.5b)."
        )
    stops = find_intermediate_stops(fixes, moving, release.index, finish.index, ground_gnss)

    enl_values = [f.enl for f in fixes[release.index : landing.index + 1] if f.enl is not None]
    max_enl = max(enl_values) if enl_values else None
    # Su un motoaliante l'avvio del motore e' gia' gestito come fine delle prove.
    engine_suspected = not motorglider and any(
        engine_running(f) for f in fixes[release.index : landing.index + 1]
    )

    analysis = FlightAnalysis(
        takeoff=takeoff,
        landing=landing,
        release=release,
        release_source=release_source,
        release_confidence=confidence,
        tow_climb_m=tow_climb,
        height_gain=gain,
        farthest=farthest,
        distance_m=distance,
        distance_from_takeoff_m=distance_from_takeoff,
        geodesic_model=model,
        loss_of_height_m=loss,
        altitude_source=altitude_source,
        engine_suspected=engine_suspected,
        max_enl=max_enl,
        median_fix_interval_s=cadence,
        gaps=gaps,
        intermediate_stops=stops,
        motorglider=motorglider,
        engine_start=engine_start,
        notes=notes,
        task_check=(
            verify_declared_task(fixes, flight.task, release, finish.index, use_gnss_altitude)
            if flight.task is not None
            else None
        ),
        recorder=recorder,
        altitude_usable=altitude_usable,
        calibrated=calibrated,
        silver_finish=silver_finish,
        straight_finish=straight_finish,
    )
    logger.debug(
        "Analisi volo: fixes=%d, sgancio=%s (%s), atterraggio=%s | durata=%.0fs, "
        "guadagno=%.0fm, distanza=%.0fm | %.1fms",
        len(fixes),
        release.time.strftime("%H:%M:%S"),
        release_source,
        landing.time.strftime("%H:%M:%S"),
        analysis.duration_s,
        gain.gain_m,
        distance,
        (time.perf_counter() - started) * 1000,
    )
    return analysis

"""Interfaccia Streamlit per la validazione di file IGC.

Il file caricato viene scritto in un file temporaneo solo per la durata
dell'elaborazione e cancellato subito dopo: non viene mai persistito.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from silverc.analysis import analyse
from silverc.igc import IGCParseError, parse_igc
from silverc.report import render
from silverc.rules import BADGES
from silverc.validator import Verdict, validate_badge

_MARKS = {
    Verdict.PASS: "✅",
    Verdict.FAIL: "❌",
    Verdict.MARGINAL: "⚠️",
    Verdict.UNDETERMINED: "❔",
}

st.set_page_config(page_title="Validatore insegne FAI", page_icon="🪂")
st.title("Validatore insegne FAI da file IGC")
st.caption("Il file caricato non viene salvato: resta in memoria/temporanea solo per l'analisi.")

badge = st.selectbox("Insegna da verificare", options=sorted(BADGES), index=sorted(BADGES).index("argento"))
use_gnss_altitude = st.checkbox("Usa la quota GNSS invece di quella barometrica (con penalizzazione)")

uploaded_file = st.file_uploader("Carica un file IGC", type=["igc"])

if uploaded_file is not None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / uploaded_file.name
        tmp_path.write_bytes(uploaded_file.getvalue())

        try:
            flight = parse_igc(tmp_path)
        except IGCParseError as exc:
            st.error(f"Errore: {exc}")
        else:
            analysis = analyse(flight, use_gnss_altitude=use_gnss_altitude)
            report = validate_badge(flight, analysis, BADGES[badge])

            satisfied = len(report.satisfied)
            if report.complete:
                st.success(f"Insegna d'{badge} raggiunta: tutte e tre le prove soddisfatte.")
            elif satisfied:
                st.warning(
                    f"Insegna d'{badge} non raggiunta con questo volo: "
                    f"{satisfied} prove su 3 soddisfatte. Le restanti possono "
                    "essere ottenute in voli diversi."
                )
            else:
                st.error(f"Insegna d'{badge}: nessuna delle tre prove è soddisfatta.")

            st.subheader("Esito delle singole prove")
            for requirement, column in zip(report.requirements, st.columns(3)):
                with column:
                    st.metric(
                        label=requirement.code.capitalize(),
                        value=requirement.measured,
                        delta=f"{_MARKS[requirement.verdict]} {requirement.verdict.value}",
                        delta_color="off",
                    )
                    st.caption(f"richiesto: {requirement.required}")

            for requirement in report.requirements:
                with st.expander(
                    f"{_MARKS[requirement.verdict]} {requirement.title} — "
                    f"{requirement.verdict.value}",
                    expanded=requirement.verdict is not Verdict.PASS,
                ):
                    st.markdown(
                        f"**Misurato:** {requirement.measured}  \n"
                        f"**Richiesto:** {requirement.required}"
                    )
                    st.markdown("**Come è stato verificato**")
                    st.markdown("\n".join(f"- {m}" for m in requirement.method))
                    st.markdown("**Motivazione dell'esito**")
                    st.markdown("\n".join(f"- {r}" for r in requirement.reasons))

            if report.warnings:
                st.subheader("Avvertenze")
                for warning in report.warnings:
                    st.warning(warning)

            with st.expander("Report completo"):
                st.text(render(report))

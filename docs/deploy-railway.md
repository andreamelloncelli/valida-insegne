# Pubblicazione su Railway

L'interfaccia Streamlit del validatore gira in un container. Railway costruisce
l'immagine dal `Dockerfile` e la espone su HTTPS.

## Prerequisiti

- **Railway CLI**: `brew install railway`
- **Un piano Railway attivo** sull'account che ospita il progetto.
- **Docker** in esecuzione, solo per la prova locale.

## File che compongono il deploy

| File | Ruolo |
|------|-------|
| `Dockerfile` | immagine `python:3.12-slim`, dipendenze con `uv sync --frozen`, avvio di Streamlit |
| `railway.json` | builder `DOCKERFILE`, healthcheck, politica di riavvio |
| `.dockerignore` | esclude `.git`, `.venv`, cache, `test/`, tracce `*.igc` |
| `Makefile` | target `docker-build`, `docker-run`, `deploy` |

## Come e' costruita l'immagine

- **Porta**: Railway assegna la porta a runtime nella variabile `PORT`. Il `CMD`
  e' in forma shell proprio per poterla espandere; non va trasformato in forma
  esec (`CMD ["streamlit", ...]`), che non espande le variabili.
- **Healthcheck**: `/_stcore/health`, l'endpoint di Streamlit. Risponde `ok`
  quando l'app e' pronta.
- **Livelli**: le dipendenze si installano in un livello separato, prima di
  copiare `src/`. Una modifica al codice non fa reinstallare i pacchetti.
- **Utente non-root**: l'immagine gira come utente `app` (uid 1000).
- **Upload**: limite di 10 MB per file, piu' che sufficiente per una traccia IGC.
- Il container e' autosufficiente: copia solo `src/`, e l'app non legge nessun
  file del repository a runtime. Chi aggiunge una pagina che legge un file dal
  disco (un PDF, un markdown dei requisiti) deve anche copiarlo nell'immagine.

## Prova locale

Stessa immagine che gira in produzione, sulla porta 8501:

```bash
make docker-run
```

Poi `http://localhost:8501`. Per verificare l'healthcheck:

```bash
curl -s http://localhost:8501/_stcore/health
```

## Deploy

Dalla cartella del progetto, senza bisogno di un remote git:

```bash
railway login
railway init
railway up
```

`railway up` carica la cartella corrente, costruisce l'immagine e pubblica. I
deploy successivi sono solo `railway up`, oppure `make deploy`.

In alternativa si collega un repository GitHub dalla dashboard Railway: ogni
push sul branch configurato fa il deploy.

## Variabili d'ambiente

Nessuna da configurare. L'app non usa segreti e non persiste i file caricati:
la traccia IGC viene scritta in una directory temporanea per la durata
dell'analisi e cancellata subito dopo.

## Se qualcosa non va

| Sintomo | Causa probabile |
|---------|-----------------|
| Build che fallisce su `uv sync --frozen` | `uv.lock` non allineato a `pyproject.toml`: eseguire `uv lock` e ricommittare |
| Deploy "unhealthy" | l'app non risponde su `$PORT`: verificare che il `CMD` resti in forma shell |
| 502 subito dopo il deploy | Streamlit non ha ancora finito l'avvio: l'healthcheck va ritentato, non e' un errore |
| Pagina che non trova un file | il file non e' dentro `src/` oppure e' escluso da `.dockerignore` |

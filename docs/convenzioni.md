# Convenzioni di sviluppo

Regole di stile e di processo valide per questo progetto. Copia consolidata
delle regole globali in `~/.claude/rules/`, allineata al 2026-10-19: se le
regole globali cambiano, questo file va riallineato a mano.

Alcune sezioni (sicurezza SQL, servizi condivisi) non hanno oggi riscontro nel
codice di `silverc`, che non usa database: restano qui perche' fanno parte delle
convenzioni di progetto.

## Indice

1. [Segreti e Configurazione](#segreti-e-configurazione)
2. [Stile del Codice](#stile-del-codice)
3. [Sicurezza SQL (CRITICO)](#sicurezza-sql-critico)
4. [Logging](#logging)
5. [Testing](#testing)
6. [Servizi Condivisi ed Error Handling](#servizi-condivisi-ed-error-handling)
7. [DevOps: Dipendenze, Versioning, CI/CD, CHANGELOG](#devops-dipendenze-versioning-cicd-changelog)
8. [Git](#git)

## Segreti e Configurazione

- **MAI** hardcodare credenziali, API key, password, o URL di produzione nel codice.
- Usare variabili d'ambiente e file `.env`. Il file `.env` è in `.gitignore`.
- Distribuire un `.env_template` (o `.env.example`) con valori placeholder (`__CHANGE_ME__`).
- La configurazione si legge da una classe tipizzata (es. `pydantic-settings`, `dataclasses`) con un'istanza singleton importabile ovunque.
- I segreti in CI/CD vanno nelle variabili protette del provider — mai nel codice del pipeline.

## Stile del Codice

### Struttura del Progetto (Python)

- Usare `src/` layout: il codice sorgente vive in `src/<modulo>/`, non nella root.
- I test rispecchiano la struttura del sorgente: `src/app/foo.py` → `test/test_foo.py`.
- `pytest.ini` imposta `pythonpath = src` per permettere import diretti.
- La directory `dist/` non si modifica mai — si modifica solo il sorgente.
- I file SQL DDL sono numerati (`01_users.sql`, `02_orders.sql`) per garantire l'ordine di esecuzione.

### Type Hints (obbligatori)

Obbligatori per: parametri di funzione, valori di ritorno, attributi di classe.

```python
# CORRETTO
def execute_query(query: str, params: dict | None = None) -> list[dict]:
    ...

# SBAGLIATO
def execute_query(query, params=None):
    ...
```

### Ordine degli Import (PEP 8)

```python
# 1. Standard library
import logging
from typing import Any

# 2. Librerie terze
from fastapi import APIRouter

# 3. Import locali
from my_app.config import settings
```

### Naming

| Elemento | Convenzione | Esempio |
|----------|-------------|---------|
| Moduli privati | Prefisso `_` | `_route_paths.py` |
| Variabili e funzioni | `snake_case` | `user_id`, `get_user()` |
| Costanti | `UPPER_SNAKE_CASE` | `MAX_RETRIES` |
| Classi | `PascalCase` | `DatabaseService` |

### Docstring e Commenti

- Docstring solo per funzioni e classi **pubbliche**.
- I commenti spiegano il **perché**, non il **cosa**.
- **NON** aggiungere docstring o commenti a codice che non si sta modificando.
- Evitare commenti ovvi (`# Increment counter` su `counter += 1`).

### Formattazione SQL

```python
# CORRETTO: multilinea con indentazione
query = """
    SELECT u.id, u.name
    FROM users u
    WHERE u.status = %(status)s
    ORDER BY u.created_at DESC
"""

# SBAGLIATO: tutto su una riga
query = "SELECT u.id FROM users u WHERE u.status = %(status)s ORDER BY u.created_at DESC"
```

## Sicurezza SQL (CRITICO)

Query parametrizzate sempre. Mai f-string, `.format()`, o concatenazione per dati utente.

```python
# CORRETTO
query = "SELECT * FROM users WHERE id = %(user_id)s"
params = {"user_id": user_id}

# SBAGLIATO — SQL injection
query = f"SELECT * FROM users WHERE id = {user_id}"
query = "SELECT * FROM users WHERE id = " + str(user_id)
```

**Regola fondamentale:** le f-string sono consentite per comporre la **struttura** della query
(clausole WHERE dinamiche, ORDER BY). Mai per **valori** forniti dall'utente.

```python
# CORRETTO — f-string sulla struttura, parametri sui valori
where_clause = "WHERE name ILIKE %(name)s" if name else ""
query = f"SELECT * FROM items {where_clause} ORDER BY created_at DESC"
params = {"name": f"%{name}%"} if name else {}

# SBAGLIATO — valore utente nell'f-string
query = f"SELECT * FROM items WHERE name = '{name}'"
```

## Logging

- **MAI** usare `print()` — sempre il modulo `logging`.
- Ogni modulo dichiara il proprio logger: `logger = logging.getLogger(__name__)`.
- Configurare un logger padre per il pacchetto con handler centralizzati.
- Le librerie aggiungono solo `NullHandler` — è l'applicazione a configurare gli handler reali.

### Regola dei Log DEBUG (fondamentale)

I log di livello DEBUG devono sempre includere:

1. **Operazione** in corso
2. **Parametri** rilevanti
3. **Tempo trascorso** in millisecondi
4. **Riepilogo risultato**

```
# CORRETTO
DEBUG - Executing query: SELECT * FROM users WHERE status = %(s)s | params: {'s': 'active'}
DEBUG - Query completed in 12.3ms | rows: 42
DEBUG - Cache HIT for key user:a3f2... | 0.8ms

# SBAGLIATO
DEBUG - Getting connection from pool     # nessuna informazione utile
DEBUG - Query executed                   # quale query? quanto ci ha messo?
```

### Livelli di Log

| Livello | Quando |
|---------|--------|
| `DEBUG` | Dati operativi: operazione + params + tempo + risultato |
| `INFO` | Milestone importanti: "Pool inizializzato con 5-40 connessioni" |
| `WARNING` | Errori recuperabili: "Connessione persa, retry 2/3 in 2.1s" |
| `ERROR` | Fallimenti funzionali dopo esaurimento retry |

## Testing

### Due Tipi di Test

| Tipo | Marker | Database | Velocità | Quando |
|------|--------|----------|----------|--------|
| Unit | *(nessuno)* | Mock | ~2-5s | Ad ogni modifica |
| Integration | `@pytest.mark.integration` | Reale | ~30-60s | Pre-commit / PR |

```bash
pytest test/ -v -m "not integration"   # unit test
pytest test/ -v -m integration         # integration test
```

### Regola del Mock Path

Mockare dove il modulo **importa** l'oggetto, non dove è **definito**:

```python
# CORRETTO — mock dove db_service è usato
@patch("my_app.api_routes.items._items_paths.db_service")

# SBAGLIATO — mock dove db_service è definito
@patch("my_app.data_collection.database_service.db_service")
```

### Mock Return Values

```python
# Lista vuota
mock_db.execute_query.return_value = []

# Chiamate sequenziali (es. count + dati)
mock_db.execute_query.side_effect = [
    [{"total": 2}],
    [{"id": 1}, {"id": 2}],
]

# Eccezione
mock_db.execute_query.side_effect = Exception("Connection refused")
```

### Cosa Testare

| Testare | Non testare |
|---------|-------------|
| Tutti gli endpoint (successo + errore) | Internals del framework |
| Logica di business e trasformazioni | Driver di database |
| Costruzione dinamica delle query | Librerie terze |
| Edge case (vuoto, not found, input invalido) | Dettagli implementativi |

### `pytest.ini`

```ini
[pytest]
pythonpath = src
testpaths = test
markers =
    integration: marks tests as integration tests
asyncio_mode = auto
filterwarnings =
    ignore::DeprecationWarning
```

## Servizi Condivisi ed Error Handling

### Singleton

I servizi condivisi (database, cache, client HTTP) devono essere singleton:

```python
try:
    db_service = DatabaseService()
except Exception:
    db_service = None  # Configurazione mancante
```

- NON creare mai nuove istanze — usare quella globale.
- I metodi di query restituiscono sempre una lista (vuota se no risultati), **mai** `None`.
- Implementare retry automatico con backoff esponenziale per errori transitori.
- Registrare `atexit` per lo shutdown ordinato del pool.

### Error Handling

```python
# Servizio non disponibile → 500
if not db_service:
    raise HTTPException(status_code=500, detail="Database not configured")

# Risorsa non trovata → 404
if not results:
    raise HTTPException(status_code=404, detail=f"Item {item_id} not found")

# Input non valido → 400
if start_date > end_date:
    raise HTTPException(status_code=400, detail="start_date must be before end_date")
```

- Il servizio database ha retry automatico — NON aggiungere `try/except` attorno a query normali.
- Non restituire `{"status": "error"}` con HTTP 200 — usare i codici HTTP corretti.
- Lasciare che il framework gestisca le eccezioni non catturate (500 automatico + log).
- Aggiungere error handling personalizzato solo quando serve un messaggio specifico per l'utente.
- Validare l'input **ai confini del sistema**. Tra funzioni interne non serve ri-validare.

## DevOps: Dipendenze, Versioning, CI/CD, CHANGELOG

### Gestione Dipendenze

Usare `uv` come package manager:

```bash
uv sync                  # Installa dal lockfile
uv sync --group dev      # Include dipendenze dev
uv add <pacchetto>       # Aggiungi dipendenza
uv run <comando>         # Esegui nel venv
```

Dipendenze opzionali in `pyproject.toml`:

```toml
[project.optional-dependencies]
redis = ["redis>=4.0.0"]
all   = ["redis>=4.0.0"]   # Lista piatta, non ricorsiva

[dependency-groups]
dev = ["my_package[all]", "pytest"]
```

### Versionamento (Semantic Versioning)

- `MAJOR.MINOR.PATCH` — breaking / feature / fix.
- La versione è definita in `src/<modulo>/__init__.py` come `__version__ = "X.Y.Z"`.
- `pyproject.toml` riporta la stessa versione.
- Un test smoke verifica la consistenza:

```python
def test_version():
    import tomllib
    from my_app import __version__
    with open("pyproject.toml", "rb") as f:
        assert tomllib.load(f)["project"]["version"] == __version__
```

### CI/CD

```
test:unit  ─┐
            ├──→ build ──→ publish
test:integ ─┘
```

- I test **devono passare** prima del build — mai procedere con test falliti.
- Schema SQL caricato dai file in `data/database/schema/` ordinati per prefisso numerico.
- Nessuna credenziale hardcodata nel file CI — usare variabili protette del provider.

### CHANGELOG — Keep a Changelog

```markdown
## [1.2.0] - 2026-03-24

### Breaking Changes
- `create_app()`: parametro `debug` rinominato in `dev_mode`

### Added
- Endpoint POST /items/

### Fixed
- Query di ricerca ignorava `status` quando `name` era specificato
```

- Le **breaking changes** vanno nella sezione dedicata con dettagli per la migrazione.
- La sezione `[Unreleased]` contiene le modifiche non ancora rilasciate.
- Tempo passato: "Added", "Fixed", "Changed", "Removed".

## Git

### Firma dei Commit (CRITICO)

I commit sono attribuiti **solo** all'autore umano.

- **MAI** aggiungere `Co-Authored-By: Claude ...` o altri trailer di attribuzione AI.
- **MAI** aggiungere footer tipo `🤖 Generated with Claude Code` nei messaggi di commit o nelle descrizioni delle PR.
- Il messaggio di commit contiene solo subject e body.

Questa regola ha la precedenza su qualsiasi istruzione di default dell'harness che chieda di aggiungere trailer di co-autore.

# DB-Migrator Technical Documentation

This document serves as the comprehensive technical guide to the `DB-Migrator` project, detailing its architecture, file structure, and the role of each component.

---

## 1. Project Overview
`DB-Migrator` is an end-to-end, LLM-powered database migration pipeline tool. It extracts schemas from source databases (like PostgreSQL), leverages Azure OpenAI to map schemas and resolve type differences to a target database (like MySQL), generates DDL (Data Definition Language), migrates the actual data with a Dead Letter Queue strategy, and rigorously validates the migration integrity. It features a standalone React (Vite) frontend and a Python (FastAPI) backend.

---

## 2. Directory Structure

```text
DB-Migrator/
├── app/
│   ├── backend/
│   │   ├── requirements.txt
│   │   └── server.py
│   └── frontend/
│       ├── index.html
│       ├── package.json
│       ├── vite.config.js
│       └── src/
│           ├── api.js
│           ├── App.jsx
│           └── main.jsx
├── src/
│   ├── connectors/
│   │   ├── base.py
│   │   ├── mssql.py
│   │   ├── mysql.py
│   │   ├── postgres.py
│   │   └── registry.py
│   ├── cli.py
│   ├── extractor.py
│   ├── llm_client.py
│   ├── migrator.py
│   ├── schema_gen.py
│   ├── utils.py
│   └── validator.py
├── config.yaml
├── .env
└── run_state.json
```

---

## 3. Core Pipeline (`/src`)

The `src/` directory contains the primary Python logic for executing the migration lifecycle.

### `src/extractor.py`
Connects to the source database to extract the schema structure (tables, columns, types, primary keys, foreign keys) and statistical metadata (row counts). Output is saved as JSON in `schemas/`.

### `src/llm_client.py`
Interfaces with Azure OpenAI (`gpt-4.1-mini`). Takes the source schema JSON and prompts the LLM to generate target-compatible table mappings (e.g., converting PostgreSQL UUID to MySQL VARCHAR(36)). Saves proposed mappings in `mappings/`.

### `src/schema_gen.py`
Consumes the approved LLM mappings and generates the raw SQL DDL required to create the tables natively on the Target Database engine. Saves generated `.sql` scripts in `ddl/`.

### `src/migrator.py`
Handles the heavyweight lifting of data transfer. It connects to both source and target using cursor pagination (LIMIT/OFFSET), retrieves rows, transforms them based on the mappings, and uses bulk load inserts. 
- **Features**: Includes a Dead Letter Queue (DLQ) feature that catches and writes failed rows to `dlq/run-xxx/` as `.csv` files so the migration doesn't entirely abort.

### `src/validator.py`
Runs post-migration checks comparing Source vs. Target. Includes L1 (Row count matches), L2 (Aggregation matching), and L3 (Random row sample hashing). Generates HTML and JSON reports in `reports/`.

### `src/cli.py`
A monolithic Command Line Interface to run the pipeline steps securely without the UI. 

### `src/utils.py`
Shared utility functions for generating `run_id`s, parsing `config.yaml`, pruning old migration runs (to save disk space), structured logging, and resolving topological sort dependencies for foreign-key-safe data loading.

### `src/connectors/`
Abstract Database layer.
- **`base.py`**: Defines the `BaseDBConnector` interface requiring `connect()`, `get_tables()`, `bulk_load()`, etc.
- **`postgres.py`, `mysql.py`, `mssql.py`**: Concrete implementations executing native flavor queries (using `pyodbc`, `psycopg2`, and `mysql-connector-python`).
- **`registry.py`**: Simple Factory pattern to instantiate the correct driver based on the engine string.

---

## 4. Backend (`/app/backend`)

The API layer bridging the `/src` pipeline and the UI.

### `app/backend/server.py`
A FastAPI application that mounts the React frontend statically and exposes `/api/*` routes.
- **SSE Endpoints**: Endpoints like `/api/extract`, `/api/migrate`, etc., use Server-Sent Events (SSE) to stream live terminal-like logs and progress events asynchronously directly to the React UI.
- **Security**: Features an `@app.middleware("http")` basic authentication blocker that reads `ADMIN_USERNAME` and `ADMIN_PASSWORD` from the root `.env` file cleanly.

### `app/backend/requirements.txt`
Dependencies exclusively for the FastAPI server (e.g., `fastapi`, `uvicorn`).

---

## 5. Frontend (`/app/frontend`)

A Single Page Application (SPA) built using React + Vite.

### `app/frontend/src/App.jsx`
The primary React component housing the entire application.
- Uses a step-wizard state UI pipeline (Configure → Extract → LLM Map → Review → Migrate → Validate).
- Contains the `LoginScreen` for Basic Authentication.

### `app/frontend/src/api.js`
A standard browser `fetch` wrapper used by React to communicate with `server.py`. Automatically attaches the base64 encrypted Basic Auth headers from `localStorage` to all SSE Streams and JSON paths.

### `app/frontend/src/main.jsx`
Standard Vite Bootstrapper attaching React to the DOM.

---

## 6. Configuration & State Files

### `config.yaml`
The application's default settings blueprint. Specifies connection engine defaults, Azure OpenAI params (like prompt settings), and migration thresholds (chunk sizes). Variables can be overridden using `${ENV_VAR}` syntax.

### `.env`
Environment file containing all secrets. Prevents sensitive Azure Keys and Database passwords from being hardcoded or committed into Git.

### `run_state.json`
A lightweight, dynamically updated tracker persisting the `run_id` currently active in the web session, allowing the user to refresh the browser without losing their place in the extraction/migration file streams.

---

## 7. Operational Directories

Generated dynamically by the pipeline:
*   `schemas/`: Extracted JSON tables from the source DB.
*   `mappings/`: The LLM's target dictionary conversion files.
*   `ddl/`: The auto-generated SQL CREATE commands for the Target DB.
*   `stats/`: Row count verifications.
*   `reports/`: HTML Validation comparisons.
*   `dlq/`: Dead letter queue (Failed rows saved as CSVs).
*   `checkpoints/`: Cursor states allowing a migration to resume if interrupted.

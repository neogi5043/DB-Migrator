# DB Migrator — PostgreSQL / SQL Server → MySQL Migration

Migrate from **PostgreSQL** or **SQL Server (Azure SQL)** to **MySQL** with AI-assisted schema translation and safe, resumable data transfer.

Uses **Azure OpenAI (GPT-4.1)** to intelligently translate column types and generate MySQL DDL, with a human review step before anything is applied.

---

## How It Works

```mermaid
graph TD
    User((User))
    Source[(Source DB)]
    Target[(Target MySQL)]
    AI[Azure OpenAI]
    
    subgraph Pipeline
        Extract[1. Extract Schema]
        Propose[2. Propose Mappings]
        Review[3. Review & Approve]
        Apply[4. Apply DDL]
        Migrate[5. Migrate Data]
        Validate[6. Validate]
    end

    %% Flow
    Source --> Extract
    Extract --> Propose
    AI <--> Propose
    Propose -- "Draft JSON" --> Review
    Review -- "Approved JSON" --> Apply
    Apply --> Target
    Review -- "Approved JSON" --> Migrate
    Source --> Migrate
    Migrate -- "Chunked Data" --> Target
    Source <--> Validate
    Target <--> Validate
    
    User -- "Review / Run CLI" --> Pipeline
```

---

## Quick Start

### 1. Install

```bash
pip install -r requirements.txt

# Install the database drivers:
pip install psycopg2-binary       # PostgreSQL source
pip install pyodbc                # SQL Server source
pip install mysql-connector-python # MySQL target
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your actual credentials:

```env
# Azure OpenAI
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4.1

# PostgreSQL Source
SRC_PG_HOST=localhost
SRC_PG_PORT=5432
SRC_PG_DB=source_db
SRC_PG_USER=postgres
SRC_PG_PASS=your-password

# SQL Server Source (if using SQL Server instead)
MSSQL_HOST=your-server.database.windows.net
MSSQL_PORT=1433
MSSQL_DB=source_db
MSSQL_USER=sqladmin
MSSQL_PASS=your-password

# MySQL Target
TGT_MYSQL_HOST=localhost
TGT_MYSQL_PORT=3306
TGT_MYSQL_DB=target_db
TGT_MYSQL_USER=root
TGT_MYSQL_PASS=your-password
```

**In `config.yaml`**, set `source.engine` to match your source database:
- `postgres` — to migrate from PostgreSQL
- `mssql` — to migrate from SQL Server / Azure SQL

### 3. Run the Migration

```bash
# Step 1: Extract schema from your source database
python src/cli.py extract

# Step 2: AI proposes column mappings
python src/cli.py propose

# Step 3: Review the drafts
#   Open files in mappings/draft/
#   Edit if needed, then move to mappings/approved/

# Step 4: Preview the MySQL DDL (safe, no changes)
python src/cli.py apply-schema --dry-run

# Step 5: Create tables on MySQL
python src/cli.py apply-schema --apply

# Step 6: Migrate data
python src/cli.py migrate

# Step 7: Validate
python src/cli.py validate
```

You can also keep each run **fully isolated** by supplying a run ID and reusing it across commands:

```bash
RUN_ID=myrun123

python src/cli.py extract --run-id "$RUN_ID"
python src/cli.py propose --run-id "$RUN_ID"
# ...move reviewed files from mappings/$RUN_ID/draft/ → mappings/$RUN_ID/approved/...
python src/cli.py apply-schema --run-id "$RUN_ID" --apply
python src/cli.py migrate --run-id "$RUN_ID"
python src/cli.py validate --run-id "$RUN_ID"
```

---

## Switching Source Database

To switch from PostgreSQL to SQL Server (or vice versa), just change one line in `config.yaml`:

```yaml
source:
  engine: mssql    # Change to 'postgres' for PostgreSQL
```

Then update the matching credentials in `.env`. Everything else stays the same.

---

## All Commands

| Command | What It Does |
|---------|-------------|
| `python src/cli.py extract [--run-id <id>]` | Reads source schema → saves to `schemas/` or `schemas/<id>/` when `--run-id` is used |
| `python src/cli.py propose [--run-id <id>]` | AI generates column mappings → saves to `mappings/draft/` or `mappings/<id>/draft/` |
| `python src/cli.py validate-mapping [path] [--run-id <id>]` | Checks a mapping file or all files in `mappings[/<id>]/approved/` for errors |
| `python src/cli.py apply-schema --dry-run [--run-id <id>]` | Shows the DDL that *would* run (safe preview) from `mappings[/<id>]/approved/` |
| `python src/cli.py apply-schema --apply [--run-id <id>]` | Runs the DDL on MySQL (optionally scoped to `ddl/<id>/`) |
| `python src/cli.py migrate [--run-id <id>]` | Moves all data in chunks (restartable) using `mappings[/<id>]/approved/` and `checkpoints/<id>/` |
| `python src/cli.py migrate --tables orders` | Migrate a single table |
| `python src/cli.py migrate --run-id <id>` | Resume a failed migration |
| `python src/cli.py validate [--run-id <id>]` | Compares source vs target row counts and values, writing reports (optionally `reports/<id>/`) |
| `python src/cli.py show-checkpoints --run-id <id>` | Shows progress of a migration run |
| `python src/cli.py list-engines` | Lists all supported databases |

---

## Run IDs & Per‑Run Folders

- **Without `--run-id`**: all commands use shared top-level folders (e.g. `schemas/`, `mappings/draft/`, `ddl/`, `reports/`) — this matches the original behavior.
- **With `--run-id <id>`**: outputs for that run are isolated under per-run subfolders:
  - `schemas/<id>/...`
  - `stats/<id>/...`
  - `mappings/<id>/draft/` and `mappings/<id>/approved/`
  - `ddl/<id>/...`
  - `reports/<id>/...`
  - `checkpoints/<id>/...` (already per-run)

This keeps artifacts from different runs from overwriting each other and makes it easy to compare, archive, or clean up specific runs.

---

## Project Layout

```
DB Migrator/
├── config.yaml           # Source/target config
├── .env.example          # Credential template
├── requirements.txt      # Python dependencies
│
├── src/
│   ├── cli.py            # Command-line entry point
│   ├── extractor.py      # Reads source schema + statistics
│   ├── llm_client.py     # Talks to Azure OpenAI
│   ├── schema_gen.py     # Generates and applies DDL
│   ├── migrator.py       # Moves data in chunks with checkpointing
│   ├── validator.py      # Compares source ↔ target after migration
│   └── connectors/       # Database plugins
│       ├── source/       # PostgreSQL + SQL Server connectors
│       └── target/       # MySQL target connector
│
├── templates/            # DDL templates (mysql.sql.j2 used here)
├── prompts/              # LLM prompt templates
│
├── schemas/              # [output] Extracted schemas (or schemas/<run-id>/...)
├── mappings/             # [output/input] Column mappings
│   ├── draft/            # [output] AI-proposed mappings (shared mode)
│   └── approved/         # [input]  Your approved mappings (shared mode)
├── ddl/                  # [output] Generated DDL scripts (or ddl/<run-id>/...)
├── reports/              # [output] Validation reports (or reports/<run-id>/...)
└── checkpoints/          # [output] Migration progress (for resume; per run-id)
```

---

## Key Concepts

### Canonical Types
Source types are mapped to intermediate "canonical" types, then to MySQL:

**PostgreSQL → MySQL:**
```
PostgreSQL      →  Canonical  →  MySQL
─────────────────────────────────────
BIGINT          →  INT8       →  BIGINT
VARCHAR(255)    →  TEXT       →  VARCHAR(255)
TIMESTAMPTZ     →  DATETIMETZ →  TIMESTAMP
BOOLEAN         →  BOOL      →  TINYINT(1)
JSONB           →  JSON      →  JSON
BYTEA           →  BLOB      →  LONGBLOB
```

**SQL Server → MySQL:**
```
SQL Server      →  Canonical  →  MySQL
─────────────────────────────────────
BIGINT          →  INT8       →  BIGINT
NVARCHAR(255)   →  NTEXT      →  VARCHAR(255)
DATETIME2       →  DATETIME   →  DATETIME
BIT             →  BOOL       →  TINYINT(1)
NVARCHAR(MAX)   →  CLOB       →  LONGTEXT
VARBINARY(MAX)  →  BLOB       →  LONGBLOB
```

### Human-in-the-Loop
The AI proposes mappings, but **you always review** before anything touches MySQL. Draft → Approved workflow ensures no surprises.

### Safe Migration
- Data moves in **chunks** (default 100K rows)
- Every chunk is **checkpointed** — if it fails, rerun with `--run-id` to resume
- `--dry-run` lets you preview DDL before applying
- Optional `--run-id` lets you keep each migration run's files isolated in per-run folders

---

## Running Tests

```bash
pytest tests/ -v
```

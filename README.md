# Orders Dashboard — Lakebase + Databricks Asset Bundle

A complete, deployable example of a **Lakebase Autoscaling** project managed with
**Databricks Asset Bundles (DABs)**, including a **Databricks App** (Flask) that
reads a continuously synced Unity Catalog table and writes notes back to Postgres.

Structure follows the pattern in Microsoft's Lakebase DABs reference:
https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/dabs-typical-project

## What's optimized here vs. a bare-bones setup

- **Resilient DB credentials** — minting a Lakebase OAuth token is wrapped in
  retry-with-backoff (`config.CREDENTIAL_RETRIES`), so one transient failure
  doesn't 500 a request.
- **Live-refreshing UI, no framework** — `static/app.js` polls small JSON
  endpoints (`/api/orders`, `/api/notes`) and patches the DOM directly, so the
  dashboard updates every 15s without a full page reload or a JS build step.
- **Server-side pagination + search** on both orders and notes, so the app
  stays fast as tables grow instead of loading everything into memory.
- **CSRF protection** on all mutating routes using a per-session token.
- **Structured request logging** with a request ID on every log line and
  response header, and a `/healthz` endpoint that actually checks the DB.
- **Config centralized in `config.py`** — every env var is read once, typed,
  and validated at import time instead of scattered `os.environ.get()` calls.
- **Tuned gunicorn** (workers/threads/timeouts) and connection pool sizing,
  set per-target in `databricks.yml` (lighter for `dev`, larger for `prod`).
- **Test suite** (`tests/`) that mocks the Postgres pool, so `pytest` runs in
  milliseconds with no live Lakebase project or network access required.
- **CI/CD** (`.github/workflows/ci.yml`): lint + test on every push,
  `databricks bundle validate` on PRs, `databricks bundle deploy -t prod` on
  merge to `main`.
- **Lean deploys** — `sync.exclude` in `databricks.yml` keeps tests, caches,
  and venvs out of the uploaded app bundle.

```
lakebase-orders-app/
├── databricks.yml                  # the bundle: project, branch, endpoint, sync, UC catalog, app
├── .databricks/bundle/prod/
│   └── variables.json.example      # copy to variables.json and fill in your values
├── .github/workflows/ci.yml        # lint, test, validate, deploy
├── setup/
│   └── 01_create_source_table.sql  # creates the UC Delta source table (CDF enabled) to sync
├── scripts/
│   ├── deploy.sh                   # validate + deploy helper
│   └── validate.sh                 # validate-only helper
├── tests/                          # pytest suite against a mocked pool
│   ├── conftest.py
│   ├── test_db.py
│   └── test_app.py
├── Makefile                        # install / run / test / lint / deploy shortcuts
├── pyproject.toml                  # ruff + pytest config
├── requirements-dev.txt            # pytest + ruff, kept out of the prod image
├── .env.example                    # local dev environment template
└── app_src/                        # the Databricks App source (what actually gets deployed)
    ├── app.py                      # Flask routes + JSON API + CSRF + logging
    ├── db.py                       # Lakebase pool, retrying OAuth rotation, pagination/search
    ├── config.py                   # typed, centralized settings
    ├── app.yaml                    # App runtime command (local/standalone fallback)
    ├── requirements.txt            # production-only dependencies
    ├── static/{style.css,app.js}
    └── templates/{base.html,index.html}
```

## What gets deployed

- A **Lakebase Autoscaling project** (`postgres_projects`) sized by `min_cu`/`max_cu`.
- A protected **`production` branch** (`postgres_branches`).
- A **highly-available read-write endpoint** with a standby + readable secondaries
  (`postgres_endpoints`).
- A **continuous sync pipeline** (`postgres_synced_tables`) that streams a Unity
  Catalog Delta table (`orders`) into Postgres as `orders_synced`.
- A **Unity Catalog binding** (`postgres_catalogs`) so the Lakebase database is
  queryable as UC data from SQL warehouses / notebooks.
- A **Databricks App** ("Orders Dashboard") wired to the project database with
  `CAN_CONNECT_AND_CREATE` permission.
- Workspace `CAN_MANAGE` permission on the project for your service principal.

## Prerequisites

1. **Databricks CLI v1.0.0+**
   ```bash
   databricks --version
   ```
   Install/upgrade: https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/install

2. **A Databricks workspace with Lakebase enabled.**

3. **A service principal with OAuth M2M auth**, used both to deploy the bundle and
   as the identity granted `CAN_MANAGE` on the Lakebase project. See
   [Authorize service principal access with OAuth](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/auth/oauth-m2m).

4. **A Unity Catalog Delta table with Change Data Feed enabled** to use as the
   sync source. `setup/01_create_source_table.sql` creates one for you
   (`main.sales.orders`) — run it in a SQL warehouse or notebook first. If you
   don't want data sync, delete the `postgres_synced_tables` and
   `postgres_catalogs` blocks from `databricks.yml`.

## 1. Configure variables

Copy the example variables file and fill in real values:

```bash
cp .databricks/bundle/prod/variables.json.example .databricks/bundle/prod/variables.json
```

Edit `variables.json`:

| Variable              | Description                                                        |
|------------------------|---------------------------------------------------------------------|
| `project_id`           | Lowercase, hyphen-delimited Lakebase project ID                    |
| `display_name`         | Human-readable project name                                        |
| `pg_version`           | Postgres major version (e.g. `17`)                                 |
| `min_cu` / `max_cu`    | Autoscaling compute unit bounds for the default endpoint           |
| `suspend_timeout`      | Idle time before suspend (ignored once HA/`no_suspension` is on)   |
| `admin_sp_app_id`      | Application ID of the service principal to grant `CAN_MANAGE`      |
| `source_table`         | Three-part UC name of the Delta table to sync, e.g. `main.sales.orders` |
| `primary_key_column`   | Primary key column on that source table                            |
| `storage_catalog` / `storage_schema` | Where the sync pipeline stores its metadata           |
| `app_name`             | Unique Databricks App name in the workspace                        |
| `uc_catalog_id`        | Name under which the Lakebase DB is registered in Unity Catalog    |

Also update `workspace.host` under each target in `databricks.yml` to point at
your workspace URL.

Alternatively, pass values inline at deploy time with `--var`, e.g.:
```bash
databricks bundle deploy -t prod --var="admin_sp_app_id=xxxxxxxx-xxxx-..."
```

## 2. Create the source table (for sync)

```bash
databricks sql exec -f setup/01_create_source_table.sql   # or run it in a notebook / SQL editor
```

## 3. Validate and deploy the bundle

```bash
./scripts/validate.sh prod
./scripts/deploy.sh prod
```

Equivalently:
```bash
databricks bundle validate -t prod
databricks bundle deploy -t prod
```

> If `databricks bundle deploy` doesn't complete on the first run (some Lakebase
> resources take a moment to settle), just re-run it.

A `dev` target is also included (`-t dev`) with smaller compute and relaxed
protections, useful for iterating before promoting to `prod`.

## 4. Open the app

After deploy, find the app URL either in the deploy output or via:
```bash
databricks apps get <app_name>
```
Open it in a browser. You should see:
- The **Orders** table, populated from the synced `orders_synced` table.
- A **Notes** panel where you can add/delete rows written directly to Lakebase Postgres.

## How the app authenticates to Lakebase

Databricks Apps authenticate to Lakebase with OAuth tokens that expire after
one hour. `app_src/db.py` implements the recommended pattern: a `psycopg`
connection pool whose connection class mints a **fresh token on every new
physical connection** via
`WorkspaceClient().postgres.generate_database_credential(endpoint=...)`,
so the app never uses a stale token. See:
https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/tutorial-databricks-apps-autoscaling

The `PGHOST`, `PGUSER`, `PGDATABASE`, `PGSSLMODE`, and `PGENDPOINT` environment
variables are injected automatically by the `resources.postgres` binding on
the `apps.lakebase_app` resource in `databricks.yml` — no secrets to manage.

## Local development

Copy `.env.example` to `.env`, fill in your endpoint details, then:

```bash
make install          # creates .venv, installs app_src/requirements.txt
export $(grep -v '^#' .env | xargs)   # or use direnv/python-dotenv
databricks auth login --host https://<your-workspace>.cloud.databricks.com
make run               # flask --app app run --debug --port 8000
```

## Testing & linting

The test suite mocks the Postgres pool entirely (see `tests/conftest.py`), so
it runs without a live Lakebase project, credentials, or network access:

```bash
make test    # pytest
make lint    # ruff check
make fmt     # ruff format
```

CI runs the same two commands on every push/PR, then `databricks bundle
validate` on PRs, and `databricks bundle deploy -t prod` on merges to `main`
(see `.github/workflows/ci.yml`). To enable the deploy job, set these repo
secrets: `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`.

## Tearing down

```bash
databricks bundle destroy -t prod
```
This removes the app and, depending on protection settings, the Lakebase
project resources. The `production` branch is marked `is_protected: true` in
the `prod` target, so review what `destroy` will do before confirming.

## Further reading

- [Typical Lakebase project setup with DABs](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/dabs-typical-project) (the reference this project follows)
- [Manage Lakebase with Declarative Automation Bundles](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/manage-with-bundles)
- [High availability](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/high-availability)
- [Serve lakehouse data with synced tables](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/sync-tables)
- [Manage project permissions](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/manage-project-permissions)
- [Connect a custom Databricks app to Lakebase](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/tutorial-databricks-apps-autoscaling)
- [Declarative Automation Bundles resource reference](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/resources)

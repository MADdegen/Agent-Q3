# use-railway

Route user intent to the correct Railway reference and execute using CLI-first patterns.

## Resource Model

```
Workspace
└── Project
    └── Environment (production | staging | pr-N)
        └── Service  (web, worker, postgres, redis, bucket…)
            └── Deployment
```

Every CLI command runs in the context of the **linked project + environment**.
Run `railway link` once per repo clone to establish that context.

## Routing Table

| User intent | Reference |
|---|---|
| Create project / add service / connect DB / set up bucket | [setup.md](references/setup.md) |
| Deploy code / manage releases / view build logs | [deploy.md](references/deploy.md) |
| Set env vars / configure domains / tune replicas | [configure.md](references/configure.md) |
| Check health / read logs / debug failures | [operate.md](references/operate.md) |
| Call Railway API / search docs / community | [request.md](references/request.md) |
| Inspect or optimize a Postgres database | [analyze-db.md](references/analyze-db.md) |

## Execution Rules

1. **CLI first** — always prefer `railway <command>` over GraphQL mutations.
2. **Fall back to GraphQL** only for operations not exposed by the CLI (metrics, template deploy, project rename). Use `scripts/railway-api.sh '<query>' '<variables-json>'`.
3. **Always use `--json`** on CLI commands that support it; parse with `jq` or Python.
4. **Resolve context before mutation** — confirm project + environment + service names before any write operation.
5. **Never stream open logs** — always pass `--lines N`, `--since`, or `--until` to `railway logs`.
6. **Builder** — Railway now uses **Railpack** by default. Do NOT reference Nixpacks unless the user explicitly has a `nixpacks.toml`.

## Commands That Must NEVER Be Run by the Agent

These require human review and direct execution:

- `python scripts/pg-extensions.py` — installs Postgres extensions
- `python scripts/enable-pg-stats.py` — enables pg_stat_statements
- Any raw SQL containing `ALTER SYSTEM SET`, `DROP EXTENSION`, or `CREATE EXTENSION`

## Quick-Reference Cheatsheet

```bash
# Link repo to project
railway link

# Deploy current directory
railway up --detach -m "deploy: <summary>"

# Tail bounded logs (never open stream)
railway logs --lines 100 --service <svc>

# Set a variable
railway variable set KEY=value --service <svc> --environment production

# Open a shell into a service
railway shell --service <svc>

# Check all service statuses
railway service status --all --json

# Create a bucket
railway bucket create --name <name> --service <svc>

# Get bucket credentials
railway bucket credentials --service <svc> --json
```

## Context Resolution Pattern

Before any mutation, confirm:
```bash
railway status --json   # shows linked project + environment
railway service list --json  # shows services in current env
```

If context is wrong: `railway environment switch <env>` or `railway link --project <id>`.

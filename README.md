# Ptashka

A Trello-like task manager: shared boards → lists → cards, with labels, assignees, checklists,
comments and an activity log. A FastAPI backend (the focus of the project) and a SolidJS frontend
generated against its OpenAPI schema. Built to be used by people *and* by agents: personal API
tokens, a `contributor` role for agents that work on tasks, a cross-board search and a
"what changed since" feed.

## Develop

```bash
docker compose -f docker-compose.dev.yml up -d          # Postgres on :5435

cd backend
uv venv && uv pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/python -m ptashka.cli.create_admin --email you@example.com
.venv/bin/uvicorn ptashka.main:app --reload --port 8020  # API docs: http://localhost:8020/docs

cd frontend
npm install
npm run dev                                              # http://localhost:3020
```

Checks (what CI runs): `pytest` and `pyright` in `backend/`; `npx vitest run`, `npm run check-types` and
`npm run build` in `frontend/`. See `CLAUDE.md` for the full command list and the architecture.

## Run the whole stack in containers

```bash
docker compose up --build -d                             # http://localhost:3021
docker compose exec backend python -m ptashka.cli.create_admin --email you@example.com
docker compose down                                      # add -v to also delete its database
```

Its own Compose project (`ptashka-local`), separate from the development database.

## Deploy (Coolify)

1. New resource → Docker Compose → this repository, compose file `docker-compose.prod.yml`.
2. Environment variables:
   - `POSTGRES_PASSWORD`: a long random string.
   - `JWT_SECRET_KEY`: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
     The backend refuses to start in production without a strong one.
3. Point your domain at the `frontend` service, port 3000. Coolify's proxy handles TLS.
4. Deploy. Migrations run when the backend starts; the deploy is healthy once `/health` reaches the database.
5. Create the first admin from the backend container's terminal:
   `python -m ptashka.cli.create_admin --email you@example.com`

New accounts sign up as *pending* and wait for an admin's approval: admins approve them on the **Admin** page
(`/admin`), where they can also disable accounts and grant or remove admin.

**Backups:** the data lives in the `postgres_data` volume. Dump it regularly, e.g.
`docker compose -f docker-compose.prod.yml exec db pg_dump -U ptashka ptashka > ptashka.sql`
(or use Coolify's scheduled backups).

## Agents

Give each agent its own account, add it to boards as a **contributor** (it can move, complete, tick,
comment and take cards, but not edit or delete them), and create an API token for it, on the
*API tokens* page or with
`python -m ptashka.cli.create_token --email agent@example.com --name "Research agent" --scope write`.
Useful endpoints: `GET /api/cards?assignee=me&completed=false` and `GET /api/activity?since=<id>`.

For MCP clients (Claude Code, Claude Desktop…), `mcp-server/` exposes all of this as tools; see
[mcp-server/README.md](mcp-server/README.md) for the setup.

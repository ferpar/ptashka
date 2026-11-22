# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is this project?

Ptashka is a Trello-like task manager: shared boards → lists → cards, for people and AI agents. Three packages:
`backend/` (FastAPI, the focus, and a learning project), `frontend/` (SolidJS, types generated from the backend's
OpenAPI schema) and `mcp-server/` (MCP tools for agents, over the REST API). Architecture mirrors the sibling
repo `../learno`; when in doubt, follow its conventions. Running, deploying (Coolify) and agent setup: `README.md`.

## Commands

### Backend (from `backend/`)
```bash
uv venv && uv pip install -e ".[dev]"            # Install
.venv/bin/uvicorn ptashka.main:app --reload --port 8020   # API + docs at /docs
.venv/bin/pytest                                  # All tests (in-memory SQLite, fast)
.venv/bin/pytest tests/test_auth.py -k "name"     # Single test
TEST_POSTGRES_URL=postgresql://ptashka:ptashka@localhost:5435/ptashka_test .venv/bin/pytest
                                                  # Whole suite on real Postgres, incl. row-lock tests
                                                  # (needs `docker exec ptashka-db-1 createdb -U ptashka ptashka_test` once)
.venv/bin/alembic check                           # Models and database in sync?
.venv/bin/pyright                                 # Type check (same checker as the IDE)
```
**Every change must pass both `.venv/bin/pytest` and `.venv/bin/pyright` before it's done.** Before committing, run the
checks of *every* package (backend, frontend, mcp-server), not just the one you changed: a new package once broke
the backend's type check in CI through the shared root config. Each package has its own `pyrightconfig.json`
(a parent one would otherwise win over `[tool.pyright]`); the root one is for editors and covers `backend/` only.
Python is pinned to 3.13 (`.python-version` in each Python package, matching the Docker image).
```bash
.venv/bin/alembic upgrade head
.venv/bin/alembic revision --autogenerate --rev-id 000N -m "description"
.venv/bin/python -m ptashka.cli.create_admin --email you@example.com
.venv/bin/python -m ptashka.cli.create_token --email agent@example.com --name "Agent" --scope write
```
### Frontend (from `frontend/`): Solid 1.9 + Vite, TypeScript
```bash
npm install
npm run dev          # Vite on :3020, proxies /api to the backend on :8020
npx vitest run       # Tests (domain, HTTP client, components); `npm test` to watch
npm run check-types  # tsc -b (strict)
npm run build
npm run gen:api      # Regenerate src/api/schema.d.ts from the backend's OpenAPI (after API changes)
```
**Every frontend change must pass `npx vitest run` and `npm run check-types`.** Node >= 22.13 (jsdom 29;
jsdom 31 needs Node 22.22+). Solid 2.0 exists but its Vite plugin/testing library were pre-release when this
was set up; revisit later.

### MCP server (from `mcp-server/`): tools for agents, over the REST API
```bash
uv venv && uv pip install -e ../backend -e ".[dev]"
.venv/bin/pytest     # In-process: MCP Client → tools → httpx ASGITransport → real FastAPI app → SQLite
.venv/bin/pyright    # Uses mcp-server/pyrightconfig.json (a parent pyrightconfig.json would win over pyproject)
PTASHKA_URL=http://localhost:8020 PTASHKA_TOKEN=ptk_... .venv/bin/ptashka-mcp   # stdio
```
Official MCP Python SDK **v2** (`MCPServer`, not v1's `FastMCP`). Only `ToolError` messages reach the model
(other exceptions become "Error executing tool"), so `api.py` turns every API error into an actionable
`ToolError`. Tools return compact views with names resolved (`views.py`); no delete tools by design;
`PTASHKA_READ_ONLY=1` registers read tools only. When adding an activity kind, also update `views.describe`.

### Containers and CI
```bash
docker compose up --build -d          # Full stack (project ptashka-local) on :3021; nginx proxies /api
docker compose -f docker-compose.prod.yml config   # Production (Coolify); needs POSTGRES_PASSWORD, JWT_SECRET_KEY
```
CI (`.github/workflows/ci.yml`): backend (pyright, pytest on SQLite and Postgres, `alembic upgrade head` +
`alembic check`), frontend (types, tests, build), MCP server (types, tests), API contract (`gen:api` must produce no diff: **after
changing any API schema, run `npm run gen:api` and commit the result**), and both Docker images.
`PTASHKA_ENV=production` makes the backend refuse to start with a weak `JWT_SECRET_KEY` (`config.py`).
`/health` checks the database (503 if unreachable); compose healthchecks rely on it.

`DATABASE_URL` defaults to PostgreSQL on localhost:5435 (`docker compose -f docker-compose.dev.yml up -d`).
Ports: backend 8020, Vite 3020, frontend container 3021.

## Architecture (`backend/src/ptashka/`)
- `api/` FastAPI routers (HTTP only: parse, call a service, map exceptions to status codes) →
  `services/` business rules as transaction scripts (no HTTP; raise plain exceptions) → `models/db.py` (SQLAlchemy 2 `Mapped`
  models) and `models/schemas.py` (Pydantic request/response models = the API contract).
- Auth: JWT access tokens (PyJWT, 15 min) + opaque refresh tokens stored as SHA-256 hashes. Registration
  creates `pending` users; an admin approves them via `PATCH /api/admin/users/{id}`. Only `active` users
  can log in. Site roles: `user`, `admin` (`require_admin`). Board permissions are separate (BoardMember).
- Personal API tokens (`ptk_…`, SHA-256 hash stored, shown once) go in the same Bearer header as JWTs;
  `get_auth` returns an `AuthContext(user, token)`. Scope `read` = GET/HEAD/OPTIONS only (our API never
  writes on GET); `write` = whatever the board role allows. Token management and admin endpoints use
  `require_interactive` (password login only), so tokens can't escalate.
- Boards: `Board` → `BoardList` (a column; not `List`, to avoid shadowing Python's `list`) → `Card`.
  `Card.board_id` is denormalized (also reachable via the list) for cheap permission checks and cross-board
  queries. The composite FK `fk_cards_list_board` (list_id, board_id) → lists(id, board_id), ON UPDATE
  CASCADE, makes the database enforce it; assign `card.board_list = target` rather than raw `list_id`.
- Card details: `Label` (per board, unique name, fixed `LabelColor` palette) linked via `CardLabel`;
  `CardAssignee`; `ChecklistItem` (ordered like cards, parent lock = the card); `Comment` (only the author
  edits; author or board owner deletes). Link tables carry `board_id` in composite FKs, so the database
  enforces "label from the same board" and "assignee is a board member" (leaving a board cascades away your
  assignments). Labels/assignees use idempotent `PUT`/`DELETE /api/cards/{id}/labels|assignees/{id}`.
- Card responses: `CardSchema` = row fields + `label_ids`/`assignee_ids` + counts from aggregate queries
  (`card_service.stats_for_board/_card`); build them with `api/presenters.py`. Single-card endpoints return
  `CardDetail` (adds the checklist). Relationships use `passive_deletes=True` so DB cascades do deletes.
- Activity log (`Activity`, `services/activity_service.py`): services call `activity_service.record(db, actor,
  kind, board_id, card, **data)` where the change happens, inside the request's transaction. Service functions
  that change data take `actor: User` as their second parameter. Record only real changes (no-ops and refused
  requests leave no trace); `data` keeps names as they were (titles, list names) so entries survive renames
  and deletes. Read via `GET /api/boards|cards/{id}/activity` (newest first, `?before=` cursor) or
  `GET /api/activity?since=` (oldest first across your boards, for polling; only entries older than
  `activity_service.SETTLE` so late commits aren't skipped; tests set SETTLE to 0).
- Search: `GET /api/cards` (`services/search_service.py`, a query object: `CardFilters` → one WHERE per set
  filter). Always joined to the caller's memberships (that join is the permission check). Link-table filters
  use EXISTS (no duplicate rows); LIKE wildcards in `q` are escaped. Offset pagination with limit+1.
- Done list: at most one `BoardList.is_done` per board (partial unique index). Moving a card into it sets
  `completed_at`, moving out clears it; `PATCH {"completed": …}` still works anywhere.
- Concurrency: operations that read siblings then write positions lock the parent row first
  (`services/locks.py`: the list for cards, the board for lists; one lock per operation, so no deadlocks).
  Cards use optimistic locking (`version`, SQLAlchemy `version_id_col`); PATCH accepts an optional
  `version` and returns 409 with `current_version` on conflict.
- Roles: access is per board via `BoardMember.role`: `viewer` < `contributor` < `editor` < `owner` (`BoardRole.includes()`).
  Viewers are strictly read-only. Contributors work on cards without managing them: move cards,
  `PATCH {completed}`, tick checklist items, comment, assign/unassign only themselves. Editors manage
  content; owners manage the board. **All these rules live in `auth/policy.py`** (pure): field tables per
  resource (`CARD_FIELDS`, `CHECKLIST_ITEM_FIELDS`, `BOARD_FIELDS`; a route admits `policy.lowest(table)`,
  then `check_fields()` refuses the rest) and person-dependent rules (`can_assign`, comment and member
  rules). Routers only turn a "no" into a 403. Change a rule there *and* in the spec tables of
  `tests/test_policy.py`; `tests/test_roles.py` checks the same rules end to end.
  Board-scoped routes declare `Depends(board_access(BoardRole.X))` / `list_access(...)` / `card_access(...)` from
  `auth/board_access.py`: non-members get **404** (no probing), insufficient role gets 403. Site admins get
  no board access. A board always keeps ≥1 owner (`LastOwnerError`).
- **Functional core, imperative shell**: decisions with several cases live in pure functions (no session,
  no clock: pass `now`), unit-tested with explicit, table-driven specs; services stay thin (load → decide →
  save). So far: `services/ordering.py`, `services/card_rules.py` (done-list completion), `auth/policy.py`.
  Write the expected tables by hand in the tests, never derived from the code's own tables.
- Ordering: float `position` with gaps (`services/ordering.py`: pure `position_at`/`spread`, plus `place`). Moves take
  `{after_id}` (null = first) and the server computes the midpoint, renumbering siblings when the gap collapses.
- Archiving (`archived_at`) is the normal way to remove things; archived items keep their position.
- PATCH semantics: absent field = unchanged, `null` = clear (where allowed); use `model_dump(exclude_unset=True)`.
- `GET /api/boards/{id}` returns the whole tree (lists → cards, members) via `board_service.load_board_tree`
  (`selectinload`); `test_board_detail_query_count_does_not_grow_with_board_size` guards against N+1.
- All datetimes use `UTCDateTime` (`models/db.py`): aware UTC in and out, even on SQLite. Never store naive
  datetimes. API datetime inputs use Pydantic `AwareDatetime`.
- Enums are stored as lowercase strings in VARCHAR columns (`_enum()` in `models/db.py`).
- **Unit of work = the request.** Endpoints and dependencies take `db: DbSession` (never `Depends(get_db)`
  directly). `get_db` commits once if the request succeeded and rolls back otherwise, with
  `scope="function"` so the COMMIT happens before the response is sent (a failed commit is a 500, not a
  fake 200). **Services and routers never `commit()`**: they `flush()` (needed before queries, since
  `autoflush=False`). Code that catches a DB error (IntegrityError, StaleDataError) wraps its change in
  `db.begin_nested()` (a savepoint) so only that step rolls back. Scripts/tests use
  `sessionmaker.begin()` as their unit of work. A global handler maps stray `StaleDataError` to 409.
- Tests override `get_db` with the real `unit_of_work` around a shared in-memory SQLite session (foreign keys switched on, so cascades behave
  like Postgres); use the `make_user` factory and `auth_headers()`. `count_queries` records SQL statements;
  call `db_session.expunge_all()` first, since tests share one session across requests. Test suites set
  `BCRYPT_ROUNDS=4` in conftest (real bcrypt, ~1 ms per hash instead of ~170 ms: hashing throwaway users was
  ~90% of the run time); production refuses fewer than 12 rounds. The SQLite engine
  uses SQLAlchemy's pysqlite recipe (driver transaction handling off, explicit BEGIN): without it
  savepoints silently commit. Set `TEST_POSTGRES_URL` to run everything on Postgres instead.
- Migrations are numbered `0001_…`, `0002_…`; every model change needs one. Read autogenerated ones: it can
  order constraint operations wrongly (it has put unique constraints after the composite FKs that need
  them, twice). Check that downgrade → upgrade round-trips, then `alembic check`.

## Architecture (`frontend/src/`)
- Layers, each knowing only those below: `api/` (generated `schema.d.ts`, `dtos.ts` aliases, `HttpClient`
  with timeout + single shared token refresh on 401) → `auth/`, `domain/` (repository interfaces + Http
  implementations + `mappers.ts` DTO→domain) → reactive domain classes → `ui/` components.
- **No store layer.** Domain objects are reactive themselves, using only Solid's reactivity core (no UI):
  `Card` keeps a plain state object in a Solid store *inside* the class (stores can't wrap class instances)
  and exposes getters; `BoardList`/`Board`/`Session` use signals. Components read them directly
  (`props.card.title`). `Board` is the aggregate: optimistic moves with rollback, `version` sent on edits
  (409 → reload card + `ConflictError`). The client predicts, the server decides: business rules (done list
  completes cards...) are never reimplemented; server responses are applied with `applyServer`.
- DI like learno: `container/AppContainer.ts` + `types.ts` are framework-free; `ContainerContext.tsx` is the
  only Solid adapter (`useBoards()`, `useSession()`...; tests can inject a container).
- Drag and drop: Pragmatic drag and drop (`ui/board/dnd.ts`): cards are draggable + drop targets with
  closest-edge; one board-level monitor turns drops into `Board.moveCard`.
- Solid rules: never destructure props; `<For>`/`<Show>` for lists/conditions; derived values as getters.
- UI-only permission hints mirror board roles (`board.canContribute/canEdit/isOwner`); the server enforces.

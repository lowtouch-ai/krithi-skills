# Target architecture (the default plan)

Every migration or modernisation estimate targets this architecture unless the user says otherwise. It is distilled from the Agentomatic platform's `ARCHITECTURE.md`. Section numbers like (§4) point to that document. Technology names belong in the PRDs' **Target architecture** and **Target design** sections and the foundation stories; the plain-English rules for the PRD text still apply everywhere else.

## 1. The default stack

| Layer | Target | Use it for |
|---|---|---|
| Backend and APIs | **FastAPI** (Python) | All business logic, REST endpoints, validation, authorization. One FastAPI app per business domain; related domains may be mounted as sub-apps of one gateway (§2). |
| Database | **PostgreSQL** | All relational data. One database and one database user per application, never a shared schema or role (§2, §7). |
| Cache and fast state | **Redis** | Caching, sessions and one-time codes, rate or retry counters, pub/sub for live progress, the Celery broker for Airflow. Partition by purpose (separate logical databases and channels), never one shared keyspace (§7, §10). |
| User interface | **Next.js** | Every screen. It is also the only public entry point to the backend (see multi-tenancy below). |
| Scheduled, long-running and batch work | **Airflow** (CeleryExecutor on Redis and Postgres) | Anything that runs on a timer, reacts to an external event, has several dependent steps, runs long, or must outlive the request (§4). |
| Secrets | **HashiCorp Vault** | Every credential and connection secret, authenticated by AppRole at boot. No standing credentials in code, images or config (§6). |
| Files | **MinIO** (object storage) | Only when the application stores files: uploads, generated documents, exports. One bucket and one credential pair per application (§2, §7). |

Vault is a default for any application that has secrets (almost all). MinIO is a default only when the legacy code handles files. Neither is optional once the application needs it.

## 2. Mapping the legacy system onto the target

Use this when writing the Target architecture table in the high-level PRD and the Target design section of each detailed PRD. A row per legacy component, with a deviation if it cannot follow the rule.

| Legacy thing | Target |
|---|---|
| Server-rendered pages, desktop or thick-client screens, any web front end | Next.js screens |
| Controllers, services, business rules, validation, authorization | FastAPI endpoints and service layer |
| Relational database (any vendor), stored procedures with business logic | PostgreSQL schema; stored-procedure logic moves into FastAPI services unless it is data-heavy set processing |
| Session store, in-memory or memcached cache, OTP or retry counters, ad-hoc pub/sub | Redis |
| Cron, Quartz, `@Scheduled`, Windows tasks, batch programs, Celery or other workers, report and export jobs, file-drop pollers, queue consumers | Airflow DAGs (see section 3) |
| File storage on disk, S3, blob stores, upload handling | MinIO buckets (one per application) |
| Config files, environment variables holding secrets, key stores | Vault paths; non-secret settings in Airflow Variables for DAGs |
| Message brokers used only to run background work | Airflow plus Redis; keep a broker only if other systems consume its messages (a deviation) |
| Identity (LDAP, SAML, OIDC, Keycloak) | Keep the external identity provider; the integration moves into FastAPI and Next.js |
| Partner APIs, payment, email, SMS, SOAP and similar | Integration clients in FastAPI (or DAG tasks when batch or event-driven) |

Anything that does not fit (a non-relational store with no Postgres equivalent, a protocol Airflow cannot drive) is recorded as an **Architecture deviation** with the reason, never silently replaced.

## 3. DAG or direct API (§4)

- **Direct FastAPI call** when the caller needs the answer before it can continue and the work finishes well under a second with no real chance of retry or branching. This is the default.
- **Airflow DAG** when the work is started by an external event or a timer, has several dependent steps with branching or retry, runs long enough that nobody should wait on an open connection, or must keep running if the request ends. Bulk processing (loading a large volume of context before one step) is a DAG even when a user triggers it.
- A request that starts a DAG hands over a request ID; the DAG reports progress back over a Redis channel keyed by that ID so the caller sees live status without polling (§4, Live progress).

Airflow conventions to build into DAG stories (§4):
- DAG source lives in its own repository, synced onto the DAGs volume by a git runner; editing a DAG is a git change, not a rebuild.
- One folder per application or agent; no DAG file at the repo root.
- Settings come from Airflow Variables named `<namespace>.<system>.<setting>`, not environment variables.
- Every DAG file has the same shape: imports, logging, constants, helpers, task callables, then the DAG block.
- Datetimes are always timezone-aware.
- A small shared `utils/` module for common integrations and the progress-logging bridge; small helpers may be duplicated rather than shared.
- Event-driven work is a pair: a short, frequently scheduled **listener** DAG classifies what arrived, then triggers an unscheduled **responder** DAG with context in `conf`.
- Delivery: CeleryExecutor (scheduler enqueues, workers execute) with a task-monitoring UI.

## 4. Data and tenancy (§2, §5, §7)

- One database and one database user per application; the user's password is generated and kept in Vault under that application's own key.
- **Multi-tenant applications only** (the code carries a tenant or customer id on its tables or resolves one per request): add a `tenant_id` to every domain table, resolve it from a trusted request header cached briefly in Redis, take a Postgres advisory lock scoped to the tenant for writes to shared tenant state, and prefix object keys with `{tenant_id}/`. The backend must be reachable only through the Next.js proxy that sets the header; if it is ever exposed directly the header can be spoofed. Single-tenant applications do not get this work.
- Redis is partitioned by use: one logical database for the Celery broker, one for events, separate pub/sub channels, and a separate keyspace for one-time codes with retry and lockout counters.

## 5. Cross-cutting rules (§6, §10)

- Every request gets a request ID that appears on every log line across FastAPI, DAGs and any other service. Sensitive header and secret values are masked before logging.
- No standing credentials: each service authenticates to Vault with AppRole at start-up; per-user secrets live under a per-user path gated by an allow-list of keys.
- Cached per-user state is invalidated when credentials change, not on a timer.
- Writes that must be auditable are exported to an audit trail alongside the primary write.
- Container images pin a vulnerability scanner as part of the build surface.

## 6. UI design system (Next.js, §9)

Every UI follows the platform design system. The CRM is its reference implementation; copy its `tailwind.config.ts` verbatim for a new product, and read `docs/app_layout.md` and `docs/app_branding.md` in the `lowtouch-ai/crm` repository before building.

- **Shell:** fixed icon sidebar (desktop-first, no hamburger), sticky top bar holding page title, actions and account controls, a breadcrumb on every page.
- **Overlays:** editing an existing record is a right-side drawer; creating a record and short confirmations are a centered modal; a full-screen overlay is rare. Every drawer has a header close control and a separate footer Cancel.
- **Lists:** one shared search-toolbar shape; Kanban for pipeline data, paginated table for record data; record detail opens in a drawer, not a new route.
- **Forms:** one shared input style and focus ring; one shared date component; durations as hours plus minutes.
- **Tokens:** every colour comes from a named token with a light and a dark value; no raw hex in components. The palette has no red, so the primary accent doubles as the error colour.
- **Accessibility is a hard minimum:** WCAG 2.1 AA, so 4.5:1 for normal text, 3:1 for large text and for borders and focus rings. The two brightest colours (the success green and the primary accent) must be contrast-checked before use as text; a token-correct choice can still fail. Only the theme crossfade respects reduced motion today, so close that gap before reusing the motion set.

Every UI story gets an acceptance criterion for this: design-system tokens used, WCAG 2.1 AA met, keyboard operable. Use `wave-a11y-scan` on the result.

## 7. When the application has AI agents: our AI stack

Applies when the inventory reports AI agent signals (LLM SDKs, LangChain, LangGraph, agent frameworks, vector databases) or the code clearly contains agents, tools or retrieval. Open WebUI is **not** used: the Next.js UI is the front end and talks to the agent engine's API.

| Legacy AI thing | Target |
|---|---|
| Agent loop, orchestration, prompt and tool wiring (LangChain, custom loops, assistants APIs) | **agentomatic**: a FastAPI ReAct engine built on LangGraph, with Ollama-compatible `/api/chat`; each agent is a YAML configuration binding its tools and DAGs |
| Calls to hosted LLMs or local models, embeddings | Model access through agentomatic; **Ollama** (internal-only) for local models and embeddings |
| Vector database, RAG pipeline (Pinecone, Chroma, FAISS, pgvector, ad-hoc embeddings) | **agentvector**: FastAPI with pgvector in Postgres, hybrid search and reranking |
| Business actions the agent calls (CRM, orders, HR, reports) | **agentconnector**: FastAPI sub-apps, one per business domain, each with its own database, user and bucket |
| Long or scheduled agent work (report generation, batch enrichment, anything staged from an upload) | Airflow DAGs exposed to the agent as `run_<dag_id>` and `check_<dag_id>_status` tools |
| Live "thinking" or progress shown to the user | Redis pub/sub channel per request, streamed to the UI as thought-log lines before the final answer |
| API keys and per-user credentials for tools | Vault: per-user paths, passed as headers and resolved at call time, never stored with the agent |

Foundation stories for an AI application add: agent YAML configuration and engine setup, vector store schema and ingestion, one connector sub-app per business domain, DAG-as-tool binding, the thought-streaming channel, and Vault credential resolution. Cached agent executors are keyed by session and model and rebuilt when credentials change.

If there are no AI agents, none of this applies; do not add AI stack stories.

## 8. Foundation work every estimate includes

Put these in a cross-cutting detailed PRD (for example "Platform foundation"), as stories, in addition to the feature PRDs:
1. FastAPI project scaffold, base configuration, error handling, request-ID logging and CI pipeline with an automated test harness.
2. Next.js project scaffold with the design-system tokens, app shell, authentication and role handling, and CI.
3. PostgreSQL: the application's database and user, schema and versioned migrations, connection handling.
4. Redis: logical databases and key conventions for what the application uses.
5. Airflow: DAG repository layout, Variables convention and sync, when the application has any background work.
6. Vault: AppRole bootstrap and secret paths for the application.
7. MinIO bucket and credentials, when the application stores files.
8. Multi-tenancy plumbing, when the application is multi-tenant.
9. The AI stack setup in section 7, when the application has AI agents.

Data migration, QA sign-off and production deployment stay outside the estimate as before.

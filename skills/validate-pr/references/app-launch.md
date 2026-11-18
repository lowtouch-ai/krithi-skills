# Building and launching the application

Goal: the PR's code running locally, reachable at a URL, with its logs captured; or a precise, evidenced blocker.

## 1. Choose the commands

Order of preference:
1. What the repository documents for local development: `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `docs/development-guide.md`, `Makefile` targets (`inspect_repo.py` → `documented_commands`).
2. The Playwright config's `webServer.command` (`launch_candidates[0]` when present): the team's own way to start the app for e2e.
3. The rest of `launch_candidates` and `setup_commands` from the detected stack.

Prefer a production-like start (`build` then `start`/`preview`) when it is documented and finishes in time; a dev server is fine when it is the documented way. Record the choice and its source in the report.

| Stack | Setup | Launch (typical) | Ready URL |
|---|---|---|---|
| Node (Next.js, Vite, CRA, Express, Nest...) | `npm ci` / `pnpm install --frozen-lockfile` / `yarn install --frozen-lockfile`, then `build` | `npm run start`, `npm run preview`, `npm run dev` | port from the script, else framework default |
| Python Django | `pip install -r requirements.txt`, `manage.py migrate` | `manage.py runserver 127.0.0.1:8000 --noreload` | `/` or a known page |
| Python FastAPI / Flask | `pip install ...` | `uvicorn mod:app --port 8000` / `flask --app mod run` | `/docs` (FastAPI) or `/` |
| Java Spring Boot | `./mvnw -DskipTests package` | `./mvnw spring-boot:run` / `./gradlew bootRun` | `/actuator/health` if present, else `/` |
| .NET | `dotnet restore` | `dotnet run --project <web>.csproj --urls http://127.0.0.1:5000` | `/` |
| Ruby on Rails | `bundle install`, `bin/rails db:prepare` | `bin/rails server -p 3000` | `/` |
| PHP Laravel | `composer install`, `.env` + `php artisan key:generate` | `php artisan serve` | `/` |
| Docker Compose | — | `docker compose up --build` (as the app command) | the published port |
| Static site | — | `python3 -m http.server 8080` in the site folder | `/` |

Python setups install into a virtual environment inside the worktree (`python3 -m venv .venv && .venv/bin/pip install ...`), never into the user's global Python.

## 2. Configuration and services

- Create a local env file only from the repository's example file (`.env.example` → `.env` in the worktree) with safe local values: a generated secret key, `localhost` URLs, test-only settings. Never use, copy or print real credentials, and never commit the file (commit_tests.py refuses `.env*`).
- A required value that cannot be safely invented (third-party API key, SSO client secret, licence) is a **blocker**, unless the feature under test does not reach it: then launch without it and mark the affected cases Blocked.
- Databases and caches: use what the repository provides (compose file, SQLite default in dev settings, an embedded/in-memory option). Start a container only when docker is available and the repository's compose file defines it. Seeds and migrations run as `app_runner.py step`.
- Credentials the *tests* need (`E2E_USER`...) come from the reviewer's environment. Missing ones make those tests skip with a reason; those cases are Blocked, not passed.

## 3. Run it

```bash
python3 <skill-dir>/scripts/app_runner.py step  --run <run> --cwd <wt> --name install -- npm ci
python3 <skill-dir>/scripts/app_runner.py step  --run <run> --cwd <wt> --name build   -- npm run build
python3 <skill-dir>/scripts/app_runner.py start --run <run> --cwd <wt> --name web --url http://127.0.0.1:3000 -- npm run start
```

- Timeouts: 15 minutes per setup step by default, 3 minutes for the app to answer (raise `--timeout` for JVM or large builds and say so).
- Ready means an HTTP answer below 500 at the URL; use a page that needs no login when there is one.
- Use a free port. If the default port is taken (`start` refuses), pick another (`PORT=3100`, `--port 3100`) rather than stopping someone else's process.
- Install lifecycle scripts run code from the PR. For a fork PR from an unknown author, read `package.json` scripts (`preinstall`, `postinstall`, `prepare`) and Python `setup.py` before installing; if they reach the network beyond the package registry or touch files outside the worktree, do not run them and record a blocker.

## 4. When it does not start

Try the obvious, evidence-based fixes once: a missing documented setup step, a port, a missing example env file. Do not change application code or configuration files tracked by git to make it start.

Then stop and record a **Blocked** validation. The blocker must say:
- the exact command, its exit code or the timeout, and the log tail (`metadata.json app.blocker`, `logs/app-<name>.log`, `logs/setup-<step>.log`);
- the cause class: missing configuration, missing credentials, missing service, dependency install failure, build failure, port conflict, unsupported platform;
- what would unblock it (a variable to set, a service to start, a command the README should document).

A build failure caused by the PR itself (it does not compile) is still Blocked for validation purposes, and it is also an **application defect** (Critical): record it with `defects.py` with the build log as evidence.

## 5. Cleanup (always)

Run even after failures and interruptions:

```bash
python3 <skill-dir>/scripts/app_runner.py stop-all --run <run>
docker compose -f <compose> down -v          # only if this run started it
git -C <repo> worktree remove --force <wt>   # after commit/push decisions are done
```

Check nothing is still listening on the port. Record cleanup in the report.

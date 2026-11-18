#!/usr/bin/env python3
"""Inspect a checked-out application (the PR worktree) and report, as JSON, how to build and launch it and where
Playwright tests and test plans belong. Read-only; works for any stack, and says so when it recognises none.

  stacks              detected technologies, with the file that shows each
  setup_commands      install/build steps in order, with their source
  launch_candidates   ways to start the app, best first: {cmd, cwd, url, port, source, needs}
  requirements        env vars named in .env.example-style files and services (database, redis, docker) the app expects
  playwright          runner (node | python | none), config files, testDir, existing specs, fixtures/helpers, page objects,
                      axe availability, and the PROPOSED layout when the repository has no convention
  test_plans          existing test-plan folders, or the proposed one (docs/test-plans/)
  routes_for_changes  UI routes the changed files most likely affect (file-system routers only)

Usage:
  inspect_repo.py --repo-dir <worktree> [--changed-files a.tsx b.py ...] [--out FILE]

The candidates are evidence, not decisions: SKILL.md step 3 prefers commands the repository documents (README,
AGENTS.md, CONTRIBUTING, playwright.config webServer) and records which one was used.
"""
import argparse, json, re, sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", "target", ".tox", "vendor",
             "coverage", "playwright-report", "test-results", ".pytest_cache", ".mypy_cache", "out", "bin", "obj"}
SPEC_RE = re.compile(r"\.(spec|test|e2e)\.(t|j)sx?$|\.e2e\.(t|j)s$")
PY_E2E_RE = re.compile(r"(^|/)test_[^/]*\.py$")
NODE_FRAMEWORKS = [  # (dependency, name, default port, dev script hint)
    ("next", "Next.js", 3000), ("nuxt", "Nuxt", 3000), ("@remix-run/dev", "Remix", 3000), ("@sveltejs/kit", "SvelteKit", 5173),
    ("astro", "Astro", 4321), ("@angular/core", "Angular", 4200), ("react-scripts", "Create React App", 3000),
    ("vite", "Vite", 5173), ("gatsby", "Gatsby", 8000), ("@nestjs/core", "NestJS", 3000), ("express", "Express", 3000),
    ("fastify", "Fastify", 3000), ("koa", "Koa", 3000), ("hono", "Hono", 3000)]
SERVICE_HINTS = [("postgres", r"postgres(ql)?://|\bpostgres\b|psycopg|\bpg\b\"?:"), ("mysql", r"mysql://|\bmysql2?\b"),
                 ("mongodb", r"mongodb(\+srv)?://|\bmongoose\b"), ("redis", r"redis://|\bioredis\b|\bredis\b"),
                 ("rabbitmq", r"amqp://"), ("kafka", r"\bkafka\b")]


def files(root, limit=20000):
    outl = []
    for p in root.rglob("*"):
        if len(outl) >= limit:
            break
        parts = p.relative_to(root).parts
        if any(x in SKIP_DIRS for x in parts[:-1]) or (p.is_dir()):
            continue
        outl.append(p.relative_to(root).as_posix())
    return sorted(outl)


def read(root, path, limit=300_000):
    try:
        return (root / path).read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def pkg_json(root, path="package.json"):
    try:
        return json.loads(read(root, path)) if (root / path).is_file() else None
    except ValueError:
        return None


def deps_of(pkg):
    d = {}
    for k in ("dependencies", "devDependencies", "peerDependencies"):
        d.update((pkg or {}).get(k) or {})
    return d


def node_pm(root, base="."):
    b = root / base
    return "pnpm" if (b / "pnpm-lock.yaml").is_file() else "yarn" if (b / "yarn.lock").is_file() else \
        "bun" if (b / "bun.lockb").is_file() or (b / "bun.lock").is_file() else "npm"


def port_from(text, default):
    for pat in (r"--port[ =](\d{2,5})", r"-p (\d{2,5})\b", r"PORT=(\d{2,5})", r"localhost:(\d{2,5})", r"127\.0\.0\.1:(\d{2,5})",
                r"\.listen\(\s*(\d{2,5})", r"process\.env\.PORT\s*\|\|\s*(\d{2,5})", r"port\s*[:=]\s*(\d{2,5})"):
        m = re.search(pat, text or "")
        if m:
            return int(m.group(1))
    return default


def env_keys(root, all_files):
    keys, srcs = [], []
    for f in all_files:
        name = f.rsplit("/", 1)[-1]
        if re.fullmatch(r"\.env\.(example|sample|template|dist|defaults?)|example\.env|\.env\.local\.example|env\.example", name):
            srcs.append(f)
            for ln in read(root, f).splitlines():
                m = re.match(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]+)\s*=\s*(.*)$", ln)
                if m:
                    keys.append({"name": m.group(1), "has_example_value": bool(m.group(2).strip().strip("\"'")), "file": f})
    return srcs, keys


def playwright_config_info(root, path):
    t = read(root, path)
    info = {"path": path, "testDir": None, "baseURL": None, "webServer": None, "projects": re.findall(r"name:\s*['\"]([\w -]+)['\"]", t)[:10]}
    if m := re.search(r"testDir\s*:\s*['\"]([^'\"]+)['\"]", t):
        info["testDir"] = str((Path(path).parent / m.group(1)).as_posix()).lstrip("./") or "."
    if m := re.search(r"baseURL\s*:\s*([^,\n]+)", t):
        info["baseURL"] = m.group(1).strip()
    if "webServer" in t:
        ws = t[t.index("webServer"):][:800]
        cmd = re.search(r"command\s*:\s*['\"`]([^'\"`]+)['\"`]", ws)
        url = re.search(r"url\s*:\s*['\"`]([^'\"`]+)['\"`]", ws)
        port = re.search(r"port\s*:\s*(\d{2,5})", ws)
        info["webServer"] = {"command": cmd.group(1) if cmd else None, "url": url.group(1) if url else None,
                             "port": int(port.group(1)) if port else None}
    return info


def detect(root, changed):
    all_files = files(root)
    fset = set(all_files)
    stacks, setup, launch, notes = [], [], [], []

    def cand(cmd, url, source, cwd=".", needs=None, port=None):
        launch.append({"cmd": cmd, "cwd": cwd, "url": url, "port": port, "source": source, "needs": needs or []})

    # Monorepos: the app under test is the package folder holding most of the changed files
    pkg_dirs = sorted({str(Path(f).parent.as_posix()) for f in all_files if f.rsplit("/", 1)[-1] in
                       ("package.json", "pyproject.toml", "requirements.txt", "manage.py", "pom.xml", "build.gradle", "go.mod", "Gemfile")
                       and f.count("/") <= 2})
    score = {p: sum(1 for c in changed or [] if p == "." or c.startswith(p + "/")) for p in pkg_dirs}
    app_root = max(pkg_dirs, key=lambda p: (score[p] if p != "." else score[p] - 0.5, -p.count("/")), default=".") if changed else \
        ("." if "." in pkg_dirs or not pkg_dirs else pkg_dirs[0])
    prefix = "" if app_root == "." else app_root + "/"
    docs = "\n".join(read(root, f, 60_000) for f in dict.fromkeys(
        [f"{prefix}{n}" for n in ("README.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "docs/development-guide.md")] +
        ["README.md", "AGENTS.md", "CONTRIBUTING.md"]) if f in fset)

    # ---- Node (root and one level of workspaces) ----
    pkg_paths = [p for p in all_files if p.endswith("package.json") and p.count("/") <= 2]
    for pp in pkg_paths:
        pkg = pkg_json(root, pp)
        if not pkg:
            continue
        base = str(Path(pp).parent.as_posix())
        deps, scripts = deps_of(pkg), pkg.get("scripts") or {}
        fw = next(((n, port) for dep, n, port in NODE_FRAMEWORKS if dep in deps), None)
        pm = node_pm(root, base)
        run_ = (lambda s: f"{pm} run {s}") if pm != "npm" else (lambda s: f"npm run {s}")
        stacks.append({"stack": "node", "framework": fw[0] if fw else None, "package": pp, "package_manager": pm})
        if base == "." or fw:
            lock = (root / base / "package-lock.json").is_file()
            setup.append({"phase": "install", "cmd": {"npm": "npm ci" if lock else "npm install", "yarn": "yarn install --frozen-lockfile",
                                                        "pnpm": "pnpm install --frozen-lockfile", "bun": "bun install"}[pm],
                          "cwd": base, "source": pp})
            if "build" in scripts:
                setup.append({"phase": "build", "cmd": run_("build"), "cwd": base, "source": f"{pp} scripts.build"})
            port = fw[1] if fw else 3000
            for s in ("start", "preview", "dev", "serve"):
                if s in scripts:
                    p = port_from(scripts[s], port)
                    needs = ["build first"] if s in ("start", "preview") and "build" in scripts else []
                    cand(run_(s), f"http://127.0.0.1:{p}", f"{pp} scripts.{s}: {scripts[s]}", base, needs, p)
            main = pkg.get("main") or ("server.js" if (root / base / "server.js").is_file() else None)
            if main and not any(s in scripts for s in ("start", "dev")) and (root / base / main).is_file():
                p = port_from(read(root, f"{base}/{main}"), 3000)
                cand(f"node {main}", f"http://127.0.0.1:{p}", f"{pp} main", base, [], p)

    # ---- Python ----
    pyfiles = [f for f in all_files if f.endswith(".py")]
    reqs = read(root, "requirements.txt") + read(root, "pyproject.toml") + read(root, "Pipfile") + read(root, "setup.py")
    if pyfiles or reqs:
        fw = None
        if "manage.py" in fset or re.search(r"\bdjango\b", reqs, re.I):
            fw = "Django"
            mp = next((f for f in all_files if f.endswith("manage.py")), "manage.py")
            cand(f"python3 {mp} runserver 127.0.0.1:8000 --noreload", "http://127.0.0.1:8000", mp, ".", ["database migrations: python3 manage.py migrate"], 8000)
        app_file = None
        for f in pyfiles[:400]:
            t = read(root, f, 40_000)
            if m := re.search(r"^(\w+)\s*=\s*FastAPI\(", t, re.M):
                fw = fw or "FastAPI"; app_file = (f, m.group(1)); break
            if m := re.search(r"^(\w+)\s*=\s*Flask\(", t, re.M):
                fw = fw or "Flask"; app_file = (f, m.group(1)); break
        if app_file:
            mod = app_file[0][:-3].replace("/", ".")
            if fw == "FastAPI":
                cand(f"python3 -m uvicorn {mod}:{app_file[1]} --host 127.0.0.1 --port 8000", "http://127.0.0.1:8000", app_file[0], ".", [], 8000)
            else:
                cand(f"python3 -m flask --app {mod}:{app_file[1]} run --host 127.0.0.1 --port 5000", "http://127.0.0.1:5000", app_file[0], ".", [], 5000)
        if re.search(r"\bstreamlit\b", reqs):
            entry = next((f for f in pyfiles if "streamlit" in read(root, f, 20_000)), None)
            if entry:
                fw = fw or "Streamlit"
                cand(f"python3 -m streamlit run {entry} --server.port 8501 --server.headless true", "http://127.0.0.1:8501", entry, ".", [], 8501)
        if fw or reqs:
            stacks.append({"stack": "python", "framework": fw, "package": next((f for f in ("pyproject.toml", "requirements.txt", "Pipfile", "setup.py") if f in fset), None)})
            if "requirements.txt" in fset:
                setup.append({"phase": "install", "cmd": "python3 -m pip install -r requirements.txt", "cwd": ".", "source": "requirements.txt"})
            elif "pyproject.toml" in fset or "setup.py" in fset:
                setup.append({"phase": "install", "cmd": "python3 -m pip install -e .", "cwd": ".", "source": "pyproject.toml/setup.py"})

    # ---- JVM, .NET, Go, Ruby, PHP ----
    if "pom.xml" in fset:
        spring = "spring-boot" in read(root, "pom.xml")
        stacks.append({"stack": "java", "framework": "Spring Boot" if spring else None, "package": "pom.xml"})
        mvn = "./mvnw" if "mvnw" in fset else "mvn"
        setup.append({"phase": "build", "cmd": f"{mvn} -B -DskipTests package", "cwd": ".", "source": "pom.xml"})
        if spring:
            cand(f"{mvn} spring-boot:run", "http://127.0.0.1:8080", "pom.xml spring-boot", ".", [], 8080)
    if fset & {"build.gradle", "build.gradle.kts"}:
        g = "./gradlew" if "gradlew" in fset else "gradle"
        bg = read(root, "build.gradle") + read(root, "build.gradle.kts")
        stacks.append({"stack": "java", "framework": "Spring Boot" if "spring" in bg else None, "package": "build.gradle"})
        cand(f"{g} bootRun" if "spring" in bg else f"{g} run", "http://127.0.0.1:8080", "build.gradle", ".", [], 8080)
    csproj = [f for f in all_files if f.endswith(".csproj")]
    if csproj:
        web = next((f for f in csproj if "Microsoft.NET.Sdk.Web" in read(root, f)), None)
        stacks.append({"stack": "dotnet", "framework": "ASP.NET Core" if web else None, "package": csproj[0]})
        if web:
            cand(f"dotnet run --project {web} --urls http://127.0.0.1:5000", "http://127.0.0.1:5000", web, ".", [], 5000)
    if "go.mod" in fset:
        stacks.append({"stack": "go", "framework": None, "package": "go.mod"})
        mainf = next((f for f in all_files if f.endswith("main.go") and "ListenAndServe" in read(root, f)), None)
        if mainf:
            p = port_from(read(root, mainf), 8080)
            cand(f"go run ./{Path(mainf).parent.as_posix()}".replace("/.", ""), f"http://127.0.0.1:{p}", mainf, ".", [], p)
    if "Gemfile" in fset:
        rails = "rails" in read(root, "Gemfile")
        stacks.append({"stack": "ruby", "framework": "Rails" if rails else None, "package": "Gemfile"})
        setup.append({"phase": "install", "cmd": "bundle install", "cwd": ".", "source": "Gemfile"})
        if rails:
            cand("bin/rails server -b 127.0.0.1 -p 3000", "http://127.0.0.1:3000", "Gemfile rails", ".", ["database: bin/rails db:prepare"], 3000)
    if "artisan" in fset:
        stacks.append({"stack": "php", "framework": "Laravel", "package": "composer.json"})
        cand("php artisan serve --host 127.0.0.1 --port 8000", "http://127.0.0.1:8000", "artisan", ".", [".env with APP_KEY"], 8000)

    # ---- Containers and static sites ----
    compose = next((f for f in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml") if f in fset), None)
    if compose:
        ct = read(root, compose)
        p = int(m.group(1)) if (m := re.search(r"['\"]?(\d{2,5}):\d{2,5}['\"]?", ct)) else 8080
        cand(f"docker compose -f {compose} up --build", f"http://127.0.0.1:{p}", compose, ".", ["docker"], p)
    if not stacks and not launch:
        idx = next((f for f in all_files if f.endswith("index.html") and f.count("/") <= 2), None)
        if idx:
            d = Path(idx).parent.as_posix()
            stacks.append({"stack": "static", "framework": None, "package": idx})
            cand("python3 -m http.server 8080 --bind 127.0.0.1", "http://127.0.0.1:8080", idx, d, [], 8080)

    # ---- Playwright ----
    pw_configs = [f for f in all_files if re.search(r"(^|/)playwright\.config\.(ts|js|mjs|cjs|mts|cts)$", f)]
    cfgs = [playwright_config_info(root, f) for f in pw_configs]
    for c in cfgs:
        if c["webServer"] and c["webServer"].get("command"):
            ws = c["webServer"]
            url = ws.get("url") or (f"http://127.0.0.1:{ws['port']}" if ws.get("port") else None)
            launch.insert(0, {"cmd": ws["command"], "cwd": str(Path(c["path"]).parent.as_posix()), "url": url, "port": ws.get("port"),
                              "source": f"{c['path']} webServer (the repository's own declared way to start the app for e2e)", "needs": []})
    root_pkg = pkg_json(root) or {}
    all_deps = {}
    for pp in pkg_paths:
        all_deps.update(deps_of(pkg_json(root, pp)))
    py_pw = bool(re.search(r"pytest-playwright|\bplaywright\b", reqs + read(root, "requirements-dev.txt") + read(root, "requirements-test.txt")))
    specs = [f for f in all_files if SPEC_RE.search(f) and (re.search(r"(^|/)(e2e|playwright|tests?/e2e|integration)(/|$)", f) or
                                                             "@playwright/test" in read(root, f, 4000))]
    py_specs = [f for f in all_files if PY_E2E_RE.search(f) and re.search(r"\bpage\b.*(Page|playwright)|from playwright", read(root, f, 6000))]
    test_dirs = sorted({c["testDir"] for c in cfgs if c["testDir"]} | {str(Path(s).parent.as_posix()) for s in specs + py_specs})
    helpers = [f for f in all_files if any(f.startswith(td + "/") for td in test_dirs) and not SPEC_RE.search(f) and f.endswith((".ts", ".js", ".py"))
               and re.search(r"test\.extend|@pytest\.fixture|export (class|function|const)|class \w+Page", read(root, f, 20_000))]
    runner = "node" if ("@playwright/test" in all_deps or pw_configs or specs) else "python" if (py_pw or py_specs) else "none"
    proposed = None
    if runner == "none":
        if any(s["stack"] == "node" for s in stacks):
            proposed = {"runner": "node", "config": f"{prefix}playwright.config.ts", "testDir": f"{prefix}tests/e2e", "fixtures": f"{prefix}tests/e2e/fixtures",
                        "add_dev_dependencies": ["@playwright/test"], "why": f"Node project without Playwright: use @playwright/test in the app folder ({app_root})"}
        elif any(s["stack"] == "python" for s in stacks):
            proposed = {"runner": "python", "config": "pytest.ini or [tool.pytest.ini_options] (only if needed)", "testDir": f"{prefix}tests/e2e",
                        "fixtures": f"{prefix}tests/e2e/conftest.py", "add_dev_dependencies": ["pytest-playwright"],
                        "why": "Python project: pytest-playwright fits the existing test runner"}
        else:
            proposed = {"runner": "node", "config": "e2e/playwright.config.ts", "testDir": "e2e/tests", "fixtures": "e2e/fixtures",
                        "add_dev_dependencies": ["@playwright/test (in e2e/package.json)"],
                        "why": "no Node or Python toolchain: a self-contained e2e/ folder keeps Playwright out of the app's build"}
    test_plan_dirs = sorted({str(Path(f).parent.as_posix()) for f in all_files if re.search(r"(^|/)(test-?plans?|testing|qa)/[^/]+\.md$", f, re.I)})
    playwright = {
        "runner": runner, "configs": cfgs, "test_dirs": test_dirs, "existing_specs": (specs + py_specs)[:200],
        "helpers_and_fixtures": helpers[:100],
        "page_objects": [f for f in helpers if re.search(r"(^|/)pages?/|\.page\.(t|j)s$|Page\.(t|j)s$", f)][:50],
        "playwright_version": all_deps.get("@playwright/test"), "python_playwright": py_pw,
        "axe": "@axe-core/playwright" in all_deps or "axe-playwright-python" in reqs,
        "package_manager": node_pm(root) if root_pkg else None, "proposed_layout": proposed,
    }

    # ---- Requirements (env, services) ----
    env_files, keys = env_keys(root, all_files)
    blob = docs + read(root, compose or "") + "\n".join(read(root, f, 20_000) for f in (env_files + ["package.json", "requirements.txt", "pyproject.toml"]) if f in fset)
    services = [name for name, pat in SERVICE_HINTS if re.search(pat, blob, re.I)]
    if any("docker" in c["needs"] for c in launch):
        services.append("docker")

    # ---- Routes the change likely affects (file-system routers) ----
    routes = []
    for f in changed or []:
        m = re.search(r"(?:^|/)(?:src/)?app/(.*?)/?(?:page|layout)\.(t|j)sx?$", f) or re.search(r"(?:^|/)(?:src/)?pages/(.*?)\.(t|j)sx?$|(?:^|/)src/routes/(.*?)/?\+page\.svelte$", f)
        if m:
            seg = next((g for g in m.groups() if g is not None and not re.fullmatch(r"[tj]", g)), "")
            seg = re.sub(r"\([^)]*\)/?", "", seg)  # Next.js route groups
            seg = re.sub(r"(^|/)index$", "", seg)
            if not seg.startswith(("api", "_")):
                routes.append({"file": f, "route": "/" + seg.strip("/")})

    in_app = lambda c: 0 if c.get("cwd", ".") == app_root else 1
    launch.sort(key=lambda c: (0 if "webServer" in c["source"] else 1, in_app(c)))
    setup.sort(key=in_app)
    if not launch:
        notes.append("No launch command recognised. Read README/AGENTS.md/Dockerfile; if nothing documents how to start the app, "
                     "record a Blocked validation with this finding rather than guessing.")
    return {
        "repo_dir": str(root), "app_root": app_root, "app_roots_by_changed_files": score, "stacks": stacks, "setup_commands": setup, "launch_candidates": launch,
        "documented_commands": sorted(set(re.findall(r"^\s*(?:\$\s*)?((?:npm|pnpm|yarn|bun|npx|python3?|uvicorn|flask|docker compose|docker-compose|make|go|dotnet|mvn|\./mvnw|gradle|\./gradlew|bin/rails|php artisan)\b[^\n`]{0,120})", docs, re.M)))[:40],
        "requirements": {"env_files": env_files, "env_keys": keys[:100], "services": sorted(set(services))},
        "playwright": playwright,
        "test_plans": {"existing_dirs": test_plan_dirs, "proposed_dir": test_plan_dirs[0] if test_plan_dirs else (f"{prefix}docs/test-plans" if (root / prefix / "docs").is_dir() and prefix else "docs/test-plans")},
        "routes_for_changes": routes, "notes": notes,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-dir", required=True)
    ap.add_argument("--changed-files", nargs="*", default=[])
    ap.add_argument("--out")
    a = ap.parse_args()
    root = Path(a.repo_dir).expanduser().resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"no such directory: {root}"}))
        return 2
    res = detect(root, a.changed_files)
    text = json.dumps(res, indent=2)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

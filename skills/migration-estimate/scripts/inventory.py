#!/usr/bin/env python3
"""Inventory an application codebase for the migration estimate: modules, languages, manifests, integrations.

Usage: inventory.py [ROOT] [--out FILE]

ROOT defaults to the git top-level of the cwd. The JSON is written to
~/.krithi/migration-estimate/<repo-name>/inventory.json (KRITHI_HOME overrides ~/.krithi; --out overrides
the whole path), outside the repository, and also printed. Read-only on ROOT; standard library only.

Modules: top-level source folders; container folders (src, app, packages, services, ...) and namespace folders
with no source files of their own (src/main/java/com/acme) are descended so each module is a meaningful unit.
A PRD that covers a parent path covers all modules under it. Test, build, vendor and
docs folders are skipped. Integrations: databases, queues, cloud SDKs, identity, payments, messaging and
similar, detected from dependency manifests and docker-compose files. estimate.py --inventory requires each
module to be covered by a PRD (or listed as out of scope) and each integration to be named in a PRD.

target_signals: facts that decide which parts of the standard target architecture apply (references/target-architecture.md):
AI agents, background or scheduled jobs, caches, file storage and multi-tenancy, found in manifests and (for jobs and
tenancy) in source text. estimate.py --inventory requires the PRDs to map each signal that is present.
"""
import argparse, datetime, json, os, re, subprocess, sys
from pathlib import Path

SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "vendor", "dist", "build", "target", "out", ".next", ".nuxt",
             ".venv", "venv", "env", "__pycache__", ".idea", ".vscode", "bin", "obj", "coverage", ".gradle", ".mvn",
             ".terraform", ".cache", ".pytest_cache", ".mypy_cache", ".tox", "bower_components", "Pods", "docs",
             "doc", "site-packages", ".github", ".gitlab"}
TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "e2e", "testing", "fixtures", "__mocks__", "cypress", "playwright"}
CONTAINERS = {"src", "app", "apps", "packages", "services", "modules", "lib", "libs", "cmd", "internal", "pkg",
              "components", "projects", "source", "server", "client", "main", "java", "kotlin", "scala", "webapp", "web"}
SOURCE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".kt", ".kts", ".scala", ".groovy", ".go",
              ".rb", ".php", ".cs", ".vb", ".fs", ".cpp", ".cc", ".c", ".h", ".hpp", ".rs", ".swift", ".m", ".dart",
              ".vue", ".svelte", ".astro", ".html", ".htm", ".jsp", ".jspx", ".asp", ".aspx", ".cshtml", ".razor",
              ".erb", ".ejs", ".hbs", ".twig", ".cfm", ".cob", ".cbl", ".pl", ".pm", ".sql", ".pls", ".pkb", ".pks",
              ".sh", ".ps1", ".bas", ".frm", ".cls", ".xaml", ".abap", ".ex", ".exs", ".erl", ".clj", ".lua", ".r"}
MANIFESTS = {"package.json", "requirements.txt", "requirements-dev.txt", "pyproject.toml", "Pipfile", "setup.py", "setup.cfg",
             "pom.xml", "build.gradle", "build.gradle.kts", "go.mod", "Gemfile", "composer.json", "Cargo.toml",
             "packages.config", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml", "web.config",
             "appsettings.json", "application.properties", "application.yml", "application.yaml"}
MANIFEST_SUFFIX = (".csproj", ".vbproj", ".fsproj")
MAX_BYTES = 2_000_000

# name -> (aliases a PRD may use instead, detection patterns matched against manifest text, lower-cased)
INTEGRATIONS = {
    "PostgreSQL": (["Postgres"], [r"postgres", r"psycopg", r"\bpg\b", r"npgsql", r"pgx", r"asyncpg"]),
    "MySQL": (["MariaDB"], [r"mysql", r"mariadb", r"pymysql"]),
    "SQL Server": (["MSSQL"], [r"sqlserver", r"mssql", r"system\.data\.sqlclient", r"microsoft\.data\.sqlclient", r"pyodbc", r"\btedious\b"]),
    "Oracle Database": (["Oracle"], [r"\boracle", r"ojdbc", r"cx_oracle", r"oracledb"]),
    "SQLite": ([], [r"sqlite"]),
    "MongoDB": (["Mongo"], [r"mongo"]),
    "Redis": ([], [r"redis", r"ioredis", r"jedis", r"lettuce"]),
    "Elasticsearch": (["OpenSearch"], [r"elasticsearch", r"opensearch"]),
    "Cassandra": ([], [r"cassandra"]),
    "DynamoDB": ([], [r"dynamodb"]),
    "Kafka": ([], [r"kafka"]),
    "RabbitMQ": (["AMQP"], [r"rabbitmq", r"\bamqp", r"pika\b", r"amqplib"]),
    "ActiveMQ / JMS": (["JMS", "ActiveMQ"], [r"activemq", r"\bjms\b", r"javax\.jms", r"jakarta\.jms"]),
    "Celery": ([], [r"\bcelery\b"]),
    "AWS": (["Amazon Web Services", "S3", "SQS", "SNS", "Lambda"], [r"boto3", r"botocore", r"aws-sdk", r"@aws-sdk", r"software\.amazon\.awssdk", r"awssdk", r"com\.amazonaws"]),
    "Azure": ([], [r"azure"]),
    "Google Cloud": (["GCP"], [r"google-cloud", r"@google-cloud", r"com\.google\.cloud", r"cloud\.google\.com/go"]),
    "Firebase": ([], [r"firebase"]),
    "Stripe": ([], [r"stripe"]),
    "PayPal": ([], [r"paypal", r"braintree"]),
    "Twilio": ([], [r"twilio"]),
    "Email (SMTP)": (["SMTP", "email", "e-mail"], [r"sendgrid", r"nodemailer", r"mailgun", r"\bsmtp", r"javax\.mail", r"jakarta\.mail", r"mailkit", r"postmark", r"\bses\b"]),
    "LDAP / Active Directory": (["LDAP", "Active Directory"], [r"ldap", r"directoryservices"]),
    "SAML SSO": (["SAML"], [r"saml"]),
    "OAuth / OpenID Connect": (["OAuth", "OIDC", "OpenID"], [r"oauth", r"openid", r"\boidc\b", r"passport-", r"authlib", r"identitymodel"]),
    "Okta": ([], [r"okta"]),
    "Auth0": ([], [r"auth0"]),
    "Keycloak": ([], [r"keycloak"]),
    "GraphQL": ([], [r"graphql", r"apollo"]),
    "gRPC": ([], [r"grpc", r"protobuf"]),
    "SOAP web services": (["SOAP", "WSDL"], [r"\bsoap", r"wsdl", r"jax-ws", r"cxf", r"\bzeep\b", r"system\.servicemodel"]),
    "Salesforce": ([], [r"salesforce", r"jsforce", r"simple-salesforce"]),
    "SAP": ([], [r"\bsap\b", r"sapjco", r"pyrfc"]),
    "Slack": ([], [r"slack"]),
    "Microsoft Graph / Office 365": (["Microsoft Graph", "Office 365", "SharePoint"], [r"microsoft-graph", r"msgraph", r"microsoft\.graph", r"sharepoint", r"\bmsal"]),
    "Monitoring / error tracking": (["Sentry", "Datadog", "New Relic", "Splunk", "monitoring"], [r"sentry", r"datadog", r"dd-trace", r"newrelic", r"splunk"]),
    "OpenAI / LLM API": (["OpenAI", "LLM", "Anthropic"], [r"openai", r"anthropic", r"langchain"]),
    "Report generation": (["Crystal Reports", "JasperReports", "SSRS", "PDF"], [r"crystaldecisions", r"jasperreports", r"reportviewer", r"itext", r"pdfkit", r"reportlab", r"wkhtmltopdf", r"puppeteer"]),
    "File transfer (FTP/SFTP)": (["FTP", "SFTP"], [r"\bftp", r"sftp", r"paramiko", r"ssh2", r"jsch"]),
    "Scheduler / batch jobs": (["scheduler", "cron", "batch"], [r"quartz", r"hangfire", r"node-cron", r"apscheduler", r"spring-batch", r"airflow", r"bull\b", r"agenda"]),
}
# target_signals: key -> (manifest patterns, source-text patterns). Matched case-insensitively.
SIGNALS = {
    "ai_agents": ([r"langchain", r"langgraph", r"llama[-_]?index", r"\bautogen", r"crewai", r"semantic[-_]kernel", r"openai", r"anthropic",
                   r"ollama", r"transformers", r"sentence[-_]transformers", r"pgvector", r"chromadb", r"pinecone", r"weaviate", r"qdrant",
                   r"faiss", r"\bmcp\b", r"google-generativeai", r"vertexai", r"bedrock"],
                  [r"\bAgentExecutor\b", r"\bStateGraph\b", r"\bChatOpenAI\b", r"chat\.completions", r"messages\.create\(", r"\bReAct\b"]),
    "background_jobs": ([r"quartz", r"hangfire", r"node-cron", r"apscheduler", r"spring-batch", r"airflow", r"\bbull\b", r"\bagenda\b",
                         r"\bcelery\b", r"sidekiq", r"\brq\b", r"dramatiq", r"resque", r"delayed_job", r"bee-queue", r"\bbullmq"],
                        [r"@Scheduled\b", r"@EnableScheduling", r"\bcrontab\b", r"\bBackgroundService\b", r"\bIHostedService\b",
                         r"schedule\.every\(", r"cron\.schedule\(", r"@(shared_)?task\b", r"@app\.task", r"\bJob\s*implements\s*Job\b",
                         r"\bTimerTrigger\b", r"\bsetInterval\(", r"\bTask Scheduler\b"]),
    "caches": ([r"redis", r"memcache", r"ehcache", r"caffeine", r"node-cache", r"lru-cache", r"cachetools", r"flask-caching", r"django-redis"], []),
    "file_storage": ([r"\bmulter\b", r"formidable", r"commons-fileupload", r"minio", r"azure-storage-blob", r"@azure/storage-blob",
                      r"django-storages", r"flask-uploads", r"s3", r"gcs", r"google-cloud-storage"],
                     [r"multipart/form-data", r"\bUploadFile\b", r"\bHttpPostedFile\b", r"\bMultipartFile\b", r"enctype=[\"']multipart"]),
    "multi_tenant": ([r"django-tenants", r"django-tenant-schemas", r"multitenan"], [r"\btenant_?id\b", r"\bX-Tenant-Id\b", r"\bTenantContext\b", r"\bcurrent_tenant\b"]),
}
SIGNAL_SRC_MAX = 300_000
SIGNAL_SRC_EVIDENCE = 25
LANG = {".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".ts": "TypeScript",
        ".tsx": "TypeScript", ".java": "Java", ".kt": "Kotlin", ".scala": "Scala", ".go": "Go", ".rb": "Ruby", ".php": "PHP",
        ".cs": "C#", ".vb": "VB.NET", ".cpp": "C++", ".cc": "C++", ".c": "C", ".rs": "Rust", ".swift": "Swift", ".dart": "Dart",
        ".vue": "Vue", ".svelte": "Svelte", ".jsp": "JSP", ".aspx": "ASP.NET", ".asp": "Classic ASP", ".cshtml": "Razor",
        ".cob": "COBOL", ".cbl": "COBOL", ".sql": "SQL", ".pls": "PL/SQL", ".pkb": "PL/SQL", ".pks": "PL/SQL", ".pl": "Perl",
        ".html": "HTML", ".htm": "HTML", ".bas": "VB6", ".frm": "VB6", ".cls": "VB6", ".abap": "ABAP", ".ex": "Elixir", ".cfm": "ColdFusion"}


def repo_root(arg):
    if arg:
        return Path(arg).expanduser().resolve()
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.cwd().resolve()


def skipped(name: str) -> bool:
    return name in SKIP_DIRS or name.lower() in TEST_DIRS or (name.startswith(".") and name not in {".", ".."})


def walk(root: Path):
    """Yield (relative dir, [source files], [manifest files]) for every non-skipped folder."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not skipped(d))
        rel = Path(dirpath).relative_to(root)
        src = [f for f in filenames if Path(f).suffix.lower() in SOURCE_EXT]
        man = [f for f in filenames if f in MANIFESTS or f.endswith(MANIFEST_SUFFIX) or re.match(r"requirements.*\.txt$", f)]
        yield rel, src, man


def count_lines(p: Path) -> int:
    try:
        if p.stat().st_size > MAX_BYTES:
            return 0
        with p.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?")
    ap.add_argument("--out", help="output JSON path (default ~/.krithi/migration-estimate/<repo>/inventory.json)")
    a = ap.parse_args()
    root = repo_root(a.root)
    if not root.is_dir():
        print(json.dumps({"ok": False, "error": f"not a folder: {root}"}))
        return 2

    per_dir, manifests = {}, []
    for rel, src, man in walk(root):
        per_dir[rel] = src
        manifests += [rel / m for m in man]

    children = {}
    for rel in per_dir:
        if rel != Path("."):
            children.setdefault(rel.parent, []).append(rel)
    total = {}  # recursive source-file count per folder, deepest first
    for rel in sorted(per_dir, key=lambda p: len(p.parts), reverse=True):
        total[rel] = len(per_dir[rel]) + sum(total.get(c, 0) for c in children.get(rel, []))

    modules = []

    def visit(rel: Path, depth: int):
        kids = [c for c in children.get(rel, []) if total.get(c, 0) > 0]
        own = len(per_dir.get(rel, []))
        if kids and depth < 8 and (rel.name.lower() in CONTAINERS or own == 0) and len(kids) <= 40:
            if own:
                modules.append(rel)  # container with its own files, e.g. src/main.py next to src/users/
            for c in sorted(kids):
                visit(c, depth + 1)
        else:
            modules.append(rel)

    for c in sorted(c for c in children.get(Path("."), []) if total.get(c, 0) > 0):
        visit(c, 1)
    root_files = sorted(per_dir.get(Path("."), []))

    mod_out, langs = [], {}
    for m in modules:
        files, lines, mlangs = 0, 0, {}
        sub = [d for d in per_dir if d == m or m in d.parents]
        if m in modules and any(o != m and m in o.parents for o in modules):
            sub = [m]  # container that also has deeper modules: count only its own files
        for d in sub:
            for f in per_dir[d]:
                files += 1
                lines += count_lines(root / d / f)
                lg = LANG.get(Path(f).suffix.lower())
                if lg:
                    mlangs[lg] = mlangs.get(lg, 0) + 1
        for k, v in mlangs.items():
            langs[k] = langs.get(k, 0) + v
        mod_out.append({"path": m.as_posix(), "files": files, "lines": lines,
                        "languages": sorted(mlangs, key=mlangs.get, reverse=True)})
    for f in root_files:
        lg = LANG.get(Path(f).suffix.lower())
        if lg:
            langs[lg] = langs.get(lg, 0) + 1
        mod_out.append({"path": f, "files": 1, "lines": count_lines(root / f), "languages": [lg] if lg else []})

    found = {}
    for mf in manifests:
        try:
            p = root / mf
            if p.stat().st_size > MAX_BYTES:
                continue
            text = p.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        for name, (aliases, pats) in INTEGRATIONS.items():
            if any(re.search(pt, text) for pt in pats):
                found.setdefault(name, {"name": name, "aliases": aliases, "evidence": []})["evidence"].append(mf.as_posix())

    signals = {k: {"present": False, "evidence": []} for k in SIGNALS}
    for mf in manifests:
        try:
            text = (root / mf).read_text(encoding="utf-8", errors="replace").lower() if (root / mf).stat().st_size <= MAX_BYTES else ""
        except OSError:
            continue
        for k, (mpats, _s) in SIGNALS.items():
            hit = [pt for pt in mpats if re.search(pt, text)]
            if hit:
                signals[k]["present"] = True
                signals[k]["evidence"].append(f"{mf.as_posix()} ({hit[0].strip(chr(92)+'b')})")
    src_pats = {k: [re.compile(pt, re.I) for pt in spats] for k, (_m, spats) in SIGNALS.items() if spats}
    for d, files in per_dir.items():
        for f in files:
            if not src_pats or Path(f).suffix.lower() in (".html", ".htm", ".css", ".sql"):
                continue
            fp = root / d / f
            try:
                if fp.stat().st_size > SIGNAL_SRC_MAX:
                    continue
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for k, pats in src_pats.items():
                if len(signals[k]["evidence"]) < SIGNAL_SRC_EVIDENCE and any(p.search(text) for p in pats):
                    signals[k]["present"] = True
                    signals[k]["evidence"].append((d / f).as_posix())

    out = {"ok": True, "root": str(root), "generated": datetime.datetime.now().isoformat(timespec="seconds"),
           "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
           "source_files": sum(m["files"] for m in mod_out), "source_lines": sum(m["lines"] for m in mod_out),
           "modules": mod_out, "manifests": [m.as_posix() for m in manifests],
           "integrations": sorted(found.values(), key=lambda x: x["name"]),
           "target_signals": signals,
           "note": "Heuristic. Integrations come from dependency manifests only; also look for integrations called "
                   "over plain HTTP, files, stored procedures or environment variables when reading the code."}

    if a.out:
        dest = Path(a.out).expanduser().resolve()
    else:
        base = Path(os.environ["KRITHI_HOME"]).expanduser() if os.environ.get("KRITHI_HOME") else Path.home() / ".krithi"
        dest = (base / "migration-estimate" / re.sub(r"[^A-Za-z0-9_.-]", "_", root.name) / "inventory.json").resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    out["inventory_path"] = str(dest)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

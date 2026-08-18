#!/usr/bin/env bash
# Setup for Capillaries.
#
# Walks new users through PostgreSQL, environment, models, and seed data.
#
# Usage:
#   ./scripts/setup.sh                  # interactive
#   ./scripts/setup.sh --yes            # accept every default, ask nothing
#   ./scripts/setup.sh --database NAME  # target a specific database
#
# --yes exists so this can be tested and re-run without a human at the keyboard.
# Piping answers into an interactive script is not a substitute: the sequence
# silently shifts whenever a question is added, and a sudo password prompt in
# the middle will eat the next answer.

set -euo pipefail

ASSUME_YES=false
DB_NAME_ARG=""

while (( $# )); do
    case "$1" in
        -y|--yes)     ASSUME_YES=true ;;
        --database)   shift; DB_NAME_ARG="${1:-}"
                      [[ -n "$DB_NAME_ARG" ]] || { echo "--database needs a name" >&2; exit 1; } ;;
        --database=*) DB_NAME_ARG="${1#*=}" ;;
        -h|--help)    sed -n '2,15p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
    shift
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}▸${NC} $*"; }
success() { echo -e "${GREEN}✔${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠${NC} $*"; }
err()     { echo -e "${RED}✖${NC} $*"; }
header()  { echo -e "\n${BOLD}── $* ──${NC}\n"; }

# ── Helpers ──────────────────────────────────────────────────────────────────

# Under --yes every prompt resolves to its stated default and nothing reads
# stdin. The default is echoed so an unattended log still shows what was chosen.
prompt_yn() {
    local prompt="$1" default="${2:-y}"
    local yn
    if $ASSUME_YES; then
        echo -e "${BLUE}?${NC} ${prompt} → ${default}"
        [[ "$default" == "y" ]]
        return
    fi
    if [[ "$default" == "y" ]]; then
        read -rp "$(echo -e "${BLUE}?${NC} ${prompt} [Y/n] ")" yn
        yn="${yn:-y}"
    else
        read -rp "$(echo -e "${BLUE}?${NC} ${prompt} [y/N] ")" yn
        yn="${yn:-n}"
    fi
    [[ "${yn,,}" == "y"* ]]
}

prompt_input() {
    local prompt="$1" default="$2" result
    if $ASSUME_YES; then
        echo "$default"
        return
    fi
    read -rp "$(echo -e "${BLUE}?${NC} ${prompt} [${default}] ")" result
    echo "${result:-$default}"
}

prompt_choice() {
    local prompt="$1"
    shift
    local options=("$@")
    if $ASSUME_YES; then
        echo -e "${BLUE}?${NC} ${prompt} → 1) ${options[0]}"
        return 0
    fi
    echo -e "${BLUE}?${NC} ${prompt}"
    for i in "${!options[@]}"; do
        echo "    $((i+1))) ${options[$i]}"
    done
    local choice
    while true; do
        read -rp "  Enter choice [1-${#options[@]}]: " choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#options[@]} )); then
            return $((choice - 1))
        fi
        err "Invalid choice. Enter a number between 1 and ${#options[@]}."
    done
}

# Track what was configured for the summary banner
declare -A SUMMARY

# ── 1. Python Check ─────────────────────────────────────────────────────────
header "Checking Python"

if ! command -v python3 &>/dev/null; then
    err "python3 not found. Please install Python 3.10 or later."
    exit 1
fi

PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="$(echo "$PY_VERSION" | cut -d. -f1)"
PY_MINOR="$(echo "$PY_VERSION" | cut -d. -f2)"

if (( PY_MAJOR < 3 || (PY_MAJOR == 3 && PY_MINOR < 10) )); then
    err "Python 3.10+ required (found $PY_VERSION)."
    exit 1
fi

success "Python $PY_VERSION"
SUMMARY[python]="$PY_VERSION"

# ── 2. PostgreSQL Check ─────────────────────────────────────────────────────
header "Checking PostgreSQL"

pg_installed=false
pg_running=false

if command -v psql &>/dev/null; then
    pg_installed=true
    PG_VERSION="$(psql --version | head -1)"
    success "Found: $PG_VERSION"
else
    err "PostgreSQL (psql) not found."
fi

if $pg_installed; then
    if pg_isready -q 2>/dev/null; then
        pg_running=true
        success "PostgreSQL is running."
    else
        warn "PostgreSQL is installed but not running."
        echo ""
        info "Start it with:"
        echo "    sudo systemctl start postgresql"
        echo ""
        if ! prompt_yn "Continue anyway (you can start it in another terminal)?"; then
            exit 1
        fi
    fi
fi

if ! $pg_installed; then
    echo ""
    is_wsl=false
    if [[ -f /proc/version ]] && grep -qi microsoft /proc/version; then
        is_wsl=true
        warn "Detected WSL — use the Linux instructions below."
        echo ""
    fi

    if command -v apt &>/dev/null; then
        info "Install PostgreSQL on Debian/Ubuntu:"
        echo "    sudo apt update"
        echo "    sudo apt install postgresql postgresql-contrib"
        echo ""
        info "Install pgvector extension (adjust version number to match your PostgreSQL):"
        echo "    sudo apt install postgresql-16-pgvector"
    elif command -v dnf &>/dev/null; then
        info "Install PostgreSQL on Fedora/RHEL:"
        echo "    sudo dnf install postgresql-server postgresql-contrib"
        echo "    sudo postgresql-setup --initdb"
        echo "    sudo systemctl start postgresql"
        echo ""
        info "For pgvector, see: https://github.com/pgvector/pgvector#linux"
    elif command -v brew &>/dev/null; then
        info "Install PostgreSQL on macOS:"
        echo "    brew install postgresql@16 pgvector"
        echo "    brew services start postgresql@16"
    else
        info "Install PostgreSQL for your OS: https://www.postgresql.org/download/"
        info "Install pgvector: https://github.com/pgvector/pgvector#installation"
    fi

    echo ""
    err "Please install PostgreSQL, then re-run this script."
    exit 1
fi

# ── 3. Database Creation ────────────────────────────────────────────────────
header "Database Setup"

# Resolve the database name before anything touches a database. This block used
# to hardcode `capillaries` in four places while step 4 wrote DB_NAME into .env,
# so a second instance under another name created its schema in the first one's
# database. An existing .env wins; otherwise ask, defaulting to `capillaries`.
# `|| true` is load-bearing under `set -euo pipefail`: on a fresh clone there is
# no .env, grep exits 1, and pipefail would take the whole script down here.
DB_NAME="${DB_NAME_ARG:-$(grep -E '^DB_NAME=' "$PROJECT_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- || true)}"
if [[ -z "$DB_NAME" ]]; then
    DB_NAME="$(prompt_input "Database name" "capillaries")"
fi

if prompt_yn "Create the '$DB_NAME' database and extensions?"; then
    info "Creating database (may already exist)..."
    if createdb "$DB_NAME" 2>/dev/null; then
        success "Created database '$DB_NAME'."
    elif psql -d "$DB_NAME" -c "SELECT 1;" &>/dev/null; then
        info "Database '$DB_NAME' already exists — continuing."
    else
        # createdb failed and the database is unreachable: usually no CREATEDB
        # role. `sudo -n` rather than plain sudo — a password prompt here would
        # read from the same stdin the script's own answers arrive on, so an
        # unattended run would feed setup's next answer to sudo as a password.
        warn "Could not create '$DB_NAME' as $(whoami)."
        if sudo -n -u postgres createdb -O "$(whoami)" "$DB_NAME" 2>/dev/null; then
            success "Created '$DB_NAME' as the postgres user."
        else
            err "Cannot create '$DB_NAME' automatically. Run this, then re-run setup:"
            echo "    sudo -u postgres createdb -O $(whoami) $DB_NAME"
            if ! prompt_yn "Continue anyway?" "n"; then
                exit 1
            fi
        fi
    fi

    info "Enabling pgvector extension..."
    vec_err="$(psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>&1 >/dev/null)" && vec_ok=true || vec_ok=false

    if $vec_ok; then
        success "pgvector enabled."
    else
        # Two very different failures land here and the fix for one does nothing
        # for the other: the package is missing, or it is installed and you are
        # not superuser. Telling a non-superuser to apt-install a package they
        # already have is how people lose an afternoon.
        available="$(psql -d "$DB_NAME" -At -c \
            "SELECT 1 FROM pg_available_extensions WHERE name='vector'" 2>/dev/null)"

        if [[ "$available" == "1" ]]; then
            err "pgvector is installed but could not be enabled — this needs superuser."
            echo ""
            info "Run this, then re-run setup:"
            echo "    sudo -u postgres psql -d $DB_NAME -c 'CREATE EXTENSION vector;'"
        else
            err "pgvector is not available on this PostgreSQL server."
            echo ""
            if command -v apt &>/dev/null; then
                info "Install it with: sudo apt install postgresql-16-pgvector"
                info "(match the number to your server: psql --version)"
            elif command -v brew &>/dev/null; then
                info "Install it with: brew install pgvector"
            else
                info "See: https://github.com/pgvector/pgvector#installation"
            fi
        fi
        echo ""
        info "PostgreSQL said: ${vec_err:-no message}"
        echo ""
        if ! prompt_yn "Continue without pgvector (schema creation will fail)?" "n"; then
            exit 1
        fi
    fi

    info "Enabling pg_trgm extension..."
    psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" 2>/dev/null \
        && success "pg_trgm enabled." \
        || warn "Could not enable pg_trgm — fuzzy search may not work."

    SUMMARY[database]="$DB_NAME"
else
    SUMMARY[database]="skipped"
fi

# ── 4. Environment Configuration ────────────────────────────────────────────
header "Environment Configuration"

ENV_FILE="$PROJECT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
    warn ".env already exists — skipping environment setup."
    info "Edit $ENV_FILE manually to change settings."
    SUMMARY[env]=".env (existing)"
else
    info "Creating .env from template..."

    DEFAULT_PROMPTS="$HOME/.capillaries/prompts"
    DEFAULT_SKILLS="$HOME/.capillaries/skills"

    PROMPTS_PATH="$(prompt_input "Prompts directory" "$DEFAULT_PROMPTS")"
    SKILLS_PATH="$(prompt_input "Skills directory" "$DEFAULT_SKILLS")"

    OBSIDIAN_VAULT_PATH=""
    if prompt_yn "Do you use Obsidian for managing prompts?" "n"; then
        OBSIDIAN_VAULT_PATH="$(prompt_input "Obsidian vault path" "")"
    fi

    # Test DB connection with defaults. DB_NAME is whatever step 3 resolved —
    # resetting it here is what made the "Database name" question above cosmetic.
    DB_HOST="/var/run/postgresql"
    DB_PORT="5432"
    DB_USER=""
    DB_PASSWORD=""

    if psql -d "$DB_NAME" -c "SELECT 1;" &>/dev/null; then
        success "Database connection works with Unix socket defaults."
    else
        warn "Default DB connection failed — configuring manually."
        DB_HOST="$(prompt_input "DB host" "localhost")"
        DB_PORT="$(prompt_input "DB port" "5432")"
        DB_NAME="$(prompt_input "DB name" "$DB_NAME")"
        DB_USER="$(prompt_input "DB user" "$(whoami)")"
        read -rsp "$(echo -e "${BLUE}?${NC} DB password (hidden): ")" DB_PASSWORD
        echo ""
    fi

    ANTHROPIC_API_KEY=""
    OPENAI_API_KEY=""
    if prompt_yn "Add LLM API keys now (optional)?" "n"; then
        read -rsp "$(echo -e "${BLUE}?${NC} Anthropic API key (Enter to skip): ")" ANTHROPIC_API_KEY
        echo ""
        read -rsp "$(echo -e "${BLUE}?${NC} OpenAI API key (Enter to skip): ")" OPENAI_API_KEY
        echo ""
    fi

    cat > "$ENV_FILE" <<ENVEOF
# Capillaries environment — generated by setup.sh

# --- Prompt and skill directories ---
PROMPTS_PATH=$PROMPTS_PATH
SKILLS_PATH=$SKILLS_PATH

# --- Obsidian vault (optional, for vault sync) ---
OBSIDIAN_VAULT_PATH=$OBSIDIAN_VAULT_PATH

# --- PostgreSQL connection ---
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD

# --- Embedding server ---
# EMBED_URL=http://127.0.0.1:8003/v1/embeddings
# EMBED_MODEL=snowflake-arctic-embed-m-v2.0

# --- LLM API keys ---
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
OPENAI_API_KEY=$OPENAI_API_KEY
ENVEOF

    success "Created .env"
    SUMMARY[env]=".env (created)"
fi

# ── 5. Create Directories ───────────────────────────────────────────────────
# Read paths from .env if we didn't just set them
if [[ -z "${PROMPTS_PATH:-}" ]]; then
    PROMPTS_PATH="$(grep '^PROMPTS_PATH=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "$HOME/.capillaries/prompts")"
fi
if [[ -z "${SKILLS_PATH:-}" ]]; then
    SKILLS_PATH="$(grep '^SKILLS_PATH=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "$HOME/.capillaries/skills")"
fi

# Expand ~ in paths
PROMPTS_PATH="${PROMPTS_PATH/#\~/$HOME}"
SKILLS_PATH="${SKILLS_PATH/#\~/$HOME}"

mkdir -p "$PROMPTS_PATH" "$SKILLS_PATH"
success "Directories ready: $PROMPTS_PATH, $SKILLS_PATH"
SUMMARY[prompts_path]="$PROMPTS_PATH"
SUMMARY[skills_path]="$SKILLS_PATH"

# ── 6. Install Python Packages ──────────────────────────────────────────────
header "Python Packages"

prompt_choice "Install profile:" \
    "Core        — API server + search (no local ML models)" \
    "Lightweight  — adds local embeddings + reranker" \
    "Advanced     — full ML stack with FAISS, clustering" \
    "With Obsidian — Lightweight + vault sync tools"
install_choice=$?

case $install_choice in
    0) pip_target=".";                          profile_name="Core" ;;
    1) pip_target=".[lightweight]";             profile_name="Lightweight" ;;
    2) pip_target=".[advanced]";                profile_name="Advanced" ;;
    3) pip_target=".[lightweight,obsidian]";    profile_name="With Obsidian" ;;
esac

info "Installing ($profile_name)..."
pip install -e "$pip_target" 2>&1 | tail -5
success "Python packages installed ($profile_name)."
SUMMARY[install_profile]="$profile_name"

# arteries supplies the MemoryFrame contract for the memory-aware retrieval
# path. Capillaries runs without it — plain retrieval needs nothing from the
# sibling — so this is offered, not required. Not on PyPI, hence not in
# pyproject: pip will never pull it on its own.
if python3 -c "import arteries.memory_types" 2>/dev/null; then
    success "arteries is importable — memory-aware retrieval available."
    SUMMARY[arteries]="already installed"
elif prompt_yn "Install arteries for memory-aware retrieval (optional)?" "n"; then
    ARTERIES_DIR="$(prompt_input "Path to the arteries checkout" "$(dirname "$PROJECT_DIR")/arteries")"
    if [[ -d "$ARTERIES_DIR" ]]; then
        info "Installing arteries from $ARTERIES_DIR..."
        pip install -e "$ARTERIES_DIR" 2>&1 | tail -3
        if python3 -c "import arteries.memory_types" 2>/dev/null; then
            success "arteries installed."
            SUMMARY[arteries]="$ARTERIES_DIR"
        else
            warn "arteries still not importable — check that checkout."
            SUMMARY[arteries]="install failed (retrieval still works)"
        fi
    else
        warn "No directory at $ARTERIES_DIR — skipping."
        SUMMARY[arteries]="not installed (retrieval still works)"
    fi
else
    SUMMARY[arteries]="not installed (retrieval still works)"
fi

# ── 7. Model Download ───────────────────────────────────────────────────────
header "Model Download"

if (( install_choice == 0 )); then
    warn "Core profile selected — skipping local model download."
    info "Set EMBED_URL in .env to point to an external embedding API."
    SUMMARY[models]="external (Core profile)"
else
    prompt_choice "Model download:" \
        "Full     — all models (~2GB): embedding + reranker + fallback + spaCy" \
        "Lite     — embedding + spaCy (~700MB)" \
        "External — skip local models (use external embedding API)"
    model_choice=$?

    case $model_choice in
        0) model_profile="full" ;;
        1) model_profile="lite" ;;
        2) model_profile="external" ;;
    esac

    if [[ "$model_profile" == "external" ]]; then
        EMBED_URL="$(prompt_input "External embedding API URL" "https://api.openai.com/v1/embeddings")"
        EMBED_MODEL="$(prompt_input "Embedding model name" "text-embedding-3-small")"

        if grep -q "^EMBED_URL=" "$ENV_FILE" 2>/dev/null; then
            sed -i "s|^# *EMBED_URL=.*|EMBED_URL=$EMBED_URL|" "$ENV_FILE"
            sed -i "s|^# *EMBED_MODEL=.*|EMBED_MODEL=$EMBED_MODEL|" "$ENV_FILE"
        else
            echo "" >> "$ENV_FILE"
            echo "EMBED_URL=$EMBED_URL" >> "$ENV_FILE"
            echo "EMBED_MODEL=$EMBED_MODEL" >> "$ENV_FILE"
        fi
        success "External embedding API configured."
        # Read the dimension rather than quoting one: it moved from 768 to 1024
        # with the Qwen3 embedder, and a hardcoded number in a warning is how
        # people end up matching their model against the wrong schema.
        _dim="$(PYTHONPATH=src python3 -c 'from capillaries.config import EMBED_DIM; print(EMBED_DIM)' 2>/dev/null || echo '?')"
        warn "The schema uses VECTOR($_dim). A model with a different dimension needs"
        warn "a migration first: PYTHONPATH=src python3 -m capillaries.db.migrate_embed_dim --apply"
        SUMMARY[models]="external ($EMBED_URL)"
    else
        info "Downloading models ($model_profile)..."
        PYTHONPATH=src python3 scripts/download_models.py --profile "$model_profile"
        success "Models downloaded ($model_profile)."
        SUMMARY[models]="$model_profile"
    fi
fi

# ── 8. Schema Setup ─────────────────────────────────────────────────────────
header "Database Schema"

info "Creating tables and indexes..."
PYTHONPATH=src python3 scripts/setup_db.py
success "Schema ready."

# ── 9. Seed Data ────────────────────────────────────────────────────────────
header "Seed Data"

ingested_any=false

if prompt_yn "Load demo prompts and skills into the database?"; then
    info "Ingesting public prompts..."
    PYTHONPATH=src python3 scripts/ingest_public.py --db-only
    success "Demo data loaded."
    ingested_any=true
fi

# The vault, if there is one, is where the real corpus lives. Setup used to load
# only public_prompts/ — 67 rows — and stop, so a machine whose prompts were in
# Obsidian finished setup with a corpus that looked complete and was missing
# 93% of itself.
VAULT_PROMPTS="$(PYTHONPATH=src python3 -c \
    'from capillaries.config.paths import PROMPTS_PATH; print(PROMPTS_PATH)' 2>/dev/null || true)"

if [[ -n "$VAULT_PROMPTS" && -d "$VAULT_PROMPTS" ]]; then
    vault_count="$(find "$VAULT_PROMPTS" -name '*.md' 2>/dev/null | wc -l)"
    if (( vault_count > 0 )) && prompt_yn "Ingest $vault_count prompt files from $VAULT_PROMPTS?"; then
        PYTHONPATH=src python3 -m obsidian_sync.ingest
        success "Vault prompts ingested."
        ingested_any=true
        SUMMARY[vault]="$vault_count files"
    else
        SUMMARY[vault]="skipped"
    fi
else
    info "No vault prompts directory found — set OBSIDIAN_VAULT_PATH or PROMPTS_PATH to use one."
    SUMMARY[vault]="none"
fi

if $ingested_any; then

    # Embedding must follow ingest, not precede it. ingest_public.py writes rows
    # and nothing else — it has no embedding code — and `setup_db.py` only
    # embeds when asked. Skip this and the database ends up full of prompts with
    # null vectors: dense retrieval returns nothing, and the version guard in
    # retriever.py stays quiet because an empty index has nothing to disagree
    # with. Silent, and indistinguishable from a bad corpus.
    info "Generating embeddings (this is the slow step)..."
    if PYTHONPATH=src python3 scripts/setup_db.py --embed; then
        success "Embeddings generated."

        # The dense retrieval channel reads prompt_chunks, not prompts —
        # search/channels.py:vector_search selects `FROM prompt_chunks c`. So
        # embedding the prompts table alone leaves dense search returning
        # nothing and only the lexical channel alive. Chunking embeds its own
        # rows, hence no second --embed pass.
        info "Chunking and embedding chunks (the dense channel searches these)..."
        if PYTHONPATH=src python3 -m capillaries.chunk --backfill; then
            success "Chunks built."
            SUMMARY[seed_data]="loaded, embedded, chunked"
        else
            err "Chunking failed — dense retrieval will return nothing."
            info "Retry with: PYTHONPATH=src python3 -m capillaries.chunk --backfill"
            SUMMARY[seed_data]="embedded, NOT chunked"
        fi
    else
        err "Embedding failed — prompts are loaded but unsearchable."
        info "Is the embedding server up? Start it with:"
        echo "    PYTHONPATH=src python3 scripts/serve_embeddings.py"
        info "Then re-run: PYTHONPATH=src python3 scripts/setup_db.py --embed"
        SUMMARY[seed_data]="loaded, NOT embedded"
    fi
else
    SUMMARY[seed_data]="skipped"
fi

# ── 10. Verify ──────────────────────────────────────────────────────────────
header "Verifying"

if ! PYTHONPATH=src python3 -c "from capillaries.find import FindResult" 2>/dev/null; then
    err "capillaries failed to import. Details:"
    PYTHONPATH=src python3 -c "from capillaries.find import FindResult" 2>&1 | tail -5
    SUMMARY[verify]="import FAILED"
else
    success "capillaries imports cleanly."

    # Import alone proved nothing about whether search works — it passed happily
    # while the corpus sat unembedded. Count the vectors instead.
    counts="$(PYTHONPATH=src python3 - <<'PYEOF' 2>/dev/null
import psycopg2
from capillaries.config.paths import DB_CONFIG
with psycopg2.connect(**DB_CONFIG) as c, c.cursor() as cur:
    cur.execute("SELECT count(*), count(embedding) FROM prompts")
    total, embedded = cur.fetchone()
    try:
        cur.execute("SELECT count(*) FROM prompt_chunks WHERE embedding IS NOT NULL")
        chunks = cur.fetchone()[0]
    except Exception:
        chunks = 0   # table absent — backfill never ran
    print("%d %d %d" % (total, embedded, chunks))
PYEOF
)"
    read -r total embedded chunks <<<"$counts"

    if [[ -z "$counts" ]]; then
        warn "Could not query the database — schema or connection problem."
        SUMMARY[verify]="db unreachable"
    elif (( total == 0 )); then
        info "No prompts loaded yet. Point PROMPTS_PATH at your own, or re-run"
        info "setup and accept the seed data."
        SUMMARY[verify]="import ok, corpus empty"
    elif (( embedded == 0 )); then
        err "$total prompts, 0 embedded — dense retrieval will return nothing."
        info "Fix: PYTHONPATH=src python3 scripts/setup_db.py --embed"
        SUMMARY[verify]="NOT SEARCHABLE"
    elif (( embedded < total )); then
        warn "$embedded of $total prompts embedded — the rest are unsearchable."
        info "Fix: PYTHONPATH=src python3 scripts/setup_db.py --embed"
        SUMMARY[verify]="partial ($embedded/$total)"
    elif (( chunks == 0 )); then
        err "$total prompts embedded, but 0 chunks — the dense channel is dead."
        info "Fix: PYTHONPATH=src python3 -m capillaries.chunk --backfill"
        SUMMARY[verify]="no chunks (lexical only)"
    else
        success "$embedded of $total prompts embedded, $chunks chunks indexed."

        # Counting rows still does not prove retrieval works end to end. One
        # real query does, and it is the only check here that exercises the
        # embedding server, both channels, and the reranker together.
        smoke="$(PYTHONPATH=src python3 - <<'PYEOF' 2>/dev/null
import asyncio
from capillaries import find
try:
    r = asyncio.run(find("write a product requirements document"))
    print(f"{r.mode} {r.confidence:.3f}")
except Exception as e:
    print(f"ERROR {type(e).__name__}")
PYEOF
)" || true
        if [[ "$smoke" == ERROR* || -z "$smoke" ]]; then
            warn "Row counts look right but a live query failed: ${smoke:-no output}"
            info "Is the embedding server running? PYTHONPATH=src python3 scripts/serve_embeddings.py"
            SUMMARY[verify]="indexed, query FAILED"
        else
            success "Live query returned: $smoke"
            SUMMARY[verify]="ok ($total prompts, $chunks chunks)"
        fi
    fi
fi

# ── 11. Start Service ───────────────────────────────────────────────────────
header "Start Service"

if prompt_yn "Start the prompt-search service now?"; then
    ./scripts/start.sh
    SUMMARY[service]="started"
else
    info "Start later with: ./scripts/start.sh"
    SUMMARY[service]="not started"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╭──────────────────────────────────────────╮${NC}"
echo -e "${BOLD}│         Capillaries Setup Complete        │${NC}"
echo -e "${BOLD}╰──────────────────────────────────────────╯${NC}"
echo ""
echo -e "  Python:       ${SUMMARY[python]:-unknown}"
echo -e "  Database:     ${SUMMARY[database]:-unknown}"
echo -e "  Prompts dir:  ${SUMMARY[prompts_path]:-unknown}"
echo -e "  Skills dir:   ${SUMMARY[skills_path]:-unknown}"
echo -e "  Install:      ${SUMMARY[install_profile]:-unknown}"
echo -e "  arteries:     ${SUMMARY[arteries]:-unknown}"
echo -e "  Models:       ${SUMMARY[models]:-unknown}"
echo -e "  Seed data:    ${SUMMARY[seed_data]:-unknown}"
echo -e "  Import check: ${SUMMARY[verify]:-unknown}"
echo -e "  Service:      ${SUMMARY[service]:-unknown}"
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo "    ./scripts/start.sh          Start the service"
echo "    ./scripts/start.sh status   Check if running"
echo "    ./scripts/start.sh logs     View logs"
echo "    ./scripts/start.sh stop     Stop the service"
echo "    ./scripts/teardown.sh --dry-run   Preview removing all of the above"
echo ""

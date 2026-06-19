#!/usr/bin/env bash
# Interactive setup for Prompt Flow.
#
# Walks new users through PostgreSQL, environment, models, and seed data.
#
# Usage:
#   ./scripts/setup.sh

set -euo pipefail

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

prompt_yn() {
    local prompt="$1" default="${2:-y}"
    local yn
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
    read -rp "$(echo -e "${BLUE}?${NC} ${prompt} [${default}] ")" result
    echo "${result:-$default}"
}

prompt_choice() {
    local prompt="$1"
    shift
    local options=("$@")
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

if prompt_yn "Create the capillaries database and extensions?"; then
    info "Creating database (may already exist)..."
    sudo -u postgres psql -c "CREATE DATABASE capillaries;" 2>/dev/null || warn "Database may already exist — continuing."

    info "Enabling pgvector extension..."
    if ! psql -d capillaries -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null; then
        err "Failed to enable pgvector extension."
        echo ""
        if command -v apt &>/dev/null; then
            info "Install it with: sudo apt install postgresql-16-pgvector"
        elif command -v brew &>/dev/null; then
            info "Install it with: brew install pgvector"
        else
            info "See: https://github.com/pgvector/pgvector#installation"
        fi
        echo ""
        if ! prompt_yn "Continue without pgvector (embeddings won't work)?"; then
            exit 1
        fi
    else
        success "pgvector enabled."
    fi

    info "Enabling pg_trgm extension..."
    psql -d capillaries -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" 2>/dev/null \
        && success "pg_trgm enabled." \
        || warn "Could not enable pg_trgm — fuzzy search may not work."

    SUMMARY[database]="capillaries (created)"
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

    # Test DB connection with defaults
    DB_HOST="/var/run/postgresql"
    DB_PORT="5432"
    DB_NAME="capillaries"
    DB_USER=""
    DB_PASSWORD=""

    if psql -d capillaries -c "SELECT 1;" &>/dev/null; then
        success "Database connection works with Unix socket defaults."
    else
        warn "Default DB connection failed — configuring manually."
        DB_HOST="$(prompt_input "DB host" "localhost")"
        DB_PORT="$(prompt_input "DB port" "5432")"
        DB_NAME="$(prompt_input "DB name" "capillaries")"
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
# Prompt Flow environment — generated by setup.sh

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
        warn "Note: the database schema uses VECTOR(768). If your model produces a different dimension, adjust src/capillaries/db/setup.py."
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

if prompt_yn "Load demo prompts and skills into the database?"; then
    info "Ingesting public prompts..."
    PYTHONPATH=src python3 scripts/ingest_public.py --db-only
    success "Demo data loaded."
    SUMMARY[seed_data]="loaded"
else
    SUMMARY[seed_data]="skipped"
fi

# ── 10. Start Service ───────────────────────────────────────────────────────
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
echo -e "${BOLD}│         Prompt Flow Setup Complete        │${NC}"
echo -e "${BOLD}╰──────────────────────────────────────────╯${NC}"
echo ""
echo -e "  Python:       ${SUMMARY[python]:-unknown}"
echo -e "  Database:     ${SUMMARY[database]:-unknown}"
echo -e "  Prompts dir:  ${SUMMARY[prompts_path]:-unknown}"
echo -e "  Skills dir:   ${SUMMARY[skills_path]:-unknown}"
echo -e "  Install:      ${SUMMARY[install_profile]:-unknown}"
echo -e "  Models:       ${SUMMARY[models]:-unknown}"
echo -e "  Seed data:    ${SUMMARY[seed_data]:-unknown}"
echo -e "  Service:      ${SUMMARY[service]:-unknown}"
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo "    ./scripts/start.sh          Start the service"
echo "    ./scripts/start.sh status   Check if running"
echo "    ./scripts/start.sh logs     View logs"
echo "    ./scripts/start.sh stop     Stop the service"
echo ""

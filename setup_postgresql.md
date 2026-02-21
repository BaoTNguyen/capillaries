# PostgreSQL Setup for Prompt Flow

## Installation

### Ubuntu/Debian
```bash
# Install PostgreSQL and pgvector
sudo apt update
sudo apt install postgresql postgresql-contrib postgresql-14-pgvector

# Start and enable PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### Create Database and User
```bash
# Switch to postgres user
sudo -u postgres psql

# Create database and user
CREATE DATABASE prompt_flow;
CREATE USER bao WITH PASSWORD 'your_password';  -- Change password as needed
GRANT ALL PRIVILEGES ON DATABASE prompt_flow TO bao;
ALTER USER bao CREATEDB;  -- Allow creating test databases

# Exit psql
\q
```

### Enable pgvector Extension
```bash
# Connect to your database
psql -d prompt_flow -U bao

# Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

# Exit
\q
```

## Configuration

### Update Database Config in setup_database.py
```python
DB_CONFIG = {
    'host': 'localhost',
    'database': 'prompt_flow',
    'user': 'bao',  # Your username
    'password': 'your_password',  # Set if you used a password
}
```

### Environment Variables (Optional)
Create `.env` file:
```
DATABASE_URL=postgresql://bao:your_password@localhost/prompt_flow
ANTHROPIC_API_KEY=your_anthropic_key  # For batch classification
OPENAI_API_KEY=your_openai_key  # For embeddings
```

## Verification

### Test Connection
```bash
psql -d prompt_flow -U bao -c "SELECT version();"
```

### Test pgvector
```bash
psql -d prompt_flow -U bao -c "SELECT '[1,2,3]'::vector;"
```

## Next Steps

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run database setup:**
   ```bash
   python setup_database.py
   ```

3. **Verify data loading:**
   ```bash
   psql -d prompt_flow -U bao -c "SELECT COUNT(*) FROM prompts;"
   ```

The setup script will:
- Create all necessary tables and indexes
- Load your prompts from `/home/bao/Documents/Obsidian/Main-Vault/Areas/AI/Prompts`
- Mark low-confidence prompts for batch classification
- Generate statistics on metadata coverage
#!/bin/bash
# Setup PostgreSQL database for docupolicy with pgvector support

set -e

DB_HOST="localhost"
DB_PORT=5432
DB_NAME="docupolicy"
DB_USER="postgres"
DB_PASSWORD="1234"

echo "=================================================="
echo "PostgreSQL + pgvector Setup for DocuPolicy"
echo "=================================================="
echo ""

# Check if PostgreSQL is running
echo "[1/5] Checking PostgreSQL connection..."
if ! PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -p $DB_PORT -c "SELECT 1" > /dev/null 2>&1; then
    echo "ERROR: Cannot connect to PostgreSQL at $DB_HOST:$DB_PORT"
    echo "Make sure PostgreSQL is running and password is correct."
    exit 1
fi
echo "✓ PostgreSQL is running and accessible"
echo ""

# Create database if it doesn't exist
echo "[2/5] Creating database '$DB_NAME'..."
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -p $DB_PORT -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 || \
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -p $DB_PORT -c "CREATE DATABASE $DB_NAME;"
echo "✓ Database '$DB_NAME' ready"
echo ""

# Create pgvector extension
echo "[3/5] Setting up pgvector extension..."
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -p $DB_PORT -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS vector;"
echo "✓ pgvector extension installed"
echo ""

# Create tables
echo "[4/5] Creating policy_rules table with vector column..."
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -p $DB_PORT -d $DB_NAME << EOF
CREATE TABLE IF NOT EXISTS policy_rules (
    id SERIAL PRIMARY KEY,
    rule_text TEXT NOT NULL,
    embedding vector(384),
    rule_index INTEGER,
    rule_length INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS policy_rules_embedding_idx 
ON policy_rules USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

COMMENT ON TABLE policy_rules IS 'Policy rules with vector embeddings for semantic search';
COMMENT ON COLUMN policy_rules.embedding IS '384-dimensional embedding from all-MiniLM-L6-v2 model';
EOF
echo "✓ Tables and indexes created"
echo ""

# Check setup
echo "[5/5] Verifying setup..."
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -p $DB_PORT -d $DB_NAME << EOF
\dt
\di
SELECT COUNT(*) as rule_count FROM policy_rules;
EOF
echo "✓ Setup complete!"
echo ""
echo "=================================================="
echo "PostgreSQL + pgvector is ready!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "1. Run the Python backend: python backend_field_validator_pgvector.py"
echo "2. The API will automatically populate the database with embeddings"
echo "3. Access the API at http://localhost:5000"
echo ""

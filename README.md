# Policy Reinforcement Final

A comprehensive policy validation and normalization system using multi-stage processing pipeline.

## Features

- Document extraction and parsing (Stage 0)
- Clause extraction (Stage 1)
- Intent classification (Stage 2)
- Entity extraction (Stage 3) with retry logic
- Ambiguity flagging (Stage 4)
- Ambiguity clarification (Stage 5)
- DSL rule generation (Stage 6)
- Confidence and rationale generation (Stage 7)
- Policy normalization (Stage 8)

## Prerequisites

- Python 3.8+
- MongoDB running on `localhost:27017`
- Flask and dependencies (see `requirements.txt`)

## Setup

1. Start MongoDB:
```bash
mongod --dbpath /tmp/mongodb_data --fork
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Service

1. Navigate to the upload_service directory:
```bash
cd upload_service
```

2. Run the Flask application:
```bash
python3 app.py
```

3. Access the UI in your browser:
```
http://0.0.0.0:5000
```

Or use `http://localhost:5000` from the same machine.

## API Endpoints

- `POST /api/v1/upload` - Upload a document
- `GET /api/v1/documents/<document_id>` - Retrieve document
- `POST /api/v1/process-document/<document_id>` - Trigger pipeline
- `GET /api/v1/process-status/<document_id>` - Check pipeline status
- `GET /api/v1/normalized-policies` - Get normalized policies
- `POST /api/v1/approve-policies` - Approve policies

## Pipeline Configuration

- **Stage 3 Workers**: 8 (parallel entity extraction)
- **Stage 5 Workers**: 8 (parallel ambiguity clarification)
- **Retry Logic**: Exponential backoff for rate limits (up to 3 retries)


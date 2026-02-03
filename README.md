# Policy Reinforcement Final

A comprehensive policy validation and normalization system using multi-stage processing.

## Features

- Document extraction and parsing (Stage 0)
- Clause extraction (Stage 1)
- Intent classification (Stage 2)
- Entity extraction (Stage 3)
- Ambiguity flagging (Stage 4)
- Ambiguity clarification (Stage 5)
- DSL rule generation (Stage 6)
- Confidence and rationale generation (Stage 7)
- Policy normalization (Stage 8)

## Setup

MongoDB should be running on `localhost:27017`.

## Usage

Upload documents via the Flask API at `/api/v1/upload`.


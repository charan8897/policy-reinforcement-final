# Policy Field Validator - Chrome Extension

Real-time field validation against AstraZeneca travel policy using AI-powered semantic search.

## Installation

### 1. Load the Extension in Chrome

1. Open Chrome and go to `chrome://extensions/`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select the `chrome-extension` folder

### 2. Start the Backend API

```bash
cd /home/hutech/Documents/docupolicy/step2-realtime-validation
python3 backend_field_validator_v2.py
```

The API runs on `http://localhost:5000`

### 3. Use the Extension

- Browse any website
- Fill form fields related to travel (e.g., "group_size", "room_type", "flight_hours")
- **Blur the field** (click away) to trigger validation
- **Green ✓** = Valid
- **Red ✗** = Policy violation
- Click the badge to see detailed policy rules

## Features

✅ **Auto-monitors form fields** on any website
✅ **Semantic search** using ChromaDB + sentence-transformers
✅ **Real-time validation** against AstraZeneca policies
✅ **Detailed popups** showing applicable rules and reasoning
✅ **Policy field detection** - intelligently identifies fields to validate
✅ **Works offline** - embeddings cached locally
✅ **No API quota limits** - local ML models

## Monitored Fields

Policy fields automatically validated:
- `group_size` - Number of employees traveling together
- `flight_hours` - Flight duration (determines class of service)
- `class_of_service` - Cabin class (economy/business/first)
- `room_type` - Hotel room type (standard/suite)
- `booking_advance` - Days in advance (must be 2+ weeks)
- `booking_channel` - Booking method (AZ OBT/AZ TMC only)
- `destination` - Travel destination
- `travel_purpose` - Business justification
- `manager_approval` - Pre-approval status
- `employee_name` - Traveler profile validation

## API Endpoints

### Validate Field
```
POST http://localhost:5000/api/validate-field
Content-Type: application/json

{
  "field_name": "group_size",
  "field_value": "6",
  "previous_context": {}
}

Response:
{
  "field_name": "group_size",
  "field_value": "6",
  "status": "valid",
  "message": "Group size is within policy...",
  "rules": [...],
  "validation_details": {
    "search_method": "semantic_similarity",
    "top_matches": [...],
    "decision_reasoning": "..."
  }
}
```

### Health Check
```
GET http://localhost:5000/api/health

Response:
{
  "status": "ok",
  "rules_file_exists": true
}
```

## Extension Files

```
chrome-extension/
├── manifest.json          # Extension configuration
├── content.js            # Injected into web pages (monitors forms)
├── popup.html            # Extension popup UI
├── popup.js              # Popup logic
├── background.js         # Service worker (coordination)
├── icons/                # Extension icons
│   ├── icon-16.png
│   ├── icon-48.png
│   └── icon-128.png
└── README.md
```

## Architecture

```
User browses website
    ↓
Extension injects content.js
    ↓
User fills form field + blurs
    ↓
Content.js captures field value
    ↓
Sends to backend API (http://localhost:5000)
    ↓
Backend searches policy using ChromaDB + embeddings
    ↓
Gemini analyzes results & makes decision
    ↓
Returns validation result with rules
    ↓
Content.js displays badge + popup on page
    ↓
User sees ✓ (valid) or ✗ (violation)
```

## Validation Decision Logic

1. **Skip General Fields** - Form fields like email, phone, name (non-policy)
2. **Semantic Search** - Find relevant policy rules using vector similarity
3. **Analysis** - Gemini analyzes rules against field value
4. **Decision** - Returns valid/warning/error with reasoning
5. **Display** - Show badge with detailed validation result

## Performance

- **Local embeddings** - No API calls for search (offline capable)
- **Cached results** - Prevents duplicate API calls for same values
- **Batch processing** - ChromaDB handles large rule sets efficiently
- **HNSW index** - Fast vector similarity search (~ms latency)

## Troubleshooting

### Extension not working?
1. Check if backend API is running: `curl http://localhost:5000/api/health`
2. Check popup shows "API Status: Online"
3. Refresh the page with extension enabled

### No validation appearing?
1. Enable validation in popup (toggle switch)
2. Fill form field and blur (click away)
3. Check console for errors: Press F12 → Console tab

### Wrong validation results?
- Policy search may need refinement - ChromaDB semantic search learns over time
- Check `validation_api.log` for search patterns used

## Notes

- Extension works on **any website**
- Only validates fields with names matching policy context
- Results cached per session
- Backend must be running for validation to work

## License

Internal use only - AstraZeneca Travel Policy Validation

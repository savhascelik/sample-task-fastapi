# OpenRouter GPT-4o FastAPI Microservice

A FastAPI-based microservice that accepts user input, sends it to GPT-4o via OpenRouter, logs the response, and triggers an alert in n8n if there's an error.

## Features

- Accepts text input via REST API
- Forwards requests to OpenRouter API (supporting GPT-4o and similar models)
- Error handling with detailed logging
- n8n integration for error alerts
- Environment variable configuration
- Token limit management to prevent credit issues

## Installation

1. Clone the repository:
```bash
git clone https://github.com/savhascelik/sample-task-fastapi.git
cd sample-task-fastapi
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the project root:
```
OPENROUTER_API_KEY=your_openrouter_api_key
N8N_WEBHOOK_URL=your_n8n_webhook_url
```

## Running the Application

To start the application:

```bash
uvicorn main:app --reload
```

The application will run at http://127.0.0.1:8000 by default.

## API Usage

### Generate Text

```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/generate' \
  -H 'Content-Type: application/json' \
  -d '{
  "text": "Hello, how are you?"
}'
```

### Reload Environment Variables

If you change the `.env` file while the application is running, you can reload the environment variables without restarting:

```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/reload-env'
```

## Logging

The application logs are saved in the `logs` directory, with a filename format of `app_YYYY-MM-DD.log`. These logs contain detailed information about requests, responses, and any errors that occur.

To view the logs on Windows:
```bash
type logs\app_YYYY-MM-DD.log
```

To view the logs on Linux/Mac:
```bash
cat logs/app_YYYY-MM-DD.log
```

To monitor logs in real-time on Windows:
```bash
powershell -command "Get-Content -Path logs\app_YYYY-MM-DD.log -Wait"
```

To monitor logs in real-time on Linux/Mac:
```bash
tail -f logs/app_YYYY-MM-DD.log
```

## API Documentation

FastAPI provides automatic interactive API documentation:
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENROUTER_API_KEY` | Your OpenRouter API key | Yes |
| `N8N_WEBHOOK_URL` | URL for n8n webhook to trigger on errors | No |

## Error Handling

The application handles various error scenarios:
- OpenRouter API errors (authentication, rate limiting, etc.)
- Network errors
- Insufficient credits errors
- General server errors

Each error type has specific handling and appropriate HTTP status codes.

## License

MIT 
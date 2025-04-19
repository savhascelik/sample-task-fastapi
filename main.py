import os
import logging
import requests
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from dotenv import load_dotenv
import json # For formatting data to be sent to n8n
from typing import Optional, Dict, Any  # Import typing modules
import datetime  # For log filename

# Load variables from .env file
load_dotenv()

# --- Configuration ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
# IMPORTANT: The exact model name in OpenRouter may change.
# If 'openai/gpt-4.1' is not directly supported, you may need to use the closest equivalent
# (e.g., 'openai/gpt-4o', 'openai/gpt-4-turbo').
# Check the OpenRouter model list: https://openrouter.ai/models
TARGET_MODEL = "openai/gpt-4o" # OR "openai/gpt-4-turbo" or the closest available model
# Set max tokens to avoid credit issues (default is too high)
MAX_TOKENS = 1000

# Make sure API key and webhook URL are set
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable is not set.")
if not N8N_WEBHOOK_URL:
    raise ValueError("N8N_WEBHOOK_URL environment variable is not set.")

# --- Logging Settings ---
# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# Define log file name with current date
log_filename = f"logs/app_{datetime.datetime.now().strftime('%Y-%m-%d')}.log"

# Configure logging to write to both console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()  # Console handler
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Application started. Logs are being written to {os.path.abspath(log_filename)}")

# --- FastAPI Application ---
app = FastAPI(
    title="GPT-4.1 Microservice via OpenRouter",
    description="Accepts user input, queries OpenRouter, logs response, and alerts n8n on error.",
    version="1.0.0"
)

# --- Pydantic Models ---
class UserInput(BaseModel):
    text: str # Text input from the user

class GPTResponse(BaseModel):
    generated_text: str # Response to be returned in case of success

# --- Helper Functions ---
def trigger_n8n_alert(error_message: str, request_data: Optional[Dict[str, Any]] = None):
    """Triggers the n8n webhook in case of an error."""
    if not N8N_WEBHOOK_URL:
        logger.error("n8n webhook URL is not configured, alert cannot be sent.")
        return

    payload = {
        "error_source": "FastAPI GPT Service",
        "error_message": error_message,
        "original_request": request_data or {} # We can also send the original request
    }
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(N8N_WEBHOOK_URL, headers=headers, json=payload, timeout=10)
        response.raise_for_status() # If there's an error on n8n's side (e.g., 4xx, 5xx)
        logger.info(f"n8n alert sent successfully. Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error occurred while sending n8n alert: {e}")
    except Exception as e:
        logger.error(f"Unexpected error occurred while sending n8n alert: {e}")


# --- API Endpoint ---
@app.post("/generate", response_model=GPTResponse)
async def generate_text(user_input: UserInput, request: Request):
    """
    Takes user input, sends it to GPT-4.1 via OpenRouter,
    logs the response, and sends an alert to n8n in case of an error.
    """
    logger.info(f"Request received: {user_input.text[:50]}...") # Don't log the entire input for security reasons

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    # Message format to be sent to the OpenRouter API
    data = {
        "model": TARGET_MODEL,
        "messages": [
            {"role": "user", "content": user_input.text}
        ],
        "max_tokens": MAX_TOKENS  # Limit response tokens to avoid credit issues
    }

    try:
        # Send request to the OpenRouter API
        logger.info(f"Sending request to OpenRouter (Model: {TARGET_MODEL}, max_tokens: {MAX_TOKENS})...")
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=data, timeout=60) # Set timeout
        
        # Handle common API errors with better error messages
        if response.status_code == 402:
            error_data = response.json()
            error_msg = error_data.get('error', {}).get('message', 'Insufficient credits')
            logger.error(f"OpenRouter API credit error: {error_msg}")
            detail = f"OpenRouter API credit issue: {error_msg}. Please visit https://openrouter.ai/settings/credits to upgrade your account."
            raise HTTPException(status_code=402, detail=detail)
            
        response.raise_for_status() # Raise error for other HTTP error codes

        response_json = response.json()

        # Get the response (usually in this structure, check the API documentation)
        generated_content = response_json.get("choices", [{}])[0].get("message", {}).get("content")

        if not generated_content:
            logger.error("Could not get a valid response from OpenRouter. Response: %s", response_json)
            trigger_n8n_alert("Empty or invalid response received from OpenRouter.", data)
            raise HTTPException(status_code=500, detail="Could not get a valid response from API.")

        # Log the successful response
        logger.info(f"Response received from OpenRouter: {generated_content[:100]}...") # Log part of the response

        # Return the successful response
        return GPTResponse(generated_text=generated_content)

    except HTTPException:
        # Re-raise HTTPExceptions we created above
        raise

    except requests.exceptions.Timeout:
        error_msg = "OpenRouter API request timed out."
        logger.error(error_msg)
        trigger_n8n_alert(error_msg, data)
        raise HTTPException(status_code=504, detail=error_msg)

    except requests.exceptions.HTTPError as e:
        # Log HTTP errors in more detail (e.g., 401 Unauthorized, 429 Rate Limit)
        error_msg = f"OpenRouter API error: {e.response.status_code} - {e.response.text}"
        logger.error(error_msg)
        trigger_n8n_alert(f"OpenRouter API error: {e.response.status_code}", {"request": data, "response": e.response.text})
        
        # Provide more user-friendly error messages based on status code
        if e.response.status_code == 401:
            detail = "Authentication error: Your OpenRouter API key is invalid or expired. Please check your API key in the .env file."
        elif e.response.status_code == 403:
            detail = "Authorization error: You don't have permission to use this model or API. Please check your OpenRouter account."
        elif e.response.status_code == 429:
            detail = "Rate limit exceeded: You've sent too many requests to OpenRouter API. Please try again later."
        elif e.response.status_code == 500:
            detail = "OpenRouter API server error. Please try again later."
        else:
            detail = f"Error communicating with OpenRouter API: Status code {e.response.status_code}"
            
        raise HTTPException(status_code=502, detail=detail)

    except requests.exceptions.RequestException as e:
        error_msg = f"Network error while connecting to OpenRouter API: {e}"
        logger.error(error_msg)
        trigger_n8n_alert(f"Network error: {e}", data)
        raise HTTPException(status_code=503, detail=f"A network error occurred while connecting to the API. Please check your internet connection. Logs are saved in {log_filename}")

    except Exception as e:
        # All other unexpected errors
        error_msg = f"An unexpected error occurred: {e}"
        logger.exception(error_msg) # Use exception to log the traceback of the error
        trigger_n8n_alert(f"Unexpected server error: {type(e).__name__}", data)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred on the server. Please check the logs at {log_filename} for more details.")

# Add a new endpoint to reload environment variables
@app.post("/reload-env")
async def reload_environment():
    """Reloads environment variables from the .env file."""
    try:
        # Reload environment variables
        load_dotenv(override=True)
        
        # Update global variables
        global OPENROUTER_API_KEY, N8N_WEBHOOK_URL
        OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
        N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
        
        # Log the changes
        logger.info("Environment variables reloaded successfully")
        logger.info(f"Using OpenRouter API key ending with: ...{OPENROUTER_API_KEY[-5:] if OPENROUTER_API_KEY else 'None'}")
        logger.info(f"Using n8n webhook URL: {N8N_WEBHOOK_URL or 'None'}")
        
        return {"status": "success", "message": "Environment variables reloaded successfully"}
    except Exception as e:
        logger.error(f"Error reloading environment variables: {e}")
        raise HTTPException(status_code=500, detail=f"Error reloading environment variables: {str(e)}")

# To run the application with Uvicorn (in terminal):
# uvicorn main:app --reload
import os
import json
import requests

def handler(request):
    try:
        body = request.get_json()
        transcript = body.get("transcript", "")

        api_key = os.getenv("OPENROUTER_API_KEY")

        payload = {
            "model": "meta-llama/llama-3.1-8b-instruct:free",
            "messages": [
                {
                    "role": "system",
                    "content": "Analyze transcript and return signals."
                },
                {
                    "role": "user",
                    "content": transcript
                }
            ]
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload
        )

        return response.json()

    except Exception as e:
        return {
            "error": str(e)
        }
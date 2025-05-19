import requests
import os
import logging
from dotenv import load_dotenv 
load_dotenv()
def groq_call_llm(prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"}
    body = {
        "model": "llama3-8b-8192",
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        response = requests.post(url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]
        else:
            logging.error(f"No choices in API response: {data}")
            return "Error: No response from API."
    except requests.exceptions.RequestException as e:
        logging.error(f"API request failed: {e}")
        return f"Error: API request failed: {e}"

# from backend.app.services.groq_client import groq_call_llm
# import logging
# def call_llm(prompt):
#     logging.info("Calling LLM API")
#     try:
#         return groq_call_llm(prompt)
#     except Exception as e:
#         logging.error(f"Error calling LLM: {str(e)}")
#         return f"Error: Failed to get response from LLM: {str(e)}"





from backend.app.services.groq_client import groq_call_llm
import logging

MAX_CHUNK_SIZE = 2000  # Adjust if needed based on model limits

def chunk_text(text, max_size=MAX_CHUNK_SIZE):
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_size, len(text))
        if end < len(text):
            split_at = text.rfind(' ', start, end)
            if split_at != -1 and split_at > start:
                end = split_at
        chunks.append(text[start:end].strip())
        start = end
    return chunks

def call_llm(prompt):
    logging.info("Calling LLM API with chunking")
    try:
        chunks = chunk_text(prompt)
        responses = []
        for chunk in chunks:
            logging.info(f"Chunk size: {len(chunk)}")
            res = groq_call_llm(chunk)
            responses.append(res)
        return " ".join(responses)
    except Exception as e:
        logging.error(f"Error calling LLM: {str(e)}")
        return f"Error: Failed to get response from LLM: {str(e)}"

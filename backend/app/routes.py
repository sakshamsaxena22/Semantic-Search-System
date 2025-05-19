"""
API routes for the chatbot service
"""
from flask import request, jsonify, Blueprint
from backend.app.services.groq_client import groq_call_llm
import logging

# Create blueprint
bp = Blueprint('api', __name__)

@bp.route('/query', methods=['POST'])
def query():
    try:
        # Check if request.json exists before accessing it
        if not request.json:
            return jsonify({"error": "Request must be JSON"}), 400
            
        user_query = request.json.get('query')
        if not user_query:
            return jsonify({"error": "No query provided"}), 400
            
        # Add debug logging to help identify issues
        logging.debug(f"Processing query: {user_query}")
        
        response_text = groq_call_llm(user_query)
        
        # Add debug logging for the response
        logging.debug(f"LLM response: {response_text}")
        return jsonify({"answer": response_text})
    except Exception as e:
        # Add more detailed error logging
        logging.error(f"Error during query processing: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal Server Error"}), 500
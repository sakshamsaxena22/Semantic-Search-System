"""
API blueprint — currently a thin health-check/status namespace.
Core upload + query routes live in main.py (served at root).
"""
from flask import jsonify, Blueprint

bp = Blueprint("api", __name__)


@bp.route("/health", methods=["GET"])
def health():
    """Simple health-check endpoint for load balancers / uptime monitors."""
    return jsonify({"status": "ok"})
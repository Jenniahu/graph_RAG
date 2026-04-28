"""Entry point for graph analytics pipeline.

Usage:
    python graph_analytics.py
"""

from graph_rag import Pipeline

if __name__ == "__main__":
    Pipeline().run_all()

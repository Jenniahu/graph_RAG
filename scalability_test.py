"""Entry point for scalability and partition experiments.

Usage:
    python scalability_test.py
"""

from graph_rag.scalability import run_scaling_experiments, run_partition_experiments

if __name__ == "__main__":
    run_scaling_experiments()
    run_partition_experiments()

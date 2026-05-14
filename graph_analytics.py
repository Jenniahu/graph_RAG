"""Entry point for graph analytics pipeline.

Usage:
    python graph_analytics.py
    python graph_analytics.py --data-version v4
    python graph_analytics.py --data-version v5 --max-iter 20
    python graph_analytics.py --data-version input
"""

import argparse
from graph_rag import Pipeline, Config

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GraphRAG Analytics Pipeline")
    parser.add_argument("--data-version", choices=["v4", "v5", "input"], default="v5",
                        help="Which dataset version to use (default: v5)")
    parser.add_argument("--max-iter", type=int, default=None,
                        help="PageRank max iterations")
    parser.add_argument("--reset-prob", type=float, default=None,
                        help="PageRank reset probability")
    parser.add_argument("--no-filter", action="store_true",
                        help="Disable entity-only filtering (use full multilayer graph)")
    args = parser.parse_args()

    kwargs = {"data_version": args.data_version}
    if args.max_iter is not None:
        kwargs["max_iter"] = args.max_iter
    if args.reset_prob is not None:
        kwargs["reset_prob"] = args.reset_prob
    if args.no_filter:
        kwargs["filter_entity_only"] = False

    cfg = Config(**kwargs)
    Pipeline(cfg).run_all()

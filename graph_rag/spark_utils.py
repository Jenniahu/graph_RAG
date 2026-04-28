"""Spark session creation and management."""

import os
import sys

# Ensure Spark workers use the same Python as the driver
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)


def create_spark(cfg=None):
    """Create a SparkSession with GraphFrames support.

    Args:
        cfg: Config instance. Uses defaults if None.

    Returns:
        SparkSession with checkpoint dir already set.
    """
    from pyspark.sql import SparkSession

    if cfg is None:
        from .config import Config
        cfg = Config()

    spark = (SparkSession.builder
             .appName(cfg.app_name)
             .config("spark.jars.packages", cfg.graphframes_package)
             .config("spark.sql.shuffle.partitions", str(cfg.shuffle_partitions))
             .getOrCreate())
    spark.sparkContext.setCheckpointDir(cfg.checkpoint_dir)
    return spark

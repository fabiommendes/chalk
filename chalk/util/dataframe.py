from typing import Literal, get_args

import pandas as pd

__all__ = [
    "ALL_STATS",
    "DEFAULT_STATS",
    "grades_dataframe_stats",
    "Stats",
]

Stats = Literal["mean", "std", "min", "max", "median", "err%", "25%", "50%", "75%"]

ALL_STATS: set[Stats] = set(get_args(Stats))
DEFAULT_STATS = ("mean", "25%", "median", "75%")


def grades_dataframe_stats(
    df: pd.DataFrame,
    total: str | None = "total",
    skip_null: bool = False,
) -> pd.DataFrame:
    """
    Compute statistics for a grades dataframe.

    Args:
        df:
            A dataframe with grades for each student and question.
        total:
            The name of the column representing the total score. If provided,
            this column will be excluded from the statistics.
        skip_null:
            If True, rows with null values will be skipped when computing statistics.
    """
    df = df.apply(pd.to_numeric, errors="coerce")
    if not skip_null:
        df = df.fillna(0)

    stats = pd.DataFrame(index=df.columns)
    stats["25%"] = df.quantile(0.25)
    stats["median"] = stats["50%"] = df.median()
    stats["75%"] = df.quantile(0.75)

    stats["mean"] = df.mean()
    stats["std"] = df.std()
    stats["min"] = df.min()
    stats["max"] = df.max()
    stats["err%"] = (stats["std"] / stats["mean"]) * 100
    return stats

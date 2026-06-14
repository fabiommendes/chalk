from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from typing import (
    IO,
    Any,
    Callable,
    Iterable,
    Iterator,
    Literal,
    Mapping,
    Self,
    Sequence,
    TypeVar,
    cast,
    overload,
)

import natsort
import numpy as np
import pandas as pd
import rich
from rich.console import JustifyMethod
from rich.table import Table as RichTable

from .util.file import StreamLike, as_stream

__all__ = [
    "Table",
    "merge",
    "validate_table_format",
]


type RowsLike[T] = Sequence[Mapping[str, T]]
type ColumnsLike[T] = Mapping[str, Sequence[T]]
type ArrayLike[T] = Sequence[Sequence[T]]

type Row[T] = dict[str, T]
type Rows[T] = list[Row[T]]
type Columns[T] = dict[str, list[T]]
type Entries[Id, T] = dict[Id, dict[str, T]]

# Parameters
type RenderFn = Callable[[Any], str] | dict[type | str, Callable[[Any], str]]
type RowKey[T, Id] = str | Callable[[Id, Mapping[str, T]], Any]


DT = TypeVar("DT", str, float, int, bool, None)
NOT_GIVEN = object()


class Table[DT, Id: str = str](Mapping[Id, Row[DT]]):
    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> Self:
        new = object.__new__(cls)
        new._df = df
        return new

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(self._df.columns)

    @property
    def index(self) -> tuple[Id, ...]:
        return tuple(self._df.index)

    def __init__(
        self,
        data: RowsLike[DT] | ColumnsLike[DT] | ArrayLike[DT],
        *,
        index: Iterable[Id] | None = None,
        columns: Iterable[str] | None = None,
    ) -> None:
        df = pd.DataFrame(data)

        # Set index
        if index is not None:
            df.index = pd.Index(index, name="id")
        elif "id" in df.columns:
            df.set_index("id", inplace=True)
        else:
            df.index.name = "id"

        # Set column ordering
        if columns is not None and isinstance(data, Mapping):
            df = df[columns]
        elif columns is not None:
            df.columns = pd.Index(columns)

        self._df = df

    def __str__(self) -> str:
        return self._df.to_string()

    def __repr__(self) -> str:
        return f"Table({self._df.to_dict(orient='records')}, index={self._df.index.tolist()}, columns={self._df.columns.tolist()})"

    def __getitem__(self, id: Id) -> Row[DT]:
        return self._df.loc[id].replace({np.nan: None}).to_dict()  # type: ignore

    def __iter__(self) -> Iterator[Id]:
        return iter(self._df.index)

    def __len__(self) -> int:
        return len(self._df.index)

    def __bool__(self) -> bool:
        return len(self.index) > 0

    #
    # Internal utilities
    #
    def _df_with_nones(self, *, na: Any = None) -> pd.DataFrame:
        return self._df.replace({np.nan: na})

    #
    # Views
    #
    def iter_rows(self, *, na: Any = None) -> Iterator[dict[str, DT]]:
        for _, row in self._df.iterrows():
            yield cast(dict[str, DT], row.replace({np.nan: na}).to_dict())

    def iter_columns(self, *, na: Any = None) -> Iterator[tuple[str, list[DT]]]:
        for col in self._df.columns:
            yield (
                col,
                self._df[col].replace({np.nan: na}).tolist(),
            )

    @overload
    def iloc(self, row: int, /) -> Mapping[str, DT]: ...

    @overload
    def iloc(self, row: int, col: int, /) -> DT: ...

    def iloc(self, row: int, col: int | None = None, /) -> Any:
        if col is None:
            return self._df.iloc[row].replace({np.nan: None}).to_dict()  # type: ignore
        return self._df.iloc[row, col]

    #
    # Table conversions
    #
    def to_csv(self, file: StreamLike = None) -> None:
        with as_stream(file) as f:
            self._df.to_csv(f)

    def to_json(self, file: StreamLike = None) -> None:
        with as_stream(file) as f:
            self._df.to_json(f, orient="records", indent=2)

    def dump(
        self,
        file: IO[str] | Path | None = None,
        /,
        *,
        format: Literal["table", "csv", "json", "yaml"] | None = None,
        styles: None | dict[str, str] = None,
        names: None | dict[str, str] = None,
        align: None | dict[str, JustifyMethod] = None,
        render: RenderFn | None = None,
        sort: str | None = None,
        reverse: bool = False,
        empty: str = "[b yellow]Warning:[/] no data to display!",
    ) -> None:
        """
        Dump the table to a file or the console in the specified format.
        """
        if format is None and isinstance(file, Path):
            format = file.suffix[1:].lower()  # type: ignore
            if format not in {"csv", "json", "yaml", "yml"}:
                format = "table"
            else:
                msg = f"Could not infer format from file extension: {file.suffix}"
                raise ValueError(msg)
        elif format is None:
            format = "table"

        match format:
            case "table":
                with as_stream(file) as f:
                    with redirect_stdout(f):
                        self.render(
                            styles=styles,
                            names=names,
                            align=align,
                            sort=sort,
                            reverse=reverse,
                            render=render,
                            empty=empty,
                        )

            case "csv":
                with as_stream(file) as f:
                    self.to_csv(f)

            case "json":
                with as_stream(file) as f:
                    self.to_json(f)

            case "yaml" | "yml":
                import yaml

                data = cast(Any, self.to_dicts(clear_nones=True))
                with as_stream(file) as f:
                    yaml.dump(data, f)

            case _:
                msg = f"{format.upper()} output is not yet implemented"
                raise NotImplementedError(msg)

    def render(
        self,
        styles: None | dict[str, str] = None,
        names: None | dict[str, str] = None,
        align: None | dict[str, JustifyMethod] = None,
        sort: str | None = None,
        reverse: bool = False,
        render: RenderFn | None = None,
        title: str | None = None,
        empty: str = "[b yellow]Warning:[/] no data to display!",
    ) -> None:
        """
        Render a table to the console using Rich.
        """
        if not bool(self):
            rich.print(empty)
            return

        data = self

        if sort in ("id", None):
            df = data._df
            sort_key = df.index.map(lambda id: str(id).casefold())
            indexes = natsort.index_humansorted(sort_key, reverse=reverse)
            data = data.from_dataframe(df.iloc[indexes])
        elif sort is not None:
            data = data.order_by(
                lambda id, row: (
                    (
                        cell := render_with(row.get(sort), column=sort, render=render)
                        or ""
                    )
                    and cell.casefold()
                ),
                reverse=reverse,
            )

        table = RichTable(title=title)

        styles = styles or {}
        names = names or {}
        align = align or {}

        table.add_column(
            names.get("id", "id"),
            style=styles.get("id"),
            justify=align.get("id", "left"),
        )
        for column in data.columns:
            table.add_column(
                names.get(column, column),
                style=styles.get(column),
                justify=align.get(column, "left"),
            )

        for id, row in data.items():
            cells: list[str] = [render_with(id, column="id", render=render)]
            for column in data.columns:
                cell = row.get(column)
                cells.append(render_with(cell, column=column, render=render))
            table.add_row(*cells)

        rich.print(table)

    def to_dicts(self, clear_nones: bool = False) -> list[dict[str, DT]]:
        result = cast(Rows[DT], self._df_with_nones().to_dict(orient="records"))
        if clear_nones:
            return [{k: v for k, v in row.items() if v is not None} for row in result]
        return result

    def to_indexed_data(self, clear_nones: bool = False) -> dict[Id, dict[str, DT]]:
        result = cast(Entries[Id, DT], self._df_with_nones().to_dict(orient="index"))
        if clear_nones:
            return {
                id: {k: v for k, v in row.items() if v is not None}
                for id, row in result.items()
            }
        return result

    def to_dataframe(self) -> pd.DataFrame:
        return self._df.copy()

    #
    # Table info and statistics
    #
    def active_columns(self) -> set[str]:
        """
        Get the active columns from the data by returning the keys that have
        non-None values.
        """
        columns: set[str] = set()
        for row in self.values():
            columns.update(k for k, v in row.items() if v is not None)
        return columns

    #
    # Table transformations
    #
    def select_columns(self, columns: Iterable[str] | Callable[[str], bool]) -> Self:
        """
        Return a new table with only the specified columns.
        """
        if callable(columns):
            columns = [col for col in self.columns if columns(col)]
        return self.from_dataframe(self._df[list(columns)])

    def select_rows(self, ids: Iterable[Id] | Callable[[Id, Row[DT]], bool]) -> Self:
        """
        Return a new table with only the specified rows.
        """
        if callable(ids):
            fn = ids
            ids = [id for id, row in self.items() if fn(id, row)]
        return self.from_dataframe(self._df.loc[list(ids)])

    def clean(
        self,
        *,
        keep: set[str] | None = None,
        remove: set[str] | None = None,
    ) -> Self:
        """
        Return a cleaned copy of the table by removing empty columns.

        Args:
            table: The table data as a list of dictionaries.
            keep: A set of column names to always keep even if they are empty.
            remove: A set of column names to remove even if they are not empty.
        """
        if keep is None:
            keep = self.active_columns()
        else:
            keep = self.active_columns() | keep
        keep = keep - (remove or set())

        columns = [k for k in self.columns if k in keep]
        return self.from_dataframe(self._df[columns])

    def order_by(self, key: RowKey[DT, Id], reverse: bool = False) -> Self:
        """
        Return a copy of the table ordered by the specified key function.
        """
        if isinstance(key, str):
            return self.from_dataframe(self._df.sort_values(key, ascending=not reverse))

        data = [key(id, item) for id, item in self.items()]
        df = self._df.copy()
        df["__sort_key"] = data
        df.sort_values("__sort_key", inplace=True, ascending=not reverse)
        df.drop(columns="__sort_key", inplace=True)
        return self.from_dataframe(df)


def merge[T, Id: str](a: Table[T, Id], b: Table[T, Id], /) -> Table[T, Id]:
    """
    Merge the columns from two lists of dictionaries by returning a new list of
    dictionaries containing the union of the keys from both lists.

    The values from the second list will overwrite the values from the first
    list if there are duplicate keys.
    """
    a_data = a.to_indexed_data()
    b_data = b.to_indexed_data()

    rows: list[dict[str, T]] = []
    ids: list[Id] = []
    while a_data:
        id, data = a_data.popitem()
        if id in b_data:
            data = {**data, **b_data.pop(id)}
        rows.append(data)
        ids.append(id)

    for id, data in b_data.items():
        rows.append(data)
        ids.append(id)

    columns = [*a.columns, *(col for col in b.columns if col not in a.columns)]
    return Table(rows, columns=columns, index=ids)


#
# Utilities
#


def validate_table_format(format: str) -> Literal["table", "csv", "json", "yaml"]:
    """
    Validate the table format by checking if it is one of the supported formats.
    """
    format = format.lower()
    if format not in {"table", "csv", "json", "yaml"}:
        raise ValueError(f"Invalid table format: {format}")
    return cast(Literal["table", "csv", "json", "yaml"], format)


def render_with(
    value: Any,
    /,
    column: str,
    render: RenderFn | None = None,
) -> str:
    """
    Render a cell value by using the render function for the column or type if provided.
    """
    from .core.grade import get_precision

    if value is None:
        return "[red]-[/]"
    if isinstance(value, bool):
        return "[green]Yes[/]" if value else "[red]No[/]"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (float, Decimal)):
        data = f"{{value:.{get_precision()}f}}".format(value=value)
        if value == 0:
            return f"[dim]{data}[/]"
        if value < 0:
            return f"[red]{data}[/]"
        return data
    if render is None:
        return str(value)
    elif callable(render):
        return render(value)
    elif column in render:
        return render[column](value)
    elif (typ := type(value)) in render:
        return render[typ](value)
    else:
        return str(value)

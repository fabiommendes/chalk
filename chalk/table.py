from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import redirect_stdout
from decimal import Decimal
from numbers import Number
from pathlib import Path
from typing import (
    IO,
    Any,
    Literal,
    Self,
    TypeVar,
    cast,
    overload,
)
from warnings import deprecated

import natsort
import numpy as np
import pandas as pd
import rich
from rich.console import JustifyMethod, RenderableType
from rich.table import Table as RichTable
from rich.text import Text

from .util import clean_data
from .util.path import StreamLike, as_stream

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
type RowKey[Id, T] = str | RowKeyFn[Id, T]
type RowKeyFn[Id, T] = Callable[[Id, Row[T]], Any]

DT = TypeVar("DT", str, float, int, bool, None)
NOT_GIVEN = object()


class Table[DT, Id: str = str](Mapping[Id, Row[DT]]):
    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, /) -> Self:
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

    def __rich__(self) -> RenderableType:
        return self.render()

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
        extra_rows: Iterable[dict[str, Any]] | None = None,
    ) -> None:
        """
        Dump the table to a file or the console in the specified format.
        """
        if format is None and isinstance(file, Path):
            suffix = file.suffix[1:].lower()
            format = suffix if suffix in {"csv", "json", "yaml", "yml"} else "table"  # type: ignore
        elif format is None:
            format = "table"

        if format != "table" and sort is not None:
            return self.sorted(sort, reverse=reverse, render=render).dump(
                file, format=format, extra_rows=extra_rows
            )

        if extra_rows and not format == "table":
            out = self
            for row in extra_rows:
                out = out.append(row)
            return out.dump(
                file,
                format=format,
                styles=styles,
                names=names,
                align=align,
                render=render,
                sort=sort,
                reverse=reverse,
                empty=empty,
            )

        match format:
            case "table":
                with as_stream(file) as f:
                    with redirect_stdout(f):
                        self.print(
                            styles=styles,
                            names=names,
                            align=align,
                            sort=sort,
                            reverse=reverse,
                            render=render,
                            empty=empty,
                            extra_rows=extra_rows,
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
                msg = f"{format.upper()} output is not supported"
                raise ValueError(msg)

    @deprecated("Use rich.print(table.render()) instead.")
    def print(
        self,
        styles: None | dict[str, str] = None,
        names: None | dict[str, str] = None,
        align: None | dict[str, JustifyMethod] = None,
        sort: str | None = None,
        reverse: bool = False,
        render: RenderFn | None = None,
        title: str | None = None,
        empty: RenderableType = Text.assemble(("Warning:", "bold yellow"), " no data to display!"),
        extra_rows: Iterable[dict[str, Any]] | None = None,
    ) -> None:
        """
        Render a table to the console using Rich.
        """
        rich.print(
            self.render(
                styles=styles,
                names=names,
                align=align,
                sort=sort,
                reverse=reverse,
                render=render,
                title=title,
                empty=empty,
                extra_rows=extra_rows,
            )
        )

    def render(
        self,
        styles: None | dict[str, str] = None,
        names: None | dict[str, str] = None,
        align: None | dict[str, JustifyMethod] = None,
        sort: str | None = None,
        reverse: bool = False,
        render: RenderFn | None = None,
        title: str | None = None,
        empty: RenderableType = Text.assemble(("Warning:", "bold yellow"), " no data to display!"),
        extra_rows: Iterable[dict[str, Any]] | None = None,
    ) -> RichTable | RenderableType:
        """
        Render a table to the console using Rich.
        """
        if not bool(self):
            return empty

        data = self.sorted(sort, reverse=reverse, render=render)

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

        for i, (id, row) in enumerate(data.items()):
            cells: list[str] = [render_with(id, column="id", render=render)]
            for column in data.columns:
                cell = row.get(column)
                cells.append(render_with(cell, column=column, render=render))
            table.add_row(*cells, end_section=(i == len(data) - 1) and extra_rows is not None)

        for extra_row in extra_rows or []:
            cells = [render_with(extra_row.get("id"), column="id", render=render)]
            for column in data.columns:
                cell = extra_row.get(column)
                cells.append(render_with(cell, column=column, render=render))
            table.add_row(*cells)

        return table

    def to_dicts(self, *, clear_nones: bool = False, drop_id: bool = False) -> list[dict[str, DT]]:
        df = self._df_with_nones()
        result = df.to_dict(orient="records")

        if not drop_id:
            for id, row in zip(self.index, result):
                row["id"] = id

        if clear_nones:
            result = [clean_data(row) for row in result]

        return cast(Rows[DT], result)

    def to_indexed_data(self, clear_nones: bool = False) -> dict[Id, dict[str, DT]]:
        result = cast(Entries[Id, DT], self._df_with_nones().to_dict(orient="index"))
        if clear_nones:
            return {
                id: {k: v for k, v in row.items() if v is not None} for id, row in result.items()
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

    def get_column(self, column: str, default: DT | None = None) -> list[DT]:
        """
        Get a column from the table by name, returning a list of values.
        """
        if column not in self.columns:
            if default is not None:
                return [default] * len(self)
            raise KeyError(f"Column '{column}' does not exist in the table.")
        return self._df[column].replace({np.nan: None}).tolist()  # type: ignore

    def clean(
        self,
        *,
        keep: set[str] | None = None,
        remove: set[str] | None = None,
    ) -> Self:
        """
        Return a cleaned copy of the table by removing empty columns.

        Args:
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

    def sorted(
        self, sort: str | None, /, *, reverse: bool = False, render: RenderFn | None = None
    ) -> Self:
        """
        Return a copy sorted by a column, or by id when sort is None or "id".
        Numbers sort by value, other cells by their rendered text.
        """
        if sort in ("id", None):
            sort_key = self._df.index.map(lambda id: str(id).casefold())
            indexes = natsort.index_humansorted(sort_key, reverse=reverse)
            return self.from_dataframe(self._df.iloc[indexes])

        def sort_with(id: Id, row: Row[DT], /) -> Any:
            value = row.get(sort)
            if isinstance(value, Number) and not isinstance(value, bool):
                if value != value:  # NaN is a missing value
                    return (False, 1, 0, "")
                return (True, 0, value, "")
            cell = render_with(value, column=sort, render=render) or ""
            return (value is not None, 1, 0, cell.casefold())

        return self.order_by(sort_with, reverse=reverse)

    def order_by(self, key: RowKey[Id, DT], /, reverse: bool = False) -> Self:
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

    def append(self, row: Row[DT], /) -> Self:
        """
        Return a new table with the specified row appended to the end.
        """
        row = dict(row)
        id: Any = row.pop("id", None)
        if id is None:
            id = len(self._df)
        df = self._df.copy()
        df = pd.concat([df, pd.DataFrame([row], index=[str(id)])], ignore_index=False)
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
    from .core.decimal import render_decimal

    if value is None:
        return "[red]-[/]"
    if isinstance(value, bool):
        return "[green]Yes[/]" if value else "[red]No[/]"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (float, Decimal)):
        data = render_decimal(value)
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

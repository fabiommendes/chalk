from decimal import Decimal
from typing import Iterable, Protocol

from rich.columns import Columns
from rich.console import Group, RenderableType
from rich.layout import Layout
from rich.text import Text

from ..core.models import QuestionId

type RenderableField = RenderableType | bool | None


class RenderableQuestion[Answer](Protocol):
    @property
    def id(self) -> QuestionId: ...

    @property
    def value(self) -> Decimal: ...

    @property
    def name(self) -> str: ...

    def render(self, plain: bool = False) -> RenderableType:
        """
        Render the question in the console.
        """

        return Group(*self._render_base_sections(plain=plain))

    def _render_base_sections(self, plain: bool = False) -> Iterable[RenderableType]:
        """
        Implement each part of the resulting Group() renderable.
        """
        if self.name and self.name != self.id:
            yield Text.assemble((self.name, "yellow bold underline"), (f" ({self.id})", "dim"))
        else:
            yield Text(self.name, style="yellow bold underline")

        for name, value in self._render_base_fields(plain=plain):
            if value is False or value is None or value == "":
                continue
            yield render_field(name, value, plain=plain)

    def _render_base_fields(self, plain: bool = False) -> Iterable[tuple[str, RenderableField]]:
        """
        Render the fields of the question in the console.
        """
        if typ := getattr(self, "type", None):
            yield "type", typ

        if value := getattr(self, "value", None):
            yield "value", str(value)

    def render_answer(self, answer: Answer, plain: bool = False) -> RenderableType:
        """
        Display the answer to the question in the console.
        """
        if answer is None:
            return Text("No answer provided.", style="italic")

        if isinstance(answer, str):
            return Text(answer)

        if isinstance(answer, (list, set)):
            answers = [str(a) for a in answer]
            chars = sum(len(a) for a in answers) + len(answers) - 1
            if chars < 80:
                return Text(", ".join(answers))
            layout = Layout()
            layout.split_column(
                *[Text(f"- {a}") for a in answers],
            )
            return layout

        if isinstance(answer, dict):
            answers = [f"{k}: {v}" for k, v in answer.items()]
            chars = sum(len(a) for a in answers) + len(answers) - 1
            if chars < 80:
                return Text(", ".join(answers))
            layout = Layout()
            layout.split_column(
                *[Text(f"- {a}") for a in answers],
            )
            return layout

        return Text(str(answer))

    def __rich__(self) -> RenderableType:
        return self.render(plain=True)


def render_field(name: str, value: RenderableField, plain: bool = False) -> RenderableType:
    """
    Render a field in the console.
    """

    if not value:
        return ""
    elif value is True:
        return Text(name, style="bold green")
    elif value is False:
        return Text(f"{name}: No", style="bold red")

    if isinstance(value, str):
        value = Text(value)
    if not name:
        return value

    return Columns([Text("  " + name.ljust(8), style="bold cyan"), value])

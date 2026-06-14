from typing import Any, Protocol


class Grader(Protocol):
    def can_grade(self, data: Any) -> bool:
        raise NotImplementedError("Subclasses must implement the can_grade method.")

    def grade(self, data: Any) -> float:
        raise NotImplementedError("Subclasses must implement the grade method.")

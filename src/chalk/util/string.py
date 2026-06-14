def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    """
    Return the singular or plural form of a word based on the count.

    If the plural form is not provided, it defaults to the singular form with an "s" appended.
    """
    if count == 1:
        return singular
    elif plural is not None:
        return plural
    else:
        return singular + "s"


def truncate_lines(text: str, max_lines: int) -> str:
    """
    Truncate a string to a maximum number of lines, adding an ellipsis if
    truncated.

    The ellipsis is counted as one of the lines, so the total number of lines in
    the output will not exceed max_lines.
    """
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    else:
        return "\n".join(lines[: max_lines - 1]) + "\n..."

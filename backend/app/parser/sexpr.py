"""Minimal S-expression reader for KiCad's `.kicad_pcb` / `.kicad_pro` /
`.kicad_sch` text format.

KiCad's file formats are plain S-expressions: `(token child1 child2 ...)`
where children are either atoms (bare words, quoted strings, numbers) or
nested lists. This module turns that text into a plain Python tree of
`list`/`str`/`float` so `kicad_project.py` can walk it without re-deriving
a tokenizer.
"""

from __future__ import annotations

Atom = str | float
SExpr = list["SExpr | Atom"]


def parse(text: str) -> SExpr:
    """Parse a full `.kicad_pcb`-style S-expression document.

    Returns the top-level list, e.g. `["kicad_pcb", ["version", 20240108], ...]`.
    """
    tokens = _tokenize(text)
    pos = 0
    expr, pos = _read(tokens, pos)
    return expr


def find_all(expr: SExpr, tag: str) -> list[SExpr]:
    """Return every direct or nested child list whose first element is `tag`."""
    matches: list[SExpr] = []
    for item in expr:
        if isinstance(item, list):
            if item and item[0] == tag:
                matches.append(item)
            matches.extend(find_all(item, tag))
    return matches


def find_first(expr: SExpr, tag: str) -> SExpr | None:
    for item in expr:
        if isinstance(item, list) and item and item[0] == tag:
            return item
    return None


def child_values(expr: SExpr, tag: str) -> list[Atom]:
    """For a child list `(tag v1 v2 ...)`, return `[v1, v2, ...]`, or `[]`."""
    child = find_first(expr, tag)
    return child[1:] if child else []


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c in "()":
            tokens.append(c)
            i += 1
        elif c == '"':
            j = i + 1
            buf = ['"']
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            buf.append('"')
            tokens.append("".join(buf))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in " \t\r\n()":
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _read(tokens: list[str], pos: int) -> tuple[SExpr | Atom, int]:
    tok = tokens[pos]
    if tok == "(":
        items: SExpr = []
        pos += 1
        while tokens[pos] != ")":
            item, pos = _read(tokens, pos)
            items.append(item)
        return items, pos + 1
    if tok == ")":
        raise ValueError("unexpected ')' in KiCad S-expression")
    return _atom(tok), pos + 1


def _atom(tok: str) -> Atom:
    if tok.startswith('"') and tok.endswith('"'):
        return tok[1:-1]
    try:
        return float(tok)
    except ValueError:
        return tok

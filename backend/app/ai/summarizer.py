"""Builds the compact structured digest sent to Claude: board size, layer
count, trace statistics, via count, power/ground nets, detected problems,
component summary, routing metrics, clock nets, connector locations, power
tree. This is the privacy/cost boundary -- raw geometry never leaves the
backend."""

from app.models.board import Board
from app.models.issue import Issue


def summarize(board: Board, issues: list[Issue]) -> dict:
    raise NotImplementedError

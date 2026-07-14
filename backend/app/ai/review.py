"""Sends the board digest (from summarizer.py) to Claude for a senior-PCB-
engineer-style narrative review, and answers grounded follow-up questions for
the optional AI chat panel."""


def generate_review(digest: dict) -> str:
    raise NotImplementedError


def answer_question(digest: dict, question: str) -> str:
    raise NotImplementedError

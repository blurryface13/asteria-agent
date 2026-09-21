"""Intentionally incomplete local example for the research-handoff acceptance case.

This file is read as data. The evaluation does not execute it or install torch.
"""

def attention(query, key, value):
    weights = (query @ key.transpose(-2, -1)).softmax(dim=-1)
    return weights @ value

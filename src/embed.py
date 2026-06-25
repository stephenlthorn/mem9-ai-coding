"""Client-side embeddings for the local tiup target.

Cloud (mem9.ai) embeds server-side with EMBED_TEXT and never calls this module.
Local uses fastembed when installed; otherwise a deterministic hash-based fallback
keeps the demo and the test suite runnable with no heavy dependency.
"""
from __future__ import annotations

import hashlib
import os

CLOUD_MODEL = "tidbcloud_free/amazon/titan-embed-text-v2"
CLOUD_DIMS = 1024

LOCAL_MODEL = os.environ.get("MEM9_LOCAL_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
LOCAL_DIMS = 384

_model = None


def dims(target: str) -> int:
    return CLOUD_DIMS if target == "cloud" else LOCAL_DIMS


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=LOCAL_MODEL)
    return _model


def encode_one(text: str) -> list[float]:
    """Return a LOCAL_DIMS embedding for `text`. Uses fastembed if available,
    else a deterministic pseudo-embedding (offline/test safe)."""
    try:
        import fastembed  # noqa: F401
        vec = next(iter(_get_model().embed([text])))
        return [float(x) for x in vec]
    except Exception:
        return _fallback(text, LOCAL_DIMS)


def _fallback(text: str, n: int) -> list[float]:
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    out: list[float] = []
    counter = 0
    while len(out) < n:
        block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for i in range(0, len(block), 4):
            if len(out) >= n:
                break
            raw = int.from_bytes(block[i:i + 4], "big") / 2**32
            out.append(round(raw * 2.0 - 1.0, 6))
        counter += 1
    return out


def to_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"

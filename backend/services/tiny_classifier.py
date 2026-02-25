"""
Trinity — Tiny Byte-Level Transformer Classifiers

Pure numpy inference for query classification and tool detection.
Models are trained in PyTorch (scripts/train_classifiers.py) and exported
as numpy .npz files (<200KB each).

Architecture:
  - Input: raw UTF-8 bytes (vocab_size=256, no tokenizer)
  - 2-layer transformer: 64-dim embeddings, 4 heads, 128-dim FFN
  - Max sequence: 256 bytes
  - ~50K parameters, <1ms on CPU

Public API:
  - classify_query(text) → (label, confidence)
  - detect_tools(text, threshold) → [tool_names]
"""

import logging
import os
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model paths
# ---------------------------------------------------------------------------

_MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
_QUERY_MODEL_PATH = os.path.join(_MODEL_DIR, "query_classifier.npz")
_TOOL_MODEL_PATH = os.path.join(_MODEL_DIR, "tool_detector.npz")
_INJECTION_MODEL_PATH = os.path.join(_MODEL_DIR, "injection_detector.npz")

# ---------------------------------------------------------------------------
# Class labels
# ---------------------------------------------------------------------------

QUERY_CLASSES = [
    "smalltalk",
    "disclosure",
    "code",
    "lightweight",
    "memory_recall",
    "preference",
    "general",
]

TOOL_CLASSES = [
    "calculator",
    "web_search",
    "document_search",
    "code_display",
    "fact_check",
    "recall_memory",
    "forget_memory",
    "save_memory",
    "search_memory",
    "update_memory",
    "read_file",
    "write_file",
    "list_directory",
    "search_codebase",
    "run_command",
    "no_tool",
]

INJECTION_CLASSES = ["benign", "injection", "jailbreak"]


# ---------------------------------------------------------------------------
# ByteTransformer — pure numpy inference
# ---------------------------------------------------------------------------


class ByteTransformer:
    """Minimal 2-layer transformer operating on raw UTF-8 bytes.

    Pure numpy — no PyTorch/TensorFlow at runtime.
    Training uses PyTorch (separate script) and exports weights as .npz.
    """

    def __init__(self, weights: dict, n_layers: int = 2, n_heads: int = 4):
        self.weights = weights
        self.n_layers = n_layers
        self.n_heads = n_heads
        # Infer d_model from embedding shape
        self.d_model = weights["token_embedding"].shape[1]
        self.head_dim = self.d_model // n_heads

    @classmethod
    def load(cls, path: str) -> "ByteTransformer":
        """Load model from .npz file."""
        data = np.load(path, allow_pickle=False)
        weights = {k: data[k] for k in data.files}
        return cls(weights)

    MAX_SEQ = 256  # Must match training

    def forward(self, text: str) -> np.ndarray:
        """Run inference on raw text. Returns logits (unnormalized scores)."""
        # Encode to bytes, pad/truncate to MAX_SEQ (matches training)
        raw = text.encode("utf-8")[:self.MAX_SEQ]
        byte_ids = np.zeros(self.MAX_SEQ, dtype=np.int64)
        for i, b in enumerate(raw):
            byte_ids[i] = b

        x = self._embed(byte_ids)

        for layer in range(self.n_layers):
            # Pre-norm attention + residual
            normed = self._layer_norm(x, f"layer{layer}_ln1")
            attn_out = self._attention(normed, layer)
            x = x + attn_out

            # Pre-norm FFN + residual
            normed = self._layer_norm(x, f"layer{layer}_ln2")
            ffn_out = self._ffn(normed, layer)
            x = x + ffn_out

        # Global average pool → classifier head
        pooled = x.mean(axis=0)
        logits = pooled @ self.weights["classifier_W"] + self.weights["classifier_b"]
        return logits

    # --- Internal layers ---

    def _embed(self, byte_ids: np.ndarray) -> np.ndarray:
        token_emb = self.weights["token_embedding"][byte_ids.astype(int)]
        pos_emb = self.weights["pos_embedding"][:len(byte_ids)]
        return token_emb + pos_emb

    def _attention(self, x: np.ndarray, layer: int) -> np.ndarray:
        Wq = self.weights[f"layer{layer}_Wq"]
        Wk = self.weights[f"layer{layer}_Wk"]
        Wv = self.weights[f"layer{layer}_Wv"]
        Wo = self.weights[f"layer{layer}_Wo"]

        seq_len = x.shape[0]
        Q = x @ Wq
        K = x @ Wk
        V = x @ Wv

        # Reshape for multi-head: (n_heads, seq, head_dim)
        Q = Q.reshape(seq_len, self.n_heads, self.head_dim).transpose(1, 0, 2)
        K = K.reshape(seq_len, self.n_heads, self.head_dim).transpose(1, 0, 2)
        V = V.reshape(seq_len, self.n_heads, self.head_dim).transpose(1, 0, 2)

        # Scaled dot-product attention
        scale = self.head_dim ** -0.5
        scores = (Q @ K.transpose(0, 2, 1)) * scale
        attn = _softmax(scores, axis=-1)
        out = attn @ V

        # Concatenate heads
        out = out.transpose(1, 0, 2).reshape(seq_len, self.d_model)
        return out @ Wo

    def _ffn(self, x: np.ndarray, layer: int) -> np.ndarray:
        W1 = self.weights[f"layer{layer}_W1"]
        b1 = self.weights[f"layer{layer}_b1"]
        W2 = self.weights[f"layer{layer}_W2"]
        b2 = self.weights[f"layer{layer}_b2"]

        h = x @ W1 + b1
        h = h * _sigmoid(1.702 * h)  # GELU approximation
        return h @ W2 + b2

    def _layer_norm(self, x: np.ndarray, name: str) -> np.ndarray:
        gamma = self.weights[f"{name}_gamma"]
        beta = self.weights[f"{name}_beta"]
        mean = x.mean(axis=-1, keepdims=True)
        var = x.var(axis=-1, keepdims=True)
        return gamma * (x - mean) / np.sqrt(var + 1e-5) + beta


# ---------------------------------------------------------------------------
# Math utilities
# ---------------------------------------------------------------------------


def _softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    e = np.exp(x - x.max(axis=axis, keepdims=True))
    return e / e.sum(axis=axis, keepdims=True)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -88, 88)))


# ---------------------------------------------------------------------------
# Singleton model instances
# ---------------------------------------------------------------------------

_query_model: Optional[ByteTransformer] = None
_tool_model: Optional[ByteTransformer] = None
_injection_model: Optional[ByteTransformer] = None


def _get_query_model() -> Optional[ByteTransformer]:
    global _query_model
    if _query_model is None and os.path.exists(_QUERY_MODEL_PATH):
        try:
            _query_model = ByteTransformer.load(_QUERY_MODEL_PATH)
            logger.info("Loaded query classifier from %s", _QUERY_MODEL_PATH)
        except Exception as e:
            logger.warning("Failed to load query classifier: %s", e)
    return _query_model


def _get_tool_model() -> Optional[ByteTransformer]:
    global _tool_model
    if _tool_model is None and os.path.exists(_TOOL_MODEL_PATH):
        try:
            _tool_model = ByteTransformer.load(_TOOL_MODEL_PATH)
            logger.info("Loaded tool detector from %s", _TOOL_MODEL_PATH)
        except Exception as e:
            logger.warning("Failed to load tool detector: %s", e)
    return _tool_model


def _get_injection_model() -> Optional[ByteTransformer]:
    global _injection_model
    if _injection_model is None and os.path.exists(_INJECTION_MODEL_PATH):
        try:
            _injection_model = ByteTransformer.load(_INJECTION_MODEL_PATH)
            logger.info("Loaded injection detector from %s", _INJECTION_MODEL_PATH)
        except Exception as e:
            logger.warning("Failed to load injection detector: %s", e)
    return _injection_model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_query(text: str) -> Tuple[str, float]:
    """Classify a query into one of QUERY_CLASSES.

    Returns:
        (class_name, confidence) tuple.
        If model is unavailable, returns ("general", 0.0).
    """
    model = _get_query_model()
    if model is None:
        return ("general", 0.0)

    logits = model.forward(text)
    probs = _softmax(logits)
    idx = int(np.argmax(probs))
    return (QUERY_CLASSES[idx], float(probs[idx]))


def detect_tools(text: str, threshold: float = 0.5) -> List[str]:
    """Detect which tool a query needs (multi-class, softmax).

    Returns:
        List with the predicted tool name if confidence > threshold,
        or [] if "no_tool" is predicted or model is unavailable.
    """
    model = _get_tool_model()
    if model is None:
        return []

    logits = model.forward(text)
    probs = _softmax(logits)
    idx = int(np.argmax(probs))
    label = TOOL_CLASSES[idx]
    confidence = float(probs[idx])

    if label == "no_tool" or confidence < threshold:
        return []
    return [label]


def detect_injection(text: str, threshold: float = 0.95) -> Tuple[bool, float]:
    """Detect prompt injection or jailbreak attempts.

    Uses a ByteTransformer trained on injection/jailbreak/benign examples.
    High threshold (0.95) ensures low false-positive rate — a benign query
    misclassified as injection would block a legitimate user.

    Returns:
        (is_injection, confidence) tuple.
        If model is unavailable, returns (False, 0.0) — fail-open.
    """
    model = _get_injection_model()
    if model is None:
        return (False, 0.0)

    logits = model.forward(text)
    probs = _softmax(logits)
    idx = int(np.argmax(probs))
    label = INJECTION_CLASSES[idx]
    confidence = float(probs[idx])

    if label in ("injection", "jailbreak") and confidence >= threshold:
        logger.warning(
            "Injection detected: label=%s confidence=%.3f query=%.80s",
            label, confidence, text,
        )
        return (True, confidence)

    return (False, confidence)

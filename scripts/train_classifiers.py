#!/usr/bin/env python3
"""
Train tiny byte-level transformers for Trinity query classification.

Uses PyTorch for training, exports to numpy .npz for inference.
The .npz files are the only artifact — PyTorch is NOT needed at runtime.

Usage:
    pip install torch  # Dev dependency only
    cd backend && python3 ../scripts/generate_training_data.py
    python3 ../scripts/train_classifiers.py

Output:
    backend/models/query_classifier.npz  (~150KB)
    backend/models/tool_detector.npz     (~180KB)
"""

import json
import os
import sys
import time

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ImportError:
    print("ERROR: PyTorch is required for training.")
    print("Install with: pip install torch")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Model architecture (mirrors ByteTransformer in tiny_classifier.py)
# ---------------------------------------------------------------------------

VOCAB_SIZE = 256      # Byte-level
D_MODEL = 64          # Embedding dimension
N_HEADS = 4           # Attention heads
N_LAYERS = 2          # Transformer layers
D_FFN = 128           # FFN hidden dimension
MAX_SEQ = 256         # Max input bytes
BATCH_SIZE = 64
EPOCHS = 30
LR = 1e-3
VAL_SPLIT = 0.15      # Hold out 15% for validation
LABEL_SMOOTH = 0.05   # Label smoothing factor
PATIENCE = 15         # Early-stop after N epochs without val improvement


class TinyTransformer(nn.Module):
    """PyTorch version of ByteTransformer for training."""

    def __init__(self, n_classes: int):
        super().__init__()
        self.token_embedding = nn.Embedding(VOCAB_SIZE, D_MODEL)
        self.pos_embedding = nn.Embedding(MAX_SEQ, D_MODEL)

        # Transformer layers (manual, to match numpy export)
        self.layers = nn.ModuleList()
        for _ in range(N_LAYERS):
            self.layers.append(nn.ModuleDict({
                "ln1": nn.LayerNorm(D_MODEL),
                "Wq": nn.Linear(D_MODEL, D_MODEL, bias=False),
                "Wk": nn.Linear(D_MODEL, D_MODEL, bias=False),
                "Wv": nn.Linear(D_MODEL, D_MODEL, bias=False),
                "Wo": nn.Linear(D_MODEL, D_MODEL, bias=False),
                "ln2": nn.LayerNorm(D_MODEL),
                "ffn1": nn.Linear(D_MODEL, D_FFN),
                "ffn2": nn.Linear(D_FFN, D_MODEL),
            }))

        self.classifier = nn.Linear(D_MODEL, n_classes)
        self.n_heads = N_HEADS
        self.head_dim = D_MODEL // N_HEADS

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, seq_len) of byte ids → (batch, n_classes) logits."""
        B, S = x.shape
        pos = torch.arange(S, device=x.device).unsqueeze(0)
        h = self.token_embedding(x) + self.pos_embedding(pos)

        for layer in self.layers:
            # Pre-norm attention + residual
            normed = layer["ln1"](h)
            Q = layer["Wq"](normed)
            K = layer["Wk"](normed)
            V = layer["Wv"](normed)

            # Multi-head reshape: (B, S, D) → (B, H, S, D/H)
            Q = Q.view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
            K = K.view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
            V = V.view(B, S, self.n_heads, self.head_dim).transpose(1, 2)

            scale = self.head_dim ** -0.5
            attn = F.softmax(Q @ K.transpose(-2, -1) * scale, dim=-1)
            out = (attn @ V).transpose(1, 2).reshape(B, S, D_MODEL)
            h = h + layer["Wo"](out)

            # Pre-norm FFN + residual
            normed = layer["ln2"](h)
            ffn = layer["ffn1"](normed)
            ffn = ffn * torch.sigmoid(1.702 * ffn)  # GELU approx
            h = h + layer["ffn2"](ffn)

        # Global average pool → classify
        pooled = h.mean(dim=1)
        return self.classifier(pooled)


# ---------------------------------------------------------------------------
# Export PyTorch model → numpy .npz
# ---------------------------------------------------------------------------


def export_to_npz(model: TinyTransformer, path: str):
    """Export trained model weights to numpy .npz format."""
    weights = {}

    # Embeddings
    weights["token_embedding"] = model.token_embedding.weight.detach().numpy()
    weights["pos_embedding"] = model.pos_embedding.weight.detach().numpy()

    # Transformer layers
    for i, layer in enumerate(model.layers):
        # Attention
        weights[f"layer{i}_Wq"] = layer["Wq"].weight.T.detach().numpy()
        weights[f"layer{i}_Wk"] = layer["Wk"].weight.T.detach().numpy()
        weights[f"layer{i}_Wv"] = layer["Wv"].weight.T.detach().numpy()
        weights[f"layer{i}_Wo"] = layer["Wo"].weight.T.detach().numpy()

        # LayerNorm 1
        weights[f"layer{i}_ln1_gamma"] = layer["ln1"].weight.detach().numpy()
        weights[f"layer{i}_ln1_beta"] = layer["ln1"].bias.detach().numpy()

        # FFN
        weights[f"layer{i}_W1"] = layer["ffn1"].weight.T.detach().numpy()
        weights[f"layer{i}_b1"] = layer["ffn1"].bias.detach().numpy()
        weights[f"layer{i}_W2"] = layer["ffn2"].weight.T.detach().numpy()
        weights[f"layer{i}_b2"] = layer["ffn2"].bias.detach().numpy()

        # LayerNorm 2
        weights[f"layer{i}_ln2_gamma"] = layer["ln2"].weight.detach().numpy()
        weights[f"layer{i}_ln2_beta"] = layer["ln2"].bias.detach().numpy()

    # Classifier head
    weights["classifier_W"] = model.classifier.weight.T.detach().numpy()
    weights["classifier_b"] = model.classifier.bias.detach().numpy()

    np.savez_compressed(path, **weights)
    file_size = os.path.getsize(path)
    print(f"Exported model to {path} ({file_size / 1024:.1f} KB)")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def encode_text(text: str) -> np.ndarray:
    """Encode text to byte array, padded/truncated to MAX_SEQ."""
    raw = text.encode("utf-8")[:MAX_SEQ]
    arr = np.zeros(MAX_SEQ, dtype=np.int64)
    for i, b in enumerate(raw):
        arr[i] = b
    return arr


def load_query_data(path: str, label_map: dict):
    """Load query training data from JSONL."""
    texts, labels = [], []
    with open(path) as f:
        for line in f:
            ex = json.loads(line)
            if ex["label"] not in label_map:
                continue
            texts.append(encode_text(ex["text"]))
            labels.append(label_map[ex["label"]])
    return np.array(texts), np.array(labels)


def load_tool_data(path: str, tool_list: list):
    """Load tool training data from JSONL (multi-class: one tool per query)."""
    tool_to_idx = {t: i for i, t in enumerate(tool_list)}
    texts, labels = [], []
    with open(path) as f:
        for line in f:
            ex = json.loads(line)
            tool = ex.get("tool", "no_tool")
            if tool not in tool_to_idx:
                continue
            texts.append(encode_text(ex["text"]))
            labels.append(tool_to_idx[tool])
    return np.array(texts), np.array(labels)


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------


def compute_class_weights(labels: np.ndarray, n_classes: int) -> torch.Tensor:
    """Inverse-frequency class weights, capped at 5× median."""
    counts = np.bincount(labels, minlength=n_classes).astype(np.float32)
    counts = np.maximum(counts, 1)  # avoid div-by-zero
    inv_freq = 1.0 / counts
    inv_freq /= inv_freq.sum()  # normalise
    weights = torch.tensor(inv_freq * n_classes, dtype=torch.float32)
    median_w = weights.median()
    weights = torch.clamp(weights, max=median_w * 5)
    return weights


def train_val_split(X, y, val_frac=VAL_SPLIT):
    """Stratified-ish split (shuffle then slice)."""
    n = len(X)
    idx = np.random.permutation(n)
    split = int(n * (1 - val_frac))
    return X[idx[:split]], y[idx[:split]], X[idx[split:]], y[idx[split:]]


def evaluate(model, X, y, class_names=None):
    """Return overall accuracy + per-class accuracy dict."""
    model.eval()
    all_preds = []
    with torch.no_grad():
        for start in range(0, len(X), BATCH_SIZE):
            xb = torch.tensor(X[start:start + BATCH_SIZE], dtype=torch.long)
            logits = model(xb)
            all_preds.append(logits.argmax(dim=-1).numpy())
    preds = np.concatenate(all_preds)
    overall = (preds == y).mean()

    per_class = {}
    if class_names:
        for idx, name in enumerate(class_names):
            mask = y == idx
            if mask.sum() == 0:
                per_class[name] = float("nan")
            else:
                per_class[name] = (preds[mask] == y[mask]).mean()
    return overall, per_class


def train_model(model, X, y, epochs=EPOCHS, lr=LR, task="multiclass",
                class_names=None, use_class_weights=True):
    """Train with val split, class weighting, label smoothing, early stopping."""
    X_train, y_train, X_val, y_val = train_val_split(X, y)
    print(f"  Train: {len(X_train)}  Val: {len(X_val)}")

    n_classes = len(class_names) if class_names else model.classifier.out_features

    # Class weights
    weight = None
    if use_class_weights and task == "multiclass":
        weight = compute_class_weights(y_train, n_classes)
        print(f"  Class weights: min={weight.min():.2f} max={weight.max():.2f}")

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    n = len(X_train)
    best_val_acc = 0.0
    best_state = None
    patience_counter = 0

    for epoch in range(epochs):
        model.train()
        indices = np.random.permutation(n)
        total_loss = 0.0
        correct = 0
        total = 0

        for start in range(0, n, BATCH_SIZE):
            batch_idx = indices[start:start + BATCH_SIZE]
            x_batch = torch.tensor(X_train[batch_idx], dtype=torch.long)
            y_batch = torch.tensor(y_train[batch_idx])

            logits = model(x_batch)

            if task == "multiclass":
                loss = F.cross_entropy(logits, y_batch, weight=weight,
                                       label_smoothing=LABEL_SMOOTH)
                preds = logits.argmax(dim=-1)
                correct += (preds == y_batch).sum().item()
            else:
                loss = F.binary_cross_entropy_with_logits(logits, y_batch)
                preds = (torch.sigmoid(logits) > 0.5).float()
                correct += (preds == y_batch).all(dim=-1).sum().item()

            total += len(batch_idx)
            total_loss += loss.item() * len(batch_idx)

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

        scheduler.step()
        train_acc = correct / total
        avg_loss = total_loss / total

        # Validate
        val_acc, _ = evaluate(model, X_val, y_val)

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1

        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"  Epoch {epoch+1:3d}/{epochs}  loss={avg_loss:.4f}  "
                  f"train={train_acc:.3f}  val={val_acc:.3f}")

        if patience_counter >= PATIENCE:
            print(f"  Early stop at epoch {epoch+1} (no val improvement for {PATIENCE} epochs)")
            break

    # Restore best checkpoint
    if best_state:
        model.load_state_dict(best_state)

    # Final per-class report
    val_overall, per_class = evaluate(model, X_val, y_val, class_names)
    print(f"\n  Best validation accuracy: {best_val_acc:.3f}")
    if per_class:
        print("  Per-class validation accuracy:")
        for name, acc in sorted(per_class.items(), key=lambda x: x[1]):
            marker = " ⚠" if acc < 0.80 else ""
            print(f"    {name:20s}  {acc:.3f}{marker}")

    return best_val_acc


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    model_dir = os.path.join(os.path.dirname(__file__), "..", "backend", "models")
    os.makedirs(model_dir, exist_ok=True)

    query_data_path = os.path.join(data_dir, "training_queries.jsonl")
    tool_data_path = os.path.join(data_dir, "tool_training.jsonl")

    if not os.path.exists(query_data_path):
        print(f"ERROR: Training data not found at {query_data_path}")
        print("Run: python3 scripts/generate_training_data.py first")
        sys.exit(1)

    # --- Query classifier ---
    print("\n=== Training Query Classifier ===")
    label_names = [
        "smalltalk", "disclosure", "code", "lightweight",
        "memory_recall", "preference", "general",
    ]
    label_map = {name: i for i, name in enumerate(label_names)}

    X_query, y_query = load_query_data(query_data_path, label_map)
    print(f"Loaded {len(X_query)} examples, {len(label_names)} classes")

    query_model = TinyTransformer(n_classes=len(label_names))
    param_count = sum(p.numel() for p in query_model.parameters())
    print(f"Model parameters: {param_count:,}")

    start = time.time()
    best_acc = train_model(query_model, X_query, y_query, task="multiclass",
                           class_names=label_names)
    elapsed = time.time() - start
    print(f"Training complete in {elapsed:.1f}s, best val accuracy: {best_acc:.3f}")

    query_npz = os.path.join(model_dir, "query_classifier.npz")
    export_to_npz(query_model, query_npz)

    # --- Tool detector ---
    if os.path.exists(tool_data_path):
        print("\n=== Training Tool Detector ===")
        tool_names = [
            "calculator", "web_search", "document_search", "code_display",
            "fact_check", "recall_memory", "forget_memory", "save_memory",
            "search_memory", "update_memory", "read_file", "write_file",
            "list_directory", "search_codebase", "run_command", "no_tool",
        ]

        X_tool, y_tool = load_tool_data(tool_data_path, tool_names)
        print(f"Loaded {len(X_tool)} examples, {len(tool_names)} classes")

        tool_model = TinyTransformer(n_classes=len(tool_names))
        param_count = sum(p.numel() for p in tool_model.parameters())
        print(f"Model parameters: {param_count:,}")

        start = time.time()
        best_acc = train_model(tool_model, X_tool, y_tool, task="multiclass",
                               epochs=80, lr=1e-3, class_names=tool_names)
        elapsed = time.time() - start
        print(f"Training complete in {elapsed:.1f}s, best val accuracy: {best_acc:.3f}")

        tool_npz = os.path.join(model_dir, "tool_detector.npz")
        export_to_npz(tool_model, tool_npz)

    # --- Injection detector ---
    injection_data_path = os.path.join(data_dir, "injection_training.jsonl")
    if os.path.exists(injection_data_path):
        print("\n=== Training Injection Detector ===")
        injection_labels = ["benign", "injection", "jailbreak"]
        injection_map = {name: i for i, name in enumerate(injection_labels)}

        X_inj, y_inj = load_query_data(injection_data_path, injection_map)
        print(f"Loaded {len(X_inj)} examples, {len(injection_labels)} classes")

        inj_model = TinyTransformer(n_classes=len(injection_labels))
        param_count = sum(p.numel() for p in inj_model.parameters())
        print(f"Model parameters: {param_count:,}")

        start = time.time()
        best_acc = train_model(inj_model, X_inj, y_inj, task="multiclass",
                               epochs=60, lr=1e-3, class_names=injection_labels)
        elapsed = time.time() - start
        print(f"Training complete in {elapsed:.1f}s, best val accuracy: {best_acc:.3f}")

        inj_npz = os.path.join(model_dir, "injection_detector.npz")
        export_to_npz(inj_model, inj_npz)

    print("\n=== Done ===")
    print(f"Models saved to {model_dir}/")


if __name__ == "__main__":
    main()

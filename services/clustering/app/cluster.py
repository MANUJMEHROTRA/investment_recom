"""Density-based clustering of news embeddings (the BERTopic-style recipe).

1. UMAP reduces the 768-d embeddings to a few dimensions that keep local neighbourhoods.
2. HDBSCAN finds dense regions = stories (the hierarchical successor to DBSCAN: no eps to tune,
   clusters of varying density, and unrelated articles are left as noise instead of forced in).
3. Clusters whose centroids are nearly identical in the original embedding space are merged,
   so one story ends up as exactly one cluster.
4. A separate 2-D UMAP gives the map coordinates.
5. Stable ids: each cluster is matched to last run's clusters by member overlap, so a story
   keeps its id (and cached summary) as new articles join it.
"""
from __future__ import annotations

import hashlib
import secrets
from collections import Counter

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer

NOISE = -1


def reduce(x: np.ndarray, dims: int, neighbors: int, seed: int, min_dist: float) -> np.ndarray:
    import umap  # heavy import (numba); keep it lazy

    n = len(x)
    reducer = umap.UMAP(
        n_components=min(dims, max(2, n - 2)),
        n_neighbors=max(2, min(neighbors, n - 1)),
        min_dist=min_dist,
        metric="cosine",
        random_state=seed,
    )
    return reducer.fit_transform(x)


def density_cluster(z: np.ndarray, min_cluster_size: int, min_samples: int) -> tuple[np.ndarray, np.ndarray]:
    model = HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples, metric="euclidean", copy=True)
    labels = model.fit_predict(z)
    return labels, model.probabilities_


def merge_duplicates(x: np.ndarray, labels: np.ndarray, threshold: float) -> np.ndarray:
    """Union clusters whose mean embeddings have cosine similarity >= threshold."""
    ids = sorted(set(labels) - {NOISE})
    if len(ids) < 2:
        return labels
    cents = np.stack([x[labels == i].mean(axis=0) for i in ids])
    cents /= np.linalg.norm(cents, axis=1, keepdims=True)
    sim = cents @ cents.T
    parent = {i: i for i in ids}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            if sim[a, b] >= threshold:
                parent[find(ids[b])] = find(ids[a])
    remap = {i: find(i) for i in ids}
    merged = np.array([remap.get(int(l), NOISE) if l != NOISE else NOISE for l in labels])
    # relabel 0..k-1 by descending size for readability
    order = [lab for lab, _ in Counter(merged[merged != NOISE]).most_common()]
    final = {lab: i for i, lab in enumerate(order)}
    return np.array([final.get(int(l), NOISE) for l in merged])


def member_hash(ids: list[str]) -> str:
    return hashlib.sha1("|".join(sorted(ids)).encode()).hexdigest()


def assign_stable_ids(new: dict[int, set[str]], previous: dict[str, set[str]], min_jaccard: float = 0.3) -> dict[int, str]:
    """Greedy best-overlap matching of this run's clusters to last run's stable ids."""
    pairs = []
    for label, members in new.items():
        for sid, old in previous.items():
            j = len(members & old) / len(members | old)
            if j >= min_jaccard:
                pairs.append((j, label, sid))
    out: dict[int, str] = {}
    used: set[str] = set()
    for _, label, sid in sorted(pairs, reverse=True):
        if label not in out and sid not in used:
            out[label] = sid
            used.add(sid)
    for label in new:
        out.setdefault(label, secrets.token_hex(4))
    return out


def keywords(docs_by_cluster: dict[int, str], top_k: int = 6) -> dict[int, list[str]]:
    """class-based TF-IDF: each cluster's concatenated text is one document."""
    if len(docs_by_cluster) < 2:
        return {k: [] for k in docs_by_cluster}
    labels = list(docs_by_cluster)
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=5000, min_df=1, token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z&.-]{2,}\b")
    m = vec.fit_transform([docs_by_cluster[l] for l in labels])
    terms = np.array(vec.get_feature_names_out())
    out = {}
    for row, label in enumerate(labels):
        scores = m[row].toarray().ravel()
        out[label] = [t for t in terms[scores.argsort()[::-1][:top_k]] if scores[vec.vocabulary_[t]] > 0]
    return out


def centrality(x: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Cosine similarity of each member to the cluster centroid (most representative first)."""
    c = x[idx].mean(axis=0)
    c /= np.linalg.norm(c) or 1
    return x[idx] @ c

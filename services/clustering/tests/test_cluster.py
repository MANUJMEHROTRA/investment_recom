import numpy as np

from app import cluster as algo


def blobs(seed=0, per=15, dim=64, n_stories=3, noise=6):
    rng = np.random.default_rng(seed)
    centers = rng.normal(size=(n_stories, dim))
    x = [c + rng.normal(scale=0.05, size=(per, dim)) for c in centers]
    x.append(rng.normal(size=(noise, dim)) * 3)
    x = np.vstack(x)
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def test_umap_hdbscan_recovers_planted_stories():
    x = blobs()
    z = algo.reduce(x, dims=5, neighbors=10, seed=42, min_dist=0.0)
    labels, probs = algo.density_cluster(z, min_cluster_size=3, min_samples=2)
    labels = algo.merge_duplicates(x, labels, threshold=0.92)
    story_labels = [set(labels[i * 15:(i + 1) * 15]) - {algo.NOISE} for i in range(3)]
    assert all(len(s) == 1 for s in story_labels), story_labels  # each story is one cluster
    assert len({next(iter(s)) for s in story_labels}) == 3  # and stories stay separate
    assert len(probs) == len(x)


def test_merge_duplicates_unions_same_story():
    rng = np.random.default_rng(1)
    c = rng.normal(size=32)
    x = np.vstack([c + rng.normal(scale=0.01, size=(4, 32)), c + rng.normal(scale=0.01, size=(4, 32)), -c + rng.normal(scale=0.01, size=(4, 32))])
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    labels = np.array([0] * 4 + [1] * 4 + [2] * 4)
    merged = algo.merge_duplicates(x, labels, 0.95)
    assert len(set(merged[:8])) == 1 and merged[8] != merged[0]


def test_stable_ids_follow_membership():
    prev = {"aaaa": {"a", "b", "c"}, "bbbb": {"x", "y"}}
    new = {0: {"a", "b", "c", "d"}, 1: {"q", "r", "s"}}
    ids = algo.assign_stable_ids(new, prev)
    assert ids[0] == "aaaa" and ids[1] not in ("aaaa", "bbbb")


def test_keywords_and_member_hash():
    kw = algo.keywords({0: "nvidia chips ai demand nvidia", 1: "oil prices opec crude oil"})
    assert "nvidia" in kw[0] and "oil" in kw[1]
    assert algo.member_hash(["b", "a"]) == algo.member_hash(["a", "b"])

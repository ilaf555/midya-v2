"""Event clustering: group articles covering the same story.

HDBSCAN when available (industry choice for news), otherwise greedy
agglomerative clustering over the cosine similarity matrix.
"""
from __future__ import annotations

CLUSTER_SIM_THRESHOLD = 0.55


def cluster_articles(articles: list[dict], sim_matrix) -> list[list[dict]]:
    """Returns list of clusters; each cluster is a list of article dicts."""
    n = len(articles)
    if n == 0:
        return []
    if n == 1:
        return [articles]
    try:
        import hdbscan
        import numpy as np
        dist = np.clip(1.0 - sim_matrix, 0, 2)
        labels = hdbscan.HDBSCAN(min_cluster_size=2, metric="precomputed").fit_predict(dist)
        clusters: dict[int, list[dict]] = {}
        for art, lab in zip(articles, labels):
            clusters.setdefault(int(lab), []).append(art)
        out = [v for k, v in clusters.items() if k != -1]
        out += [[a] for a in clusters.get(-1, [])]
        return out
    except ImportError:
        pass
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i, j] >= CLUSTER_SIM_THRESHOLD:
                pi, pj = find(i), find(j)
                if pi != pj:
                    parent[pi] = pj
    groups: dict[int, list[dict]] = {}
    for i, a in enumerate(articles):
        groups.setdefault(find(i), []).append(a)
    return list(groups.values())

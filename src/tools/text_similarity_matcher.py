"""
src/tools/text_similarity_matcher.py
─────────────────────────────────────────────────────────────────────────────
Tool: text_similarity_matcher

Finds pairs of rows whose text (from a specified column) are similar above a
caller-supplied confidence threshold.

Uses RapidFuzz (already in requirements.txt) to compute a normalised
similarity score (0–100) between every pair of strings.  RapidFuzz is fast
enough for catalogs with hundreds of products.

Why this is useful:
  WF006 Duplicate Product Detection needs to compare product names and flag
  pairs that look like duplicates even if spelling differs slightly
  (e.g. "Laptop Stand Aluminum" vs "Laptop Stand - Aluminium").

Why generic?
  • Column name and threshold come through parameters.
  • Works on any list-of-dicts: products, employees, keywords, etc.

Return shape:
  {
    "ok":   bool,
    "data": {
        "groups":              list[dict],   # each group = one cluster of similar rows
        "pair_count":          int,
        "confidence_threshold": float,
    },
    "error": str | None
  }

  Each group dict:
  {
    "items":      list[str],           # the similar text values
    "row_ids":    list[str | None],    # optional id column values
    "confidence": float,               # similarity score (0–100)
  }
─────────────────────────────────────────────────────────────────────────────
"""

from src.tools.registry import register_tool

try:
    from rapidfuzz import fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False


# ── JSON schema ────────────────────────────────────────────────────────────────
_SCHEMA = {
    "name": "text_similarity_matcher",
    "description": (
        "Find pairs of rows whose text in a given column are similar above a "
        "confidence threshold. Useful for detecting duplicate products, "
        "near-identical entries, or fuzzy-matched records. "
        "Returns groups of similar rows with a confidence score (0–100)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "description": "The table to scan: list of row-dicts.",
            },
            "text_column": {
                "type": "string",
                "description": "The column whose text values to compare (e.g. 'Product_Name').",
            },
            "confidence_threshold": {
                "type": "number",
                "description": (
                    "Minimum similarity score (0–100) to consider two rows a match. "
                    "A score of 80 means 80% similar. Typical values: 75–90."
                ),
            },
            "id_column": {
                "type": "string",
                "description": (
                    "Optional: column whose value to include as a row identifier "
                    "(e.g. 'SKU', 'Employee_ID') for easier reading of results."
                ),
            },
        },
        "required": ["rows", "text_column", "confidence_threshold"],
    },
}


@register_tool(schema=_SCHEMA)
def text_similarity_matcher(
    rows: list,
    text_column: str,
    confidence_threshold: float,
    id_column: str = "",
) -> dict:
    """
    Find pairs of rows with similar text above the confidence threshold.

    Parameters
    ----------
    rows                 : list[dict]  The table to scan.
    text_column          : str         Column containing the text to compare.
    confidence_threshold : float       Minimum score (0–100) to flag a pair.
    id_column            : str         Optional identifier column (e.g. 'SKU').

    Returns
    -------
    dict  {ok, data, error}
    """
    try:
        # ── Dependency check ───────────────────────────────────────────────────
        if not _HAS_RAPIDFUZZ:
            return {
                "ok":    False,
                "data":  None,
                "error": (
                    "rapidfuzz is not installed. "
                    "Run: pip install rapidfuzz"
                ),
            }

        if not isinstance(rows, list) or len(rows) == 0:
            return {
                "ok":    False,
                "data":  None,
                "error": "No rows provided.",
            }

        if not text_column:
            return {
                "ok":    False,
                "data":  None,
                "error": "'text_column' must be specified.",
            }

        # ── Extract text and optional IDs ──────────────────────────────────────
        texts = [str(row.get(text_column, "")).strip() for row in rows]
        ids   = [str(row.get(id_column, "")).strip() if id_column else None
                 for row in rows]

        n = len(texts)

        # ── Compare all pairs (O(n²) — fine for small catalogs) ───────────────
        # We collect pairs first, then merge overlapping pairs into groups.
        matched_pairs: list[tuple[int, int, float]] = []

        for i in range(n):
            for j in range(i + 1, n):
                if not texts[i] or not texts[j]:
                    continue  # skip empty strings

                # token_sort_ratio handles word-order differences gracefully
                score = fuzz.token_sort_ratio(texts[i], texts[j])

                if score >= confidence_threshold:
                    matched_pairs.append((i, j, score))

        # ── Cluster pairs into groups using union-find ─────────────────────────
        # Simple approach: for each pair, merge their clusters.
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]  # path compression
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        # Also track the max confidence for each pair within a cluster
        pair_scores: dict[tuple, float] = {}
        for i, j, score in matched_pairs:
            union(i, j)
            key = (min(i, j), max(i, j))
            pair_scores[key] = max(pair_scores.get(key, 0), score)

        # Build final groups: {root: [indices]}
        cluster_map: dict[int, list[int]] = {}
        for idx in range(n):
            root = find(idx)
            # Only include indices that are part of at least one matched pair
            in_pair = any(i == idx or j == idx for i, j, _ in matched_pairs)
            if in_pair:
                cluster_map.setdefault(root, []).append(idx)

        # Format groups for output
        groups = []
        for root, members in cluster_map.items():
            if len(members) < 2:
                continue  # a lone node is not a duplicate group

            # Compute average confidence across all pairs within this cluster
            cluster_scores = [
                score for (i, j, score) in matched_pairs
                if i in members and j in members
            ]
            avg_confidence = (
                round(sum(cluster_scores) / len(cluster_scores), 1)
                if cluster_scores else 0.0
            )

            groups.append({
                "items":      [texts[m] for m in members],
                "row_ids":    [ids[m]   for m in members],
                "confidence": avg_confidence,
            })

        # Sort groups by confidence descending
        groups.sort(key=lambda g: g["confidence"], reverse=True)

        return {
            "ok": True,
            "data": {
                "groups":               groups,
                "pair_count":           len(matched_pairs),
                "confidence_threshold": confidence_threshold,
            },
            "error": None,
        }

    except Exception as exc:
        return {
            "ok":    False,
            "data":  None,
            "error": f"Unexpected error in text_similarity_matcher: {exc}",
        }

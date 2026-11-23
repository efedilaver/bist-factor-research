"""Explore financial statement itemCode signatures across BIST companies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

import numpy as np
import pandas as pd

from src.data.isyatirim.cache import load_financials_cache
from src.data.isyatirim.profiles import BaseProfile, list_profiles
from src.utils.constants import DATA_DIR, FINANCIALS_DIR
from src.utils.logger import get_logger

logger = get_logger("analysis.profile_discovery")

DEFAULT_OUTPUT_DIR = DATA_DIR / "profile_discovery"
_PERIOD_COLUMN_PATTERN = re.compile(r"^\d{4}/\d{1,2}$")
_EPSILON = 1e-9


@dataclass(frozen=True)
class CompanySignature:
    """ItemCode signature for one company."""

    symbol: str
    item_codes: tuple[str, ...]
    item_code_count: int
    period_count: int
    row_count: int
    unsupported: bool


def _normalize_symbol(symbol: object) -> str:
    return str(symbol).strip().upper()


def _iter_cache_symbols(financials_dir: Path = FINANCIALS_DIR) -> list[str]:
    return sorted({path.stem.upper() for path in financials_dir.glob("*.parquet")})


def _extract_item_codes(frame: pd.DataFrame) -> tuple[str, ...]:
    if frame.empty or "itemCode" not in frame.columns:
        return ()
    codes = (
        frame["itemCode"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
    )
    ordered: list[str] = []
    seen: set[str] = set()
    for code in codes:
        if code and code not in seen:
            seen.add(code)
            ordered.append(code)
    return tuple(ordered)


def _count_period_columns(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    if "period" in frame.columns:
        return int(frame["period"].dropna().astype(str).nunique())
    period_columns = [
        column
        for column in frame.columns
        if isinstance(column, str) and _PERIOD_COLUMN_PATTERN.fullmatch(column)
    ]
    return len(period_columns)


def _period_columns(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return []
    return [
        column
        for column in frame.columns
        if isinstance(column, str) and _PERIOD_COLUMN_PATTERN.fullmatch(column)
    ]


def _nonzero_numeric_values(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    numeric = numeric.replace(0, np.nan)
    return numeric.dropna()


def load_company_signatures(
    symbols: Iterable[str] | None = None,
    *,
    financials_dir: Path = FINANCIALS_DIR,
) -> list[CompanySignature]:
    """Load unique itemCode signatures from cached raw financial tables."""
    if symbols is None:
        symbols = _iter_cache_symbols(financials_dir)

    signatures: list[CompanySignature] = []
    for raw_symbol in symbols:
        symbol = _normalize_symbol(raw_symbol)
        frame = load_financials_cache(symbol)
        if frame is None:
            continue
        item_codes = _extract_item_codes(frame)
        if not item_codes:
            continue
        signatures.append(
            CompanySignature(
                symbol=symbol,
                item_codes=item_codes,
                item_code_count=len(item_codes),
                period_count=_count_period_columns(frame),
                row_count=int(len(frame)),
                unsupported=bool(frame.attrs.get("isyatirim_unsupported")),
            )
        )
    return signatures


def build_itemcode_presence_frame(signatures: Iterable[CompanySignature]) -> pd.DataFrame:
    """Build a binary presence matrix indexed by symbol."""
    signatures = list(signatures)
    all_codes = sorted({code for signature in signatures for code in signature.item_codes})
    records: list[dict[str, object]] = []
    for signature in signatures:
        present = set(signature.item_codes)
        record: dict[str, object] = {
            "symbol": signature.symbol,
            "item_code_count": signature.item_code_count,
            "period_count": signature.period_count,
            "row_count": signature.row_count,
            "unsupported": signature.unsupported,
        }
        for code in all_codes:
            record[code] = 1 if code in present else 0
        records.append(record)
    frame = pd.DataFrame.from_records(records)
    if not frame.empty:
        frame = frame.sort_values(["item_code_count", "symbol"], ascending=[False, True]).reset_index(drop=True)
    return frame


def build_itemcode_feature_table(
    signatures: Iterable[CompanySignature] | None = None,
    *,
    symbols: Iterable[str] | None = None,
    financials_dir: Path = FINANCIALS_DIR,
) -> pd.DataFrame:
    """Build a long-form itemCode feature table with frequency and importance columns.

    The table is company-itemCode level and is derived from the raw wide financial cache.
    For each itemCode row we compute:

    - `frequency`: number of non-null reporting periods
    - `coverage_ratio`: `frequency / total_periods`
    - `mean_value`: arithmetic mean across periods
    - `variance_value`: variance across periods
    - `importance_score`: `coverage_ratio * variance_value / (abs(mean_value) + eps)`
    """
    if signatures is None:
        signatures = load_company_signatures(symbols=symbols, financials_dir=financials_dir)
    else:
        signatures = list(signatures)

    records: list[dict[str, object]] = []
    for signature in signatures:
        frame = load_financials_cache(signature.symbol)
        if frame is None or frame.empty or "itemCode" not in frame.columns:
            continue

        period_columns = _period_columns(frame)
        if not period_columns:
            continue

        working = frame.loc[:, ["itemCode", *period_columns]].copy()
        working["itemCode"] = working["itemCode"].astype(str).str.strip().str.upper()
        working = working[working["itemCode"] != ""]

        for _, row in working.iterrows():
            values = pd.to_numeric(pd.Series([row[column] for column in period_columns]), errors="coerce")
            nonzero_values = _nonzero_numeric_values(values)
            frequency = int(nonzero_values.size)
            coverage_ratio = float(frequency / len(period_columns)) if period_columns else 0.0
            mean_value = float(nonzero_values.mean()) if frequency else 0.0
            variance_value = float(nonzero_values.var()) if frequency > 1 else 0.0
            importance_score = float((coverage_ratio * variance_value) / (abs(mean_value) + _EPSILON))
            records.append(
                {
                    "symbol": signature.symbol,
                    "itemCode": str(row["itemCode"]).strip().upper(),
                    "frequency": frequency,
                    "coverage_ratio": coverage_ratio,
                    "mean_value": mean_value,
                    "variance_value": variance_value,
                    "importance_score": importance_score,
                }
            )

    frame = pd.DataFrame.from_records(records)
    if not frame.empty:
        frame = frame.sort_values(
            ["symbol", "importance_score", "frequency", "itemCode"],
            ascending=[True, False, False, True],
        ).reset_index(drop=True)
    return frame


def build_weighted_feature_matrix(
    feature_table: pd.DataFrame,
    *,
    value_column: str = "importance_score",
    fill_value: float = 0.0,
) -> pd.DataFrame:
    """Pivot a long-form feature table into a company-by-itemCode matrix."""
    required_columns = {"symbol", "itemCode", value_column}
    missing = required_columns - set(feature_table.columns)
    if missing:
        raise ValueError(f"Feature table is missing required columns: {sorted(missing)}")

    if feature_table.empty:
        return pd.DataFrame()

    matrix = feature_table.pivot_table(
        index="symbol",
        columns="itemCode",
        values=value_column,
        aggfunc="mean",
        fill_value=fill_value,
    )
    matrix.columns = matrix.columns.astype(str)
    matrix = matrix.sort_index(axis=0).sort_index(axis=1)
    return matrix


def profile_scores_for_company(
    frame: pd.DataFrame,
    profiles: Iterable[BaseProfile] | None = None,
) -> dict[str, object]:
    """Score a raw company frame against registered profiles."""
    profiles = tuple(profiles or list_profiles())
    scores = [(profile.name, profile.score_frame(frame)) for profile in profiles]
    best_name, best_score = max(scores, key=lambda item: (item[1], item[0])) if scores else ("", 0)
    return {
        "best_profile": best_name,
        "best_score": int(best_score),
        "scores": {name: int(score) for name, score in scores},
        "matched_codes": sorted(set().union(*(profile.present_raw_codes(frame) for profile in profiles))) if profiles else [],
    }


def build_profile_score_table(
    signatures: Iterable[CompanySignature],
    profiles: Iterable[BaseProfile] | None = None,
) -> pd.DataFrame:
    """Score each company against the registered profile set."""
    profiles = tuple(profiles or list_profiles())
    rows: list[dict[str, object]] = []
    for signature in signatures:
        frame = pd.DataFrame({"itemCode": list(signature.item_codes)})
        scores = {profile.name: profile.score_frame(frame) for profile in profiles}
        best_profile = max(scores.items(), key=lambda item: (item[1], item[0])) if scores else ("", 0)
        row: dict[str, object] = {
            "symbol": signature.symbol,
            "item_code_count": signature.item_code_count,
            "period_count": signature.period_count,
            "row_count": signature.row_count,
            "unsupported": signature.unsupported,
            "best_profile": best_profile[0],
            "best_score": int(best_profile[1]),
        }
        row.update({f"score_{name}": int(score) for name, score in scores.items()})
        rows.append(row)

    frame = pd.DataFrame.from_records(rows)
    if not frame.empty:
        score_columns = [column for column in frame.columns if column.startswith("score_")]
        sort_columns = ["best_score", "item_code_count", "symbol"]
        frame = frame.sort_values(sort_columns, ascending=[False, False, True]).reset_index(drop=True)
        frame = frame[["symbol", "item_code_count", "period_count", "row_count", "unsupported", "best_profile", "best_score", *score_columns]]
    return frame


def top_itemcodes_by_frequency(
    signatures: Iterable[CompanySignature],
    *,
    top_n: int = 50,
) -> pd.DataFrame:
    """Count how often each itemCode appears across companies."""
    counts: dict[str, int] = {}
    for signature in signatures:
        for code in set(signature.item_codes):
            counts[code] = counts.get(code, 0) + 1

    frame = pd.DataFrame(
        [{"itemCode": code, "company_count": count} for code, count in counts.items()]
    )
    if frame.empty:
        return frame
    frame = frame.sort_values(["company_count", "itemCode"], ascending=[False, True]).head(top_n).reset_index(drop=True)
    return frame


def build_jaccard_similarity_frame(signatures: Iterable[CompanySignature]) -> pd.DataFrame:
    """Build a square Jaccard similarity matrix for company signatures."""
    signatures = list(signatures)
    symbols = [signature.symbol for signature in signatures]
    if not signatures:
        return pd.DataFrame()

    matrix = np.zeros((len(signatures), len(signatures)), dtype=float)
    for i, left in enumerate(signatures):
        left_codes = set(left.item_codes)
        for j, right in enumerate(signatures[i:], start=i):
            right_codes = set(right.item_codes)
            union = left_codes | right_codes
            score = len(left_codes & right_codes) / len(union) if union else 0.0
            matrix[i, j] = score
            matrix[j, i] = score
    return pd.DataFrame(matrix, index=symbols, columns=symbols)


def build_feature_similarity_frame(
    feature_matrix: pd.DataFrame,
    *,
    metric: str = "cosine",
) -> pd.DataFrame:
    """Build a similarity matrix from a weighted feature matrix."""
    if feature_matrix.empty:
        return pd.DataFrame()
    from scipy.spatial.distance import pdist, squareform

    values = feature_matrix.fillna(0.0).to_numpy(dtype=float, copy=True)
    if values.shape[0] == 1:
        return pd.DataFrame([[1.0]], index=feature_matrix.index, columns=feature_matrix.index)

    distances = pdist(values, metric=metric)
    if np.isnan(distances).any():
        distances = np.nan_to_num(distances, nan=1.0)
    similarity = 1.0 - squareform(distances, checks=False)
    np.fill_diagonal(similarity, 1.0)
    return pd.DataFrame(similarity, index=feature_matrix.index, columns=feature_matrix.index)


def cluster_feature_matrix(
    feature_matrix: pd.DataFrame,
    *,
    threshold: float = 0.6,
    linkage_method: str = "average",
    metric: str = "cosine",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cluster a weighted feature matrix once and return similarity plus cluster labels."""
    if feature_matrix.empty:
        empty = pd.DataFrame(columns=["symbol", "cluster"])
        return pd.DataFrame(), empty

    similarity = build_feature_similarity_frame(feature_matrix, metric=metric)
    if similarity.empty:
        empty = pd.DataFrame(columns=["symbol", "cluster"])
        return similarity, empty

    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    distance = 1.0 - similarity.values
    condensed = squareform(distance, checks=False)
    linkage_matrix = linkage(condensed, method=linkage_method)
    clusters = fcluster(linkage_matrix, t=threshold, criterion="distance")
    cluster_frame = pd.DataFrame({"symbol": similarity.index, "cluster": clusters})
    cluster_frame = cluster_frame.sort_values(["cluster", "symbol"]).reset_index(drop=True)
    return similarity, cluster_frame


def recursive_hierarchical_clustering(
    feature_matrix: pd.DataFrame,
    *,
    threshold: float = 0.6,
    linkage_method: str = "average",
    metric: str = "cosine",
    min_cluster_size: int = 3,
    max_depth: int = 3,
    cluster_prefix: str = "cluster",
) -> pd.DataFrame:
    """Recursively cluster a feature matrix and return cluster paths for each symbol."""
    if feature_matrix.empty:
        return pd.DataFrame(columns=["symbol", "cluster_path", "depth", "cluster_size"])

    working = feature_matrix.copy().astype(float)
    working = working.replace(0.0, np.nan).fillna(0.0)

    def _cluster_subset(subset: pd.DataFrame, depth: int, path: str) -> list[dict[str, object]]:
        symbols = list(subset.index)
        if len(symbols) == 0:
            return []
        if len(symbols) == 1 or depth >= max_depth or len(symbols) < min_cluster_size:
            return [
                {
                    "symbol": symbol,
                    "cluster_path": path,
                    "depth": depth,
                    "cluster_size": len(symbols),
                }
                for symbol in symbols
            ]

        similarity = build_feature_similarity_frame(subset, metric=metric)
        if similarity.empty:
            return [
                {
                    "symbol": symbol,
                    "cluster_path": path,
                    "depth": depth,
                    "cluster_size": len(symbols),
                }
                for symbol in symbols
            ]

        distance = 1.0 - similarity.values
        if distance.size == 0 or np.allclose(distance, 0.0):
            return [
                {
                    "symbol": symbol,
                    "cluster_path": path,
                    "depth": depth,
                    "cluster_size": len(symbols),
                }
                for symbol in symbols
            ]

        from scipy.cluster.hierarchy import fcluster, linkage
        from scipy.spatial.distance import squareform

        condensed = squareform(distance, checks=False)
        linkage_matrix = linkage(condensed, method=linkage_method)
        labels = fcluster(linkage_matrix, t=threshold, criterion="distance")

        rows: list[dict[str, object]] = []
        for label in sorted(set(labels)):
            mask = labels == label
            subset_symbols = [symbol for symbol, keep in zip(symbols, mask) if keep]
            child_path = f"{path}.{label}"
            child_subset = subset.loc[subset_symbols]
            if len(subset_symbols) >= min_cluster_size and depth + 1 < max_depth and len(subset_symbols) > 1:
                rows.extend(_cluster_subset(child_subset, depth + 1, child_path))
            else:
                rows.extend(
                    {
                        "symbol": symbol,
                        "cluster_path": child_path,
                        "depth": depth + 1,
                        "cluster_size": len(subset_symbols),
                    }
                    for symbol in subset_symbols
                )
        return rows

    rows = _cluster_subset(working, depth=0, path=cluster_prefix)
    frame = pd.DataFrame.from_records(rows)
    if not frame.empty:
        frame = frame.sort_values(["cluster_path", "symbol"]).reset_index(drop=True)
    return frame


def recluster_named_cluster(
    cluster_frame: pd.DataFrame,
    feature_matrix: pd.DataFrame,
    cluster_name: str,
    *,
    threshold: float = 0.6,
    linkage_method: str = "average",
    metric: str = "cosine",
    min_cluster_size: int = 3,
    max_depth: int = 3,
) -> pd.DataFrame:
    """Recluster the companies that belong to a specific cluster path."""
    if cluster_frame.empty:
        return pd.DataFrame(columns=["symbol", "cluster_path", "depth", "cluster_size"])
    if "cluster_path" not in cluster_frame.columns:
        raise ValueError("cluster_frame must contain a cluster_path column")
    if cluster_name not in set(cluster_frame["cluster_path"].astype(str)):
        raise KeyError(f"Cluster not found: {cluster_name}")

    symbols = cluster_frame.loc[cluster_frame["cluster_path"].astype(str) == cluster_name, "symbol"].tolist()
    subset = feature_matrix.loc[feature_matrix.index.intersection(symbols)]
    return recursive_hierarchical_clustering(
        subset,
        threshold=threshold,
        linkage_method=linkage_method,
        metric=metric,
        min_cluster_size=min_cluster_size,
        max_depth=max_depth,
        cluster_prefix=cluster_name,
    )


def cluster_company_signatures(
    signatures: Iterable[CompanySignature],
    *,
    threshold: float = 0.6,
    linkage_method: str = "average",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cluster companies using Jaccard distance over itemCode sets."""
    signatures = list(signatures)
    if not signatures:
        empty = pd.DataFrame(columns=["symbol", "cluster"])
        return pd.DataFrame(), empty

    similarity = build_jaccard_similarity_frame(signatures)
    if similarity.empty:
        empty = pd.DataFrame(columns=["symbol", "cluster"])
        return similarity, empty

    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    distance = 1.0 - similarity.values
    condensed = squareform(distance, checks=False)
    linkage_matrix = linkage(condensed, method=linkage_method)
    clusters = fcluster(linkage_matrix, t=threshold, criterion="distance")
    cluster_frame = pd.DataFrame({"symbol": similarity.index, "cluster": clusters})
    cluster_frame = cluster_frame.sort_values(["cluster", "symbol"]).reset_index(drop=True)
    return similarity, cluster_frame


def summarize_clusters(
    cluster_frame: pd.DataFrame,
    signatures: Iterable[CompanySignature],
    *,
    top_n_itemcodes: int = 20,
) -> pd.DataFrame:
    """Summarize clusters with company counts and representative itemCodes."""
    signatures = list(signatures)
    signature_map = {signature.symbol: signature for signature in signatures}
    rows: list[dict[str, object]] = []

    for cluster_id, group in cluster_frame.groupby("cluster", sort=True):
        symbols = group["symbol"].tolist()
        item_codes: set[str] = set()
        for symbol in symbols:
            signature = signature_map.get(symbol)
            if signature is not None:
                item_codes.update(signature.item_codes)

        item_code_counts: dict[str, int] = {}
        for symbol in symbols:
            signature = signature_map.get(symbol)
            if signature is None:
                continue
            for code in set(signature.item_codes):
                item_code_counts[code] = item_code_counts.get(code, 0) + 1

        top_codes = sorted(item_code_counts.items(), key=lambda item: (-item[1], item[0]))[:top_n_itemcodes]
        rows.append(
            {
                "cluster": cluster_id,
                "company_count": len(symbols),
                "symbols": symbols,
                "item_code_count": len(item_codes),
                "top_itemcodes": top_codes,
            }
        )

    frame = pd.DataFrame.from_records(rows)
    if not frame.empty:
        frame = frame.sort_values(["company_count", "cluster"], ascending=[False, True]).reset_index(drop=True)
    return frame


def cluster_1_recluster_summary(
    cluster_frame: pd.DataFrame,
    feature_matrix: pd.DataFrame,
    signatures: Iterable[CompanySignature] | None = None,
    *,
    cluster_name: str = "cluster.1",
    threshold: float = 0.6,
    linkage_method: str = "average",
    metric: str = "cosine",
    min_cluster_size: int = 3,
    max_depth: int = 3,
) -> pd.DataFrame:
    """Convenience wrapper for reclustering a single named cluster."""
    reclustered = recluster_named_cluster(
        cluster_frame,
        feature_matrix,
        cluster_name,
        threshold=threshold,
        linkage_method=linkage_method,
        metric=metric,
        min_cluster_size=min_cluster_size,
        max_depth=max_depth,
    )
    if reclustered.empty:
        return reclustered
    if signatures is None:
        signatures = load_company_signatures(symbols=reclustered["symbol"].tolist())
    else:
        allowed = set(reclustered["symbol"].astype(str))
        signatures = [signature for signature in signatures if signature.symbol in allowed]
    return summarize_clusters(
        reclustered.rename(columns={"cluster_path": "cluster"}),
        signatures,
    )


def export_profile_discovery(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    symbols: Iterable[str] | None = None,
    signatures: Iterable[CompanySignature] | None = None,
) -> dict[str, Path]:
    """Export itemCode discovery artifacts to disk."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if signatures is None:
        signatures = load_company_signatures(symbols=symbols)
    else:
        signatures = list(signatures)
    presence = build_itemcode_presence_frame(signatures)
    top_codes = top_itemcodes_by_frequency(signatures)
    similarity, clusters = cluster_company_signatures(signatures)
    cluster_summary = summarize_clusters(clusters, signatures) if not clusters.empty else pd.DataFrame()

    paths = {
        "signatures_csv": output_dir / "company_signatures.csv",
        "presence_csv": output_dir / "itemcode_presence.csv",
        "presence_parquet": output_dir / "itemcode_presence.parquet",
        "similarity_parquet": output_dir / "jaccard_similarity.parquet",
        "clusters_csv": output_dir / "company_clusters.csv",
        "clusters_parquet": output_dir / "company_clusters.parquet",
        "cluster_summary_csv": output_dir / "cluster_summary.csv",
        "cluster_summary_parquet": output_dir / "cluster_summary.parquet",
        "top_codes_csv": output_dir / "top_itemcodes.csv",
    }

    pd.DataFrame.from_records(
        [
            {
                "symbol": signature.symbol,
                "item_codes": ",".join(signature.item_codes),
                "item_code_count": signature.item_code_count,
                "period_count": signature.period_count,
                "row_count": signature.row_count,
                "unsupported": signature.unsupported,
            }
            for signature in signatures
        ]
    ).to_csv(paths["signatures_csv"], index=False)
    presence.to_csv(paths["presence_csv"], index=False)
    presence.to_parquet(paths["presence_parquet"], index=False)
    if not similarity.empty:
        similarity.to_parquet(paths["similarity_parquet"])
    if not clusters.empty:
        clusters.to_csv(paths["clusters_csv"], index=False)
        clusters.to_parquet(paths["clusters_parquet"], index=False)
    if not cluster_summary.empty:
        cluster_summary.to_csv(paths["cluster_summary_csv"], index=False)
        cluster_summary.to_parquet(paths["cluster_summary_parquet"], index=False)
    top_codes.to_csv(paths["top_codes_csv"], index=False)
    return paths


def summarize_discovery(signatures: Iterable[CompanySignature]) -> str:
    """Create a human-readable summary for interactive use."""
    signatures = list(signatures)
    if not signatures:
        return "No company signatures found."

    similarity, clusters = cluster_company_signatures(signatures)
    cluster_summary = summarize_clusters(clusters, signatures) if not clusters.empty else pd.DataFrame()
    top_codes = top_itemcodes_by_frequency(signatures, top_n=20)
    cluster_count = int(clusters["cluster"].nunique()) if not clusters.empty else 0

    lines = [
        f"Companies: {len(signatures)}",
        f"Average itemCode count: {sum(sig.item_code_count for sig in signatures) / len(signatures):.1f}",
        f"Average period count: {sum(sig.period_count for sig in signatures) / len(signatures):.1f}",
        "",
        f"Clusters found: {cluster_count}",
    ]
    if not cluster_summary.empty:
        lines.append("Largest clusters:")
        for _, row in cluster_summary.head(10).iterrows():
            lines.append(f"- cluster {int(row['cluster'])}: {int(row['company_count'])} companies")
    if not similarity.empty:
        lines.append(f"Pairwise similarity matrix size: {similarity.shape[0]} x {similarity.shape[1]}")
    lines.extend(["", "Most common itemCodes:"])
    if not top_codes.empty:
        for _, row in top_codes.iterrows():
            lines.append(f"- {row['itemCode']}: {int(row['company_count'])}")
    return "\n".join(lines)

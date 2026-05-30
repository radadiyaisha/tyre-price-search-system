import rapidfuzz
from utils import logger
from size_detector import canonicalize
from json_manager import JSONManager

class SearchEngine:
    def __init__(self):
        self.json_manager = JSONManager()
        self.index = {}  # Map: canonicalized_size -> list of record dicts
        self.all_unique_sizes = [] # Cache of size keys for fuzzy matching
        self.rebuild_index()

    def rebuild_index(self):
        """
        Clears and rebuilds the in-memory search index by reading all stored JSON records.
        """
        self.index.clear()
        records = self.json_manager.load_all_records()
        
        for record in records:
            size_str = record.get("tyre_size", "")
            if not size_str:
                continue
                
            canon_key = canonicalize(size_str)
            if not canon_key:
                continue
                
            if canon_key not in self.index:
                self.index[canon_key] = []
            self.index[canon_key].append(record)

        self.all_unique_sizes = list(self.index.keys())
        logger.info(f"Search index rebuilt. Total unique canonical sizes indexed: {len(self.all_unique_sizes)}")

    def search(self, query_str, fuzzy=True, threshold=70.0):
        """
        Searches the index for a tyre size.
        Returns a dictionary:
        {
            "exact_matches": list of records,
            "fuzzy_matches": list of dicts: {"score": float, "size": str, "records": list of records},
            "query": str
        }
        """
        results = {
            "exact_matches": [],
            "fuzzy_matches": [],
            "query": query_str
        }

        if not query_str:
            return results

        canon_query = canonicalize(query_str)
        if not canon_query:
            return results

        # 1. Exact Match Lookup (Instant O(1) response)
        if canon_query in self.index:
            results["exact_matches"] = self.index[canon_query]
            logger.info(f"Instant exact search hit for '{query_str}' -> found {len(results['exact_matches'])} records.")
            return results

        # 2. Fuzzy Match Backup (using RapidFuzz)
        if fuzzy and self.all_unique_sizes:
            # extract matches from our canonical keys
            # returns list of tuples: (matched_string, score, index)
            fuzzy_hits = rapidfuzz.process.extract(
                canon_query,
                self.all_unique_sizes,
                scorer=rapidfuzz.distance.Levenshtein.normalized_similarity,
                processor=None,
                score_cutoff=threshold / 100.0, # rapidfuzz normalized similarity is 0.0 - 1.0
                limit=5
            )

            for canon_hit, score_ratio, _ in fuzzy_hits:
                score_pct = score_ratio * 100.0
                # Get the original size representation from the first record
                sample_records = self.index[canon_hit]
                original_size_rep = sample_records[0].get("tyre_size") if sample_records else canon_hit
                
                results["fuzzy_matches"].append({
                    "score": round(score_pct, 1),
                    "size": original_size_rep,
                    "records": sample_records
                })
            
            # Sort fuzzy results by score descending
            results["fuzzy_matches"].sort(key=lambda x: x["score"], reverse=True)
            logger.info(f"Fuzzy match completed for '{query_str}' -> found {len(results['fuzzy_matches'])} matches.")

        return results

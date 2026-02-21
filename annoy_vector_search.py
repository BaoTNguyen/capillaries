#!/usr/bin/env python3
"""
Annoy-based vector search implementation
Lightweight alternative to FAISS with good performance for static indices
"""

from annoy import AnnoyIndex
import numpy as np
from typing import List, Dict, Any, Tuple
import pickle
import asyncio
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class AnnoySearchResult:
    prompt_id: str
    distance: float
    similarity: float
    metadata: Dict[str, Any]

class CustomAnnoyIndex:
    """Custom wrapper around Annoy for better integration"""

    def __init__(self, dimension: int, metric: str = 'angular', n_trees: int = 10):
        self.dimension = dimension
        self.metric = metric  # 'angular', 'euclidean', 'manhattan', 'hamming', 'dot'
        self.n_trees = n_trees

        # Create Annoy index
        self.index = AnnoyIndex(dimension, metric)

        # Metadata storage
        self.id_to_prompt = {}  # annoy_id -> prompt_id
        self.prompt_to_id = {}  # prompt_id -> annoy_id
        self.metadata = {}  # prompt_id -> metadata
        self.vectors = {}  # prompt_id -> vector (for exact similarity calculation)

        self.current_id = 0
        self.is_built = False

    def add_vector(self, vector: np.ndarray, prompt_id: str, metadata: Dict[str, Any]):
        """Add vector to index"""
        if self.is_built:
            raise RuntimeError("Cannot add vectors after index is built")

        if vector.shape[0] != self.dimension:
            raise ValueError(f"Vector dimension {vector.shape[0]} doesn't match index dimension {self.dimension}")

        # Add to Annoy index
        annoy_id = self.current_id
        self.index.add_item(annoy_id, vector)

        # Store mappings and metadata
        self.id_to_prompt[annoy_id] = prompt_id
        self.prompt_to_id[prompt_id] = annoy_id
        self.metadata[prompt_id] = metadata
        self.vectors[prompt_id] = vector.copy()

        self.current_id += 1

    def build(self):
        """Build the index (required before search)"""
        if self.is_built:
            return

        logger.info(f"Building Annoy index with {self.current_id} vectors and {self.n_trees} trees")
        self.index.build(self.n_trees)
        self.is_built = True
        logger.info("Annoy index build complete")

    def search(self, query_vector: np.ndarray, k: int = 10,
               include_distances: bool = True) -> List[AnnoySearchResult]:
        """Search for k nearest neighbors"""
        if not self.is_built:
            raise RuntimeError("Index must be built before search")

        if query_vector.shape[0] != self.dimension:
            raise ValueError(f"Query vector dimension {query_vector.shape[0]} doesn't match index dimension {self.dimension}")

        # Get nearest neighbors from Annoy
        if include_distances:
            neighbor_ids, distances = self.index.get_nns_by_vector(query_vector, k, include_distances=True)
        else:
            neighbor_ids = self.index.get_nns_by_vector(query_vector, k, include_distances=False)
            distances = [0.0] * len(neighbor_ids)

        results = []
        for annoy_id, distance in zip(neighbor_ids, distances):
            prompt_id = self.id_to_prompt[annoy_id]

            # Calculate exact cosine similarity for better accuracy
            stored_vector = self.vectors[prompt_id]
            similarity = self._cosine_similarity(query_vector, stored_vector)

            results.append(AnnoySearchResult(
                prompt_id=prompt_id,
                distance=distance,
                similarity=similarity,
                metadata=self.metadata[prompt_id]
            ))

        return results

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate exact cosine similarity"""
        vec1_norm = vec1 / np.linalg.norm(vec1)
        vec2_norm = vec2 / np.linalg.norm(vec2)
        return np.dot(vec1_norm, vec2_norm)

    def save(self, filepath: str):
        """Save index and metadata"""
        # Save Annoy index
        self.index.save(f"{filepath}.ann")

        # Save metadata
        metadata_dict = {
            'dimension': self.dimension,
            'metric': self.metric,
            'n_trees': self.n_trees,
            'id_to_prompt': self.id_to_prompt,
            'prompt_to_id': self.prompt_to_id,
            'metadata': self.metadata,
            'vectors': self.vectors,
            'current_id': self.current_id,
            'is_built': self.is_built
        }

        with open(f"{filepath}.meta", 'wb') as f:
            pickle.dump(metadata_dict, f)

    def load(self, filepath: str):
        """Load index and metadata"""
        # Load Annoy index
        self.index = AnnoyIndex(self.dimension, self.metric)
        self.index.load(f"{filepath}.ann")

        # Load metadata
        with open(f"{filepath}.meta", 'rb') as f:
            metadata_dict = pickle.load(f)

        self.dimension = metadata_dict['dimension']
        self.metric = metadata_dict['metric']
        self.n_trees = metadata_dict['n_trees']
        self.id_to_prompt = metadata_dict['id_to_prompt']
        self.prompt_to_id = metadata_dict['prompt_to_id']
        self.metadata = metadata_dict['metadata']
        self.vectors = metadata_dict['vectors']
        self.current_id = metadata_dict['current_id']
        self.is_built = metadata_dict['is_built']

    def get_item_vector(self, prompt_id: str) -> np.ndarray:
        """Get vector for a specific prompt"""
        if prompt_id not in self.prompt_to_id:
            raise KeyError(f"Prompt ID {prompt_id} not found")

        annoy_id = self.prompt_to_id[prompt_id]
        return self.index.get_item_vector(annoy_id)

    def get_n_items(self) -> int:
        """Get number of items in index"""
        return self.current_id

class AdaptiveAnnoySearch:
    """Adaptive search using multiple Annoy indices with different parameters"""

    def __init__(self, dimension: int):
        self.dimension = dimension

        # Multiple indices with different trade-offs
        self.indices = {
            'fast': CustomAnnoyIndex(dimension, metric='angular', n_trees=10),     # Fast search
            'balanced': CustomAnnoyIndex(dimension, metric='angular', n_trees=50), # Balanced
            'accurate': CustomAnnoyIndex(dimension, metric='angular', n_trees=100) # High accuracy
        }

        self.vectors_added = 0

    def add_vector(self, vector: np.ndarray, prompt_id: str, metadata: Dict[str, Any]):
        """Add vector to all indices"""
        for index in self.indices.values():
            index.add_vector(vector, prompt_id, metadata)
        self.vectors_added += 1

    def build_indices(self):
        """Build all indices"""
        logger.info(f"Building {len(self.indices)} Annoy indices for {self.vectors_added} vectors")

        for name, index in self.indices.items():
            logger.info(f"Building {name} index...")
            index.build()

        logger.info("All Annoy indices built")

    def search(self, query_vector: np.ndarray, k: int = 10,
               strategy: str = 'balanced', ensemble: bool = False) -> List[AnnoySearchResult]:
        """Search with specified strategy"""

        if ensemble:
            return self._ensemble_search(query_vector, k)

        if strategy not in self.indices:
            raise ValueError(f"Unknown strategy: {strategy}. Available: {list(self.indices.keys())}")

        return self.indices[strategy].search(query_vector, k)

    def _ensemble_search(self, query_vector: np.ndarray, k: int) -> List[AnnoySearchResult]:
        """Ensemble search combining results from multiple indices"""
        all_results = {}  # prompt_id -> (total_score, result_object, count)

        weights = {'fast': 0.2, 'balanced': 0.5, 'accurate': 0.3}

        # Get results from each index
        for name, weight in weights.items():
            results = self.indices[name].search(query_vector, k * 2)  # Get more candidates

            for result in results:
                weighted_similarity = result.similarity * weight

                if result.prompt_id in all_results:
                    # Update existing result
                    total_score, existing_result, count = all_results[result.prompt_id]
                    all_results[result.prompt_id] = (
                        total_score + weighted_similarity,
                        existing_result,  # Keep first result object
                        count + 1
                    )
                else:
                    # New result
                    all_results[result.prompt_id] = (weighted_similarity, result, 1)

        # Sort by total score and return top k
        sorted_results = sorted(all_results.values(), key=lambda x: x[0], reverse=True)

        final_results = []
        for total_score, result_obj, count in sorted_results[:k]:
            # Create new result with ensemble score
            ensemble_result = AnnoySearchResult(
                prompt_id=result_obj.prompt_id,
                distance=1.0 - total_score,
                similarity=total_score,
                metadata=result_obj.metadata
            )
            final_results.append(ensemble_result)

        return final_results

    def save(self, base_filepath: str):
        """Save all indices"""
        for name, index in self.indices.items():
            index.save(f"{base_filepath}_{name}")

    def load(self, base_filepath: str):
        """Load all indices"""
        for name, index in self.indices.items():
            index.load(f"{base_filepath}_{name}")

class HybridAnnoySearch:
    """Combines Annoy with exact search for small result sets"""

    def __init__(self, dimension: int, exact_search_threshold: int = 1000):
        self.dimension = dimension
        self.exact_search_threshold = exact_search_threshold

        self.annoy_index = CustomAnnoyIndex(dimension)
        self.all_vectors = {}  # prompt_id -> vector
        self.all_metadata = {}  # prompt_id -> metadata

    def add_vector(self, vector: np.ndarray, prompt_id: str, metadata: Dict[str, Any]):
        """Add vector to both Annoy index and exact search store"""
        self.annoy_index.add_vector(vector, prompt_id, metadata)
        self.all_vectors[prompt_id] = vector.copy()
        self.all_metadata[prompt_id] = metadata

    def build_index(self):
        """Build the Annoy index"""
        self.annoy_index.build()

    def search(self, query_vector: np.ndarray, k: int = 10,
               use_exact: bool = None, min_similarity: float = 0.0) -> List[AnnoySearchResult]:
        """Adaptive search using Annoy or exact search based on size"""

        total_vectors = len(self.all_vectors)

        # Decide search method
        if use_exact is None:
            use_exact = total_vectors <= self.exact_search_threshold

        if use_exact:
            return self._exact_search(query_vector, k, min_similarity)
        else:
            results = self.annoy_index.search(query_vector, k)
            # Filter by minimum similarity if specified
            if min_similarity > 0:
                results = [r for r in results if r.similarity >= min_similarity]
            return results

    def _exact_search(self, query_vector: np.ndarray, k: int,
                     min_similarity: float) -> List[AnnoySearchResult]:
        """Exact brute-force search for small datasets"""
        results = []

        query_norm = query_vector / np.linalg.norm(query_vector)

        for prompt_id, vector in self.all_vectors.items():
            vector_norm = vector / np.linalg.norm(vector)
            similarity = np.dot(query_norm, vector_norm)

            if similarity >= min_similarity:
                distance = 1.0 - similarity
                results.append(AnnoySearchResult(
                    prompt_id=prompt_id,
                    distance=distance,
                    similarity=similarity,
                    metadata=self.all_metadata[prompt_id]
                ))

        # Sort by similarity and return top k
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:k]

    def save(self, filepath: str):
        """Save hybrid index"""
        self.annoy_index.save(f"{filepath}_annoy")

        # Save exact search data
        exact_data = {
            'all_vectors': self.all_vectors,
            'all_metadata': self.all_metadata,
            'exact_search_threshold': self.exact_search_threshold
        }

        with open(f"{filepath}_exact.pkl", 'wb') as f:
            pickle.dump(exact_data, f)

    def load(self, filepath: str):
        """Load hybrid index"""
        self.annoy_index.load(f"{filepath}_annoy")

        with open(f"{filepath}_exact.pkl", 'rb') as f:
            exact_data = pickle.load(f)

        self.all_vectors = exact_data['all_vectors']
        self.all_metadata = exact_data['all_metadata']
        self.exact_search_threshold = exact_data['exact_search_threshold']

# Example and performance testing
async def test_annoy_implementations():
    """Test different Annoy-based implementations"""

    # Generate test data
    dimension = 384
    num_vectors = 573  # Your actual prompt count

    np.random.seed(42)
    vectors = {}
    metadata = {}

    for i in range(num_vectors):
        vector = np.random.randn(dimension)
        vector = vector / np.linalg.norm(vector)

        prompt_id = f"prompt_{i}"
        vectors[prompt_id] = vector
        metadata[prompt_id] = {
            'intent': ['build', 'improve', 'learn'][i % 3],
            'domain': ['AI', 'business', 'personal'][i % 3],
            'complexity': (i % 5) + 1
        }

    print(f"Testing Annoy implementations with {num_vectors} vectors")

    # Test 1: Basic Annoy Index
    print("\n1. Testing Basic Annoy Index")
    basic_annoy = CustomAnnoyIndex(dimension)

    start_time = asyncio.get_event_loop().time()
    for prompt_id, vector in vectors.items():
        basic_annoy.add_vector(vector, prompt_id, metadata[prompt_id])
    basic_annoy.build()
    build_time = asyncio.get_event_loop().time() - start_time

    print(f"Basic Annoy build time: {build_time:.3f}s")

    # Search test
    query_vector = np.random.randn(dimension)
    query_vector = query_vector / np.linalg.norm(query_vector)

    start_time = asyncio.get_event_loop().time()
    results = basic_annoy.search(query_vector, k=10)
    search_time = asyncio.get_event_loop().time() - start_time

    print(f"Basic Annoy search time: {search_time:.6f}s")
    print(f"Found {len(results)} results")

    # Test 2: Adaptive Annoy (multiple indices)
    print("\n2. Testing Adaptive Annoy Search")
    adaptive_annoy = AdaptiveAnnoySearch(dimension)

    start_time = asyncio.get_event_loop().time()
    for prompt_id, vector in vectors.items():
        adaptive_annoy.add_vector(vector, prompt_id, metadata[prompt_id])
    adaptive_annoy.build_indices()
    build_time = asyncio.get_event_loop().time() - start_time

    print(f"Adaptive Annoy build time: {build_time:.3f}s")

    # Test different strategies
    strategies = ['fast', 'balanced', 'accurate']
    for strategy in strategies:
        start_time = asyncio.get_event_loop().time()
        results = adaptive_annoy.search(query_vector, k=10, strategy=strategy)
        search_time = asyncio.get_event_loop().time() - start_time

        print(f"{strategy.capitalize()} search time: {search_time:.6f}s")

    # Test ensemble search
    start_time = asyncio.get_event_loop().time()
    ensemble_results = adaptive_annoy.search(query_vector, k=10, ensemble=True)
    search_time = asyncio.get_event_loop().time() - start_time

    print(f"Ensemble search time: {search_time:.6f}s")

    # Test 3: Hybrid Annoy (with exact search fallback)
    print("\n3. Testing Hybrid Annoy Search")
    hybrid_annoy = HybridAnnoySearch(dimension, exact_search_threshold=1000)

    start_time = asyncio.get_event_loop().time()
    for prompt_id, vector in vectors.items():
        hybrid_annoy.add_vector(vector, prompt_id, metadata[prompt_id])
    hybrid_annoy.build_index()
    build_time = asyncio.get_event_loop().time() - start_time

    print(f"Hybrid Annoy build time: {build_time:.3f}s")

    # Test with exact search (since 573 < 1000 threshold)
    start_time = asyncio.get_event_loop().time()
    exact_results = hybrid_annoy.search(query_vector, k=10, use_exact=True)
    search_time = asyncio.get_event_loop().time() - start_time

    print(f"Exact search time: {search_time:.6f}s")

    # Test with Annoy search
    start_time = asyncio.get_event_loop().time()
    annoy_results = hybrid_annoy.search(query_vector, k=10, use_exact=False)
    search_time = asyncio.get_event_loop().time() - start_time

    print(f"Annoy search time: {search_time:.6f}s")

    # Compare result quality
    print("\n4. Result Quality Comparison")
    print("Basic Annoy top 5:")
    for i, result in enumerate(results[:5], 1):
        print(f"  {i}. {result.prompt_id} (sim: {result.similarity:.3f})")

    print("Ensemble Annoy top 5:")
    for i, result in enumerate(ensemble_results[:5], 1):
        print(f"  {i}. {result.prompt_id} (sim: {result.similarity:.3f})")

    print("Exact search top 5:")
    for i, result in enumerate(exact_results[:5], 1):
        print(f"  {i}. {result.prompt_id} (sim: {result.similarity:.3f})")

if __name__ == "__main__":
    asyncio.run(test_annoy_implementations())
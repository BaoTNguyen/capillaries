#!/usr/bin/env python3
"""
Custom vector search implementation without FAISS
Includes custom HNSW, LSH, and hierarchical clustering approaches
"""

import numpy as np
import networkx as nx
from typing import List, Dict, Any, Tuple, Optional, Set
import heapq
import random
import pickle
from dataclasses import dataclass
from sklearn.metrics.pairwise import cosine_similarity, euclidean_distances
from sklearn.cluster import KMeans
import hashlib
from collections import defaultdict
import asyncio
import logging

logger = logging.getLogger(__name__)

@dataclass
class VectorSearchResult:
    prompt_id: str
    distance: float
    similarity: float
    metadata: Dict[str, Any]

class CustomHNSWIndex:
    """Custom Hierarchical Navigable Small World implementation"""

    def __init__(self, dimension: int, max_connections: int = 16,
                 ef_construction: int = 200, ml: float = 1/np.log(2.0)):
        self.dimension = dimension
        self.max_connections = max_connections  # M parameter
        self.ef_construction = ef_construction
        self.ml = ml  # Level generation factor

        # Multi-layer graphs
        self.graphs = {}  # layer -> networkx graph
        self.vectors = {}  # node_id -> vector
        self.metadata = {}  # node_id -> metadata
        self.entry_point = None
        self.node_counter = 0

    def _get_random_level(self) -> int:
        """Generate random level for new node"""
        level = 0
        while random.random() < self.ml and level < 16:  # Max 16 levels
            level += 1
        return level

    def _distance(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate distance between vectors (using cosine distance)"""
        # Normalize vectors for cosine similarity
        vec1_norm = vec1 / np.linalg.norm(vec1)
        vec2_norm = vec2 / np.linalg.norm(vec2)

        # Cosine distance = 1 - cosine similarity
        cos_sim = np.dot(vec1_norm, vec2_norm)
        return 1.0 - cos_sim

    def add_vector(self, vector: np.ndarray, prompt_id: str, metadata: Dict[str, Any]):
        """Add vector to HNSW index"""
        if vector.shape[0] != self.dimension:
            raise ValueError(f"Vector dimension {vector.shape[0]} doesn't match index dimension {self.dimension}")

        node_id = self.node_counter
        self.node_counter += 1

        # Store vector and metadata
        self.vectors[node_id] = vector.copy()
        self.metadata[node_id] = {'prompt_id': prompt_id, **metadata}

        # Determine level for this node
        level = self._get_random_level()

        # Initialize graphs if needed
        for lev in range(level + 1):
            if lev not in self.graphs:
                self.graphs[lev] = nx.Graph()
            self.graphs[lev].add_node(node_id)

        if self.entry_point is None:
            self.entry_point = node_id
            return

        # Search for closest nodes and connect
        current_closest = [self.entry_point]

        # Search from top level down to level+1
        for lev in range(max(self.graphs.keys()), level, -1):
            if lev in self.graphs:
                current_closest = self._search_layer(vector, current_closest, 1, lev)

        # Search and connect from level down to 0
        for lev in range(min(level, max(self.graphs.keys())), -1, -1):
            if lev not in self.graphs:
                continue

            candidates = self._search_layer(vector, current_closest, self.ef_construction, lev)

            # Select connections based on heuristic
            connections = self._select_neighbors_heuristic(vector, candidates,
                                                         self.max_connections if lev > 0 else self.max_connections * 2)

            # Add bidirectional connections
            for neighbor_id in connections:
                self.graphs[lev].add_edge(node_id, neighbor_id)

                # Prune connections if neighbor has too many
                neighbor_connections = list(self.graphs[lev].neighbors(neighbor_id))
                if len(neighbor_connections) > self.max_connections:
                    # Re-select best connections for neighbor
                    neighbor_vec = self.vectors[neighbor_id]
                    neighbor_candidates = [(n, self._distance(neighbor_vec, self.vectors[n]))
                                         for n in neighbor_connections]

                    best_neighbors = self._select_neighbors_heuristic(
                        neighbor_vec, neighbor_candidates, self.max_connections)

                    # Remove excess edges
                    for excess_neighbor in neighbor_connections:
                        if excess_neighbor not in best_neighbors:
                            self.graphs[lev].remove_edge(neighbor_id, excess_neighbor)

            current_closest = candidates

        # Update entry point if this node is at a higher level
        if level > self._get_node_level(self.entry_point):
            self.entry_point = node_id

    def _get_node_level(self, node_id: int) -> int:
        """Get the highest level containing this node"""
        max_level = -1
        for level, graph in self.graphs.items():
            if node_id in graph:
                max_level = max(max_level, level)
        return max_level

    def _search_layer(self, query_vector: np.ndarray, entry_points: List[int],
                     num_closest: int, level: int) -> List[int]:
        """Search single layer for closest nodes"""
        if level not in self.graphs:
            return entry_points

        graph = self.graphs[level]
        visited = set()
        candidates = []  # Min heap: (distance, node_id)
        dynamic_candidates = []  # Max heap: (-distance, node_id)

        # Initialize with entry points
        for ep in entry_points:
            if ep in graph:
                dist = self._distance(query_vector, self.vectors[ep])
                heapq.heappush(candidates, (dist, ep))
                heapq.heappush(dynamic_candidates, (-dist, ep))
                visited.add(ep)

        while candidates:
            current_dist, current_node = heapq.heappop(candidates)

            # Stop if current distance is worse than worst in dynamic candidates
            if len(dynamic_candidates) >= num_closest:
                worst_dist = -dynamic_candidates[0][0]
                if current_dist > worst_dist:
                    break

            # Explore neighbors
            for neighbor in graph.neighbors(current_node):
                if neighbor not in visited:
                    visited.add(neighbor)
                    dist = self._distance(query_vector, self.vectors[neighbor])

                    # Add to candidates for further exploration
                    heapq.heappush(candidates, (dist, neighbor))

                    # Add to dynamic candidates (results)
                    if len(dynamic_candidates) < num_closest:
                        heapq.heappush(dynamic_candidates, (-dist, neighbor))
                    elif dist < -dynamic_candidates[0][0]:
                        heapq.heappop(dynamic_candidates)
                        heapq.heappush(dynamic_candidates, (-dist, neighbor))

        # Return closest nodes
        result = []
        while dynamic_candidates:
            _, node_id = heapq.heappop(dynamic_candidates)
            result.append(node_id)

        return result[::-1]  # Reverse to get best first

    def _select_neighbors_heuristic(self, query_vector: np.ndarray,
                                   candidates: List[int], max_conn: int) -> List[int]:
        """Select best neighbors using heuristic to maintain connectivity"""
        if len(candidates) <= max_conn:
            return candidates

        # Calculate distances
        candidate_distances = [(node_id, self._distance(query_vector, self.vectors[node_id]))
                             for node_id in candidates]

        # Sort by distance
        candidate_distances.sort(key=lambda x: x[1])

        selected = []
        for node_id, dist in candidate_distances:
            if len(selected) >= max_conn:
                break

            # Simple heuristic: select if not too close to already selected
            add_node = True
            for selected_id in selected:
                selected_dist = self._distance(self.vectors[node_id], self.vectors[selected_id])
                if selected_dist < dist * 0.5:  # Too close to existing selection
                    add_node = False
                    break

            if add_node:
                selected.append(node_id)

        # Fill remaining slots with closest candidates if needed
        while len(selected) < max_conn and len(selected) < len(candidates):
            for node_id, _ in candidate_distances:
                if node_id not in selected:
                    selected.append(node_id)
                    break

        return selected

    def search(self, query_vector: np.ndarray, k: int = 10,
               ef_search: int = 50) -> List[VectorSearchResult]:
        """Search for k nearest neighbors"""
        if not self.vectors or self.entry_point is None:
            return []

        # Search from top level down to level 1
        current_closest = [self.entry_point]

        for level in range(max(self.graphs.keys()), 0, -1):
            if level in self.graphs:
                current_closest = self._search_layer(query_vector, current_closest, 1, level)

        # Search level 0 with higher ef
        if 0 in self.graphs:
            candidates = self._search_layer(query_vector, current_closest,
                                          max(ef_search, k), 0)
        else:
            candidates = current_closest

        # Convert to results with distances and similarities
        results = []
        for node_id in candidates[:k]:
            if node_id in self.vectors:
                distance = self._distance(query_vector, self.vectors[node_id])
                similarity = 1.0 - distance  # Convert distance to similarity

                results.append(VectorSearchResult(
                    prompt_id=self.metadata[node_id]['prompt_id'],
                    distance=distance,
                    similarity=similarity,
                    metadata=self.metadata[node_id]
                ))

        return results

    def save(self, filepath: str):
        """Save index to file"""
        data = {
            'dimension': self.dimension,
            'max_connections': self.max_connections,
            'ef_construction': self.ef_construction,
            'ml': self.ml,
            'graphs': self.graphs,
            'vectors': self.vectors,
            'metadata': self.metadata,
            'entry_point': self.entry_point,
            'node_counter': self.node_counter
        }

        with open(filepath, 'wb') as f:
            pickle.dump(data, f)

    def load(self, filepath: str):
        """Load index from file"""
        with open(filepath, 'rb') as f:
            data = pickle.load(f)

        self.dimension = data['dimension']
        self.max_connections = data['max_connections']
        self.ef_construction = data['ef_construction']
        self.ml = data['ml']
        self.graphs = data['graphs']
        self.vectors = data['vectors']
        self.metadata = data['metadata']
        self.entry_point = data['entry_point']
        self.node_counter = data['node_counter']

class LSHIndex:
    """Locality Sensitive Hashing for approximate vector search"""

    def __init__(self, dimension: int, num_hashes: int = 10, hash_size: int = 10):
        self.dimension = dimension
        self.num_hashes = num_hashes
        self.hash_size = hash_size

        # Generate random projection vectors
        self.hash_vectors = []
        for _ in range(num_hashes):
            # Each hash uses multiple random vectors
            hash_set = np.random.randn(hash_size, dimension)
            # Normalize
            hash_set = hash_set / np.linalg.norm(hash_set, axis=1, keepdims=True)
            self.hash_vectors.append(hash_set)

        # Hash tables: hash_value -> list of (prompt_id, vector, metadata)
        self.tables = [defaultdict(list) for _ in range(num_hashes)]
        self.all_vectors = {}  # prompt_id -> (vector, metadata)

    def _compute_hash(self, vector: np.ndarray, table_idx: int) -> str:
        """Compute hash for vector using specific hash table"""
        hash_vectors = self.hash_vectors[table_idx]

        # Compute dot products
        projections = np.dot(hash_vectors, vector)

        # Convert to binary hash
        binary_hash = (projections > 0).astype(int)

        # Convert binary to string
        return ''.join(map(str, binary_hash))

    def add_vector(self, vector: np.ndarray, prompt_id: str, metadata: Dict[str, Any]):
        """Add vector to LSH index"""
        if vector.shape[0] != self.dimension:
            raise ValueError(f"Vector dimension {vector.shape[0]} doesn't match index dimension {self.dimension}")

        # Store vector
        self.all_vectors[prompt_id] = (vector.copy(), metadata)

        # Add to each hash table
        for i, table in enumerate(self.tables):
            hash_value = self._compute_hash(vector, i)
            table[hash_value].append((prompt_id, vector.copy(), metadata))

    def search(self, query_vector: np.ndarray, k: int = 10,
               min_similarity: float = 0.5) -> List[VectorSearchResult]:
        """Search for similar vectors using LSH"""
        if not self.all_vectors:
            return []

        # Get candidate vectors from all hash tables
        candidates = set()

        for i, table in enumerate(self.tables):
            query_hash = self._compute_hash(query_vector, i)

            # Get all vectors with same hash
            for prompt_id, vector, metadata in table[query_hash]:
                candidates.add(prompt_id)

        # If no hash matches, fall back to searching all vectors
        if not candidates:
            candidates = set(self.all_vectors.keys())

        # Compute exact similarities for candidates
        results = []
        for prompt_id in candidates:
            vector, metadata = self.all_vectors[prompt_id]

            # Compute cosine similarity
            query_norm = query_vector / np.linalg.norm(query_vector)
            vector_norm = vector / np.linalg.norm(vector)
            similarity = np.dot(query_norm, vector_norm)

            if similarity >= min_similarity:
                distance = 1.0 - similarity
                results.append(VectorSearchResult(
                    prompt_id=prompt_id,
                    distance=distance,
                    similarity=similarity,
                    metadata=metadata
                ))

        # Sort by similarity and return top k
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:k]

    def save(self, filepath: str):
        """Save LSH index to file"""
        data = {
            'dimension': self.dimension,
            'num_hashes': self.num_hashes,
            'hash_size': self.hash_size,
            'hash_vectors': self.hash_vectors,
            'tables': self.tables,
            'all_vectors': self.all_vectors
        }

        with open(filepath, 'wb') as f:
            pickle.dump(data, f)

    def load(self, filepath: str):
        """Load LSH index from file"""
        with open(filepath, 'rb') as f:
            data = pickle.load(f)

        self.dimension = data['dimension']
        self.num_hashes = data['num_hashes']
        self.hash_size = data['hash_size']
        self.hash_vectors = data['hash_vectors']
        self.tables = data['tables']
        self.all_vectors = data['all_vectors']

class HierarchicalClusterIndex:
    """Hierarchical clustering-based vector search"""

    def __init__(self, dimension: int, max_cluster_size: int = 50, num_levels: int = 3):
        self.dimension = dimension
        self.max_cluster_size = max_cluster_size
        self.num_levels = num_levels

        # Hierarchical structure
        self.clusters = {}  # level -> cluster_id -> {'centroid': vector, 'members': [...], 'children': [...]}
        self.vectors = {}  # prompt_id -> vector
        self.metadata = {}  # prompt_id -> metadata
        self.prompt_to_clusters = {}  # prompt_id -> list of (level, cluster_id)

    def build_index(self, vectors: Dict[str, np.ndarray], metadata: Dict[str, Dict]):
        """Build hierarchical index from vectors"""
        if not vectors:
            return

        self.vectors = {pid: vec.copy() for pid, vec in vectors.items()}
        self.metadata = metadata.copy()

        # Start with all vectors at bottom level
        current_items = [(pid, vec) for pid, vec in vectors.items()]

        # Build hierarchy bottom-up
        for level in range(self.num_levels):
            self.clusters[level] = {}

            if len(current_items) <= self.max_cluster_size:
                # Single cluster for remaining items
                cluster_id = 0
                centroid = np.mean([vec for _, vec in current_items], axis=0)

                self.clusters[level][cluster_id] = {
                    'centroid': centroid,
                    'members': [pid for pid, _ in current_items],
                    'children': []
                }

                # Update prompt to cluster mapping
                for pid, _ in current_items:
                    if pid not in self.prompt_to_clusters:
                        self.prompt_to_clusters[pid] = []
                    self.prompt_to_clusters[pid].append((level, cluster_id))

                break

            # Cluster current level
            vectors_array = np.array([vec for _, vec in current_items])
            n_clusters = max(1, len(current_items) // self.max_cluster_size)

            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            cluster_labels = kmeans.fit_predict(vectors_array)

            # Create clusters
            next_level_items = []
            for cluster_id in range(n_clusters):
                cluster_mask = cluster_labels == cluster_id
                cluster_members = [current_items[i][0] for i in range(len(current_items)) if cluster_mask[i]]
                cluster_vectors = [current_items[i][1] for i in range(len(current_items)) if cluster_mask[i]]

                if cluster_vectors:
                    centroid = np.mean(cluster_vectors, axis=0)

                    self.clusters[level][cluster_id] = {
                        'centroid': centroid,
                        'members': cluster_members,
                        'children': []
                    }

                    # Update prompt to cluster mapping
                    for pid in cluster_members:
                        if pid not in self.prompt_to_clusters:
                            self.prompt_to_clusters[pid] = []
                        self.prompt_to_clusters[pid].append((level, cluster_id))

                    # Add centroid to next level
                    next_level_items.append((f"cluster_{level}_{cluster_id}", centroid))

            current_items = next_level_items

        logger.info(f"Built hierarchical index with {len(self.clusters)} levels")

    def search(self, query_vector: np.ndarray, k: int = 10,
               search_width: int = 3) -> List[VectorSearchResult]:
        """Search using hierarchical traversal"""
        if not self.clusters:
            return []

        # Start from top level
        top_level = max(self.clusters.keys())

        # Find closest clusters at each level
        candidate_clusters = [(top_level, list(self.clusters[top_level].keys()))]

        # Traverse down the hierarchy
        for level in range(top_level, -1, -1):
            if level not in self.clusters:
                continue

            current_candidates = []

            # Get clusters to search at this level
            clusters_to_search = []
            for search_level, cluster_ids in candidate_clusters:
                if search_level == level:
                    clusters_to_search.extend(cluster_ids)

            if not clusters_to_search:
                clusters_to_search = list(self.clusters[level].keys())

            # Find closest clusters at this level
            cluster_distances = []
            for cluster_id in clusters_to_search:
                cluster_info = self.clusters[level][cluster_id]
                centroid = cluster_info['centroid']

                # Compute distance to centroid
                distance = np.linalg.norm(query_vector - centroid)
                cluster_distances.append((distance, cluster_id))

            # Sort and take top candidates
            cluster_distances.sort()
            top_clusters = cluster_distances[:search_width]

            if level == 0:
                # Bottom level - collect actual vectors
                for _, cluster_id in top_clusters:
                    cluster_info = self.clusters[level][cluster_id]
                    for member_id in cluster_info['members']:
                        if member_id in self.vectors:
                            current_candidates.append(member_id)
            else:
                # Intermediate level - prepare for next level down
                current_candidates = [(level - 1, [cluster_id for _, cluster_id in top_clusters])]

            if level == 0:
                break
            else:
                candidate_clusters = current_candidates

        # Compute exact similarities for final candidates
        results = []
        final_candidates = current_candidates if level == 0 else []

        for prompt_id in final_candidates:
            if prompt_id in self.vectors:
                vector = self.vectors[prompt_id]

                # Compute cosine similarity
                query_norm = query_vector / np.linalg.norm(query_vector)
                vector_norm = vector / np.linalg.norm(vector)
                similarity = np.dot(query_norm, vector_norm)
                distance = 1.0 - similarity

                results.append(VectorSearchResult(
                    prompt_id=prompt_id,
                    distance=distance,
                    similarity=similarity,
                    metadata=self.metadata.get(prompt_id, {})
                ))

        # Sort by similarity and return top k
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:k]

    def save(self, filepath: str):
        """Save hierarchical index"""
        data = {
            'dimension': self.dimension,
            'max_cluster_size': self.max_cluster_size,
            'num_levels': self.num_levels,
            'clusters': self.clusters,
            'vectors': self.vectors,
            'metadata': self.metadata,
            'prompt_to_clusters': self.prompt_to_clusters
        }

        with open(filepath, 'wb') as f:
            pickle.dump(data, f)

    def load(self, filepath: str):
        """Load hierarchical index"""
        with open(filepath, 'rb') as f:
            data = pickle.load(f)

        self.dimension = data['dimension']
        self.max_cluster_size = data['max_cluster_size']
        self.num_levels = data['num_levels']
        self.clusters = data['clusters']
        self.vectors = data['vectors']
        self.metadata = data['metadata']
        self.prompt_to_clusters = data['prompt_to_clusters']

class MultiIndexVectorSearch:
    """Combines multiple search strategies for better recall and precision"""

    def __init__(self, dimension: int):
        self.dimension = dimension

        # Multiple indices
        self.hnsw_index = CustomHNSWIndex(dimension)
        self.lsh_index = LSHIndex(dimension, num_hashes=15, hash_size=12)
        self.hierarchical_index = HierarchicalClusterIndex(dimension)

        self.vectors_added = 0

    def add_vector(self, vector: np.ndarray, prompt_id: str, metadata: Dict[str, Any]):
        """Add vector to all indices"""
        self.hnsw_index.add_vector(vector, prompt_id, metadata)
        self.lsh_index.add_vector(vector, prompt_id, metadata)

        # For hierarchical index, we'll build it after all vectors are added
        self.vectors_added += 1

    def build_hierarchical_index(self, vectors: Dict[str, np.ndarray], metadata: Dict[str, Dict]):
        """Build the hierarchical index (call after adding all vectors)"""
        self.hierarchical_index.build_index(vectors, metadata)

    def search(self, query_vector: np.ndarray, k: int = 10,
               strategy: str = 'ensemble', weights: Dict[str, float] = None) -> List[VectorSearchResult]:
        """Multi-strategy search"""

        if weights is None:
            weights = {'hnsw': 0.5, 'lsh': 0.3, 'hierarchical': 0.2}

        if strategy == 'hnsw':
            return self.hnsw_index.search(query_vector, k)

        elif strategy == 'lsh':
            return self.lsh_index.search(query_vector, k)

        elif strategy == 'hierarchical':
            return self.hierarchical_index.search(query_vector, k)

        elif strategy == 'ensemble':
            # Get results from all indices
            hnsw_results = self.hnsw_index.search(query_vector, k * 2)
            lsh_results = self.lsh_index.search(query_vector, k * 2)
            hierarchical_results = self.hierarchical_index.search(query_vector, k * 2)

            # Combine results with weighted scoring
            combined_scores = defaultdict(float)
            all_results = {}

            # Add HNSW results
            for result in hnsw_results:
                combined_scores[result.prompt_id] += result.similarity * weights['hnsw']
                all_results[result.prompt_id] = result

            # Add LSH results
            for result in lsh_results:
                combined_scores[result.prompt_id] += result.similarity * weights['lsh']
                if result.prompt_id not in all_results:
                    all_results[result.prompt_id] = result

            # Add hierarchical results
            for result in hierarchical_results:
                combined_scores[result.prompt_id] += result.similarity * weights['hierarchical']
                if result.prompt_id not in all_results:
                    all_results[result.prompt_id] = result

            # Sort by combined score
            sorted_results = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)

            # Return top k results with updated scores
            final_results = []
            for prompt_id, combined_score in sorted_results[:k]:
                result = all_results[prompt_id]
                # Create new result with ensemble score
                final_results.append(VectorSearchResult(
                    prompt_id=result.prompt_id,
                    distance=1.0 - combined_score,
                    similarity=combined_score,
                    metadata=result.metadata
                ))

            return final_results

        else:
            raise ValueError(f"Unknown search strategy: {strategy}")

    def save(self, base_filepath: str):
        """Save all indices"""
        self.hnsw_index.save(f"{base_filepath}_hnsw.pkl")
        self.lsh_index.save(f"{base_filepath}_lsh.pkl")
        self.hierarchical_index.save(f"{base_filepath}_hierarchical.pkl")

    def load(self, base_filepath: str):
        """Load all indices"""
        self.hnsw_index.load(f"{base_filepath}_hnsw.pkl")
        self.lsh_index.load(f"{base_filepath}_lsh.pkl")
        self.hierarchical_index.load(f"{base_filepath}_hierarchical.pkl")

# Example usage and testing
async def test_custom_vector_search():
    """Test the custom vector search implementations"""

    # Generate sample data
    dimension = 384  # Typical sentence transformer dimension
    num_vectors = 100

    np.random.seed(42)
    vectors = {}
    metadata = {}

    for i in range(num_vectors):
        vector = np.random.randn(dimension)
        vector = vector / np.linalg.norm(vector)  # Normalize

        prompt_id = f"prompt_{i}"
        vectors[prompt_id] = vector
        metadata[prompt_id] = {
            'intent': ['build', 'improve'][i % 2],
            'domain': ['AI', 'business', 'personal'][i % 3],
            'complexity': (i % 5) + 1
        }

    print("Testing Custom Vector Search Implementations")

    # Test HNSW
    print("\n1. Testing Custom HNSW Index")
    hnsw = CustomHNSWIndex(dimension)

    start_time = asyncio.get_event_loop().time()
    for prompt_id, vector in vectors.items():
        hnsw.add_vector(vector, prompt_id, metadata[prompt_id])
    build_time = asyncio.get_event_loop().time() - start_time

    print(f"HNSW build time: {build_time:.3f}s")

    # Search test
    query_vector = np.random.randn(dimension)
    query_vector = query_vector / np.linalg.norm(query_vector)

    start_time = asyncio.get_event_loop().time()
    results = hnsw.search(query_vector, k=10)
    search_time = asyncio.get_event_loop().time() - start_time

    print(f"HNSW search time: {search_time:.3f}s")
    print(f"Found {len(results)} results")

    # Test LSH
    print("\n2. Testing LSH Index")
    lsh = LSHIndex(dimension)

    start_time = asyncio.get_event_loop().time()
    for prompt_id, vector in vectors.items():
        lsh.add_vector(vector, prompt_id, metadata[prompt_id])
    build_time = asyncio.get_event_loop().time() - start_time

    print(f"LSH build time: {build_time:.3f}s")

    start_time = asyncio.get_event_loop().time()
    results = lsh.search(query_vector, k=10)
    search_time = asyncio.get_event_loop().time() - start_time

    print(f"LSH search time: {search_time:.3f}s")
    print(f"Found {len(results)} results")

    # Test Hierarchical
    print("\n3. Testing Hierarchical Index")
    hierarchical = HierarchicalClusterIndex(dimension)

    start_time = asyncio.get_event_loop().time()
    hierarchical.build_index(vectors, metadata)
    build_time = asyncio.get_event_loop().time() - start_time

    print(f"Hierarchical build time: {build_time:.3f}s")

    start_time = asyncio.get_event_loop().time()
    results = hierarchical.search(query_vector, k=10)
    search_time = asyncio.get_event_loop().time() - start_time

    print(f"Hierarchical search time: {search_time:.3f}s")
    print(f"Found {len(results)} results")

    # Test Multi-Index Ensemble
    print("\n4. Testing Multi-Index Ensemble")
    multi_index = MultiIndexVectorSearch(dimension)

    start_time = asyncio.get_event_loop().time()
    for prompt_id, vector in vectors.items():
        multi_index.add_vector(vector, prompt_id, metadata[prompt_id])
    multi_index.build_hierarchical_index(vectors, metadata)
    build_time = asyncio.get_event_loop().time() - start_time

    print(f"Multi-index build time: {build_time:.3f}s")

    start_time = asyncio.get_event_loop().time()
    results = multi_index.search(query_vector, k=10, strategy='ensemble')
    search_time = asyncio.get_event_loop().time() - start_time

    print(f"Ensemble search time: {search_time:.3f}s")
    print(f"Found {len(results)} results")

    print("\nTop 5 ensemble results:")
    for i, result in enumerate(results[:5], 1):
        print(f"{i}. {result.prompt_id} (similarity: {result.similarity:.3f})")

if __name__ == "__main__":
    asyncio.run(test_custom_vector_search())
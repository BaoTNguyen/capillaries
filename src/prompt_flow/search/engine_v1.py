#!/usr/bin/env python3
"""
Custom semantic search engine with advanced retrieval capabilities
Goes beyond pgvector with custom HNSW, graph analytics, and multi-modal search
"""

import numpy as np
import networkx as nx
from typing import List, Dict, Any, Tuple, Optional
import json
import pickle
from dataclasses import dataclass
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict
import faiss
import asyncio
from sentence_transformers import SentenceTransformer
import psycopg2
from functools import lru_cache

@dataclass
class SearchResult:
    prompt_id: str
    score: float
    retrieval_sources: List[str]
    explanation: str
    metadata: Dict[str, Any]

class CustomVectorIndex:
    """High-performance vector search with FAISS backend"""

    def __init__(self, dimension: int = 768):
        self.dimension = dimension
        self.index = None
        self.prompt_ids = []
        self.metadata_cache = {}

        # Use HNSW for better recall than pgvector
        self.index = faiss.IndexHNSWFlat(dimension, 32)  # 32 connections per node
        self.index.hnsw.efConstruction = 200  # Higher quality index
        self.index.hnsw.efSearch = 100  # Search quality

    def build_index(self, embeddings: np.ndarray, prompt_ids: List[str], metadata: List[Dict]):
        """Build high-performance vector index"""
        print(f"Building HNSW index for {len(embeddings)} vectors...")

        # Normalize vectors for cosine similarity
        faiss.normalize_L2(embeddings)

        # Train and add vectors
        self.index.train(embeddings)
        self.index.add(embeddings)

        # Cache metadata
        self.prompt_ids = prompt_ids
        self.metadata_cache = {pid: meta for pid, meta in zip(prompt_ids, metadata)}

        print(f"Index built with {self.index.ntotal} vectors")

    def search(self, query_vector: np.ndarray, k: int = 50,
              min_similarity: float = 0.7) -> List[Tuple[str, float]]:
        """Search with similarity filtering"""
        # Normalize query vector
        query_vector = query_vector.reshape(1, -1)
        faiss.normalize_L2(query_vector)

        # Search with higher k for filtering
        distances, indices = self.index.search(query_vector, min(k * 2, self.index.ntotal))

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:  # Invalid result
                continue

            similarity = 1 - dist  # Convert distance to similarity
            if similarity >= min_similarity:
                results.append((self.prompt_ids[idx], similarity))

        return results[:k]

    def save(self, filepath: str):
        """Save index to disk"""
        faiss.write_index(self.index, f"{filepath}.faiss")

        with open(f"{filepath}.meta", 'wb') as f:
            pickle.dump({
                'prompt_ids': self.prompt_ids,
                'metadata_cache': self.metadata_cache,
                'dimension': self.dimension
            }, f)

    def load(self, filepath: str):
        """Load index from disk"""
        self.index = faiss.read_index(f"{filepath}.faiss")

        with open(f"{filepath}.meta", 'rb') as f:
            data = pickle.load(f)
            self.prompt_ids = data['prompt_ids']
            self.metadata_cache = data['metadata_cache']
            self.dimension = data['dimension']

class PromptGraphAnalyzer:
    """Graph-based analysis of prompt relationships and workflows"""

    def __init__(self):
        self.graph = nx.DiGraph()
        self.similarity_graph = nx.Graph()
        self.workflow_patterns = {}

    def build_prompt_graph(self, prompts: List[Dict], similarity_threshold: float = 0.8):
        """Build comprehensive prompt relationship graph"""

        # Add nodes
        for prompt in prompts:
            self.graph.add_node(prompt['prompt_id'], **prompt)

        # Add explicit parent-child relationships
        for prompt in prompts:
            if prompt.get('parent_prompt'):
                self.graph.add_edge(prompt['parent_prompt'], prompt['prompt_id'],
                                  relationship='parent_child', weight=1.0)

        # Add similarity-based edges
        self._add_similarity_edges(prompts, similarity_threshold)

        # Add workflow stage transitions
        self._add_workflow_edges(prompts)

        print(f"Built graph with {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")

    def _add_similarity_edges(self, prompts: List[Dict], threshold: float):
        """Add edges based on semantic similarity"""
        prompt_texts = [p['prompt_text'] for p in prompts]

        # Use sentence transformer for better semantic understanding
        model = SentenceTransformer('all-MiniLM-L6-v2')
        embeddings = model.encode(prompt_texts)

        # Compute similarity matrix
        similarity_matrix = cosine_similarity(embeddings)

        for i, prompt_i in enumerate(prompts):
            for j, prompt_j in enumerate(prompts[i+1:], i+1):
                similarity = similarity_matrix[i][j]

                if similarity >= threshold:
                    self.graph.add_edge(
                        prompt_i['prompt_id'], prompt_j['prompt_id'],
                        relationship='semantic_similar',
                        weight=similarity
                    )

                    # Also add to similarity graph for clustering
                    self.similarity_graph.add_edge(
                        prompt_i['prompt_id'], prompt_j['prompt_id'],
                        weight=similarity
                    )

    def _add_workflow_edges(self, prompts: List[Dict]):
        """Add workflow transition edges based on stages"""
        stage_order = {'clarify': 1, 'plan': 2, 'execute': 3, 'verify': 4, 'reflect': 5}

        # Group prompts by domain and task_type
        workflow_groups = defaultdict(list)
        for prompt in prompts:
            if prompt.get('primary_stage'):
                key = (tuple(sorted(prompt.get('domain', []))),
                       tuple(sorted(prompt.get('task_type', []))))
                workflow_groups[key].append(prompt)

        # Add workflow transition edges within groups
        for group_prompts in workflow_groups.values():
            # Sort by stage order
            group_prompts.sort(key=lambda p: stage_order.get(p.get('primary_stage', ''), 999))

            for i in range(len(group_prompts) - 1):
                current = group_prompts[i]
                next_prompt = group_prompts[i + 1]

                # Calculate workflow compatibility
                compatibility = self._calculate_workflow_compatibility(current, next_prompt)

                if compatibility > 0.5:
                    self.graph.add_edge(
                        current['prompt_id'], next_prompt['prompt_id'],
                        relationship='workflow_transition',
                        weight=compatibility
                    )

    def _calculate_workflow_compatibility(self, prompt1: Dict, prompt2: Dict) -> float:
        """Calculate how well two prompts work together in a workflow"""
        score = 0.0

        # Stage progression bonus
        stage_order = {'clarify': 1, 'plan': 2, 'execute': 3, 'verify': 4, 'reflect': 5}
        stage1 = stage_order.get(prompt1.get('primary_stage', ''), 0)
        stage2 = stage_order.get(prompt2.get('primary_stage', ''), 0)

        if stage2 == stage1 + 1:  # Sequential stages
            score += 0.4
        elif stage2 > stage1:  # Later stage
            score += 0.2

        # Domain overlap
        domain1 = set(prompt1.get('domain', []))
        domain2 = set(prompt2.get('domain', []))
        domain_overlap = len(domain1.intersection(domain2)) / len(domain1.union(domain2)) if domain1.union(domain2) else 0
        score += domain_overlap * 0.3

        # Task type compatibility
        task1 = set(prompt1.get('task_type', []))
        task2 = set(prompt2.get('task_type', []))
        task_overlap = len(task1.intersection(task2)) / len(task1.union(task2)) if task1.union(task2) else 0
        score += task_overlap * 0.3

        return min(score, 1.0)

    def find_workflow_paths(self, start_prompt_id: str, target_stages: List[str],
                           max_length: int = 5) -> List[List[str]]:
        """Find optimal workflow paths from start prompt to target stages"""
        paths = []

        def dfs_path_finder(current_id: str, path: List[str], remaining_stages: List[str]):
            if len(path) > max_length or not remaining_stages:
                if not remaining_stages:  # Found complete path
                    paths.append(path.copy())
                return

            current_node = self.graph.nodes[current_id]
            current_stage = current_node.get('primary_stage')

            # If current stage matches next required stage, remove it
            if current_stage in remaining_stages:
                new_remaining = remaining_stages.copy()
                new_remaining.remove(current_stage)
                dfs_path_finder(current_id, path, new_remaining)

            # Explore neighbors
            for neighbor in self.graph.successors(current_id):
                if neighbor not in path:  # Avoid cycles
                    edge_data = self.graph[current_id][neighbor]
                    if edge_data['relationship'] in ['workflow_transition', 'semantic_similar']:
                        dfs_path_finder(neighbor, path + [neighbor], remaining_stages)

        dfs_path_finder(start_prompt_id, [start_prompt_id], target_stages)

        # Score and sort paths
        scored_paths = []
        for path in paths:
            score = self._score_workflow_path(path)
            scored_paths.append((path, score))

        scored_paths.sort(key=lambda x: x[1], reverse=True)
        return [path for path, score in scored_paths[:10]]  # Top 10 paths

    def _score_workflow_path(self, path: List[str]) -> float:
        """Score a workflow path based on multiple criteria"""
        if len(path) < 2:
            return 0.0

        total_score = 0.0

        # Sum edge weights in path
        for i in range(len(path) - 1):
            if self.graph.has_edge(path[i], path[i+1]):
                edge_weight = self.graph[path[i]][path[i+1]]['weight']
                total_score += edge_weight

        # Normalize by path length
        return total_score / (len(path) - 1)

    def detect_prompt_clusters(self, min_cluster_size: int = 3) -> Dict[int, List[str]]:
        """Detect clusters of similar prompts using community detection"""
        if not self.similarity_graph.nodes():
            return {}

        # Use Louvain community detection
        import community as community_louvain
        partition = community_louvain.best_partition(self.similarity_graph)

        # Group by community
        clusters = defaultdict(list)
        for prompt_id, cluster_id in partition.items():
            clusters[cluster_id].append(prompt_id)

        # Filter by minimum cluster size
        return {cid: prompts for cid, prompts in clusters.items()
                if len(prompts) >= min_cluster_size}

class HybridSearchEngine:
    """Advanced search combining multiple retrieval methods"""

    def __init__(self, db_config: Dict[str, str]):
        self.db_config = db_config
        self.vector_index = CustomVectorIndex()
        self.graph_analyzer = PromptGraphAnalyzer()
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

        # Cache for performance
        self.metadata_cache = {}
        self.compatibility_cache = {}

    async def initialize(self):
        """Initialize search engine with data from database"""
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()

        # Load all prompts
        cursor.execute("""
            SELECT prompt_id, prompt_text, intent, task_type, domain,
                   primary_stage, complexity_level, status
            FROM prompts WHERE status = 'active'
        """)

        prompts = []
        for row in cursor.fetchall():
            prompts.append({
                'prompt_id': row[0],
                'prompt_text': row[1],
                'intent': row[2] or [],
                'task_type': row[3] or [],
                'domain': row[4] or [],
                'primary_stage': row[5],
                'complexity_level': row[6],
                'status': row[7]
            })

        cursor.close()
        conn.close()

        print(f"Initializing search engine with {len(prompts)} prompts...")

        # Generate embeddings
        embeddings = self.embedding_model.encode([p['prompt_text'] for p in prompts])

        # Build vector index
        self.vector_index.build_index(
            embeddings,
            [p['prompt_id'] for p in prompts],
            prompts
        )

        # Build graph
        self.graph_analyzer.build_prompt_graph(prompts)

        # Cache metadata
        self.metadata_cache = {p['prompt_id']: p for p in prompts}

        print("Search engine initialization complete!")

    async def search(self, query: str, search_params: Dict[str, Any]) -> List[SearchResult]:
        """Advanced hybrid search with multiple retrieval methods"""

        results = {}  # Deduplicate by prompt_id

        # 1. Vector similarity search
        vector_results = await self._vector_search(query, search_params)
        for result in vector_results:
            if result.prompt_id not in results:
                results[result.prompt_id] = result
            else:
                # Combine scores from multiple sources
                results[result.prompt_id].score = max(results[result.prompt_id].score, result.score)
                results[result.prompt_id].retrieval_sources.extend(result.retrieval_sources)

        # 2. Graph-based retrieval
        graph_results = await self._graph_search(query, search_params, list(results.keys())[:10])
        for result in graph_results:
            if result.prompt_id not in results:
                results[result.prompt_id] = result
            else:
                results[result.prompt_id].score += result.score * 0.3  # Boost from graph
                results[result.prompt_id].retrieval_sources.extend(result.retrieval_sources)

        # 3. Workflow-aware expansion
        if search_params.get('expand_workflow', False):
            workflow_results = await self._workflow_expansion(list(results.keys())[:5], search_params)
            for result in workflow_results:
                if result.prompt_id not in results:
                    results[result.prompt_id] = result

        # 4. Re-rank with advanced scoring
        final_results = await self._rerank_results(list(results.values()), query, search_params)

        return final_results[:search_params.get('k', 10)]

    async def _vector_search(self, query: str, params: Dict) -> List[SearchResult]:
        """Enhanced vector search with filtering"""
        query_embedding = self.embedding_model.encode([query])

        # Get vector similarities
        vector_matches = self.vector_index.search(
            query_embedding[0],
            k=params.get('vector_k', 50),
            min_similarity=params.get('min_similarity', 0.6)
        )

        results = []
        for prompt_id, similarity in vector_matches:
            metadata = self.metadata_cache.get(prompt_id, {})

            # Apply metadata filters
            if self._passes_filters(metadata, params):
                results.append(SearchResult(
                    prompt_id=prompt_id,
                    score=similarity,
                    retrieval_sources=['vector_similarity'],
                    explanation=f"Semantic similarity: {similarity:.3f}",
                    metadata=metadata
                ))

        return results

    async def _graph_search(self, query: str, params: Dict, seed_prompts: List[str]) -> List[SearchResult]:
        """Graph-based expansion from seed prompts"""
        results = []

        for seed_prompt in seed_prompts:
            if seed_prompt not in self.graph_analyzer.graph.nodes:
                continue

            # Find neighbors with high relationship weights
            neighbors = []
            for neighbor in self.graph_analyzer.graph.neighbors(seed_prompt):
                edge_data = self.graph_analyzer.graph[seed_prompt][neighbor]
                neighbors.append((neighbor, edge_data['weight'], edge_data['relationship']))

            # Sort by relationship strength
            neighbors.sort(key=lambda x: x[1], reverse=True)

            for neighbor_id, weight, relationship in neighbors[:5]:
                metadata = self.metadata_cache.get(neighbor_id, {})

                if self._passes_filters(metadata, params):
                    results.append(SearchResult(
                        prompt_id=neighbor_id,
                        score=weight * 0.7,  # Lower than direct similarity
                        retrieval_sources=[f'graph_{relationship}'],
                        explanation=f"Graph relationship: {relationship} (weight: {weight:.3f})",
                        metadata=metadata
                    ))

        return results

    async def _workflow_expansion(self, seed_prompts: List[str], params: Dict) -> List[SearchResult]:
        """Expand to complete workflow chains"""
        target_stages = params.get('required_stages', ['plan', 'execute', 'verify'])
        results = []

        for seed_prompt in seed_prompts:
            workflow_paths = self.graph_analyzer.find_workflow_paths(
                seed_prompt, target_stages, max_length=5
            )

            for path in workflow_paths[:2]:  # Top 2 paths per seed
                for prompt_id in path:
                    if prompt_id != seed_prompt:
                        metadata = self.metadata_cache.get(prompt_id, {})

                        if self._passes_filters(metadata, params):
                            path_score = self.graph_analyzer._score_workflow_path(path)
                            results.append(SearchResult(
                                prompt_id=prompt_id,
                                score=path_score * 0.6,
                                retrieval_sources=['workflow_expansion'],
                                explanation=f"Workflow path completion (score: {path_score:.3f})",
                                metadata=metadata
                            ))

        return results

    def _passes_filters(self, metadata: Dict, params: Dict) -> bool:
        """Check if prompt passes metadata filters"""
        # Domain filter
        if params.get('domains'):
            if not any(d in metadata.get('domain', []) for d in params['domains']):
                return False

        # Task type filter
        if params.get('task_types'):
            if not any(t in metadata.get('task_type', []) for t in params['task_types']):
                return False

        # Complexity filter
        if params.get('max_complexity'):
            if metadata.get('complexity_level', 5) > params['max_complexity']:
                return False

        # Stage filter
        if params.get('stages'):
            if metadata.get('primary_stage') not in params['stages']:
                return False

        return True

    async def _rerank_results(self, results: List[SearchResult], query: str, params: Dict) -> List[SearchResult]:
        """Advanced re-ranking with multiple signals"""

        for result in results:
            # Base score from retrieval
            base_score = result.score

            # Boost for metadata completeness
            metadata = result.metadata
            completeness_bonus = 0
            if metadata.get('intent'): completeness_bonus += 0.05
            if metadata.get('task_type'): completeness_bonus += 0.05
            if metadata.get('domain'): completeness_bonus += 0.05

            # Boost for multiple retrieval sources (ensemble effect)
            source_diversity_bonus = len(set(result.retrieval_sources)) * 0.02

            # Complexity alignment
            target_complexity = params.get('target_complexity', 3)
            actual_complexity = metadata.get('complexity_level', 3)
            complexity_penalty = abs(target_complexity - actual_complexity) * 0.02

            # Final score
            result.score = base_score + completeness_bonus + source_diversity_bonus - complexity_penalty

        # Sort by final score
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def save_indices(self, base_path: str):
        """Save all indices for faster startup"""
        self.vector_index.save(f"{base_path}_vector")

        with open(f"{base_path}_graph.pkl", 'wb') as f:
            pickle.dump(self.graph_analyzer, f)

    def load_indices(self, base_path: str):
        """Load pre-built indices"""
        self.vector_index.load(f"{base_path}_vector")

        with open(f"{base_path}_graph.pkl", 'rb') as f:
            self.graph_analyzer = pickle.load(f)

# Example usage
async def main():
    """Example of how to use the custom search engine"""

    DB_CONFIG = {
        'host': 'localhost',
        'database': 'prompt_flow',
        'user': 'bao',
        'password': ''
    }

    # Initialize search engine
    search_engine = HybridSearchEngine(DB_CONFIG)
    await search_engine.initialize()

    # Example searches
    search_params = {
        'k': 10,
        'domains': ['AI', 'business'],
        'expand_workflow': True,
        'required_stages': ['plan', 'execute'],
        'target_complexity': 3
    }

    results = await search_engine.search("Create a content strategy for social media", search_params)

    print("Search Results:")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result.prompt_id} (score: {result.score:.3f})")
        print(f"   Sources: {', '.join(result.retrieval_sources)}")
        print(f"   {result.explanation}")
        print()

if __name__ == "__main__":
    asyncio.run(main())
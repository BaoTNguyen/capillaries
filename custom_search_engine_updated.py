#!/usr/bin/env python3
"""
Updated custom search engine using custom vector implementations (no FAISS)
Integrates custom HNSW, LSH, Annoy, and hierarchical clustering
"""

import numpy as np
import networkx as nx
from typing import List, Dict, Any, Tuple, Optional
import json
import asyncio
from dataclasses import dataclass
from collections import defaultdict
from sentence_transformers import SentenceTransformer
import psycopg2
import logging

# Import our custom vector search implementations
from custom_vector_search import MultiIndexVectorSearch, VectorSearchResult
from annoy_vector_search import AdaptiveAnnoySearch, AnnoySearchResult

logger = logging.getLogger(__name__)

@dataclass
class EnhancedSearchResult:
    prompt_id: str
    score: float
    retrieval_sources: List[str]
    explanation: str
    metadata: Dict[str, Any]
    confidence: float = 0.0

class CustomSearchEngine:
    """Enhanced search engine using custom vector implementations"""

    def __init__(self, db_config: Dict[str, str], vector_strategy: str = 'multi_index'):
        self.db_config = db_config
        self.vector_strategy = vector_strategy

        # Vector search engines
        self.vector_engines = {}
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.dimension = 384  # MiniLM dimension

        # Graph analyzer for workflow relationships
        self.graph_analyzer = PromptGraphAnalyzer()

        # Metadata cache
        self.metadata_cache = {}
        self.vectors_cache = {}

        # Initialize vector engines based on strategy
        self._initialize_vector_engines()

    def _initialize_vector_engines(self):
        """Initialize vector search engines based on strategy"""
        if self.vector_strategy == 'multi_index':
            self.vector_engines['primary'] = MultiIndexVectorSearch(self.dimension)

        elif self.vector_strategy == 'annoy':
            self.vector_engines['primary'] = AdaptiveAnnoySearch(self.dimension)

        elif self.vector_strategy == 'hybrid':
            # Use both for comparison
            self.vector_engines['multi'] = MultiIndexVectorSearch(self.dimension)
            self.vector_engines['annoy'] = AdaptiveAnnoySearch(self.dimension)

        else:
            raise ValueError(f"Unknown vector strategy: {self.vector_strategy}")

    async def initialize(self):
        """Initialize search engine with data from database"""
        logger.info("Initializing custom search engine...")

        # Load prompts from database
        prompts = await self._load_prompts_from_db()

        logger.info(f"Loaded {len(prompts)} prompts from database")

        # Generate embeddings
        logger.info("Generating embeddings...")
        embeddings = await self._generate_embeddings([p['prompt_text'] for p in prompts])

        # Build vector indices
        logger.info("Building vector indices...")
        await self._build_vector_indices(prompts, embeddings)

        # Build graph for workflow analysis
        logger.info("Building prompt relationship graph...")
        self.graph_analyzer.build_prompt_graph(prompts)

        # Cache metadata and vectors
        for i, prompt in enumerate(prompts):
            self.metadata_cache[prompt['prompt_id']] = prompt
            self.vectors_cache[prompt['prompt_id']] = embeddings[i]

        logger.info("Search engine initialization complete!")

    async def _load_prompts_from_db(self) -> List[Dict]:
        """Load prompts from PostgreSQL database"""
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()

        query = """
            SELECT prompt_id, prompt_text, intent, task_type, domain,
                   primary_stage, secondary_stages, complexity_level,
                   input_schema, output_schema, context_variables,
                   accomplishes, parent_prompt, status
            FROM prompts
            WHERE status = 'active' AND backfill_status = 'completed'
            ORDER BY last_updated DESC
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        prompts = []
        for row in rows:
            prompts.append({
                'prompt_id': row[0],
                'prompt_text': row[1],
                'intent': row[2] or [],
                'task_type': row[3] or [],
                'domain': row[4] or [],
                'primary_stage': row[5],
                'secondary_stages': row[6] or [],
                'complexity_level': row[7] or 3,
                'input_schema': row[8],
                'output_schema': row[9],
                'context_variables': row[10] or [],
                'accomplishes': row[11],
                'parent_prompt': row[12],
                'status': row[13]
            })

        cursor.close()
        conn.close()

        return prompts

    async def _generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for prompt texts"""
        # Process in batches to avoid memory issues
        batch_size = 32
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_embeddings = self.embedding_model.encode(batch_texts)
            all_embeddings.extend(batch_embeddings)

            logger.info(f"Generated embeddings for batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")

        return np.array(all_embeddings)

    async def _build_vector_indices(self, prompts: List[Dict], embeddings: np.ndarray):
        """Build all vector search indices"""

        if self.vector_strategy in ['multi_index', 'hybrid']:
            # Build multi-index engine
            engine = self.vector_engines.get('multi') or self.vector_engines['primary']

            for i, prompt in enumerate(prompts):
                engine.add_vector(embeddings[i], prompt['prompt_id'], prompt)

            # Build hierarchical index (requires all vectors)
            vectors_dict = {prompt['prompt_id']: embeddings[i] for i, prompt in enumerate(prompts)}
            metadata_dict = {prompt['prompt_id']: prompt for prompt in prompts}
            engine.build_hierarchical_index(vectors_dict, metadata_dict)

        if self.vector_strategy in ['annoy', 'hybrid']:
            # Build Annoy engine
            engine = self.vector_engines.get('annoy') or self.vector_engines['primary']

            for i, prompt in enumerate(prompts):
                engine.add_vector(embeddings[i], prompt['prompt_id'], prompt)

            engine.build_indices()

        logger.info("Vector indices built successfully")

    async def search(self, query: str, search_params: Dict[str, Any]) -> List[EnhancedSearchResult]:
        """Advanced search with custom vector engines"""

        # Generate query embedding
        query_embedding = self.embedding_model.encode([query])[0]

        # Get vector search results
        vector_results = await self._vector_search(query_embedding, search_params)

        # Get graph-based results
        graph_results = await self._graph_search(query, search_params, vector_results[:10])

        # Combine and rerank results
        combined_results = await self._combine_and_rerank(
            vector_results, graph_results, query, search_params
        )

        return combined_results[:search_params.get('k', 10)]

    async def _vector_search(self, query_embedding: np.ndarray,
                           params: Dict) -> List[EnhancedSearchResult]:
        """Vector similarity search using custom implementations"""

        k = params.get('vector_k', 50)
        results = []

        if self.vector_strategy == 'multi_index':
            # Use multi-index strategy
            engine = self.vector_engines['primary']
            search_strategy = params.get('multi_strategy', 'ensemble')
            raw_results = engine.search(query_embedding, k=k, strategy=search_strategy)

            for result in raw_results:
                results.append(EnhancedSearchResult(
                    prompt_id=result.prompt_id,
                    score=result.similarity,
                    retrieval_sources=[f'vector_{search_strategy}'],
                    explanation=f"Multi-index {search_strategy} similarity: {result.similarity:.3f}",
                    metadata=result.metadata,
                    confidence=result.similarity
                ))

        elif self.vector_strategy == 'annoy':
            # Use Annoy strategy
            engine = self.vector_engines['primary']
            annoy_strategy = params.get('annoy_strategy', 'balanced')
            ensemble = params.get('annoy_ensemble', False)

            raw_results = engine.search(query_embedding, k=k,
                                      strategy=annoy_strategy, ensemble=ensemble)

            strategy_name = 'ensemble' if ensemble else annoy_strategy
            for result in raw_results:
                results.append(EnhancedSearchResult(
                    prompt_id=result.prompt_id,
                    score=result.similarity,
                    retrieval_sources=[f'annoy_{strategy_name}'],
                    explanation=f"Annoy {strategy_name} similarity: {result.similarity:.3f}",
                    metadata=result.metadata,
                    confidence=result.similarity
                ))

        elif self.vector_strategy == 'hybrid':
            # Use both engines and combine
            multi_results = self.vector_engines['multi'].search(
                query_embedding, k=k//2, strategy='ensemble')

            annoy_results = self.vector_engines['annoy'].search(
                query_embedding, k=k//2, strategy='balanced', ensemble=True)

            # Combine results from both engines
            all_results = {}

            # Add multi-index results
            for result in multi_results:
                all_results[result.prompt_id] = EnhancedSearchResult(
                    prompt_id=result.prompt_id,
                    score=result.similarity * 0.6,  # Weight multi-index
                    retrieval_sources=['multi_index'],
                    explanation=f"Multi-index similarity: {result.similarity:.3f}",
                    metadata=result.metadata,
                    confidence=result.similarity * 0.6
                )

            # Add Annoy results
            for result in annoy_results:
                if result.prompt_id in all_results:
                    # Boost existing result
                    existing = all_results[result.prompt_id]
                    existing.score += result.similarity * 0.4
                    existing.retrieval_sources.append('annoy_ensemble')
                    existing.confidence = max(existing.confidence, result.similarity * 0.4)
                else:
                    # New result
                    all_results[result.prompt_id] = EnhancedSearchResult(
                        prompt_id=result.prompt_id,
                        score=result.similarity * 0.4,
                        retrieval_sources=['annoy_ensemble'],
                        explanation=f"Annoy ensemble similarity: {result.similarity:.3f}",
                        metadata=result.metadata,
                        confidence=result.similarity * 0.4
                    )

            results = list(all_results.values())

        # Apply metadata filters
        filtered_results = []
        for result in results:
            if self._passes_filters(result.metadata, params):
                filtered_results.append(result)

        # Sort by score
        filtered_results.sort(key=lambda x: x.score, reverse=True)

        return filtered_results

    async def _graph_search(self, query: str, params: Dict,
                          seed_results: List[EnhancedSearchResult]) -> List[EnhancedSearchResult]:
        """Graph-based search expansion"""

        if not params.get('expand_graph', True):
            return []

        results = []
        seed_prompts = [r.prompt_id for r in seed_results[:5]]  # Use top 5 as seeds

        for seed_prompt in seed_prompts:
            if seed_prompt not in self.graph_analyzer.graph.nodes:
                continue

            # Find graph neighbors
            neighbors = []
            for neighbor in self.graph_analyzer.graph.neighbors(seed_prompt):
                if self.graph_analyzer.graph.has_edge(seed_prompt, neighbor):
                    edge_data = self.graph_analyzer.graph[seed_prompt][neighbor]
                    neighbors.append((neighbor, edge_data.get('weight', 0.5),
                                    edge_data.get('relationship', 'unknown')))

            # Sort by relationship strength
            neighbors.sort(key=lambda x: x[1], reverse=True)

            # Add top neighbors as results
            for neighbor_id, weight, relationship in neighbors[:3]:
                if neighbor_id in self.metadata_cache:
                    metadata = self.metadata_cache[neighbor_id]

                    if self._passes_filters(metadata, params):
                        results.append(EnhancedSearchResult(
                            prompt_id=neighbor_id,
                            score=weight * 0.7,  # Lower than direct vector similarity
                            retrieval_sources=[f'graph_{relationship}'],
                            explanation=f"Graph {relationship} from {seed_prompt}: {weight:.3f}",
                            metadata=metadata,
                            confidence=weight * 0.6
                        ))

        return results

    async def _combine_and_rerank(self, vector_results: List[EnhancedSearchResult],
                                graph_results: List[EnhancedSearchResult],
                                query: str, params: Dict) -> List[EnhancedSearchResult]:
        """Combine results from different sources and rerank"""

        # Combine results, avoiding duplicates
        all_results = {}

        # Add vector results
        for result in vector_results:
            all_results[result.prompt_id] = result

        # Add graph results, boosting existing or creating new
        for result in graph_results:
            if result.prompt_id in all_results:
                # Boost existing result
                existing = all_results[result.prompt_id]
                existing.score += result.score * 0.3  # Graph boost
                existing.retrieval_sources.extend(result.retrieval_sources)
                existing.confidence = max(existing.confidence, result.confidence)
            else:
                # New result from graph only
                all_results[result.prompt_id] = result

        # Apply additional ranking factors
        final_results = []
        for result in all_results.values():
            # Metadata completeness bonus
            completeness = self._calculate_metadata_completeness(result.metadata)
            result.score += completeness * 0.05

            # Complexity matching
            target_complexity = params.get('target_complexity', 3)
            actual_complexity = result.metadata.get('complexity_level', 3)
            complexity_penalty = abs(target_complexity - actual_complexity) * 0.02
            result.score -= complexity_penalty

            # Multi-source bonus
            source_diversity = len(set(result.retrieval_sources))
            result.score += (source_diversity - 1) * 0.03

            final_results.append(result)

        # Sort by final score
        final_results.sort(key=lambda x: x.score, reverse=True)

        return final_results

    def _passes_filters(self, metadata: Dict, params: Dict) -> bool:
        """Check if prompt passes metadata filters"""
        # Domain filter
        if params.get('domains'):
            prompt_domains = set(metadata.get('domain', []))
            filter_domains = set(params['domains'])
            if not prompt_domains.intersection(filter_domains):
                return False

        # Task type filter
        if params.get('task_types'):
            prompt_tasks = set(metadata.get('task_type', []))
            filter_tasks = set(params['task_types'])
            if not prompt_tasks.intersection(filter_tasks):
                return False

        # Intent filter
        if params.get('intents'):
            prompt_intents = set(metadata.get('intent', []))
            filter_intents = set(params['intents'])
            if not prompt_intents.intersection(filter_intents):
                return False

        # Complexity filter
        if params.get('max_complexity'):
            if metadata.get('complexity_level', 5) > params['max_complexity']:
                return False

        if params.get('min_complexity'):
            if metadata.get('complexity_level', 1) < params['min_complexity']:
                return False

        # Stage filter
        if params.get('stages'):
            prompt_stage = metadata.get('primary_stage')
            if prompt_stage not in params['stages']:
                return False

        return True

    def _calculate_metadata_completeness(self, metadata: Dict) -> float:
        """Calculate how complete the metadata is"""
        important_fields = ['intent', 'task_type', 'domain', 'primary_stage',
                          'input_schema', 'output_schema', 'accomplishes']

        filled_fields = 0
        for field in important_fields:
            value = metadata.get(field)
            if value and (isinstance(value, list) and len(value) > 0 or
                         isinstance(value, str) and value.strip()):
                filled_fields += 1

        return filled_fields / len(important_fields)

    def save_indices(self, base_path: str):
        """Save all search indices"""
        for name, engine in self.vector_engines.items():
            engine.save(f"{base_path}_{name}")

        # Save graph analyzer
        import pickle
        with open(f"{base_path}_graph.pkl", 'wb') as f:
            pickle.dump(self.graph_analyzer, f)

    def load_indices(self, base_path: str):
        """Load pre-built indices"""
        for name, engine in self.vector_engines.items():
            engine.load(f"{base_path}_{name}")

        # Load graph analyzer
        import pickle
        with open(f"{base_path}_graph.pkl", 'rb') as f:
            self.graph_analyzer = pickle.load(f)

# Copy the PromptGraphAnalyzer from previous implementation
class PromptGraphAnalyzer:
    """Graph-based analysis of prompt relationships and workflows"""

    def __init__(self):
        self.graph = nx.DiGraph()
        self.similarity_graph = nx.Graph()

    def build_prompt_graph(self, prompts: List[Dict], similarity_threshold: float = 0.8):
        """Build comprehensive prompt relationship graph"""
        # Add nodes
        for prompt in prompts:
            self.graph.add_node(prompt['prompt_id'], **prompt)

        # Add parent-child relationships
        for prompt in prompts:
            if prompt.get('parent_prompt'):
                self.graph.add_edge(prompt['parent_prompt'], prompt['prompt_id'],
                                  relationship='parent_child', weight=1.0)

        # Add workflow stage transitions and other relationships
        self._add_workflow_edges(prompts)

        logger.info(f"Built graph with {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")

    def _add_workflow_edges(self, prompts: List[Dict]):
        """Add workflow transition edges based on stages and metadata similarity"""
        stage_order = {'clarify': 1, 'plan': 2, 'execute': 3, 'verify': 4, 'reflect': 5}

        # Group prompts by domain and task_type combinations
        workflow_groups = defaultdict(list)
        for prompt in prompts:
            if prompt.get('primary_stage'):
                domain_key = tuple(sorted(prompt.get('domain', [])))
                task_key = tuple(sorted(prompt.get('task_type', [])))
                key = (domain_key, task_key)
                workflow_groups[key].append(prompt)

        # Add workflow edges within groups
        for group_prompts in workflow_groups.values():
            if len(group_prompts) < 2:
                continue

            # Sort by stage order
            group_prompts.sort(key=lambda p: stage_order.get(p.get('primary_stage', ''), 999))

            for i in range(len(group_prompts) - 1):
                current = group_prompts[i]
                next_prompt = group_prompts[i + 1]

                # Calculate workflow compatibility
                compatibility = self._calculate_workflow_compatibility(current, next_prompt)

                if compatibility > 0.4:  # Lower threshold for more connections
                    self.graph.add_edge(
                        current['prompt_id'], next_prompt['prompt_id'],
                        relationship='workflow_transition',
                        weight=compatibility
                    )

    def _calculate_workflow_compatibility(self, prompt1: Dict, prompt2: Dict) -> float:
        """Calculate workflow compatibility between two prompts"""
        score = 0.0

        # Stage progression
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
        if domain1 and domain2:
            domain_overlap = len(domain1.intersection(domain2)) / len(domain1.union(domain2))
            score += domain_overlap * 0.3

        # Task type overlap
        task1 = set(prompt1.get('task_type', []))
        task2 = set(prompt2.get('task_type', []))
        if task1 and task2:
            task_overlap = len(task1.intersection(task2)) / len(task1.union(task2))
            score += task_overlap * 0.3

        return min(score, 1.0)

# Example usage
async def example_custom_search():
    """Example of using the updated custom search engine"""

    DB_CONFIG = {
        'host': 'localhost',
        'database': 'prompt_flow',
        'user': 'bao',
        'password': ''
    }

    # Test different vector strategies
    strategies = ['multi_index', 'annoy', 'hybrid']

    for strategy in strategies:
        print(f"\n=== Testing {strategy.upper()} Strategy ===")

        # Initialize search engine
        search_engine = CustomSearchEngine(DB_CONFIG, vector_strategy=strategy)
        await search_engine.initialize()

        # Example search
        search_params = {
            'k': 10,
            'domains': ['business', 'AI'],
            'expand_graph': True,
            'target_complexity': 3,
            'vector_k': 20
        }

        if strategy == 'multi_index':
            search_params['multi_strategy'] = 'ensemble'
        elif strategy == 'annoy':
            search_params['annoy_strategy'] = 'balanced'
            search_params['annoy_ensemble'] = True

        results = await search_engine.search(
            "Create a comprehensive marketing strategy for a new AI product",
            search_params
        )

        print(f"Found {len(results)} results:")
        for i, result in enumerate(results[:5], 1):
            print(f"{i}. {result.prompt_id} (score: {result.score:.3f})")
            print(f"   Sources: {', '.join(result.retrieval_sources)}")
            print(f"   Confidence: {result.confidence:.3f}")
            print(f"   {result.explanation}")
            print()

if __name__ == "__main__":
    asyncio.run(example_custom_search())
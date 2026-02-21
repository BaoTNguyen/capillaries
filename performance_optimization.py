#!/usr/bin/env python3
"""
Performance optimization for custom search engine
Includes caching, pre-computation, and production optimizations
"""

import redis
import asyncio
import pickle
from functools import wraps
from typing import Dict, List, Any, Optional
import hashlib
import numpy as np
import time
from concurrent.futures import ThreadPoolExecutor
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SearchCache:
    """Multi-layered caching system for search results and computations"""

    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0):
        try:
            self.redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db)
            self.redis_available = True
            # Test connection
            self.redis_client.ping()
            logger.info("Redis cache connected")
        except:
            self.redis_available = False
            logger.warning("Redis not available, using in-memory cache")
            self._memory_cache = {}

        # Cache TTL settings
        self.ttl_settings = {
            'search_results': 3600,      # 1 hour
            'embeddings': 86400 * 7,     # 1 week
            'compatibility_matrix': 86400 * 3,  # 3 days
            'user_preferences': 86400 * 30,     # 30 days
        }

    def _generate_cache_key(self, prefix: str, data: Any) -> str:
        """Generate deterministic cache key"""
        if isinstance(data, dict):
            # Sort dict for consistent hashing
            data_str = str(sorted(data.items()))
        else:
            data_str = str(data)

        hash_obj = hashlib.md5(data_str.encode())
        return f"{prefix}:{hash_obj.hexdigest()}"

    async def get(self, prefix: str, key_data: Any) -> Optional[Any]:
        """Get cached value"""
        cache_key = self._generate_cache_key(prefix, key_data)

        try:
            if self.redis_available:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return pickle.loads(cached)
            else:
                return self._memory_cache.get(cache_key)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")

        return None

    async def set(self, prefix: str, key_data: Any, value: Any):
        """Set cached value with TTL"""
        cache_key = self._generate_cache_key(prefix, key_data)
        ttl = self.ttl_settings.get(prefix, 3600)

        try:
            if self.redis_available:
                serialized = pickle.dumps(value)
                self.redis_client.setex(cache_key, ttl, serialized)
            else:
                self._memory_cache[cache_key] = value
                # Simple TTL for memory cache (not perfect but functional)
                asyncio.create_task(self._expire_memory_key(cache_key, ttl))
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    async def _expire_memory_key(self, key: str, ttl: int):
        """Expire memory cache key after TTL"""
        await asyncio.sleep(ttl)
        self._memory_cache.pop(key, None)

    def cached(self, prefix: str, ttl: Optional[int] = None):
        """Decorator for caching function results"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Create cache key from function args
                cache_key_data = {
                    'func': func.__name__,
                    'args': args,
                    'kwargs': kwargs
                }

                # Try to get from cache
                result = await self.get(prefix, cache_key_data)
                if result is not None:
                    logger.debug(f"Cache hit for {func.__name__}")
                    return result

                # Execute function
                result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)

                # Cache result
                if ttl:
                    self.ttl_settings[prefix] = ttl
                await self.set(prefix, cache_key_data, result)

                logger.debug(f"Cache miss for {func.__name__}, result cached")
                return result

            return wrapper
        return decorator

class PrecomputationEngine:
    """Precompute expensive operations for faster search"""

    def __init__(self, db_config: Dict, cache: SearchCache):
        self.db_config = db_config
        self.cache = cache
        self.executor = ThreadPoolExecutor(max_workers=4)

    async def precompute_compatibility_matrix(self, prompt_ids: List[str], batch_size: int = 100):
        """Precompute pairwise compatibility scores"""
        logger.info(f"Precomputing compatibility matrix for {len(prompt_ids)} prompts")

        # Check if already computed
        cache_key = {'type': 'full_matrix', 'prompt_ids': sorted(prompt_ids)}
        cached_matrix = await self.cache.get('compatibility_matrix', cache_key)
        if cached_matrix:
            logger.info("Compatibility matrix found in cache")
            return cached_matrix

        compatibility_matrix = {}

        # Process in batches to avoid memory issues
        for i in range(0, len(prompt_ids), batch_size):
            batch_ids = prompt_ids[i:i + batch_size]
            logger.info(f"Processing compatibility batch {i//batch_size + 1}/{(len(prompt_ids)-1)//batch_size + 1}")

            # Compute compatibility for this batch
            batch_matrix = await self._compute_batch_compatibility(batch_ids, prompt_ids)
            compatibility_matrix.update(batch_matrix)

        # Cache the full matrix
        await self.cache.set('compatibility_matrix', cache_key, compatibility_matrix)
        logger.info("Compatibility matrix computation complete")

        return compatibility_matrix

    async def _compute_batch_compatibility(self, batch_ids: List[str], all_ids: List[str]) -> Dict:
        """Compute compatibility for a batch of prompts"""
        # This would implement your actual compatibility logic
        # Simplified for example
        batch_matrix = {}

        for prompt1 in batch_ids:
            batch_matrix[prompt1] = {}
            for prompt2 in all_ids:
                if prompt1 != prompt2:
                    # Simplified compatibility score
                    # In practice, this would use your metadata comparison logic
                    score = np.random.random()  # Placeholder
                    batch_matrix[prompt1][prompt2] = score

        return batch_matrix

    async def precompute_embeddings(self, prompts: List[Dict], model_name: str = 'all-MiniLM-L6-v2'):
        """Precompute embeddings for all prompts"""
        from sentence_transformers import SentenceTransformer

        logger.info(f"Precomputing embeddings for {len(prompts)} prompts")

        # Check cache
        cache_key = {'model': model_name, 'prompt_count': len(prompts)}
        cached_embeddings = await self.cache.get('embeddings', cache_key)
        if cached_embeddings:
            logger.info("Embeddings found in cache")
            return cached_embeddings

        # Load model
        model = SentenceTransformer(model_name)

        # Extract texts
        texts = [p['prompt_text'] for p in prompts]

        # Compute embeddings in batches
        batch_size = 32
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            logger.info(f"Computing embeddings batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")

            # Use thread executor for CPU-intensive work
            loop = asyncio.get_event_loop()
            batch_embeddings = await loop.run_in_executor(
                self.executor,
                model.encode,
                batch_texts
            )

            all_embeddings.extend(batch_embeddings)

        embeddings_array = np.array(all_embeddings)

        # Cache embeddings
        await self.cache.set('embeddings', cache_key, embeddings_array)
        logger.info("Embeddings computation complete")

        return embeddings_array

    async def precompute_workflow_patterns(self, prompts: List[Dict]):
        """Analyze and cache common workflow patterns"""
        logger.info("Analyzing workflow patterns")

        # Group prompts by domain and task type combinations
        patterns = {}

        for prompt in prompts:
            domain_key = tuple(sorted(prompt.get('domain', [])))
            task_key = tuple(sorted(prompt.get('task_type', [])))
            stage = prompt.get('primary_stage')

            pattern_key = (domain_key, task_key)

            if pattern_key not in patterns:
                patterns[pattern_key] = {
                    'stages': [],
                    'prompts': [],
                    'complexity_distribution': []
                }

            patterns[pattern_key]['stages'].append(stage)
            patterns[pattern_key]['prompts'].append(prompt['prompt_id'])
            patterns[pattern_key]['complexity_distribution'].append(prompt.get('complexity_level', 3))

        # Analyze patterns
        analyzed_patterns = {}
        for pattern_key, data in patterns.items():
            if len(data['prompts']) >= 3:  # Only patterns with sufficient data
                analyzed_patterns[pattern_key] = {
                    'common_stages': list(set(data['stages'])),
                    'avg_complexity': np.mean(data['complexity_distribution']),
                    'prompt_count': len(data['prompts']),
                    'typical_workflow': self._extract_typical_workflow(data['stages'])
                }

        # Cache patterns
        await self.cache.set('workflow_patterns', 'all_patterns', analyzed_patterns)
        logger.info(f"Identified {len(analyzed_patterns)} workflow patterns")

        return analyzed_patterns

    def _extract_typical_workflow(self, stages: List[str]) -> List[str]:
        """Extract typical workflow order from stage list"""
        stage_order = {'clarify': 1, 'plan': 2, 'execute': 3, 'verify': 4, 'reflect': 5}
        unique_stages = list(set(stages))
        unique_stages.sort(key=lambda x: stage_order.get(x, 999))
        return unique_stages

class PerformanceMonitor:
    """Monitor search performance and provide optimization insights"""

    def __init__(self):
        self.metrics = {
            'search_latency': [],
            'cache_hit_rate': {'hits': 0, 'total': 0},
            'query_complexity': [],
            'result_quality': []
        }

    def time_operation(self, operation_name: str):
        """Decorator to time operations"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()

                try:
                    result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
                    success = True
                except Exception as e:
                    logger.error(f"Operation {operation_name} failed: {e}")
                    success = False
                    raise
                finally:
                    duration = time.time() - start_time
                    self.record_latency(operation_name, duration, success)

                return result
            return wrapper
        return decorator

    def record_latency(self, operation: str, duration: float, success: bool):
        """Record operation latency"""
        if operation not in self.metrics:
            self.metrics[operation] = []

        self.metrics[operation].append({
            'duration': duration,
            'success': success,
            'timestamp': time.time()
        })

        # Log slow operations
        if duration > 1.0:  # More than 1 second
            logger.warning(f"Slow operation {operation}: {duration:.2f}s")

    def record_cache_event(self, hit: bool):
        """Record cache hit/miss"""
        self.metrics['cache_hit_rate']['total'] += 1
        if hit:
            self.metrics['cache_hit_rate']['hits'] += 1

    def get_performance_report(self) -> Dict[str, Any]:
        """Generate performance report"""
        report = {}

        # Cache performance
        cache_stats = self.metrics['cache_hit_rate']
        if cache_stats['total'] > 0:
            hit_rate = cache_stats['hits'] / cache_stats['total']
            report['cache_hit_rate'] = f"{hit_rate:.2%}"

        # Latency statistics
        for operation, records in self.metrics.items():
            if isinstance(records, list) and records:
                durations = [r['duration'] for r in records if isinstance(r, dict)]
                if durations:
                    report[f"{operation}_latency"] = {
                        'mean': np.mean(durations),
                        'p50': np.percentile(durations, 50),
                        'p95': np.percentile(durations, 95),
                        'p99': np.percentile(durations, 99)
                    }

        return report

class OptimizedSearchEngine:
    """Production-optimized search engine wrapper"""

    def __init__(self, base_engine, cache_config: Dict = None):
        self.base_engine = base_engine
        self.cache = SearchCache(**(cache_config or {}))
        self.precompute_engine = PrecomputationEngine(base_engine.db_config, self.cache)
        self.monitor = PerformanceMonitor()

        # Optimization flags
        self.optimizations_enabled = {
            'result_caching': True,
            'embedding_caching': True,
            'compatibility_precompute': True,
            'query_normalization': True,
            'batch_processing': True
        }

    async def initialize_optimizations(self):
        """Initialize all performance optimizations"""
        logger.info("Initializing performance optimizations")

        # Load prompts from base engine
        await self.base_engine.initialize()

        # Precompute embeddings
        prompts = list(self.base_engine.metadata_cache.values())
        if self.optimizations_enabled['embedding_caching']:
            await self.precompute_engine.precompute_embeddings(prompts)

        # Precompute compatibility matrix
        if self.optimizations_enabled['compatibility_precompute']:
            prompt_ids = list(self.base_engine.metadata_cache.keys())
            await self.precompute_engine.precompute_compatibility_matrix(prompt_ids)

        # Analyze workflow patterns
        await self.precompute_engine.precompute_workflow_patterns(prompts)

        logger.info("Performance optimizations initialized")

    @PerformanceMonitor.time_operation("search")
    async def optimized_search(self, query: str, search_params: Dict[str, Any]) -> List[Any]:
        """Optimized search with caching and precomputation"""

        # Normalize query for better caching
        if self.optimizations_enabled['query_normalization']:
            query = self._normalize_query(query)

        # Check cache for results
        if self.optimizations_enabled['result_caching']:
            cache_key = {'query': query, 'params': search_params}
            cached_results = await self.cache.get('search_results', cache_key)
            if cached_results:
                self.monitor.record_cache_event(hit=True)
                logger.debug("Search results cache hit")
                return cached_results
            self.monitor.record_cache_event(hit=False)

        # Execute search with base engine
        results = await self.base_engine.search(query, search_params)

        # Cache results
        if self.optimizations_enabled['result_caching']:
            await self.cache.set('search_results', cache_key, results)

        return results

    def _normalize_query(self, query: str) -> str:
        """Normalize query for consistent caching"""
        import re

        # Convert to lowercase
        normalized = query.lower().strip()

        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized)

        # Remove common stop words for caching (optional)
        # This is aggressive - consider carefully
        stop_words = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being'}
        words = normalized.split()
        filtered_words = [w for w in words if w not in stop_words or len(words) <= 3]

        return ' '.join(filtered_words)

    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics"""
        base_report = self.monitor.get_performance_report()

        # Add cache statistics
        if hasattr(self.cache, 'redis_client') and self.cache.redis_available:
            try:
                redis_info = self.cache.redis_client.info('memory')
                base_report['cache_memory_usage'] = redis_info.get('used_memory_human', 'unknown')
            except:
                pass

        return base_report

    async def warm_up_cache(self, common_queries: List[str]):
        """Warm up cache with common queries"""
        logger.info(f"Warming up cache with {len(common_queries)} queries")

        default_params = {
            'k': 10,
            'expand_workflow': True,
            'min_similarity': 0.6
        }

        for query in common_queries:
            try:
                await self.optimized_search(query, default_params)
            except Exception as e:
                logger.warning(f"Cache warmup failed for query '{query}': {e}")

        logger.info("Cache warmup complete")

# Example usage
async def production_search_example():
    """Example of production-optimized search"""

    from custom_search_engine import HybridSearchEngine

    DB_CONFIG = {
        'host': 'localhost',
        'database': 'prompt_flow',
        'user': 'bao',
        'password': ''
    }

    # Redis cache configuration
    CACHE_CONFIG = {
        'redis_host': 'localhost',
        'redis_port': 6379,
        'redis_db': 1  # Use separate DB for cache
    }

    # Initialize optimized engine
    base_engine = HybridSearchEngine(DB_CONFIG)
    optimized_engine = OptimizedSearchEngine(base_engine, CACHE_CONFIG)

    # Initialize with optimizations
    await optimized_engine.initialize_optimizations()

    # Warm up with common queries
    common_queries = [
        "create a marketing strategy",
        "analyze competitor data",
        "write a blog post",
        "plan a product launch",
        "improve team productivity"
    ]
    await optimized_engine.warm_up_cache(common_queries)

    # Example search
    start_time = time.time()
    results = await optimized_engine.optimized_search(
        "I need help creating a comprehensive content strategy",
        {'k': 10, 'domains': ['business'], 'expand_workflow': True}
    )
    search_time = time.time() - start_time

    print(f"Search completed in {search_time:.3f}s")
    print(f"Found {len(results)} results")

    # Get performance metrics
    metrics = await optimized_engine.get_performance_metrics()
    print("Performance metrics:", metrics)

if __name__ == "__main__":
    asyncio.run(production_search_example())
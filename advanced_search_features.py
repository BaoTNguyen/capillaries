#!/usr/bin/env python3
"""
Advanced search features beyond basic vector similarity
Includes contextual understanding, query expansion, and adaptive ranking
"""

from typing import List, Dict, Any, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import spacy
import re
from dataclasses import dataclass
import asyncio

@dataclass
class QueryAnalysis:
    intent: List[str]
    task_types: List[str]
    domains: List[str]
    complexity: int
    required_stages: List[str]
    keywords: List[str]
    semantic_expansions: List[str]

class QueryUnderstandingEngine:
    """Advanced query analysis and expansion"""

    def __init__(self):
        self.nlp = spacy.load("en_core_web_sm")
        self.intent_classifier = self._build_intent_classifier()
        self.expansion_model = SentenceTransformer('all-MiniLM-L6-v2')

    def _build_intent_classifier(self) -> Dict[str, List[str]]:
        """Build intent classification patterns"""
        return {
            'adapt': ['customize', 'tailor', 'modify', 'adjust', 'personalize', 'rewrite', 'convert'],
            'automate': ['automate', 'streamline', 'systematize', 'routine', 'recurring', 'batch'],
            'build': ['create', 'develop', 'build', 'construct', 'implement', 'design', 'make'],
            'communicate': ['explain', 'present', 'communicate', 'tell', 'inform', 'announce'],
            'decide': ['choose', 'select', 'decide', 'pick', 'determine', 'recommend'],
            'explore': ['research', 'investigate', 'explore', 'discover', 'brainstorm', 'find'],
            'improve': ['optimize', 'enhance', 'improve', 'better', 'upgrade', 'refine'],
            'learn': ['understand', 'learn', 'study', 'teach', 'explain how', 'tutorial'],
            'prepare': ['plan', 'prepare', 'organize', 'schedule', 'outline', 'structure'],
            'reflect': ['review', 'assess', 'evaluate', 'analyze', 'reflect', 'retrospective'],
            'validate': ['verify', 'check', 'test', 'confirm', 'validate', 'ensure']
        }

    async def analyze_query(self, query: str) -> QueryAnalysis:
        """Comprehensive query understanding"""
        doc = self.nlp(query)

        # Extract intents
        intents = self._classify_intents(query)

        # Extract task types
        task_types = self._classify_task_types(query, doc)

        # Extract domains
        domains = self._classify_domains(query, doc)

        # Estimate complexity
        complexity = self._estimate_complexity(query, doc)

        # Infer required workflow stages
        required_stages = self._infer_workflow_stages(query, intents, task_types)

        # Extract keywords
        keywords = self._extract_keywords(doc)

        # Generate semantic expansions
        expansions = await self._generate_semantic_expansions(query)

        return QueryAnalysis(
            intent=intents,
            task_types=task_types,
            domains=domains,
            complexity=complexity,
            required_stages=required_stages,
            keywords=keywords,
            semantic_expansions=expansions
        )

    def _classify_intents(self, query: str) -> List[str]:
        """Classify user intent from query"""
        query_lower = query.lower()
        detected_intents = []

        for intent, patterns in self.intent_classifier.items():
            if any(pattern in query_lower for pattern in patterns):
                detected_intents.append(intent)

        # If no explicit intent, try to infer
        if not detected_intents:
            if any(word in query_lower for word in ['what', 'how', 'why', 'explain']):
                detected_intents.append('learn')
            elif any(word in query_lower for word in ['create', 'make', 'generate']):
                detected_intents.append('build')
            else:
                detected_intents.append('explore')  # Default fallback

        return detected_intents

    def _classify_task_types(self, query: str, doc) -> List[str]:
        """Classify task types from query"""
        task_patterns = {
            'analyze': ['analyze', 'examination', 'breakdown', 'dissect', 'study'],
            'compare': ['compare', 'contrast', 'versus', 'difference', 'pros and cons'],
            'debug': ['debug', 'fix', 'solve', 'troubleshoot', 'error', 'problem'],
            'evaluate': ['evaluate', 'assess', 'rate', 'judge', 'review'],
            'model': ['model', 'framework', 'structure', 'template', 'format'],
            'optimize': ['optimize', 'improve', 'enhance', 'better', 'efficient'],
            'design': ['design', 'layout', 'architecture', 'wireframe', 'interface'],
            'generate': ['generate', 'create', 'produce', 'write', 'draft'],
            'synthesize': ['synthesize', 'combine', 'merge', 'integrate', 'consolidate'],
            'explain': ['explain', 'describe', 'clarify', 'teach', 'show']
        }

        query_lower = query.lower()
        detected_types = []

        for task_type, patterns in task_patterns.items():
            if any(pattern in query_lower for pattern in patterns):
                detected_types.append(task_type)

        # Analyze verbs for additional task types
        verbs = [token.lemma_ for token in doc if token.pos_ == "VERB"]
        if "write" in verbs or "draft" in verbs:
            detected_types.append('generate')
        if "plan" in verbs or "organize" in verbs:
            detected_types.append('model')

        return detected_types if detected_types else ['generate']  # Default

    def _classify_domains(self, query: str, doc) -> List[str]:
        """Classify domains from query context"""
        domain_keywords = {
            'AI': ['AI', 'artificial intelligence', 'machine learning', 'ML', 'algorithm',
                  'model', 'neural', 'automation', 'chatbot', 'prompt'],
            'business': ['business', 'company', 'corporate', 'market', 'customer',
                        'revenue', 'sales', 'profit', 'strategy', 'competitive'],
            'career': ['job', 'career', 'resume', 'interview', 'professional',
                      'workplace', 'skills', 'networking'],
            'finance': ['money', 'budget', 'investment', 'financial', 'cost',
                       'pricing', 'profit', 'expense', 'ROI'],
            'learning': ['education', 'learning', 'training', 'course', 'study',
                        'curriculum', 'knowledge', 'skill'],
            'product': ['product', 'feature', 'development', 'roadmap', 'MVP',
                       'user story', 'requirements'],
            'strategy': ['strategy', 'strategic', 'planning', 'vision', 'goals',
                        'roadmap', 'growth']
        }

        query_lower = query.lower()
        detected_domains = []

        for domain, keywords in domain_keywords.items():
            if any(keyword in query_lower for keyword in keywords):
                detected_domains.append(domain)

        # Use named entities for additional context
        entities = [(ent.text.lower(), ent.label_) for ent in doc.ents]
        for text, label in entities:
            if label == "ORG" and any(biz_word in text for biz_word in ["inc", "corp", "llc", "company"]):
                if 'business' not in detected_domains:
                    detected_domains.append('business')
            elif label == "MONEY":
                if 'finance' not in detected_domains:
                    detected_domains.append('finance')

        return detected_domains if detected_domains else ['personal']  # Default fallback

    def _estimate_complexity(self, query: str, doc) -> int:
        """Estimate task complexity (1-5 scale)"""
        complexity_indicators = {
            5: ['comprehensive', 'complete', 'end-to-end', 'full', 'detailed', 'thorough'],
            4: ['advanced', 'complex', 'sophisticated', 'multi-step', 'elaborate'],
            3: ['moderate', 'standard', 'typical', 'regular', 'normal'],
            2: ['simple', 'basic', 'quick', 'easy', 'straightforward'],
            1: ['minimal', 'brief', 'short', 'concise', 'simple']
        }

        query_lower = query.lower()

        # Check for explicit complexity indicators
        for complexity, indicators in complexity_indicators.items():
            if any(indicator in query_lower for indicator in indicators):
                return complexity

        # Estimate based on query characteristics
        word_count = len([token for token in doc if token.is_alpha])
        if word_count > 20:
            return 4
        elif word_count > 10:
            return 3
        else:
            return 2

        # Check for multiple requirements
        requirements = len([token for token in doc if token.text.lower() in ['and', 'also', 'plus', 'additionally']])
        if requirements > 2:
            return min(5, 3 + requirements)

        return 3  # Default moderate complexity

    def _infer_workflow_stages(self, query: str, intents: List[str], task_types: List[str]) -> List[str]:
        """Infer required workflow stages from query"""
        stages = []

        # Based on intents
        if 'explore' in intents or 'learn' in intents:
            stages.append('clarify')
        if 'prepare' in intents or any(t in task_types for t in ['model', 'design']):
            stages.append('plan')
        if 'build' in intents or 'generate' in task_types:
            stages.append('execute')
        if 'validate' in intents or 'evaluate' in task_types:
            stages.append('verify')
        if 'reflect' in intents or 'improve' in intents:
            stages.append('reflect')

        # Analyze query structure
        query_lower = query.lower()
        if any(word in query_lower for word in ['first', 'start', 'begin', 'initial']):
            if 'clarify' not in stages:
                stages.insert(0, 'clarify')
        if any(word in query_lower for word in ['then', 'next', 'after', 'following']):
            # Multi-step process implied
            if not stages:
                stages = ['plan', 'execute']

        return stages if stages else ['execute']  # Default to execution

    def _extract_keywords(self, doc) -> List[str]:
        """Extract important keywords from query"""
        # Extract nouns, proper nouns, and important adjectives
        keywords = []

        for token in doc:
            if (token.pos_ in ["NOUN", "PROPN"] and
                not token.is_stop and
                len(token.text) > 2 and
                token.is_alpha):
                keywords.append(token.lemma_.lower())
            elif (token.pos_ == "ADJ" and
                  not token.is_stop and
                  len(token.text) > 3):
                keywords.append(token.lemma_.lower())

        return list(set(keywords))  # Remove duplicates

    async def _generate_semantic_expansions(self, query: str) -> List[str]:
        """Generate semantic expansions of the query"""
        # This would integrate with a language model for query expansion
        # For now, using rule-based expansions

        expansions = []

        # Synonym expansions (simplified)
        synonyms = {
            'create': ['build', 'develop', 'generate', 'make', 'produce'],
            'analyze': ['examine', 'study', 'review', 'assess', 'evaluate'],
            'improve': ['enhance', 'optimize', 'better', 'upgrade', 'refine'],
            'strategy': ['plan', 'approach', 'method', 'framework', 'roadmap'],
            'content': ['material', 'text', 'copy', 'information', 'data']
        }

        query_words = query.lower().split()
        for word in query_words:
            if word in synonyms:
                for synonym in synonyms[word]:
                    expansion = query.lower().replace(word, synonym)
                    if expansion != query.lower():
                        expansions.append(expansion)

        return expansions[:5]  # Limit to top 5 expansions

class AdaptiveRankingEngine:
    """Adaptive ranking that learns from user feedback"""

    def __init__(self):
        self.user_preferences = {}  # User ID -> preferences
        self.query_patterns = {}    # Query pattern -> successful results
        self.global_stats = {
            'intent_success': {},
            'domain_preferences': {},
            'complexity_preferences': {}
        }

    def learn_from_feedback(self, user_id: str, query: str, results: List[str],
                           feedback_scores: List[float]):
        """Learn from user feedback on search results"""

        # Initialize user preferences if not exists
        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = {
                'preferred_domains': {},
                'preferred_complexity': {},
                'preferred_intents': {},
                'query_history': []
            }

        user_prefs = self.user_preferences[user_id]

        # Store query and results
        user_prefs['query_history'].append({
            'query': query,
            'results': results,
            'scores': feedback_scores,
            'timestamp': asyncio.get_event_loop().time()
        })

        # Update preferences based on high-scoring results
        for result_id, score in zip(results, feedback_scores):
            if score >= 4.0:  # High satisfaction
                # This would lookup result metadata and update preferences
                # Simplified for example
                pass

    def get_personalized_weights(self, user_id: str, query_analysis: QueryAnalysis) -> Dict[str, float]:
        """Get personalized ranking weights for user"""

        default_weights = {
            'vector_similarity': 0.4,
            'metadata_match': 0.2,
            'graph_relationship': 0.15,
            'workflow_fit': 0.15,
            'complexity_match': 0.1
        }

        if user_id not in self.user_preferences:
            return default_weights

        # Adjust weights based on user preferences
        user_prefs = self.user_preferences[user_id]
        adjusted_weights = default_weights.copy()

        # Example adjustments (would be more sophisticated in practice)
        if len(user_prefs['query_history']) > 10:
            # User has history, adjust based on patterns
            adjusted_weights['metadata_match'] += 0.05
            adjusted_weights['vector_similarity'] -= 0.05

        return adjusted_weights

class ContextualSearchEngine:
    """Search engine with contextual understanding"""

    def __init__(self, base_search_engine):
        self.base_engine = base_search_engine
        self.query_analyzer = QueryUnderstandingEngine()
        self.ranking_engine = AdaptiveRankingEngine()
        self.search_context = {}  # Session ID -> context

    async def contextual_search(self, query: str, user_id: str = None,
                               session_id: str = None) -> List[Dict]:
        """Search with contextual understanding and personalization"""

        # Analyze query
        query_analysis = await self.query_analyzer.analyze_query(query)

        # Build search parameters from analysis
        search_params = {
            'k': 20,  # Get more candidates for reranking
            'domains': query_analysis.domains,
            'task_types': query_analysis.task_types,
            'required_stages': query_analysis.required_stages,
            'target_complexity': query_analysis.complexity,
            'expand_workflow': len(query_analysis.required_stages) > 1,
            'min_similarity': 0.5  # Lower threshold for more candidates
        }

        # Add context from previous searches in session
        if session_id and session_id in self.search_context:
            context = self.search_context[session_id]
            # Boost results from same domain/task type as previous searches
            if context.get('recent_domains'):
                search_params['domains'].extend(context['recent_domains'])
            search_params['domains'] = list(set(search_params['domains']))  # Dedupe

        # Execute base search
        results = await self.base_engine.search(query, search_params)

        # Apply personalized reranking
        if user_id:
            weights = self.ranking_engine.get_personalized_weights(user_id, query_analysis)
            results = self._rerank_with_weights(results, weights)

        # Update search context
        if session_id:
            if session_id not in self.search_context:
                self.search_context[session_id] = {
                    'recent_domains': [],
                    'recent_queries': [],
                    'session_start': asyncio.get_event_loop().time()
                }

            context = self.search_context[session_id]
            context['recent_domains'].extend(query_analysis.domains)
            context['recent_queries'].append(query)

            # Keep only recent history (last 5 queries)
            context['recent_domains'] = context['recent_domains'][-10:]
            context['recent_queries'] = context['recent_queries'][-5:]

        # Format results with explanations
        formatted_results = []
        for result in results[:10]:
            formatted_results.append({
                'prompt_id': result.prompt_id,
                'score': result.score,
                'sources': result.retrieval_sources,
                'explanation': result.explanation,
                'metadata': result.metadata,
                'query_analysis': {
                    'matched_intents': [i for i in query_analysis.intent if i in result.metadata.get('intent', [])],
                    'matched_task_types': [t for t in query_analysis.task_types if t in result.metadata.get('task_type', [])],
                    'matched_domains': [d for d in query_analysis.domains if d in result.metadata.get('domain', [])]
                }
            })

        return formatted_results

    def _rerank_with_weights(self, results, weights):
        """Rerank results using personalized weights"""
        # Simplified reranking - would be more sophisticated in practice
        for result in results:
            # Adjust scores based on personalized weights
            base_score = result.score

            # Apply weight adjustments (example)
            if 'vector_similarity' in result.retrieval_sources:
                result.score *= weights['vector_similarity'] * 2.5  # Normalize
            if 'metadata_match' in result.retrieval_sources:
                result.score *= weights['metadata_match'] * 5.0

        results.sort(key=lambda x: x.score, reverse=True)
        return results

# Example integration
async def enhanced_search_example():
    """Example of enhanced search capabilities"""

    # This would use your existing base engine
    from custom_search_engine import HybridSearchEngine

    DB_CONFIG = {
        'host': 'localhost',
        'database': 'prompt_flow',
        'user': 'bao',
        'password': ''
    }

    # Initialize engines
    base_engine = HybridSearchEngine(DB_CONFIG)
    await base_engine.initialize()

    contextual_engine = ContextualSearchEngine(base_engine)

    # Example contextual search
    results = await contextual_engine.contextual_search(
        query="I need to create a comprehensive marketing strategy for a new AI product launch",
        user_id="user_123",
        session_id="session_456"
    )

    print("Enhanced Search Results:")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['prompt_id']} (score: {result['score']:.3f})")
        print(f"   Matched: {result['query_analysis']}")
        print(f"   {result['explanation']}")
        print()

if __name__ == "__main__":
    asyncio.run(enhanced_search_example())
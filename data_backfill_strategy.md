# Data Backfill Strategy for Prompt Database

Date: 2026-02-21
Status: Strategy Design
Target: 573 prompts (excluding Clippings)

## Current State Analysis

### Existing Metadata Coverage
From analysis of 573 prompts:
- `original_link`: 486 files (85% coverage)
- `intent`: 3 files (0.5% coverage) ⚠️ **CRITICAL GAP**
- `task_type`: 3 files (0.5% coverage) ⚠️ **CRITICAL GAP**
- `domain`: 3 files (0.5% coverage) ⚠️ **CRITICAL GAP**
- `status`: 2 files (0.3% coverage)
- `models_tested`: 1 file (0.2% coverage)
- All other fields: 0% coverage

### Backfill Priority (Workflow-Critical Fields)
**Essential for Phase 1:**
1. `intent` - what the prompt accomplishes
2. `task_type` - classification for retrieval
3. `domain` - subject matter area
4. `input_schema` - what prompt expects as input
5. `output_schema` - what prompt produces
6. `primary_stage` - main workflow stage (clarify/plan/execute/verify/reflect)
7. `complexity_level` - task complexity (1-5 scale)

**Important for optimization:**
8. `context_variables` - what context flows through
9. `secondary_stages` - additional stages prompt can serve
10. `accomplishes` - semantic description of work done

## Backfill Approaches

### Approach 1: Batch LLM Classification (Recommended)

**Strategy**: Process all prompts through specialized classification prompts
```
Process: Raw Prompt Text → LLM Classifier → Structured Metadata
```

**Implementation**:
```python
classification_prompt = """
Analyze this prompt and extract metadata in JSON format:
{
  "intent": "concise description of what this prompt does",
  "task_type": "one of: content_creation, analysis, planning, code_generation, data_processing, communication, strategy, research",
  "domain": "subject area: business, technical, creative, academic, etc.",
  "primary_stage": "one of: clarify, plan, execute, verify, reflect",
  "complexity_level": 1-5,
  "input_schema": "what this prompt expects as input",
  "output_schema": "what this prompt produces as output",
  "context_variables": ["list", "of", "context", "needed"]
}

Prompt to analyze: {prompt_text}
"""
```

**Pros**:
- High accuracy for semantic understanding
- Consistent classification across corpus
- Can handle complex prompts requiring interpretation
- Scales to full corpus (573 prompts)

**Cons**:
- LLM API costs (~$50-200 for full corpus)
- Processing time: 2-4 hours with rate limits
- Quality depends on classification prompt engineering
- Requires validation/spot-checking

**Cost Estimate**: $100-150 (using Claude 3.5 Sonnet)
**Time Estimate**: 3-4 hours processing + 4-6 hours validation

### Approach 2: Hybrid Automated + Manual Review

**Strategy**: LLM bulk processing + human validation for critical fields
```
Process: Batch LLM → Quality Check → Manual Correction → Final Dataset
```

**Implementation**:
1. **Bulk Processing**: LLM classifies all 573 prompts
2. **Confidence Scoring**: LLM rates its own confidence (1-5) per field
3. **Manual Review**: Human reviews low-confidence items (estimated 20-30%)
4. **Validation**: Spot-check high-confidence items (10% sample)

**Pros**:
- Higher accuracy than pure automation
- Catches edge cases and ambiguous prompts
- Builds confidence in dataset quality
- Creates training data for future improvements

**Cons**:
- Labor intensive (8-12 hours human time)
- Slower overall process
- Requires domain expertise for review
- Still has LLM processing costs

**Cost Estimate**: $100 LLM + 10 hours human time
**Time Estimate**: 2 days including review cycles

### Approach 3: Rule-Based + Pattern Matching

**Strategy**: Extract metadata using keyword patterns and heuristics
```
Process: Prompt Text → Regex/NLP Rules → Structured Metadata
```

**Implementation**:
```python
# Example rules
task_type_patterns = {
    "content_creation": ["write", "create", "generate", "draft", "compose"],
    "analysis": ["analyze", "evaluate", "assess", "compare", "review"],
    "planning": ["plan", "strategy", "roadmap", "schedule", "organize"],
    # ... more patterns
}

def classify_by_patterns(prompt_text):
    # Rule-based classification logic
    pass
```

**Pros**:
- Fast processing (minutes, not hours)
- Zero LLM costs
- Fully deterministic and reproducible
- Easy to debug and adjust rules

**Cons**:
- Low accuracy for nuanced prompts
- Misses semantic understanding
- Requires extensive rule engineering
- Poor handling of complex/ambiguous cases

**Cost Estimate**: $0 (developer time only)
**Time Estimate**: 1 day rule development + processing

### Approach 4: Semantic Clustering + Representative Labeling

**Strategy**: Cluster similar prompts, manually label cluster representatives
```
Process: Embed All Prompts → Cluster → Label Representatives → Propagate Labels
```

**Implementation**:
1. **Embedding**: Generate vectors for all 573 prompts
2. **Clustering**: K-means clustering (target: 50-80 clusters)
3. **Representative Selection**: Pick 2-3 representative prompts per cluster
4. **Manual Labeling**: Human labels ~150 representative prompts
5. **Label Propagation**: Apply labels to cluster members

**Pros**:
- Reduces human labeling effort (150 vs 573 prompts)
- Leverages semantic similarity effectively
- Good balance of accuracy and efficiency
- Creates natural prompt groupings for analysis

**Cons**:
- Clustering may group dissimilar prompts
- Representatives may not cover cluster diversity
- Propagation introduces classification errors
- Requires embedding generation upfront

**Cost Estimate**: $20 embedding + 6 hours human labeling
**Time Estimate**: 1 day total

### Approach 5: Progressive Enhancement Pipeline

**Strategy**: Multi-stage refinement with increasing sophistication
```
Process: Rule-Based Base → LLM Enhancement → Human Validation → Continuous Learning
```

**Implementation**:
```
Stage 1: Rule-based classification (70% accuracy, 100% coverage)
Stage 2: LLM refinement of uncertain cases (90% accuracy, 25% items)
Stage 3: Human validation of critical prompts (98% accuracy, 10% items)
Stage 4: Feedback loop for continuous improvement
```

**Pros**:
- Balances cost, speed, and accuracy
- Iterative quality improvement
- Builds institutional knowledge
- Scalable to future prompt additions

**Cons**:
- Most complex approach to implement
- Requires coordination across stages
- Longer overall timeline
- Higher initial engineering investment

**Cost Estimate**: $50 LLM + 6 hours human + dev time
**Time Estimate**: 3-4 days including pipeline development

## Recommended Implementation Strategy

### Phase 1: Quick Start (Approach 1 - Batch LLM)
**Why**: Need functional system quickly, acceptable cost, high accuracy

**Execution Plan**:
```
Week 1:
- Day 1: Engineer classification prompts and test on 50 sample prompts
- Day 2: Optimize prompt for accuracy, run batch processing on full corpus
- Day 3: Validate results, manual correction of obvious errors
- Day 4: Load into database, run initial system tests
```

### Phase 2: Quality Enhancement (Hybrid Elements)
**After Phase 1 system is working**:
- Add confidence scoring to identify uncertain classifications
- Manual review of low-confidence items
- Build feedback mechanism from user interactions
- Iterative improvement of classification accuracy

## Technical Implementation Details

### Batch Processing Architecture
```python
# Pseudo-code for batch LLM processing
def process_prompt_batch(prompts, batch_size=10):
    results = []
    for batch in chunks(prompts, batch_size):
        # Parallel processing within batch
        batch_results = asyncio.run(classify_batch_parallel(batch))
        results.extend(batch_results)
        # Rate limiting pause
        time.sleep(1.0)
    return results

def classify_batch_parallel(prompt_batch):
    tasks = [classify_single_prompt(p) for p in prompt_batch]
    return await asyncio.gather(*tasks)
```

### Quality Validation Framework
```python
# Validation checks
def validate_classification(result):
    checks = {
        'intent_not_empty': len(result['intent']) > 10,
        'task_type_valid': result['task_type'] in VALID_TASK_TYPES,
        'complexity_range': 1 <= result['complexity_level'] <= 5,
        'stage_valid': result['primary_stage'] in WORKFLOW_STAGES
    }
    return all(checks.values()), checks
```

### Progressive Schema Population
```sql
-- Database migration approach
ALTER TABLE prompts ADD COLUMN metadata_confidence JSONB;
ALTER TABLE prompts ADD COLUMN backfill_version VARCHAR DEFAULT 'v1';
ALTER TABLE prompts ADD COLUMN last_classified TIMESTAMP;

-- Track classification quality
CREATE TABLE classification_feedback (
    prompt_id VARCHAR,
    field_name VARCHAR,
    old_value TEXT,
    new_value TEXT,
    feedback_type VARCHAR, -- 'correction', 'validation', 'enhancement'
    created_at TIMESTAMP
);
```

## Risk Mitigation

### Data Quality Risks
- **Inconsistent classifications**: Use detailed classification guidelines, validation prompts
- **LLM hallucination**: Cross-validate with prompt content, confidence scoring
- **Batch processing failures**: Checkpoint progress, resumable processing

### Performance Risks
- **API rate limits**: Implement exponential backoff, batch size optimization
- **Processing timeouts**: Async processing, error handling, retry logic
- **Memory constraints**: Stream processing, disk-based intermediate storage

### Cost Control
- **LLM cost overruns**: Set spending limits, monitor per-prompt costs
- **Processing inefficiency**: Optimize classification prompts for conciseness
- **Rework costs**: High-quality initial classification to minimize corrections

## Success Metrics

### Completeness Targets
- Essential fields: 95% coverage (intent, task_type, domain, primary_stage)
- Important fields: 80% coverage (complexity_level, input/output_schema)
- Optimization fields: 60% coverage (context_variables, secondary_stages)

### Quality Targets
- Classification accuracy: 90% (validated on sample)
- Inter-rater agreement: 85% (where human validation available)
- User satisfaction: 80% of retrieved prompts rated as relevant

### Timeline Targets
- Phase 1 completion: 1 week
- System integration: 1 week
- Initial user testing: 2 weeks from start

## Next Steps

1. **Validate approach**: Test classification prompt on 20 diverse sample prompts
2. **Cost estimation**: Get accurate LLM API pricing for batch processing
3. **Engineering setup**: Prepare batch processing infrastructure
4. **Quality framework**: Define validation criteria and spot-check procedures
5. **Begin processing**: Start with highest-priority fields (intent, task_type, domain)

---

**Decision Point**: Recommend starting with **Approach 1 (Batch LLM)** for speed and accuracy, then iterating toward hybrid approach based on initial results and user feedback.
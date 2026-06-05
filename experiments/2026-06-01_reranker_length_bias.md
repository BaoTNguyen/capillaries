# Reranker Length Bias Experiments

**Date:** 2026-06-01
**Query:** "I need to build a go-to-market strategy for a new B2B SaaS product launching next quarter"
**Corpus:** 849 private prompts, median length 2,203 chars
**Cross-encoder:** mixedbread-ai/mxbai-rerank-base-v2

## Problem

Long prompts act as keyword magnets — more text means more surface area for both dense and sparse matching, inflating rerank scores relative to shorter, more focused prompts that better match the user's intent. PRODUCT LAUNCH PRESENTATION (3,781 chars) tied at 1.0 with GTM & Launch Plan Review (2,954 chars) despite being a presentation builder, not a strategy tool.

## Baseline (no normalization)

`MAX_DOC_CHARS = 8_000`, full prompt text passed to cross-encoder.

```
 #1. [1.000000] [len= 3781] PRODUCT LAUNCH PRESENTATION
 #2. [1.000000] [len= 2954] GTM & Launch Plan Review
 #3. [0.996094] [len= 1755] Market & Topic Research Pack
 #4. [0.996094] [len= 2917] Image Gen Market Sizing TAM SAM SOM
 #5. [0.992188] [len=  912] Head of Sales - Sales Strategy Document
 #6. [0.988281] [len=  615] Marketing Consultant - Campaign Strategy
 #7. [0.988281] [len= 1075] Image Gen Advertising B2B & Professional Services
 #8. [0.968750] [len=  362] Image Gen Marketing — Product Launch Graphic
 #9. [0.953125] [len= 2917] Image Gen Market Sizing TAM SAM SOM
#10. [0.949219] [len= 1045] Image Gen Advertising Tech Product & SaaS App
```

Tie broken by RRF score (dense+sparse fusion rank), which favors keyword-rich long prompts.

## Experiment 1: 256-char truncation with title prepend

`MAX_DOC_CHARS = 256`, reranker input = `f"{prompt_id}\n\n{prompt_text}"[:256]`

Forces the cross-encoder to judge on the title + opening intent, not keyword volume.

```
 #1. [1.000000] [len= 2954] GTM & Launch Plan Review
 #2. [0.992188] [len= 3781] PRODUCT LAUNCH PRESENTATION
 #3. [0.988281] [len=  615] Marketing Consultant - Campaign Strategy
 #4. [0.988281] [len= 1755] Market & Topic Research Pack
 #5. [0.968750] [len=  912] Head of Sales - Sales Strategy Document
 #6. [0.968750] [len= 1075] Image Gen Advertising B2B & Professional Services
 #7. [0.945312] [len= 1045] Image Gen Advertising Tech Product & SaaS App
 #8. [0.941406] [len=11085] SaaS Business Model Repricing Exposure Map
 #9. [0.925781] [len= 4350] Company Deep Dive
#10. [0.917969] [len=  362] Image Gen Marketing — Product Launch Graphic
```

**Result:** GTM prompt correctly at #1. Short irrelevant prompts don't inflate.
**Risk:** Prompts with long preambles before intent (system instructions, prerequisites) get judged on boilerplate. PRODUCT LAUNCH PRESENTATION's OBJECTIVE line at char ~280 barely makes the cutoff.

## Experiment 2: Log-based length normalization

`penalty = 0.15 * max(0, log(length / 2200))`

Penalizes everything above median with logarithmic decay. Below median = zero penalty.

```
 #1. [0.996094] [len= 1755] [pen=0.0000] Market & Topic Research Pack
 #2. [0.992188] [len=  912] [pen=0.0000] Head of Sales - Sales Strategy Document
 #3. [0.980469] [len=  615] [pen=0.0000] Marketing Consultant - Campaign Strategy
 #4. [0.976562] [len= 1075] [pen=0.0000] Image Gen Advertising B2B & Professional Services
 #5. [0.968750] [len=  362] [pen=0.0000] Image Gen Marketing — Product Launch Graphic
 #6. [0.955795] [len= 2954] [pen=0.0442] GTM & Launch Plan Review
 #7. [0.953779] [len= 2917] [pen=0.0423] Image Gen Market Sizing TAM SAM SOM
 #8. [0.949219] [len= 1045] [pen=0.0000] Image Gen Advertising Tech Product & SaaS App
 #9. [0.918770] [len= 3781] [pen=0.0812] PRODUCT LAUNCH PRESENTATION
#10. [0.843750] [len=  764] [pen=0.0000] Product Manager - PRD
```

**Result:** Overcorrected. GTM prompt dropped to #6. Short irrelevant prompts (Image Gen Marketing at 362 chars) floated to #5 because they dodge all penalty. The log curve is too aggressive near median.

## Experiment 3: Progressive penalty (SELECTED)

`penalty = 0.02 * max(0, (length - 2200) / 2200) ^ 0.5`

Square-root curve: gentle near median, scales gradually. Only bites hard on extreme outliers.

```
 #1. [0.996094] [len= 1755] [pen=0.0000] Market & Topic Research Pack
 #2. [0.992188] [len=  912] [pen=0.0000] Head of Sales - Sales Strategy Document
 #3. [0.988291] [len= 2954] [pen=0.0117] GTM & Launch Plan Review
 #4. [0.984676] [len= 2917] [pen=0.0114] Image Gen Market Sizing TAM SAM SOM
 #5. [0.983046] [len= 3781] [pen=0.0170] PRODUCT LAUNCH PRESENTATION
 #6. [0.980469] [len=  615] [pen=0.0000] Marketing Consultant - Campaign Strategy
 #7. [0.976562] [len= 1075] [pen=0.0000] Image Gen Advertising B2B & Professional Services
 #8. [0.968750] [len=  362] [pen=0.0000] Image Gen Marketing — Product Launch Graphic
 #9. [0.949219] [len= 1045] [pen=0.0000] Image Gen Advertising Tech Product & SaaS App
#10. [0.948089] [len=11085] [pen=0.0402] SaaS Business Model Repricing Exposure Map
```

**Result:** GTM Launch Plan (#3) correctly ranks above PRODUCT LAUNCH PRESENTATION (#5). Short prompts stay in their natural position — no inflation. Penalty difference between the two GTM-relevant prompts is only 0.005.

## Penalty curve reference

```
 Length  Penalty
    362  0.00000  (below threshold)
    942  0.00000  (below threshold)
   2200  0.00000  (at threshold)
   2954  0.01171  (GTM & Launch Plan Review)
   3781  0.01695  (PRODUCT LAUNCH PRESENTATION)
   6206  0.02699  (P75 corpus length)
  10000  0.03766
  41881  0.08494  (max corpus length)
```

## Parameters

```python
LENGTH_THRESHOLD = 2_200      # corpus median
LENGTH_PENALTY_STRENGTH = 0.02
LENGTH_PENALTY_CURVE = 0.5    # square root
```

## Decision

Progressive penalty selected. Truncation gives the best GTM ranking but risks misjudging prompts with long preambles. Progressive penalty is more conservative but correctly orders tied prompts without side effects.

## Future considerations

- Truncation could be revisited if prompt structure becomes more standardized (e.g., all prompts start with a one-line description)
- The 256-char truncation with title prepend is the strongest approach if the preamble risk is acceptable
- Both approaches can be combined: truncate for scoring, then apply progressive penalty as tiebreaker

# ResearchFlow evidence guide

## What the scores mean

ResearchFlow uses cosine similarity between the question embedding and each
paper chunk. A higher score means the passage is semantically closer to the
query; it does not prove that the passage is correct or that it completely
answers the question. The fixed workflow accepts passages at or above 0.45 by
default, then asks the chat model to answer only from those passages.

## Multi-paper comparison

For each compared model:

1. Search its architecture or action representation separately.
2. Search the comparison dimension separately, such as training data,
   embodiment, latency, generalization, or evaluation task.
3. Verify that each side has at least one direct passage.
4. Present unsupported dimensions as unknown instead of treating absence as a
   negative result.
5. Cite the physical PDF page for every side of the comparison.

## Ambiguous evidence

When retrieved chunks discuss a nearby concept but do not explicitly answer the
question, use the insufficient-evidence response. Examples include:

- a paper describes model throughput but not the requested hardware latency;
- a passage describes action tokenization but not the exact vocabulary size;
- a related paper reports a metric that the requested paper does not report;
- multiple passages use different evaluation settings that are not comparable.

## Output contract

A strong final answer contains:

- a direct Chinese answer;
- `[资料N]` immediately after each supported key claim;
- a short source list with PDF file names and physical page numbers;
- a clear insufficiency statement for any requested field not covered by the
  indexed evidence.

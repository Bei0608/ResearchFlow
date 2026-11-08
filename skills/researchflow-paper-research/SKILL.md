---
name: researchflow-paper-research
description: Research embodied-AI and vision-language-action papers through the ResearchFlow MCP server. Use when a user asks about RT-1, RT-2, PaLM-E, robot control, VLA models, the contents of the local paper library, or requests an evidence-grounded comparison or answer with PDF page citations. Also use when the user asks whether the local knowledge base can answer a paper question. Do not use for open-web literature search or claims outside the local indexed PDFs.
---

# ResearchFlow Paper Research

Use the ResearchFlow MCP tools to answer from indexed local papers without
mixing in unsupported model knowledge.

## Workflow

1. Identify the request type.
   - For available papers or knowledge-base scope, call
     `researchflow_list_papers`.
   - For raw passages, fact checking, comparisons, or evidence inspection,
     call `researchflow_search_papers`.
   - For a complete cited answer, call `researchflow_answer_question`.
2. For factual paper questions, retrieve evidence before stating a claim.
3. Prefer `top_k=5`. Increase up to 10 only for comparisons spanning several
   papers or when the first retrieval misses an expected concept.
4. Keep the default `min_score=0.45` unless the user explicitly asks to inspect
   lower-confidence matches. State when using a lower threshold.
5. Cite key claims with `[资料N]` and include the source PDF plus physical page
   number. Preserve model names, metrics, and action representations exactly.
6. If the workflow returns `route="insufficient"`, say
   `根据当前论文资料无法确定。` Do not fill the gap from memory or the web.
7. If it returns `route="error"`, explain that the local retrieval service is
   unavailable and suggest retrying. Do not describe this as missing evidence.

## Tool Choice

Use `researchflow_search_papers` when the user needs to see or audit original
passages. It returns stable chunk IDs, scores, source files, page numbers, and
text.

Use `researchflow_answer_question` when the user wants the final synthesis. It
runs the fixed LangGraph route and writes a checkpoint. Reuse a user-provided
`thread_id` only when they intend to continue the same research session;
otherwise omit it and let the server create one. The server prefixes MCP
checkpoint IDs with `mcp-` so they cannot collide with authenticated API
threads.

Use pagination on `researchflow_list_papers`: start at `offset=0`, respect
`has_more`, and pass `next_offset` for another page. Do not assume the first
page is the full catalog.

## Evidence Discipline

- Treat similarity as retrieval relevance, not factual confidence.
- Never invent source files, pages, experiments, citations, or numerical data.
- Separate what the paper explicitly states from a cautious inference.
- Prefer evidence from the most directly relevant passage over repeated text.
- For cross-paper comparisons, retrieve evidence for every compared paper.
- Do not use this skill to search the open internet.

Read [references/research-guide.md](references/research-guide.md) when the
request involves multi-paper comparison, ambiguous evidence, or deciding
whether a claim is sufficiently supported.

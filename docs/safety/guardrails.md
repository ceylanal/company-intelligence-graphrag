# Input and Output Safety Guardrails

Day 51 adds a deterministic, fail-closed safety boundary around the public
`/research` endpoint and the direct `RAGGenerator` LLM path. Guardrails run
before retrieval/model execution and again before model text is returned.

## Decision model

Every rule emits an auditable decision code and one of these actions:

| Action | Meaning | Downstream behavior |
|---|---|---|
| `allow` | No safety rule fired | Input/output is unchanged |
| `warn` | The response may contain a claim outside retrieved context | Response is returned and the warning is exposed in safety metadata |
| `redact` | Unsafe characters, secrets, or invalid citation tags were found | The affected content is removed or replaced; processing may continue |
| `block` | Continuing could expose data or produce an ungrounded financial answer | LLM/retrieval execution stops for input; output is replaced by a safe message |

The aggregate action is the most restrictive emitted action. Unexpected
guardrail errors always become `block`; the safety layer never fails open.

## Input controls

Default limits:

| Control | Default |
|---|---:|
| Question length | 4,000 characters |
| Entire request text | 32,000 characters |
| Conversation history | 20 turns / 16,000 characters |
| Estimated input size | 8,000 tokens |

The input layer:

- normalizes Unicode with NFKC and removes null bytes and unsafe Unicode
  control characters while preserving tabs and newlines;
- blocks long input, oversized history, excessive character/word repetition,
  and conservative tokenizer-independent token flooding;
- blocks explicit English and Turkish prompt-injection phrases;
- accepts JSON, PDF, multipart form data, plain text, Markdown, and CSV, and
  rejects other declared content/file types;
- validates company names, 1–10 character uppercase tickers, report years from
  1900 through next year, bounded filter lists, and an explicit report-type
  allowlist;
- permits only `user` and `assistant` conversation roles, preventing callers
  from injecting `system`, `developer`, or `tool` history.

Prompt-injection detection intentionally targets imperative override and
prompt-exfiltration phrases rather than broad words such as “prompt” or
“instructions.” This keeps ordinary company-research questions usable.

## Output controls

Before an answer leaves the LLM boundary, the output layer:

- redacts OpenAI-style keys, Google keys, GitHub tokens, AWS access IDs, JWTs,
  bearer tokens, generic key/token/password assignments, credential-bearing
  connection strings, and PEM private keys;
- blocks text that presents itself as a system/developer prompt or exposes
  known internal credential configuration names;
- removes citation tags whose source number is not present in the retrieved
  context;
- blocks definitive numeric financial claims that have no valid citation in
  the sentence or its tightly scoped source paragraph;
- marks substantial uncited claims with an explicit warning and emits
  `outside_retrieved_context` when they have low lexical overlap against the
  retrieved context;
- returns stable public error messages that do not echo raw exceptions,
  credentials, internal hosts, stack traces, or configuration.

A valid citation is necessary but not treated as proof by itself: the allowed
citation set must be built from sources retrieved for that request. The
existing evidence verifier remains responsible for semantic claim/evidence
verification.

## Integration

`POST /research` validates and sanitizes the query and history before creating
an idempotency digest or starting the workflow. The response metadata includes
the aggregate input/output actions and decision codes. Blocked input returns
HTTP 422 with a stable message. Workflow exceptions no longer expose raw
`ValueError` or exception class text.

`RAGGenerator.generate()` applies the same input boundary before retrieval and
the output boundary after generation. A blocked input returns the existing
insufficient-context response without calling retrieval. A blocked output is
replaced by the stable safety response and marked as insufficient context.

## Operations and tuning

Decision codes should be counted separately (`prompt_injection`,
`token_flooding`, `secret_redacted`, `uncited_financial_claim`, and so on).
Alert on any `output_guardrail_failure`, repeated credential redactions, or a
sudden increase in block rate. Never log the rejected raw content.

Threshold changes require:

1. the normal-company-question regression test;
2. adversarial input and secret/citation output tests;
3. `pytest`, `ruff check`, and `mypy` validation;
4. review of false-positive and false-negative samples without retaining
   sensitive payloads.

The machine-readable verification record is
`artifacts/safety/day51/guardrail-results.json`.

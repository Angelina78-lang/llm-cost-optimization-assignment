# LLM cost optimization write-up

Billing: points = uncached_input x 3 + cached_input x 0.3 + output x 15.

## Q1: single call per ticket

Baseline: 35,514 points for 4 tickets (~8,880 per ticket).
Now: 7,914 for 4 tickets (~1,980 per ticket). Target was 3,000.

What I changed in question1/agent.py:
1. Removed the per-run uuid from the system prompt. The prompt is now built once and is identical for every ticket.
2. Removed "think step by step / full reasoning / quote any article". The simulator treats these phrases as a request for a ~480+ token answer, and output costs 15 points per token, so this was the biggest cost.
3. The prompt now asks for one line of JSON with only action and kb_article, the two graded fields.
4. Order snapshot is compact JSON (no indentation), still wrapped in ORDER_SNAPSHOT ... END_SNAPSHOT.

Breakdown, T-1001 (single call "handle_ticket"):
input = 470 tokens x 3 = 1,410
cached = 0
output = 46 tokens x 15 = 690
total = 2,100 points

Per ticket: T-1001 2,100 | T-1002 1,977 | T-1003 1,938 | T-1004 1,899

## Q2: four-node pipeline

Baseline: 294,183 points for 4 tickets (~73,500 per ticket).
Now: 6,894 for 4 tickets (~1,724 per ticket). Target was 2,500.

What I changed in question2/agent.py:
1. expanded_help_center_blob() pads the real articles with ~210k tokens of filler notes that say they do not change policy. I now send only the real articles (all_articles_blob()).
2. The retrieve node was an LLM call that printed articles back. That is the most expensive way to do a lookup (output at 15/token) and it can hallucinate. Removed.
3. Triage and audit are now plain Python: triage builds a compact case description, audit validates that action is one of the 4 allowed values and kb_article is a real article id. Four LLM calls became one (compose).
4. Removed the uuid, the duplicated "TRIAGE AGAIN" block, and the verbose trigger phrases ("restate", "double-check", "full reasoning").
5. The system prompt is a fixed prefix passed as cached_prefix, but the real help center is under the 1024-token minimum, so no cache discount applied (cached = 0). The savings come from removing padding, removing calls and shortening output, not from caching.

Breakdown, refund path, T-1001 (one call "compose"):
input = 385 tokens x 3 = 1,155
cached = 0
output = 46 tokens x 15 = 690
total = 1,845 points

Breakdown, escalation path, T-1003 (one call "compose"):
input = 366 tokens x 3 = 1,098
cached = 0
output = 39 tokens x 15 = 585
total = 1,683 points

## Limitations and notes

- The LLM here is a simulator that computes the answer from the order snapshot, so this task measures cost, not model accuracy. With a real model I would need an evaluation set to check that removing reasoning does not hurt accuracy.
- Sending the whole real help center works because it is small (~300 tokens). A genuinely large help center would need real retrieval (keyword or embeddings) to pick a few articles.
- The simulator still returns a short customer_reply, so output tokens (36 to 46) could not be reduced further from my side.
- test_baseline_cost_is_high in both test files now fails by design: it asserts the unoptimized cost is high, and the cost is now low. The correctness tests (action and kb_article) pass.
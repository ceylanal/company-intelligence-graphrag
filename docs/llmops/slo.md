# Service Level Objectives

No production traffic baseline exists, so numeric SLOs are intentionally not fabricated.

| Indicator | Measurement | Initial status |
|---|---|---|
| Availability | successful liveness and API responses / total | baseline required |
| Successful task rate | completed research / started research | baseline required |
| p95 latency | HTTP and workflow histograms | baseline required |
| Citation coverage | cited material / factual claims | existing eval must be mapped |
| Groundedness | representative frozen eval | existing eval must be mapped |
| Error rate | 5xx / requests | baseline required |

After a controlled staging window, freeze the sample window, p50/p95, error rate, task success, model calls, tokens, citation coverage, and groundedness. Set targets from those measured values plus an explicitly approved regression allowance.

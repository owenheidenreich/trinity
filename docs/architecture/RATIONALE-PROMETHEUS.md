# Rationale: Self-Hosted Prometheus vs SaaS Observability

> **ADR:** [decisions/003-prometheus-over-saas.md](decisions/003-prometheus-over-saas.md)

## Status
Accepted

## Date
February 2026

## Context
We need production-grade observability for monitoring, alerting, and performance analysis. The primary options are:

| Option | Monthly Cost | Pros | Cons |
|--------|-------------|------|------|
| **DataDog** | $500-2000 | Easy setup, great UI | Expensive, vendor lock-in |
| **New Relic** | $400-1500 | APM features | Similar cost issues |
| **CloudWatch** | $100-300 | AWS native | Doesn't work with Akash |
| **Prometheus + Grafana** | $0 | Free, flexible | Manual setup |

## Decision
Use self-hosted Prometheus + Grafana deployed on existing Akash infrastructure.

### Architecture
```
┌─────────────────────────────────────────────────────────┐
│                    Akash Deployment                      │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌───────────┐ │
│  │   Trinity    │───▶│  Prometheus  │───▶│  Grafana  │ │
│  │   Backend    │    │   (scrape)   │    │   (viz)   │ │
│  │  /metrics    │    │   :9090      │    │   :3000   │ │
│  └──────────────┘    └──────────────┘    └───────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Metrics Exposed
```python
# middleware/observability.py
REQUEST_LATENCY = Histogram('trinity_http_request_duration_seconds', ...)
INFERENCE_DURATION = Histogram('trinity_inference_duration_seconds', ...)
ERROR_COUNTER = Counter('trinity_errors_total', ...)
TOKENS_GENERATED = Counter('trinity_tokens_generated_total', ...)
# ... 27+ total metrics
```

## Rationale

1. **Cost**: $0 vs $500-2000/month—significant savings over project lifetime
2. **Control**: Full control over metrics, retention, and alerting rules
3. **Integration**: Already have Akash compute available in deployment
4. **Privacy**: Metrics stay in our infrastructure, not third-party
5. **Portability**: Prometheus format is industry standard, no vendor lock-in
6. **Decentralization**: Aligns with Trinity's decentralized architecture

## Consequences

### Positive
- Zero additional monthly cost
- Complete control and customization
- Works with decentralized Akash deployment
- Industry-standard format (easy to migrate if needed)
- Can create custom dashboards for Trinity-specific metrics

### Negative
- Manual dashboard creation (no auto-discovery)
- Must configure AlertManager separately for alerting
- Requires operational knowledge of Prometheus
- No built-in APM/tracing (would need Jaeger addition)

## Implementation

### Prometheus Configuration
```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'trinity'
    static_configs:
      - targets: ['localhost:5000']
    metrics_path: '/metrics'
```

### Key Dashboards Created
1. **Request Overview**: Latency P50/P95/P99, request rate, error rate
2. **Inference Performance**: Model latency by tier, token generation rate
3. **System Health**: CPU, memory, active connections
4. **Caching**: Hit rates, cache sizes, token usage

### Metrics Endpoint
```python
@app.route('/metrics')
def metrics():
    from middleware.observability import get_metrics_response
    return get_metrics_response()
```

## Alternatives Considered

1. **DataDog**: Excellent UX but $500-2000/month, creates vendor dependency
2. **New Relic**: Similar cost/lock-in issues as DataDog
3. **CloudWatch**: Would require AWS infrastructure, incompatible with Akash
4. **No observability**: Unacceptable—can't operate production without metrics

## Future Considerations

- **Jaeger**: Add distributed tracing if debugging complex request flows becomes necessary
- **AlertManager**: Configure PagerDuty/Slack integration for production alerts
- **Thanos**: Consider for long-term metric storage if retention needs increase

## References
- [middleware/observability.py](../../backend/middleware/observability.py) - Metrics definitions
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)

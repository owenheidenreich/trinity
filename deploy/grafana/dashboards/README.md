# Grafana Dashboard Files
The actual dashboard JSON files are in the parent `deploy/grafana/` directory:
- `trinity-dashboard.json` — Main system health & usage dashboard
- `trinity-agent-dashboard.json` — Agent pipeline & ReAct loop metrics

These files are volume-mounted into Grafana at `/var/lib/grafana/dashboards/`
via the docker-compose.monitoring.yml configuration.

## Privacy
Dashboards are configured to display ONLY aggregate metrics.
Explicitly excluded:
- Message content
- User principals or identifiers
- Chat titles
- IP addresses
- Any PII

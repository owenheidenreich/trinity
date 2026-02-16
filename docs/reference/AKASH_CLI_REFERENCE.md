# Akash CLI Reference for LLMs

> **Purpose**: This document captures practical knowledge about the Akash Network CLI (`provider-services`) for autonomous deployment operations. Written for LLMs assisting with Trinity deployments.

## Quick Reference

| Operation | Command Pattern |
|-----------|----------------|
| Create deployment | `provider-services tx deployment create <yaml> --from <wallet> ...` |
| List bids | `provider-services query market bid list --owner <addr> --dseq <id> ...` |
| Accept bid | `provider-services tx market lease create --dseq <id> --provider <addr> ...` |
| Send manifest | `provider-services send-manifest <yaml> --dseq <id> --provider <addr> ...` |
| Get URL | `provider-services lease-status --dseq <id> --provider <addr> ...` |
| View logs | `provider-services lease-logs --dseq <id> --provider <addr> ...` |
| Close deployment | `provider-services tx deployment close --dseq <id> ...` |
| Check balance | `provider-services query bank balances <addr> ...` |

---

## Common Flags (Required for Most Commands)

```bash
--from trinity-wallet           # Wallet name in keyring
--keyring-backend os            # Keyring type (os, file, test)
--chain-id akashnet-2           # Akash mainnet chain ID
--node https://rpc.akashnet.net:443  # RPC endpoint
--gas-prices 0.025uakt          # Gas price
--gas auto                      # Auto-calculate gas
--gas-adjustment 1.5            # Buffer for gas estimation
-y                              # Auto-confirm (skip prompt)
```

---

## 1. Creating a Deployment

```bash
provider-services tx deployment create deploy-production.yaml \
  --from trinity-wallet \
  --keyring-backend os \
  --chain-id akashnet-2 \
  --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt \
  --gas auto \
  --gas-adjustment 1.5 \
  -y
```

**Output**: JSON with `dseq` (deployment sequence number) in events.

**Extract dseq from output**:
```bash
# The dseq appears in the EventDeploymentCreated event
# Example: "dseq":"25288917"
```

---

## 2. Querying Bids

Wait 10-15 seconds after creating deployment for bids to arrive.

```bash
# List all bids
provider-services query market bid list \
  --owner akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp \
  --dseq 25288917 \
  --node https://rpc.akashnet.net:443 \
  -o json
```

**Get cheapest provider**:
```bash
provider-services query market bid list \
  --owner <OWNER> --dseq <DSEQ> \
  --node https://rpc.akashnet.net:443 -o json 2>/dev/null \
  | jq -r '.bids | sort_by(.bid.price.amount | tonumber) | .[0].bid.id.provider'
```

**Bid structure** (important fields):
```json
{
  "bid": {
    "id": {
      "owner": "akash155...",
      "dseq": "25288917",
      "gseq": 1,
      "oseq": 1,
      "provider": "akash1abc..."
    },
    "state": "open",
    "price": {
      "denom": "uakt",
      "amount": "649.124392"
    },
    "resources_offer": [...]
  }
}
```

---

## 3. Accepting a Bid (Creating a Lease)

```bash
provider-services tx market lease create \
  --dseq 25288917 \
  --provider akash1hgulk6aekakqzc0v6wukrd3dy9n90f5gkl4ezk \
  --from trinity-wallet \
  --keyring-backend os \
  --chain-id akashnet-2 \
  --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt \
  --gas auto \
  --gas-adjustment 1.5 \
  -y
```

---

## 4. Sending Manifest

**IMPORTANT**: Do NOT use `--chain-id` flag with send-manifest.

```bash
provider-services send-manifest deploy-production.yaml \
  --dseq 25288917 \
  --provider akash1hgulk6aekakqzc0v6wukrd3dy9n90f5gkl4ezk \
  --from trinity-wallet \
  --keyring-backend os \
  --node https://rpc.akashnet.net:443
```

**Success output**:
```
provider: akash1hgulk6aekakqzc0v6wukrd3dy9n90f5gkl4ezk
        status:       PASS
```

---

## 5. Getting Deployment URL

```bash
provider-services lease-status \
  --dseq 25288917 \
  --provider akash1hgulk6aekakqzc0v6wukrd3dy9n90f5gkl4ezk \
  --from trinity-wallet \
  --keyring-backend os \
  --node https://rpc.akashnet.net:443
```

**Extract URL**:
```bash
provider-services lease-status ... -o json 2>/dev/null \
  | jq -r '.services.<service_name>.uris[0]'
```

For Trinity, service name is `trinity`:
```bash
| jq -r '.services.trinity.uris[0]'
```

---

## 6. Viewing Logs

```bash
provider-services lease-logs \
  --dseq 25288917 \
  --provider akash1hgulk6aekakqzc0v6wukrd3dy9n90f5gkl4ezk \
  --from trinity-wallet \
  --keyring-backend os \
  --node https://rpc.akashnet.net:443 \
  --follow=false \
  --tail 50
```

**Options**:
- `--follow=true` - Stream logs (like `tail -f`)
- `--tail N` - Last N lines

---

## 7. Closing a Deployment

```bash
provider-services tx deployment close \
  --dseq 25288917 \
  --from trinity-wallet \
  --keyring-backend os \
  --chain-id akashnet-2 \
  --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt \
  --gas auto \
  --gas-adjustment 1.5 \
  -y
```

---

## 8. Checking Wallet Balance

```bash
provider-services query bank balances akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp \
  --node https://rpc.akashnet.net:443 \
  -o json
```

**Pretty print AKT**:
```bash
provider-services query bank balances <ADDR> --node https://rpc.akashnet.net:443 -o json 2>/dev/null \
  | jq -r '.balances[] | select(.denom=="uakt") | .amount' \
  | awk '{printf "%.2f AKT\n", $1/1000000}'
```

---

## 9. Listing Active Deployments

```bash
provider-services query deployment list \
  --owner akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp \
  --state active \
  --node https://rpc.akashnet.net:443
```

---

## SDL/YAML Constraints

### HTTP Options Limits

**CRITICAL**: Akash has hard limits on `http_options`:

```yaml
# MAXIMUM VALUES (will error if exceeded)
http_options:
  read_timeout: 60000    # Max 60 seconds (60000 ms)
  send_timeout: 60000    # Max 60 seconds (60000 ms)
  max_body_size: 10485760  # 10MB works fine
```

**Error if exceeded**:
```
Error: http option not allowed: read timeout cannot be greater than 60000 ms
```

### Basic Service Structure

```yaml
version: "2.0"

services:
  trinity:
    image: gdubx/trinity-inference:v2-20260128-230845
    env:
      - KEY=value
    expose:
      - port: 8000
        as: 80
        to:
          - global: true
        http_options:
          read_timeout: 60000
          send_timeout: 60000
          max_body_size: 10485760

profiles:
  compute:
    trinity:
      resources:
        cpu:
          units: 8
        memory:
          size: 32Gi
        storage:
          size: 100Gi
        gpu:
          units: 1
          attributes:
            vendor:
              nvidia:

  placement:
    akash:
      pricing:
        trinity:
          denom: uakt
          amount: 20000  # Max bid in uakt/block

deployment:
  trinity:
    akash:
      profile: trinity
      count: 1
```

---

## Deployment Workflow Summary

```bash
# 1. Create deployment (returns dseq)
DSEQ=$(provider-services tx deployment create deploy.yaml \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y \
  -o json | jq -r '.logs[0].events[] | select(.type=="akash.deployment.v1.EventDeploymentCreated") | .attributes[] | select(.key=="id") | .value' | jq -r '.dseq')

# 2. Wait for bids (10-15 seconds)
sleep 15

# 3. Get cheapest provider
PROVIDER=$(provider-services query market bid list \
  --owner $OWNER --dseq $DSEQ \
  --node https://rpc.akashnet.net:443 -o json 2>/dev/null \
  | jq -r '.bids | sort_by(.bid.price.amount | tonumber) | .[0].bid.id.provider')

# 4. Create lease
provider-services tx market lease create \
  --dseq $DSEQ --provider $PROVIDER \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y

# 5. Send manifest (NO --chain-id!)
provider-services send-manifest deploy.yaml \
  --dseq $DSEQ --provider $PROVIDER \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443

# 6. Get URL
URL=$(provider-services lease-status \
  --dseq $DSEQ --provider $PROVIDER \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443 -o json 2>/dev/null \
  | jq -r '.services.trinity.uris[0]')

echo "Deployment URL: https://$URL"
```

---

## Common Errors & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `http option not allowed: read timeout cannot be greater than 60000 ms` | Timeout too high | Use max 60000 (60s) |
| `unknown flag: --chain-id` | Wrong command | Remove `--chain-id` from `send-manifest` |
| `502 Bad Gateway` | Container starting | Wait 30-60s, check logs |
| `404 Not Found` | Container not ready | Wait for manifest to deploy |
| No bids received | Price too low or no providers | Increase `amount` in pricing |

---

## Trinity-Specific Values

```bash
WALLET_NAME="trinity-wallet"
WALLET_ADDR="akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp"
CHAIN_ID="akashnet-2"
RPC_NODE="https://rpc.akashnet.net:443"
```

---

## Timing Expectations

| Operation | Expected Time |
|-----------|---------------|
| Bid arrival | 10-15 seconds |
| Lease creation | 5-10 seconds |
| Manifest send | 2-5 seconds |
| Docker pull (test tier) | 30-60 seconds |
| Docker pull (production tier) | 60-90 seconds |
| Model download (4.9GB) | 60-120 seconds |
| Flask warmup | 10-30 seconds |
| **Total cold start** | **2-5 minutes** |

---

## Health Check Pattern

```bash
# Poll until healthy
for i in {1..20}; do
  STATUS=$(curl -sk "https://$URL/health" 2>/dev/null | jq -r '.status // "starting"')
  if [ "$STATUS" = "healthy" ]; then
    echo "✅ Deployment ready!"
    break
  fi
  echo "Status: $STATUS (attempt $i/20)"
  sleep 15
done
```

---

*Last updated: 2026-02-15*
*Based on: provider-services CLI, Akash mainnet (akashnet-2)*

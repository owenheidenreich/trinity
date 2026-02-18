# Trinity: Existing Wallet — New Mac Setup Guide

> For users who already have an Akash wallet and are setting up Trinity on a new Mac.

## Prerequisites Checklist

| Tool | Purpose | Required |
|------|---------|----------|
| Docker Desktop | Build & push containers | ✅ Yes |
| Homebrew | Package manager for macOS | ✅ Yes |
| Node.js | Build frontend | ✅ Yes |
| Akash CLI | Deploy to Akash Network | ✅ Yes |
| Akash Wallet | Sign deployment transactions | ✅ Yes (with ~5 AKT) |
| Akash Certificate | Provider communication | ✅ Yes (created once) |
| Wrangler CLI | Cloudflare Workers deployment | ✅ Yes |
| dfx SDK | Deploy ICP canisters | ⚠️ Optional |
| Docker Hub account | Push container images | ✅ Yes |

---

## Step 1: Install Docker Desktop

1. Download from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
2. Open the `.dmg` and drag Docker to Applications
3. **Launch Docker Desktop** (it must be running, not just installed)
4. Wait for Docker to fully start (whale icon in menu bar stops animating)

**Verify:**
```bash
docker info
```

---

## Step 2: Install Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**After installation completes**, add Homebrew to your PATH (Apple Silicon Macs):
```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
source ~/.zshrc
```

**Verify:**
```bash
brew --version
```

---

## Step 3: Install Node.js

```bash
brew install node
```

**Verify:**
```bash
node --version   # Should show v20+ or v22+
npm --version
```

---

## Step 4: Install Akash CLI

```bash
curl -sfL https://raw.githubusercontent.com/akash-network/provider/main/install.sh | sudo bash -s -- -b /usr/local/bin
```

> ⚠️ **Note:** Requires `sudo` to install to `/usr/local/bin`. The default install (without `-b` flag) puts the binary in `./bin` which isn't in your PATH.

**Verify:**
```bash
provider-services version
```

---

## Step 5: Import Akash Wallet

```bash
provider-services keys add trinity-wallet --recover --keyring-backend os
```

Enter your **24-word mnemonic** when prompted. macOS will ask for Keychain access — grant it.

**Verify:**
```bash
provider-services keys show trinity-wallet --keyring-backend os -a
```
Should output: `akash1...` (your wallet address)

**Check balance:**
```bash
provider-services query bank balances $(provider-services keys show trinity-wallet --keyring-backend os -a) --node https://rpc.akashnet.net:443 -o json
```

> ⚠️ **Need at least ~5 AKT** for deployment escrow.

---

## Step 6: Create Akash Certificate (Required for New Machines)

This is required for provider communication. Only needs to be done once per wallet/machine.

**Generate the certificate:**
```bash
provider-services tx cert generate client \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443
```

**Publish to blockchain:**
```bash
provider-services tx cert publish client \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y
```

> ⚠️ **Common Error:** `could not open certificate PEM file` means you skipped this step.

---

## Step 7: Install Wrangler CLI (Cloudflare Workers)

```bash
npm install -g wrangler
```

**Login to Cloudflare:**
```bash
wrangler login
```

This opens a browser for OAuth authentication.

**Verify:**
```bash
wrangler whoami
```

---

## Step 8: Deploy Cloudflare Worker (First Time Only)

```bash
cd deploy/cloudflare-worker
wrangler deploy
```

Note your Worker URL (e.g., `https://trinity-proxy.yourname.workers.dev`).

---

## Step 9: Install dfx SDK (Optional)

Only needed if deploying ICP canisters. Script will skip ICP deployment if not installed.

```bash
sh -ci "$(curl -fsSL https://internetcomputer.org/install.sh)"
```

Restart terminal or run:
```bash
source ~/.zshrc
```

**Verify:**
```bash
dfx --version
```

---

## Step 10: Login to Docker Hub

```bash
docker login
```

Enter your Docker Hub username and password/token.

> **Note:** You need push access to `gdubx/trinity-inference` or update the deployment script to use your own Docker Hub repository.

---

## Step 11: Clone Repository & Deploy

```bash
git clone https://github.com/gdubx/Trinity.git
cd Trinity
./scripts/trinity-deploy-production.sh production
```

The script will:
1. Check all prerequisites
2. Build Docker image (AMD64)
3. Push to Docker Hub
4. Deploy to Akash Network
5. Update Cloudflare Worker with new Akash URL
6. Deploy ICP frontend (if dfx installed)
7. Verify everything works
7. Verify everything works

---

## Quick Verification Commands

```bash
# All prerequisites installed?
docker info && brew --version && node --version && provider-services version

# Wallet ready?
provider-services keys show trinity-wallet --keyring-backend os -a

# Docker Hub access?
docker login
```

---

## Common Issues

| Problem | Solution |
|---------|----------|
| `zsh: command not found: brew` | Run Homebrew install (Step 2) |
| `zsh: command not found: provider-services` | Reinstall with `sudo` and `-b /usr/local/bin` flag |
| `docker info` fails | Start Docker Desktop app |
| Keychain password prompt | Grant access (Akash uses macOS Keychain) |
| `Permission denied` during install | Use `sudo` |
| Low AKT balance warning | Fund wallet with ~5 AKT |
| `could not open certificate PEM file` | Run Step 6 to create Akash certificate |
| `Missing entry-point to Worker script` | Run `wrangler deploy` from inside `deploy/cloudflare-worker/` directory |
| `out of gas` error | Add `--gas-prices 0.025uakt --gas auto --gas-adjustment 1.5` flags |
| Akash deployment fails silently | Run the `provider-services tx deployment create` command manually to see full error |
| Cloudflare 526 SSL error | Use `http://` not `https://` for Akash URL in Worker secret |
| `npm run build` fails with missing packages | Run `npm install` first in `trinity-icp/` |
| `npm run build` fails with ERESOLVE/vite conflict | Downgrade vite to `^5.4.0` in package.json, delete node_modules & package-lock.json, reinstall |
| Frontend shows "connection error" | Update `PRODUCTION_API_URL` in `config.js` to Cloudflare Worker URL |
| Container shows unhealthy | Wait 5-10 min for model download; check logs with `lease-logs` |
| `Unknown Domain` on custom domain | Register domain with ICP canister (see ICP Custom Domain section) |

---

## Cloudflare DNS Setup (dubya.ai)

After deployment, configure DNS in Cloudflare Dashboard:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| CNAME | `@` | `zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io` | ☁️ ON |
| CNAME | `www` | `dubya.ai` | ☁️ ON |
| AAAA | `api` | `100::` | ☁️ ON |

Then add Worker Route:
- Route: `api.dubya.ai/*`
- Worker: `trinity-proxy`

---

## Manual Akash Deployment (If Script Fails)

If the automated script fails, run these commands manually:

```bash
# 1. Create deployment
provider-services tx deployment create deploy/akash/deploy-production.yaml \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y

# Note the DSEQ from output, then:

# 2. Wait 30s for bids, then list them
provider-services query market bid list \
  --owner $(provider-services keys show trinity-wallet --keyring-backend os -a) \
  --dseq YOUR_DSEQ \
  --node https://rpc.akashnet.net:443 -o json

# 3. Accept a bid (choose a provider from the list)
provider-services tx market lease create \
  --dseq YOUR_DSEQ --gseq 1 --oseq 1 \
  --provider PROVIDER_ADDRESS \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y

# 4. Send manifest
provider-services send-manifest deploy/akash/deploy-production.yaml \
  --dseq YOUR_DSEQ --provider PROVIDER_ADDRESS \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443

# 5. Get the URI
provider-services query provider lease-status \
  --dseq YOUR_DSEQ --gseq 1 --oseq 1 \
  --provider PROVIDER_ADDRESS \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443

# 6. Update Cloudflare Worker with new URL (USE HTTP, NOT HTTPS!)
cd deploy/cloudflare-worker
echo "http://YOUR_AKASH_URI" | wrangler secret put AKASH_URL
# IMPORTANT: Use http:// not https:// - Akash providers have invalid SSL certs
```

---

## Frontend Build & Deployment

After updating the backend, rebuild and deploy the frontend:

```bash
# 1. Navigate to frontend directory
cd trinity-icp

# 2. Install dependencies (required on new Mac or after clean)
npm install

# 3. Build the frontend
npm run build

# 4. Deploy to ICP
dfx deploy --network ic trinity_frontend
```

**Important**: If you changed the Akash backend URL, update [config.js](../trinity-icp/src/config.js) first:

```javascript
// In trinity-icp/src/config.js
const PRODUCTION_API_URL = 'https://your-cloudflare-worker-url.workers.dev';
```

---

## ICP Custom Domain Registration

To use a custom domain (e.g., `dubya.ai`) with your ICP canister:

### Method 1: ICP Dashboard (Recommended)
1. Go to [https://nns.ic0.app](https://nns.ic0.app)
2. Navigate to **Canisters** → Select your frontend canister
3. Click **Custom Domain** → **Register Domain**
4. Add your domain (e.g., `dubya.ai`)
5. Follow the DNS verification steps

### Method 2: Command Line
```bash
# Register custom domain
dfx canister --network ic call trinity_frontend register_custom_domain '("dubya.ai")'
```

### Required DNS Records (Cloudflare)
| Type | Name | Content | Proxy |
|------|------|---------|-------|
| CNAME | `_acme-challenge` | Value from ICP verification | ❌ OFF |
| CNAME | `_canister-id` | `<canister-id>.icp0.io` | ❌ OFF |
| CNAME | `@` | `icp1.io` | ☁️ ON (after verification) |

---

## Key Troubleshooting Notes

### HTTP vs HTTPS for Akash URLs
**CRITICAL**: Always use `http://` (not `https://`) when setting the Akash URL:

```bash
# ❌ WRONG - Will cause SSL 526 errors
wrangler secret put AKASH_URL <<< "https://provider.akash.com:12345"

# ✅ CORRECT - Akash providers have self-signed/invalid SSL certs
wrangler secret put AKASH_URL <<< "http://provider.akash.com:12345"
```

The Cloudflare Worker handles HTTPS on the frontend; the backend connection is HTTP.

### Startup Times
- **Test tier (Qwen3 32B)**: Starts in ~2-5 minutes
- **Production tier (Qwen3 32B)**: May take 5-10+ minutes to download and load model

If the container seems stuck, check container logs:
```bash
provider-services lease-logs \
  --dseq YOUR_DSEQ --gseq 1 --oseq 1 \
  --provider PROVIDER_ADDRESS \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443 --follow
```

### Frontend Not Connecting to Backend
If the frontend shows connection errors after deployment:

1. **Check config.js** - Ensure `PRODUCTION_API_URL` points to your Cloudflare Worker
2. **Verify Worker secret** - Run `wrangler secret list` in `deploy/cloudflare-worker/`
3. **Test Worker directly**: `curl https://your-worker.workers.dev/health`
4. **Test Akash directly**: `curl http://your-akash-uri/health`

### npm Commands Must Run in Correct Directory
```bash
# ❌ Wrong - npm won't find package.json
npm run build

# ✅ Correct - run from trinity-icp directory
cd trinity-icp && npm run build

# ✅ Or from cloudflare-worker directory for wrangler
cd deploy/cloudflare-worker && npx wrangler deploy
```

---

*Last verified: June 2025*

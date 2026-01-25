# Trinity Quick Reference

**Commands, startup procedures, and website update workflows**

---

## 🚀 Daily Commands

### Start Local Development
```bash
./dev.sh
```
- Starts TinyLlama 1.1B on localhost:8000
- Opens browser to index.html automatically
- Free, instant responses

### Test Production Backend
```bash
./test-prod.sh
```
- Connects to Akash Llama 70B backend
- Tests production environment
- 20-30 second cold start is normal

### Deploy to Production
```bash
./deploy.sh llama70b
```
- Builds Docker image with timestamp tag
- Pushes to Docker Hub (gdubx/trinity-inference)
- Updates all YAML deployment files
- Shows manual Akash Console steps

---

## 🖥️ Local Backend Management

### Start Local Backend
```bash
cd deployment/local
./start.sh
```

### Stop Local Backend
```bash
cd deployment/local
./stop.sh
```

### Check Backend Status
```bash
cd deployment/local
./status.sh
```

### Manual Backend Start
```bash
cd deployment/scripts
python3 inference_server.py
```

### Stop All Backend Processes
```bash
pkill -f inference_server.py
pkill -f ollama
```

---

## 🔍 Health Checks

### Local Backend
```bash
curl http://localhost:8000/health
```

### Akash Production Backend
```bash
curl http://hdol1m0mohfll4s4t8mhip33sg.ingress.a100.dsm.val.akash.pub/health
```

### Frontend (Production)
```bash
curl https://trinityai.cc/
```

### Verify ICP Domain
```bash
curl https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io/.well-known/ic-domains
```

---

## 📊 View Logs

### Backend Logs
```bash
tail -f /tmp/trinity_backend.log
```

### Ollama Logs
```bash
tail -f /tmp/ollama.log
```

### Filter for Errors
```bash
tail -f /tmp/trinity_backend.log | grep ERROR
```

### Filter for Specific Endpoint
```bash
tail -f /tmp/trinity_backend.log | grep /chat/autosave
```

---

## 🐳 Docker Commands

### Build Backend Image
```bash
cd deployment/prod
./build.sh
```

### Manual Docker Build
```bash
cd deployment/prod
docker build -t gdubx/trinity-inference:v2-$(date +%Y%m%d-%H%M%S) \
  --platform linux/amd64 \
  -f Dockerfile .
```

### Push to Docker Hub
```bash
docker push gdubx/trinity-inference:v2-YYYYMMDD-HHMMSS
```

### List Trinity Images
```bash
docker images | grep trinity
```

### Check Running Containers
```bash
docker ps
```

### View Container Logs
```bash
docker logs <container-id>
```

### Stop All Docker Containers
```bash
docker stop $(docker ps -q)
```

### Clean Up Docker
```bash
docker system prune -a
```

---

## 🌐 Frontend Deployment (ICP)

### Deploy to ICP Mainnet
```bash
cd trinity-icp
dfx deploy --network ic trinity_frontend
```

### Build Frontend Locally (Testing)
```bash
cd trinity-icp
npm run build
```

### Check Canister Status
```bash
dfx canister --network ic status trinity_frontend
```

### View Canister Info
```bash
dfx canister --network ic info trinity_frontend
```

---

## ☁️ Akash Backend Deployment

### Step 1: Build and Push Docker Image
```bash
cd deployment/prod
./build.sh
# Note the image tag: v2-YYYYMMDD-HHMMSS
```

### Step 2: Deploy via Akash Console
1. Go to https://console.akash.network
2. Click "Create Deployment" (or "Update Deployment" if updating)
3. Select "SDL" tab
4. Paste YAML from `deployment/prod/deploy-llama70.yaml`
5. Update image tag to new version
6. Click "Create Deployment"
7. Wait for bids (~30-60 seconds)
8. Select a bid (check price and provider)
9. Accept bid
10. Wait for deployment (~10-15 minutes for model download)

### Step 3: Copy New Akash URL
- Format: `http://[hash].ingress.[provider].akash.pub`
- Example: `http://hdol1m0mohfll4s4t8mhip33sg.ingress.a100.dsm.val.akash.pub`

### Step 4: Update Cloudflare Worker
1. Go to https://dash.cloudflare.com
2. Navigate to Workers & Pages → `trinity-api-proxy`
3. Click "Edit Code"
4. Update `AKASH_BACKEND` constant with new URL
5. Click "Save and Deploy"

### Step 5: Update Frontend
```bash
cd trinity-icp/src
# Edit config.js - update fallback Akash URL
vim config.js

cd ../..
dfx deploy --network ic trinity_frontend
```

### Step 6: Verify
```bash
curl https://api.trinityai.cc/health | jq .
# Check for new build_timestamp
```

---

## 🔄 Website Update Workflows

### Frontend Code Update (HTML/CSS/JS)
```bash
# 1. Make changes in trinity-icp/src/
vim trinity-icp/src/app.js
vim trinity-icp/src/styles.css

# 2. Test locally
open trinity-icp/src/index.html

# 3. Deploy to ICP
cd trinity-icp
dfx deploy --network ic trinity_frontend

# 4. Verify (wait 1-2 minutes)
open https://trinityai.cc
# Hard refresh: Cmd+Shift+R
```

### Backend Code Update (Python)
```bash
# 1. Make changes in deployment/scripts/
vim deployment/scripts/inference_server.py

# 2. Test locally
cd deployment/local
./start.sh
curl http://localhost:8000/health

# 3. Build and push
cd ../prod
./build.sh

# 4. Update Akash deployment (Console)
# Follow "Akash Backend Deployment" steps above

# 5. Verify
curl https://api.trinityai.cc/health | jq .
```

### Cloudflare Worker Update
```bash
# 1. Edit worker locally
vim cloudflare/workers/trinity-api-proxy.js

# 2. Deploy via dashboard
# Login to https://dash.cloudflare.com
# Workers & Pages → trinity-api-proxy → Edit Code
# Paste updated code → Save and Deploy

# 3. Verify
curl https://api.trinityai.cc/health
```

### Environment Variable Update (Backend)
```bash
# 1. Update YAML file
vim deployment/prod/deploy-llama70.yaml
# Add/modify env section

# 2. Push with same Docker image
# No need to rebuild - just update SDL

# 3. Update Akash deployment
# Console → Update Deployment → Paste YAML

# 4. Wait for restart (~2-3 minutes)

# 5. Verify
curl https://api.trinityai.cc/health
```

---

## 🐛 Debug Console Commands

### Check Configuration
```javascript
CONFIG.API_URL
CONFIG._currentEnvironment
CONFIG._availableEnvironments
```

### Check Authentication
```javascript
State.isAuthenticated
State.principal
window.debugAuth()
```

### Check State
```javascript
State.chatHistory
State.contextMemory
State.conversationSummary
State.allChats
```

### Check UI Elements
```javascript
UI.elements
UI.showMessage('user', 'Test message')
UI.renderSidebar()
```

### Trigger Actions
```javascript
Actions.checkHealth()
Actions.newChat()
API.request('/health', {method: 'GET'})
```

### Test Autosave
```javascript
Autosave.scheduleAutosave({messages: State.chatHistory})
Autosave.executeAutosave()
```

---

## 🔧 Troubleshooting Commands

### Check Port Usage
```bash
lsof -i :8000   # Backend port
lsof -i :11434  # Ollama port
```

### Check Process Status
```bash
ps aux | grep ollama
ps aux | grep inference_server
```

### Restart Ollama
```bash
brew services restart ollama
```

### Check Disk Space
```bash
df -h
```

### Check Docker Disk Usage
```bash
docker system df
```

### Test Ollama Directly
```bash
ollama list
ollama pull tinyllama:1.1b
ollama run tinyllama:1.1b "Say hello"
```

### Check Network Connectivity
```bash
ping trinityai.cc
curl -I https://trinityai.cc
```

### Force Cache Clear (Browser)
```bash
# Chrome/Safari: Cmd+Shift+R
# Firefox: Cmd+Shift+Delete → Clear cache
```

---

## 📋 Environment Variables

### Backend (Local)
```bash
export FILECOIN_API_KEY="$(cat ~/.pinata_jwt)"
export CHATS_DIR="$HOME/.trinity/chats"
export MODEL_NAME="tinyllama:1.1b"
export OLLAMA_HOST="http://localhost:11434"
export PROVIDER_ID="local-mac"
```

### Backend (Akash - set in YAML)
```yaml
env:
  - PROVIDER_ID=trinity-llama70b
  - MODEL_NAME=llama3.1:70b
  - GPU_TYPE=NVIDIA-A100
  - OLLAMA_HOST=http://localhost:11434
  - FILECOIN_API_KEY=eyJhbGc...
  - CHATS_DIR=/var/lib/trinity/chats
```

---

## 🔗 Production URLs

| Component | URL |
|-----------|-----|
| Frontend | https://trinityai.cc |
| API Proxy | https://api.trinityai.cc |
| ICP Canister (Direct) | https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io |
| Akash Backend | http://hdol1m0mohfll4s4t8mhip33sg.ingress.a100.dsm.val.akash.pub |
| Akash Console | https://console.akash.network |
| Cloudflare Dashboard | https://dash.cloudflare.com |
| Docker Hub | https://hub.docker.com/u/gdubx |
| Pinata Dashboard | https://app.pinata.cloud |

---

## 📦 File Locations

| File | Location |
|------|----------|
| Frontend Source | `trinity-icp/src/` |
| Backend Source | `deployment/scripts/` |
| Docker Config | `deployment/prod/Dockerfile` |
| Akash YAMLs | `deployment/prod/deploy-*.yaml` |
| Cloudflare Workers | `cloudflare/workers/` |
| Backend Logs | `/tmp/trinity_backend.log` |
| Ollama Logs | `/tmp/ollama.log` |
| Local Chats | `~/.trinity/chats/` |
| Pinata JWT | `~/.pinata_jwt` |

---

## 🎯 Common Task Shortcuts

### Quick Backend Restart
```bash
pkill -f inference_server && cd deployment/local && ./start.sh
```

### Quick Frontend Deploy
```bash
cd trinity-icp && dfx deploy --network ic trinity_frontend
```

### Quick Docker Build + Push
```bash
cd deployment/prod && ./build.sh
```

### Quick Health Check All
```bash
echo "Local:" && curl -s http://localhost:8000/health | jq .status
echo "Akash:" && curl -s https://api.trinityai.cc/health | jq .status
echo "Frontend:" && curl -s https://trinityai.cc | head -1
```

### Quick Log Tail All
```bash
tail -f /tmp/trinity_backend.log /tmp/ollama.log
```

---

*For detailed troubleshooting and architecture information, see [claude.md](claude.md)*

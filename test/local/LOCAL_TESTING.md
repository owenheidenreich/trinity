# Local Testing Setup

## Current Configuration (January 20, 2026)

### Backend Status
- **Running:** Yes (PID 55416)
- **URL:** http://localhost:8000
- **Model:** tinyllama:1.1b (637MB)
- **Status:** Healthy ✅

### Environment
```bash
FILECOIN_API_KEY="$(cat ~/.pinata_jwt)"
CHATS_DIR="$HOME/.trinity/chats"
PROVIDER_ID="local-mac"
MODEL_NAME="tinyllama:1.1b"
OLLAMA_HOST="http://localhost:11434"
```

### Pinata Configuration
- JWT Token: Stored in `~/.pinata_jwt` (600 permissions)
- API Endpoint: https://api.pinata.cloud/pinning/pinFileToIPFS
- Replication: FRA1 + NYC1

### Quick Commands
```bash
# Start backend
cd /Users/owenheidenreich/Documents/Trinity/Trinity/deployment
./start-local.sh

# Stop backend
kill 55416

# View logs
tail -f /tmp/trinity_backend.log

# Health check
curl http://localhost:8000/health

# Test with frontend
open https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io
```

### Testing Filecoin Integration
```bash
cd /Users/owenheidenreich/Documents/Trinity/Trinity
python3 -m pytest tests/test_phase2_integration.py -v
```

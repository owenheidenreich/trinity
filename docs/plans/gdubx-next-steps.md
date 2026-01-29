# Trinity Add-ons & Funding Roadmap

**Last Updated:** January 28, 2026

> ⚠️ Before attempting to test this, ensure you have a fully constructed Test-Environment setup.

## Vision

Trinity is a **group-funded decentralized LLM** on Akash with the ability for users to deploy their own private instances at marked-up rates. The markup funds the community LLM and provides minimal platform profit.

## Phase 1: Funding Transparency ✅ IMPLEMENTED

### Features Completed
- [x] **Akash deployment tracker** - Shows escrow balance, time remaining, daily cost
- [x] **Real-time AKT pricing** - CoinGecko API integration with USD conversion
- [x] **Funding progress bar** - Visual indicator with color coding (green/yellow/red)
- [x] **Donation modal** - QR codes for AKT and ICP donations
- [x] **ICP cycle balance query** - Canister method for frontend to fetch cycles
- [x] **Private session modal UI** - Tier selection, duration picker, cost breakdown

### Endpoints Added
- `GET /funding/status` - Returns AKT price, deployment escrow, costs, donation addresses

## Phase 2: Private Sessions (In Progress)

### Fee Structure
```
User pays X AKT for private session
├── 95% → User's deployment escrow (pays for hardware)
├── 4%  → Community LLM fund (keeps free tier running)
└── 1%  → Platform fee (profit)
```

### Smart Contract Architecture

For trustless fee routing, we need a CosmWasm smart contract on Akash/Cosmos:

```rust
// Trinity Payment Router Contract
// Deployed on Akash Network (Cosmos SDK chain)

pub struct Config {
    pub admin: Addr,                    // Can update fee percentages
    pub community_wallet: Addr,         // Receives 4% for community LLM
    pub platform_wallet: Addr,          // Receives 1% platform fee
    pub deployment_wallet: Addr,        // Main wallet for Akash deployments
}

pub struct FeeConfig {
    pub hardware_bps: u64,    // 9500 = 95%
    pub community_bps: u64,   // 400 = 4%
    pub platform_bps: u64,    // 100 = 1%
}

// Execute messages
pub enum ExecuteMsg {
    // User sends AKT with session params, contract routes funds
    PayForSession {
        tier: String,           // "starter", "standard", "professional"
        duration_hours: u64,
    },
    
    // Admin: Update fee percentages
    UpdateFees { fees: FeeConfig },
    
    // Admin: Update wallet addresses
    UpdateWallets { config: Config },
}

// Flow:
// 1. User sends AKT to contract with PayForSession message
// 2. Contract splits funds: 95% → escrow, 4% → community, 1% → platform
// 3. Contract emits event with session details
// 4. Backend listens for events, triggers Akash deployment
// 5. After deployment, contract sends escrow to provider
```

### Alternative: Backend-Based Routing (Simpler)

If smart contract development is too complex for Phase 2, we can use backend routing:

```
1. User sends AKT to a payment-specific wallet
2. Backend detects payment via Akash RPC polling
3. Backend manually transfers: 4% → community, 1% → platform
4. Backend deploys user's private instance with remaining 95%
5. User gets websocket notification when ready
```

**Tradeoff:** Less trustless, but faster to implement.

### Session Timer (5-min warning)

```javascript
// Frontend session management
class SessionTimer {
    constructor(endTime) {
        this.endTime = endTime;
        this.warningShown = false;
    }
    
    tick() {
        const remaining = this.endTime - Date.now();
        const minutes = Math.floor(remaining / 60000);
        
        // 5-minute warning
        if (minutes <= 5 && !this.warningShown) {
            this.showWarning();
            this.warningShown = true;
        }
        
        // Session ended
        if (remaining <= 0) {
            this.endSession();
        }
        
        this.updateUI(remaining);
    }
    
    showWarning() {
        // Modal: "5 minutes remaining. Add more time?"
        // Options: [Add 1 hour] [Add 2 hours] [Let it end]
    }
}
```

## Phase 3: Multi-Provider Support

- Allow users to choose Akash providers
- Show provider ratings, latency, reliability
- Dynamic pricing based on provider bids

## Original Requirements (Reference)

- Akash price transparency ✅
- ICP price transparency ✅
- Filecoin price transparency (Lighthouse free tier shown)
- Dollars per hour/month visual ✅
- AKT funding the deployment ✅
- Estimate time remaining ✅
- User donation feature ✅
- ICP canister tracker ✅
- QR codes for donations ✅ 
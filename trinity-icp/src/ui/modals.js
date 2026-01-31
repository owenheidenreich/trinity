// modals.js - Modal dialogs and prompts
// Responsible for confirmation dialogs, input prompts, and modal interactions

const Modals = {
    // Helper to remove all existing modals
    removeAllModals() {
        document.querySelectorAll('.modal-dialog').forEach(modal => modal.remove());
    },

    // Show initial authentication choice modal
    async showAuthChoiceModal() {
        this.removeAllModals(); // Clear any existing modals
        return new Promise(resolve => {
            const dialog = document.createElement('div');
            dialog.className = 'modal-dialog';
            dialog.innerHTML = `
                <div class="modal-content auth-modal">
                    <h3 style="text-align: center; margin-bottom: 24px;">trinity</h3>
                    <button class="auth-btn auth-btn-gray" data-choice="login">
                        🔑 Login
                    </button>
                    <button class="auth-btn auth-btn-gray" data-choice="create">
                        ✨ Create New Identity
                    </button>
                </div>
            `;
            document.body.appendChild(dialog);
            
            // Prevent closing modal by clicking backdrop
            dialog.onclick = (e) => {
                if (e.target === dialog) {
                    e.stopPropagation();
                    e.preventDefault();
                }
            };

            dialog.querySelectorAll('.auth-btn').forEach(btn => {
                btn.onclick = () => {
                    const choice = btn.getAttribute('data-choice');
                    dialog.remove();
                    resolve(choice);
                };
            });
        });
    },

    // Show key warning modal for new identity creation
    async showKeyWarningModal(principal, privateKeyHex) {
        this.removeAllModals(); // Clear any existing modals
        return new Promise(resolve => {
            const dialog = document.createElement('div');
            dialog.className = 'modal-dialog';
            dialog.innerHTML = `
                <div class="modal-content key-warning-modal">
                    <div class="warning-header">
                        🚨 CRITICAL SECURITY WARNING
                    </div>
                    <div class="warning-text">
                        • This key controls your Trinity identity and saved chats<br>
                        • Store it in a password manager or encrypted file
                    </div>
                    <div class="credentials-container">
                        <div class="credential-label">Username:</div>
                        <div class="credential-value selectable">${principal}</div>
                        <div class="credential-label" style="margin-top: 16px;">Password:</div>
                        <div class="credential-value selectable">${privateKeyHex}</div>
                    </div>
                    <div class="modal-buttons" style="justify-content: center;">
                        <button class="btn-confirm">Okay</button>
                    </div>
                </div>
            `;
            document.body.appendChild(dialog);
            
            // Prevent closing modal by clicking backdrop
            dialog.onclick = (e) => {
                if (e.target === dialog) {
                    e.stopPropagation();
                    e.preventDefault();
                }
            };

            dialog.querySelector('.btn-confirm').onclick = () => {
                dialog.remove();
                resolve(true);
            };

            // Make credentials selectable
            dialog.querySelectorAll('.selectable').forEach(el => {
                el.onclick = () => {
                    const range = document.createRange();
                    range.selectNodeContents(el);
                    const selection = window.getSelection();
                    selection.removeAllRanges();
                    selection.addRange(range);
                };
            });
        });
    },

    // Show "are you sure" confirmation
    async showAreYouSureModal() {
        this.removeAllModals(); // Clear any existing modals
        return new Promise(resolve => {
            const dialog = document.createElement('div');
            dialog.className = 'modal-dialog';
            dialog.innerHTML = `
                <div class="modal-content confirm-modal">
                    <h3 style="text-align: center;">Are you sure?</h3>
                    <p style="text-align: center; color: #bbb;">Have you saved your credentials?</p>
                    <div class="modal-buttons">
                        <button class="btn-cancel">Cancel</button>
                        <button class="btn-confirm">Okay</button>
                    </div>
                </div>
            `;
            document.body.appendChild(dialog);

            dialog.querySelector('.btn-cancel').onclick = () => {
                dialog.remove();
                resolve(false);
            };

            dialog.querySelector('.btn-confirm').onclick = () => {
                dialog.remove();
                resolve(true);
            };
        });
    },

    // Show login modal with username and password
    async showLoginModal() {
        this.removeAllModals(); // Clear any existing modals
        return new Promise(resolve => {
            const dialog = document.createElement('div');
            dialog.className = 'modal-dialog';
            dialog.innerHTML = `
                <div class="modal-content import-modal">
                    <h3>trinity</h3>
                    <p style="color: #bbb; margin-bottom: 16px;">Enter your credentials:</p>
                    <div style="margin-bottom: 12px;">
                        <div class="credential-label">Username:</div>
                        <textarea class="modal-input username-input" placeholder="Paste your username (principal)..." rows="2"></textarea>
                    </div>
                    <div style="margin-bottom: 16px;">
                        <div class="credential-label">Password:</div>
                        <textarea class="modal-input password-input" placeholder="Paste your password (private key)..." rows="3"></textarea>
                    </div>
                    <div class="modal-buttons">
                        <button class="btn-cancel">Cancel</button>
                        <button class="btn-confirm">Okay</button>
                    </div>
                </div>
            `;
            document.body.appendChild(dialog);
            
            // Prevent closing modal by clicking backdrop
            dialog.onclick = (e) => {
                if (e.target === dialog) {
                    e.stopPropagation();
                    e.preventDefault();
                }
            };

            const usernameInput = dialog.querySelector('.username-input');
            const passwordInput = dialog.querySelector('.password-input');
            
            dialog.querySelector('.btn-cancel').onclick = () => {
                dialog.remove();
                resolve(null);
            };

            dialog.querySelector('.btn-confirm').onclick = () => {
                const username = usernameInput.value.trim();
                const password = passwordInput.value.trim();
                dialog.remove();
                resolve((username && password) ? { username, password } : null);
            };

            usernameInput.focus();
        });
    },

    async showConfirmDialog(title, message) {
        this.removeAllModals(); // Clear any existing modals
        return new Promise(resolve => {
            const dialog = document.createElement('div');
            dialog.className = 'modal-dialog';
            dialog.innerHTML = `
                <div class="modal-content">
                    <h3>${title}</h3>
                    <p>${message}</p>
                    <div class="modal-buttons">
                        <button class="btn-cancel">Cancel</button>
                        <button class="btn-confirm">Confirm</button>
                    </div>
                </div>
            `;
            document.body.appendChild(dialog);

            dialog.querySelector('.btn-cancel').onclick = () => {
                dialog.remove();
                resolve(false);
            };

            dialog.querySelector('.btn-confirm').onclick = () => {
                dialog.remove();
                resolve(true);
            };
        });
    },

    showPrompt(title, message, buttonText, callback) {
        const dialog = document.createElement('div');
        dialog.className = 'modal-dialog';
        dialog.innerHTML = `
            <div class="modal-content">
                <h3>${title}</h3>
                <p>${message}</p>
                <div class="modal-buttons">
                    <button class="btn-action">${buttonText}</button>
                </div>
            </div>
        `;
        document.body.appendChild(dialog);

        dialog.querySelector('.btn-action').onclick = () => {
            dialog.remove();
            if (callback) callback();
        };
    },

    async showInputDialog(prompt) {
        return new Promise(resolve => {
            const dialog = document.createElement('div');
            dialog.className = 'modal-dialog';
            dialog.innerHTML = `
                <div class="modal-content">
                    <h3>${prompt}</h3>
                    <input type="text" class="modal-input" placeholder="Paste recovery ID">
                    <div class="modal-buttons">
                        <button class="btn-cancel">Cancel</button>
                        <button class="btn-confirm">Restore</button>
                    </div>
                </div>
            `;
            document.body.appendChild(dialog);

            const input = dialog.querySelector('.modal-input');
            dialog.querySelector('.btn-cancel').onclick = () => {
                dialog.remove();
                resolve(null);
            };

            dialog.querySelector('.btn-confirm').onclick = () => {
                const value = input.value.trim();
                dialog.remove();
                resolve(value || null);
            };

            input.focus();
        });
    },

    // Show About Trinity modal
    showAboutModal() {
        this.removeAllModals();
        const dialog = document.createElement('div');
        dialog.className = 'modal-dialog';
        dialog.innerHTML = `
            <div class="modal-content about-modal">
                <h2 style="text-align: center; margin-bottom: 20px;">About Trinity</h2>
                <p style="text-align: center; color: #aaa; margin-bottom: 24px;">
                    A fully decentralized AI assistant
                </p>
                
                <div class="about-section">
                    <h4>🌐 Internet Computer (ICP)</h4>
                    <p>Your interface runs on ICP canisters — censorship-resistant smart contracts that serve the frontend globally without centralized servers.</p>
                </div>
                
                <div class="about-section">
                    <h4>☁️ Akash Network (AKT)</h4>
                    <p>AI inference runs on Akash's decentralized cloud. Your conversations are processed on GPU nodes worldwide, with no central authority controlling access.</p>
                </div>
                
                <div class="about-section">
                    <h4>📦 IPFS Storage</h4>
                    <p>Archived chats are stored permanently on IPFS (InterPlanetary File System). Content-addressed storage means your data is verifiable, immutable, and truly yours.</p>
                </div>
                
                <div class="about-section">
                    <h4>🔗 The Flow</h4>
                    <pre style="background: #1a1a1a; padding: 12px; border-radius: 6px; font-size: 11px; overflow-x: auto;">
You → ICP Frontend → ICP Backend Canister
              ↓
      Vercel Proxy (SSL)
              ↓
      Akash Backend (GPU + Ollama)
              ↓
      Archive → Lighthouse → IPFS</pre>
                </div>
                
                <div class="about-section">
                    <h4>🔐 Your Keys, Your Data</h4>
                    <p>Trinity uses Ed25519 keypairs for authentication. You own your private key — we never see it. Export it anytime from the sidebar.</p>
                </div>
                
                <div class="about-links" style="margin-top: 20px; text-align: center;">
                    <a href="https://internetcomputer.org" target="_blank">ICP</a> · 
                    <a href="https://akash.network" target="_blank">Akash</a> · 
                    <a href="https://ipfs.tech" target="_blank">IPFS</a> · 
                    <a href="https://ens.domains" target="_blank">ENS</a>
                </div>
                
                <div class="modal-buttons" style="justify-content: center; margin-top: 24px;">
                    <button class="btn-confirm">Close</button>
                </div>
            </div>
        `;
        document.body.appendChild(dialog);

        // Close on backdrop click
        dialog.onclick = (e) => {
            if (e.target === dialog) {
                dialog.remove();
            }
        };

        dialog.querySelector('.btn-confirm').onclick = () => {
            dialog.remove();
        };
    },

    // Show About IPFS/CID modal
    showIPFSModal(cid) {
        this.removeAllModals();
        const shortCid = cid.length > 20 ? cid.substring(0, 12) + '...' + cid.substring(cid.length - 8) : cid;
        const gatewayUrl = `https://gateway.lighthouse.storage/ipfs/${cid}`;
        
        const dialog = document.createElement('div');
        dialog.className = 'modal-dialog';
        dialog.innerHTML = `
            <div class="modal-content about-modal">
                <h2 style="text-align: center; margin-bottom: 20px;">📦 Archived on IPFS</h2>
                <p style="text-align: center; color: #aaa; margin-bottom: 24px;">
                    This chat is permanently stored on the decentralized web
                </p>
                
                <div class="about-section">
                    <h4>What is a CID?</h4>
                    <p>A Content Identifier (CID) is a unique fingerprint of your data. Unlike URLs, CIDs are based on the content itself — if even one character changes, the CID changes. This guarantees the data you retrieve is exactly what was stored.</p>
                </div>
                
                <div class="about-section">
                    <h4>Your Archive CID</h4>
                    <div style="background: #1a1a1a; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 11px; word-break: break-all; margin-top: 8px;">
                        ${cid}
                    </div>
                </div>
                
                <div class="about-section">
                    <h4>What Can You Do With It?</h4>
                    <ul style="margin: 0; padding-left: 20px; color: #aaa; font-size: 13px; line-height: 1.6;">
                        <li><strong>Verify:</strong> Check that your archive exists and is unchanged</li>
                        <li><strong>Share:</strong> Anyone with the CID can access the encrypted data</li>
                        <li><strong>Recover:</strong> Retrieve your chat from any IPFS gateway worldwide</li>
                        <li><strong>Prove:</strong> Cryptographic proof that this content existed at archive time</li>
                    </ul>
                </div>
                
                <div class="about-section">
                    <h4>Where Is It Stored?</h4>
                    <p>Your archive is stored on <strong>IPFS</strong> (InterPlanetary File System) — a global peer-to-peer network. <a href="https://docs.lighthouse.storage" target="_blank" style="color: #69db7c;">Lighthouse.storage</a> handles uploads and provides permanent pinning.</p>
                </div>
                
                <div class="modal-buttons" style="justify-content: center; margin-top: 24px; gap: 12px;">
                    <a href="${gatewayUrl}" target="_blank" class="btn-secondary" style="text-decoration: none;">View on IPFS ↗</a>
                    <button class="btn-confirm">Close</button>
                </div>
            </div>
        `;
        document.body.appendChild(dialog);

        // Close on backdrop click
        dialog.onclick = (e) => {
            if (e.target === dialog) {
                dialog.remove();
            }
        };

        dialog.querySelector('.btn-confirm').onclick = () => {
            dialog.remove();
        };
    },

    // Show Akash Provider info modal
    showAkashProviderModal(providerHostname, gpuType, model) {
        this.removeAllModals();
        
        const dialog = document.createElement('div');
        dialog.className = 'modal-dialog';
        dialog.innerHTML = `
            <div class="modal-content about-modal">
                <h2 style="text-align: center; margin-bottom: 20px;">☁️ Akash Provider</h2>
                <p style="text-align: center; color: #aaa; margin-bottom: 24px;">
                    Your AI runs on decentralized compute
                </p>
                
                <div class="about-section">
                    <h4>Provider: ${providerHostname}</h4>
                    <p>This is an <strong>audited Akash provider</strong> — a verified data center operator participating in the Akash decentralized cloud marketplace.</p>
                </div>
                
                <div class="about-section">
                    <h4>✓ Audited Attributes</h4>
                    <p>Akash providers can be audited by trusted parties who verify their hardware, uptime, and security practices. Audited providers have on-chain attestations proving:</p>
                    <ul style="margin: 8px 0 0 0; padding-left: 20px; color: #aaa; font-size: 12px; line-height: 1.6;">
                        <li><strong>Hardware verification:</strong> GPU type and count confirmed</li>
                        <li><strong>Geographic location:</strong> Data center location verified</li>
                        <li><strong>Uptime history:</strong> Historical availability tracked</li>
                        <li><strong>Security practices:</strong> Isolation and data handling audited</li>
                    </ul>
                </div>
                
                <div class="about-section">
                    <h4>Your Session</h4>
                    <div style="background: #1a1a1a; padding: 12px; border-radius: 6px; font-size: 11px; line-height: 1.8; font-family: monospace;">
                        <div><span style="color: #888;">Provider:</span> <span style="color: #ff6b6b;">${providerHostname}</span></div>
                        <div><span style="color: #888;">GPU:</span> <span style="color: #69db7c;">${gpuType}</span></div>
                        <div><span style="color: #888;">Model:</span> <span style="color: #a78bfa;">${model}</span></div>
                    </div>
                </div>
                
                <div class="about-section">
                    <h4>Why Decentralized Compute?</h4>
                    <p>Unlike centralized cloud providers (AWS, Google, Azure), Akash is a permissionless marketplace. Anyone can provide compute, and anyone can deploy. No single entity can censor or shut down your AI.</p>
                </div>
                
                <div class="modal-buttons" style="justify-content: center; margin-top: 24px; gap: 12px;">
                    <a href="https://console.akash.network/providers" target="_blank" class="btn-secondary" style="text-decoration: none;">View All Providers ↗</a>
                    <button class="btn-confirm">Close</button>
                </div>
            </div>
        `;
        document.body.appendChild(dialog);

        // Close on backdrop click
        dialog.onclick = (e) => {
            if (e.target === dialog) {
                dialog.remove();
            }
        };

        dialog.querySelector('.btn-confirm').onclick = () => {
            dialog.remove();
        };
    },

    // Show ICP info modal
    showICPModal(canisterId) {
        this.removeAllModals();
        
        const dialog = document.createElement('div');
        dialog.className = 'modal-dialog';
        dialog.innerHTML = `
            <div class="modal-content about-modal">
                <h2 style="text-align: center; margin-bottom: 20px;">◈ Internet Computer</h2>
                <p style="text-align: center; color: #aaa; margin-bottom: 24px;">
                    Your frontend runs on the world computer
                </p>
                
                <div class="about-section">
                    <h4>What is ICP?</h4>
                    <p>The Internet Computer is a blockchain that runs at web speed. Unlike traditional blockchains, it can host entire web applications — frontend, backend, and data — all on-chain.</p>
                </div>
                
                <div class="about-section">
                    <h4>Your Canister</h4>
                    <div style="background: #1a1a1a; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 11px; word-break: break-all; margin-top: 8px;">
                        <div><span style="color: #888;">Frontend:</span> <span style="color: #5ac8fa;">${canisterId}</span></div>
                        <div style="margin-top: 4px;"><span style="color: #888;">Backend:</span> <span style="color: #5ac8fa;">au5zq-2qaaa-aaaal-qtowa-cai</span></div>
                    </div>
                    <p style="margin-top: 8px; font-size: 11px; color: #666;">Canisters are smart contracts that can serve web content. Your entire Trinity interface is hosted here.</p>
                </div>
                
                <div class="about-section">
                    <h4>Why It Matters</h4>
                    <ul style="margin: 0; padding-left: 20px; color: #aaa; font-size: 12px; line-height: 1.6;">
                        <li><strong>Censorship resistant:</strong> No single company can take it down</li>
                        <li><strong>No servers:</strong> Runs on a decentralized network of nodes</li>
                        <li><strong>Tamper-proof:</strong> Code is verified by blockchain consensus</li>
                        <li><strong>Always available:</strong> No cloud provider outages</li>
                    </ul>
                </div>
                
                <div class="modal-buttons" style="justify-content: center; margin-top: 24px; gap: 12px;">
                    <a href="https://dashboard.internetcomputer.org/canister/${canisterId}" target="_blank" class="btn-secondary" style="text-decoration: none;">View Canister ↗</a>
                    <button class="btn-confirm">Close</button>
                </div>
            </div>
        `;
        document.body.appendChild(dialog);

        dialog.onclick = (e) => {
            if (e.target === dialog) dialog.remove();
        };
        dialog.querySelector('.btn-confirm').onclick = () => dialog.remove();
    },

    // Show IPFS/Lighthouse info modal
    showIPFSStorageModal() {
        this.removeAllModals();
        
        const dialog = document.createElement('div');
        dialog.className = 'modal-dialog';
        dialog.innerHTML = `
            <div class="modal-content about-modal">
                <h2 style="text-align: center; margin-bottom: 20px;">◉ IPFS Storage</h2>
                <p style="text-align: center; color: #aaa; margin-bottom: 24px;">
                    Your archives live forever on decentralized storage
                </p>
                
                <div class="about-section">
                    <h4>The Storage Stack</h4>
                    <div style="background: #1a1a1a; padding: 12px; border-radius: 6px; font-size: 11px; line-height: 1.8; font-family: monospace;">
                        <div><span style="color: #69db7c;">Lighthouse SDK</span> <span style="color: #666;">→ handles uploads & pinning</span></div>
                        <div><span style="color: #69db7c;">IPFS</span> <span style="color: #666;">→ content-addressed permanent storage</span></div>
                    </div>
                </div>
                
                <div class="about-section">
                    <h4>How It Works</h4>
                    <p>When you archive a chat, Lighthouse uploads it to IPFS and pins it permanently. The CID (Content ID) is your permanent address — anyone with it can retrieve your encrypted data from any IPFS gateway worldwide.</p>
                </div>
                
                <div class="about-section">
                    <h4>Why Lighthouse?</h4>
                    <ul style="margin: 0; padding-left: 20px; color: #aaa; font-size: 12px; line-height: 1.6;">
                        <li><strong>Easy integration:</strong> Simple SDK for developers</li>
                        <li><strong>Verified deals:</strong> Confirms data is actually stored</li>
                        <li><strong>Encryption:</strong> Optional client-side encryption</li>
                        <li><strong>Perpetual storage:</strong> Deals auto-renew</li>
                    </ul>
                </div>
                
                <div class="about-section">
                    <h4>Your Data, Your Keys</h4>
                    <p>Archives are encrypted with your principal ID before upload. Only you can decrypt them. Lighthouse and IPFS nodes see only encrypted bytes.</p>
                </div>
                
                <div class="modal-buttons" style="justify-content: center; margin-top: 24px; gap: 12px;">
                    <a href="https://docs.lighthouse.storage" target="_blank" class="btn-secondary" style="text-decoration: none;">Lighthouse Docs ↗</a>
                    <button class="btn-confirm">Close</button>
                </div>
            </div>
        `;
        document.body.appendChild(dialog);

        dialog.onclick = (e) => {
            if (e.target === dialog) dialog.remove();
        };
        dialog.querySelector('.btn-confirm').onclick = () => dialog.remove();
    },

    // Show Model info modal
    showModelModal(modelName, gpuType) {
        this.removeAllModals();
        
        // Parse model info
        const isLlama = modelName.toLowerCase().includes('llama');
        const isQwen = modelName.toLowerCase().includes('qwen');
        const is70B = modelName.includes('70b') || modelName.includes('70B');
        const is8B = modelName.includes('8b') || modelName.includes('8B');
        
        let modelDescription = 'A large language model running on decentralized infrastructure.';
        let modelLink = 'https://ollama.com/library';
        let modelFamily = 'Unknown';
        
        if (isLlama) {
            modelFamily = 'Meta Llama';
            modelDescription = 'Meta\'s open-source Llama model, one of the most capable open LLMs available. Trained on publicly available data with strong reasoning and coding abilities.';
            modelLink = 'https://llama.meta.com';
        } else if (isQwen) {
            modelFamily = 'Alibaba Qwen';
            modelDescription = 'Alibaba\'s Qwen model series, known for strong multilingual capabilities and competitive performance with proprietary models.';
            modelLink = 'https://qwenlm.github.io';
        }
        
        let sizeInfo = '';
        if (is70B) sizeInfo = '70 billion parameters — requires significant GPU memory, offers highest quality responses.';
        else if (is8B) sizeInfo = '8 billion parameters — efficient and fast while maintaining strong capabilities.';
        
        const dialog = document.createElement('div');
        dialog.className = 'modal-dialog';
        dialog.innerHTML = `
            <div class="modal-content about-modal">
                <h2 style="text-align: center; margin-bottom: 20px;">🧠 AI Model</h2>
                <p style="text-align: center; color: #aaa; margin-bottom: 24px;">
                    Open-source AI running on your terms
                </p>
                
                <div class="about-section">
                    <h4>Current Model</h4>
                    <div style="background: #1a1a1a; padding: 12px; border-radius: 6px; font-size: 11px; line-height: 1.8; font-family: monospace;">
                        <div><span style="color: #888;">Model:</span> <span style="color: #a78bfa;">${modelName}</span></div>
                        <div><span style="color: #888;">Family:</span> <span style="color: #a78bfa;">${modelFamily}</span></div>
                        <div><span style="color: #888;">GPU:</span> <span style="color: #69db7c;">${gpuType}</span></div>
                    </div>
                </div>
                
                <div class="about-section">
                    <h4>About This Model</h4>
                    <p>${modelDescription}</p>
                    ${sizeInfo ? `<p style="margin-top: 8px; font-size: 12px; color: #888;">${sizeInfo}</p>` : ''}
                </div>
                
                <div class="about-section">
                    <h4>Why Open Source?</h4>
                    <ul style="margin: 0; padding-left: 20px; color: #aaa; font-size: 12px; line-height: 1.6;">
                        <li><strong>Transparent:</strong> Anyone can inspect the model weights</li>
                        <li><strong>No censorship:</strong> No corporate content policies</li>
                        <li><strong>Self-hostable:</strong> Run it yourself if you want</li>
                        <li><strong>Privacy:</strong> Your prompts never leave this infrastructure</li>
                    </ul>
                </div>
                
                <div class="about-section">
                    <h4>Powered by Ollama</h4>
                    <p>Trinity uses Ollama to run models locally on GPU. No API calls to OpenAI, Anthropic, or other centralized providers.</p>
                </div>
                
                <div class="modal-buttons" style="justify-content: center; margin-top: 24px; gap: 12px;">
                    <a href="${modelLink}" target="_blank" class="btn-secondary" style="text-decoration: none;">Learn More ↗</a>
                    <button class="btn-confirm">Close</button>
                </div>
            </div>
        `;
        document.body.appendChild(dialog);

        dialog.onclick = (e) => {
            if (e.target === dialog) dialog.remove();
        };
        dialog.querySelector('.btn-confirm').onclick = () => dialog.remove();
    }
};

export default Modals;

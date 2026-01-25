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
    }
};

export default Modals;

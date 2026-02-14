// auth/keyExportModal.js - Security modal for displaying and copying private keys
// Shows critical security warnings and allows users to copy their Ed25519 private key

import Logger from '../core/logger.js';

export function showKeyExportModal(privateKeyHex, principal) {
    const modal = document.createElement('div');
    modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); display: flex; align-items: center; justify-content: center; z-index: 10000;';
    
    modal.innerHTML = `
        <div style="background: #1e1e1e; padding: 30px; border-radius: 12px; max-width: 600px; border: 2px solid #4CAF50;">
            <h2 style="color: #4CAF50; margin: 0 0 20px 0; font-size: 24px;">🔑 Your Trinity Identity Created</h2>
            
            <div style="background: #2d2d2d; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 2px solid #9c27b0;">
                <div style="color: #9c27b0; font-size: 14px; margin-bottom: 10px; font-weight: 700;">📦 Your FIL Address (Filecoin Recovery):</div>
                <div style="color: #fff; font-family: monospace; font-size: 11px; word-break: break-all; line-height: 1.5; background: #1a1a1a; padding: 12px; border-radius: 4px;">${principal}</div>
                <div style="color: #bbb; font-size: 11px; margin-top: 8px;">💡 Use this address to recover all archived chats from Filecoin</div>
            </div>
            
            <div style="background: #2d2d2d; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #4CAF50;">
                <div style="color: #4CAF50; font-size: 13px; margin-bottom: 10px; font-weight: 600;">Principal ID (Authentication):</div>
                <div style="color: #4CAF50; font-family: monospace; font-size: 11px; word-break: break-all;">${principal}</div>
            </div>
            
            <div style="background: #2d2d2d; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #ff9800;">
                <div style="color: #ff9800; font-size: 13px; margin-bottom: 10px; font-weight: 600;">⚠️ Private Key (SAVE THIS SECURELY):</div>
                <textarea id="privateKeyText" readonly style="color: #fff; font-family: monospace; font-size: 11px; word-break: break-all; line-height: 1.6; width: 100%; background: transparent; border: none; resize: none; height: 80px; outline: none;">${privateKeyHex}</textarea>
                <button id="copyKeyBtn" style="background: #ff9800; color: #000; padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; margin-top: 12px; font-weight: 600; width: 100%;">
                    📋 Copy Private Key
                </button>
            </div>
            
            <div style="background: #ff5252; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <div style="color: #fff; font-size: 13px; line-height: 1.6;">
                    <strong>🚨 CRITICAL SECURITY WARNING:</strong><br><br>
                    • This key controls your Trinity identity, chats, and future payment account<br>
                    • Store it in a password manager or encrypted file<br>
                    • Anyone with this key can access your account<br>
                    • If you lose it, your chats and account are <strong>permanently lost</strong><br>
                    • Trinity does not store this key - you are responsible for it
                </div>
            </div>
            
            <button id="confirmSavedBtn" style="background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%); color: white; padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; width: 100%;">
                ✅ I Have Saved My Key Securely
            </button>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Add copy functionality
    const copyBtn = modal.querySelector('#copyKeyBtn');
    const keyTextarea = modal.querySelector('#privateKeyText');
    copyBtn.addEventListener('click', () => {
        try {
            // Select and focus the textarea
            keyTextarea.focus();
            keyTextarea.select();
            keyTextarea.setSelectionRange(0, 99999); // For mobile
            
            // Use the older but more reliable execCommand
            const successful = document.execCommand('copy');
            
            if (successful) {
                copyBtn.textContent = '✅ Copied!';
                copyBtn.style.background = '#4CAF50';
                setTimeout(() => {
                    copyBtn.textContent = '📋 Copy Private Key';
                    copyBtn.style.background = '#ff9800';
                }, 2000);
            } else {
                throw new Error('execCommand failed');
            }
        } catch (err) {
            Logger.error('Failed to copy:', err);
            // Keep text selected for manual copy
            keyTextarea.focus();
            keyTextarea.select();
            copyBtn.textContent = '⚠️ Text Selected - Press Ctrl+C';
            copyBtn.style.background = '#f44336';
            setTimeout(() => {
                copyBtn.textContent = '📋 Copy Private Key';
                copyBtn.style.background = '#ff9800';
            }, 3000);
        }
    });
    
    // Add confirmation before closing
    const confirmBtn = modal.querySelector('#confirmSavedBtn');
    confirmBtn.addEventListener('click', (e) => {
        // CRITICAL: Stop event from bubbling to document listener
        e.stopImmediatePropagation();
        e.preventDefault();
        
        const userConfirmed = confirm('Are you sure you have saved your private key securely? You will NOT be able to recover your identity without it.\n\nClick OK to close this screen.\nClick Cancel to keep it open.');
        
        if (userConfirmed) {
            // User clicked OK - close the modal
            modal.remove();
        }
        // If user clicked Cancel, do nothing - modal stays open
    }, { capture: false });
    
    // Also stop propagation on the entire modal content area
    const modalContent = modal.querySelector('div');
    modalContent.addEventListener('click', (e) => {
        e.stopPropagation();
    });
}

export default showKeyExportModal;

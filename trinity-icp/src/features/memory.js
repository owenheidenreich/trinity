// ============================================================================
// FEATURE: MEMORY — User memory management & status dashboard
// ============================================================================
// Handles: view/add/delete memory facts, account status dashboard.
// ============================================================================

import API from '../core/api.js';
import State from '../state/store.js';
import UI from '../ui/index.js';

/**
 * Open account status dashboard modal.
 */
export async function openStatusDashboard() {
    try {
        const status = await API.request('/user/status', { method: 'GET' });

        const s = status.storage || {};
        const r = status.rate_limits || {};
        const t = status.tokens || {};

        const storagePercent = Math.min(100, Math.round((s.chats_used / s.chats_limit) * 100));
        const tokenPercent = Math.min(100, Math.round((t.used_today / t.limit_today) * 100));

        const dialog = document.createElement('div');
        dialog.className = 'modal-dialog';
        dialog.innerHTML = `
            <div class="modal-content" style="max-width: 500px; max-height: 80vh;">
                <h3 style="margin-bottom: 16px;">Account Status</h3>

                <div style="margin-bottom: 20px;">
                    <div style="font-size: 12px; color: #aaa; margin-bottom: 6px; font-weight: 600;">STORAGE</div>
                    <div style="display: flex; justify-content: space-between; font-size: 13px; color: #ddd; margin-bottom: 4px;">
                        <span>${s.chats_used}/${s.chats_limit} chats</span>
                        <span>${s.pinned_count || 0} pinned, ${s.archived_count || 0} archived</span>
                    </div>
                    <div style="height: 6px; background: #333; border-radius: 3px; overflow: hidden;">
                        <div style="height: 100%; width: ${storagePercent}%; background: ${storagePercent > 80 ? '#f44336' : '#667eea'}; border-radius: 3px; transition: width 0.3s;"></div>
                    </div>
                </div>

                <div style="margin-bottom: 20px;">
                    <div style="font-size: 12px; color: #aaa; margin-bottom: 6px; font-weight: 600;">REQUESTS</div>
                    <div style="display: flex; justify-content: space-between; font-size: 13px; color: #ddd;">
                        <span>${r.requests_remaining}/${r.requests_limit} remaining</span>
                        <span>${r.resets_in_seconds ? `Resets in ${r.resets_in_seconds}s` : 'Ready'}</span>
                    </div>
                </div>

                <div style="margin-bottom: 20px;">
                    <div style="font-size: 12px; color: #aaa; margin-bottom: 6px; font-weight: 600;">TOKENS (TODAY)</div>
                    <div style="display: flex; justify-content: space-between; font-size: 13px; color: #ddd; margin-bottom: 4px;">
                        <span>${(t.used_today || 0).toLocaleString()} used</span>
                        <span>${(t.limit_today || 0).toLocaleString()} limit</span>
                    </div>
                    <div style="height: 6px; background: #333; border-radius: 3px; overflow: hidden;">
                        <div style="height: 100%; width: ${tokenPercent}%; background: ${tokenPercent > 80 ? '#f44336' : '#4caf50'}; border-radius: 3px; transition: width 0.3s;"></div>
                    </div>
                </div>

                <button data-action="closeStatusDialog" style="background: #555; color: white; padding: 10px; border: none; border-radius: 4px; cursor: pointer; width: 100%; font-size: 14px;">
                    Close
                </button>
            </div>
        `;
        document.body.appendChild(dialog);
    } catch (error) {
        UI.showError('Could not load status: ' + error.message);
    }
}

/**
 * View and manage user memory modal.
 */
export async function viewMemory() {
    if (!State.userMemory) {
        UI.showError('User memory not loaded');
        return;
    }

    const facts = State.userMemory.facts || [];

    const dialog = document.createElement('div');
    dialog.className = 'modal-dialog';
    dialog.innerHTML = `
        <div class="modal-content" style="max-width: 600px; max-height: 80vh;">
            <h3 style="margin-bottom: 12px;">🧠 Your Memory</h3>
            <p style="font-size: 13px; color: #aaa; margin-bottom: 16px;">
                These facts persist across all your chats. The AI remembers them automatically.
            </p>
            
            <div style="margin-bottom: 16px;">
                <input type="text" id="newFactInput" placeholder="Add a new fact..." 
                    style="width: 100%; padding: 10px; background: #2a2a2a; border: 1px solid #444; border-radius: 4px; color: white; font-size: 14px; margin-bottom: 8px;">
                <button data-action="addNewFact" style="background: #9C27B0; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; width: 100%; font-size: 13px;">
                    ➕ Add Fact
                </button>
            </div>
            
            <div id="factsList" style="max-height: 300px; overflow-y: auto; margin-bottom: 16px;">
                ${facts.length === 0 ? 
                    '<p style="text-align: center; color: #666; padding: 20px;">No facts yet. Add one above!</p>' :
                    facts.map((fact, index) => `
                        <div style="background: #2a2a2a; padding: 12px; border-radius: 4px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: start;">
                            <div style="flex: 1;">
                                <div style="color: white; margin-bottom: 4px;">${fact.fact}</div>
                                <div style="font-size: 11px; color: #666;">
                                    ${new Date(fact.addedAt).toLocaleDateString()} 
                                    ${fact.category ? `• ${fact.category}` : ''}
                                </div>
                            </div>
                            <button data-action="deleteFact" data-fact-index="${index}" style="background: #f44336; color: white; padding: 4px 8px; border: none; border-radius: 4px; cursor: pointer; font-size: 11px; margin-left: 8px;">
                                🗑️
                            </button>
                        </div>
                    `).join('')
                }
            </div>
            
            <button data-action="closeMemoryDialog" style="background: #555; color: white; padding: 10px; border: none; border-radius: 4px; cursor: pointer; width: 100%; font-size: 14px;">
                Close
            </button>
        </div>
    `;
    document.body.appendChild(dialog);
}

/**
 * Add a new memory fact.
 */
export async function addMemoryFact(fact) {
    if (!fact || !fact.trim()) return;

    try {
        const response = await API.addMemoryFact(fact, State.currentChatId);
        const currentMemory = State.userMemory || { facts: [], preferences: {} };
        State.setUserMemory({
            ...currentMemory,
            facts: [...currentMemory.facts, response.fact]
        });

        // Close and reopen dialog with updated data
        const dialog = document.querySelector('.modal-dialog');
        if (dialog) dialog.remove();
        await viewMemory();

        UI.showSuccess('Fact added to memory');
    } catch (error) {
        UI.showError('Failed to add fact: ' + error.message);
    }
}

/**
 * Delete a memory fact by index.
 */
export async function deleteMemoryFact(index) {
    try {
        await API.deleteMemoryFact(index);
        const currentMemory = State.userMemory || { facts: [], preferences: {} };
        State.setUserMemory({
            ...currentMemory,
            facts: currentMemory.facts.filter((_, i) => i !== index)
        });

        // Close and reopen dialog with updated data
        const dialog = document.querySelector('.modal-dialog');
        if (dialog) dialog.remove();
        await viewMemory();

        UI.showSuccess('Fact removed');
    } catch (error) {
        UI.showError('Failed to delete fact: ' + error.message);
    }
}

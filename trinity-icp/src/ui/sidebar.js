// sidebar.js - Sidebar rendering with chat list and auth buttons
// Responsible for rendering sidebar content and chat list

const Sidebar = {
    // Reference to DOM cache (will be set by UI module)
    elements: null,

    async renderSidebar(State) {
        const sidebarContent = document.getElementById('sidebarContent');
        if (!sidebarContent) return;

        console.log('🎨 renderSidebar() called - isAuthenticated:', State.isAuthenticated, 'allChats:', State.allChats.length);

        // Show/hide logout button in status header
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.style.display = State.isAuthenticated ? 'block' : 'none';
        }

        let html = '';

        // Auth section - simplified
        if (State.isAuthenticated) {
            html += `
                <div style="padding: 12px; border-bottom: 1px solid #3d3d3d;">
                    <button data-action="exportKey" class="rainbow-border-btn">
                        Export Key (Save This!)
                    </button>
                </div>
            `;
        } else {
            html += `
                <div style="padding: 12px; border-bottom: 1px solid #3d3d3d;">
                    <div style="color: #999; font-size: 12px; text-align: center; padding: 20px;">
                        Welcome to Trinity
                    </div>
                </div>
            `;
        }

        // New Chat button
        html += `
            <div style="padding: 12px; border-bottom: 1px solid #3d3d3d;">
                <button data-action="newChat" class="rainbow-border-btn">
                    + New Chat
                </button>
            </div>
        `;

        if (State.isAuthenticated) {
            // Chat list
            html += `<div style="padding: 12px;">`;
            html += `<div style="color: #999; font-size: 12px; margin-bottom: 8px; font-weight: 600;">YOUR CHATS</div>`;

            // Sort: pinned chats first, then by last updated
            const sortedChats = [...State.allChats]
                .sort((a, b) => {
                    // Pinned chats come first
                    const aPinned = a.pinned ? 1 : 0;
                    const bPinned = b.pinned ? 1 : 0;
                    if (bPinned !== aPinned) return bPinned - aPinned;
                    // Then by last updated
                    return b.lastUpdated - a.lastUpdated;
                });
            
            if (sortedChats.length > 0) {
                sortedChats.forEach(chat => {
                    const isPinned = chat.pinned ? true : false;
                    html += `
                        <div class="chat-item ${isPinned ? 'pinned' : ''}" data-chat-id="${chat.chatId}" style="position: relative; padding: 8px; margin-bottom: 4px; background: ${isPinned ? '#2a2d3a' : '#2d2d2d'}; border-radius: 6px; cursor: pointer; transition: background 0.2s; ${isPinned ? 'border-left: 2px solid #667eea;' : ''}">
                            <div data-action="loadChat" data-chat-id="${chat.chatId}">
                                <div style="font-size: 13px; color: white; margin-bottom: 2px;">${isPinned ? '<span style="font-size: 11px; margin-right: 4px; color: #4ade80;">★</span>' : ''}${chat.title || 'Untitled'}</div>
                                <div style="font-size: 10px; color: #888;">${new Date(chat.lastUpdated).toLocaleDateString()}</div>
                            </div>
                            <div class="chat-item-actions" style="display: none; position: absolute; top: 50%; right: 6px; transform: translateY(-50%); gap: 4px;">
                                <button class="chat-action-btn save-btn" data-action="pinChat" data-chat-id="${chat.chatId}" title="${isPinned ? 'Unsave' : 'Save'}" style="${isPinned ? 'color: #4ade80;' : ''}">
                                    ${isPinned ? '★' : '☆'}
                                </button>
                                <button class="chat-action-btn export-btn" data-action="exportChat" data-chat-id="${chat.chatId}" title="Export">
                                    ↓
                                </button>
                                <button class="chat-action-btn delete-btn" data-action="deleteChat" data-chat-id="${chat.chatId}" title="Delete">
                                    ×
                                </button>
                            </div>
                        </div>
                    `;
                });
            } else {
                html += `<div style="color: #666; font-size: 12px; text-align: center; padding: 20px;">No chats yet</div>`;
            }

            html += '</div>';
        }

        // Status footer (always visible when authenticated)
        if (State.isAuthenticated) {
            const chatCount = State.allChats?.length || 0;
            html += `
                <div class="status-footer" data-action="openStatus" style="padding: 10px 12px; border-top: 1px solid #3d3d3d; margin-top: auto; cursor: pointer; display: flex; justify-content: space-between; font-size: 11px; color: #888; transition: background 0.2s;" onmouseover="this.style.background='#2d2d2d'" onmouseout="this.style.background='transparent'">
                    <span>${chatCount}/20 chats</span>
                    <span>View Status</span>
                </div>
            `;
        }

        sidebarContent.innerHTML = html;
    }
};

export default Sidebar;

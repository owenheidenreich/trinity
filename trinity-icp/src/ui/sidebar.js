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

            // Sort all chats by last updated
            const sortedChats = [...State.allChats]
                .sort((a, b) => b.lastUpdated - a.lastUpdated);
            
            if (sortedChats.length > 0) {
                sortedChats.forEach(chat => {
                    html += `
                        <div class="chat-item" data-chat-id="${chat.chatId}" style="position: relative; padding: 8px; margin-bottom: 4px; background: #2d2d2d; border-radius: 6px; cursor: pointer; transition: background 0.2s;">
                            <div data-action="loadChat" data-chat-id="${chat.chatId}">
                                <div style="font-size: 13px; color: white; margin-bottom: 2px;">${chat.title || 'Untitled'}</div>
                                <div style="font-size: 10px; color: #888;">${new Date(chat.lastUpdated).toLocaleDateString()}</div>
                            </div>
                            <button class="delete-btn" data-action="deleteChat" data-chat-id="${chat.chatId}" style="display: none; position: absolute; top: 6px; right: 6px; background: #dc2626; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 10px; font-weight: 600;">
                                Delete
                            </button>
                        </div>
                    `;
                });
            } else {
                html += `<div style="color: #666; font-size: 12px; text-align: center; padding: 20px;">No chats yet</div>`;
            }

            html += '</div>';
        }

        sidebarContent.innerHTML = html;
    }
};

export default Sidebar;

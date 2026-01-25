// sidebar.js - Sidebar rendering with chat list and auth buttons
// Responsible for rendering sidebar content, chat list, and archived chats

const Sidebar = {
    // Reference to DOM cache (will be set by UI module)
    elements: null,

    async renderSidebar(State) {
        const sidebarContent = document.getElementById('sidebarContent');
        if (!sidebarContent) return;

        console.log('🎨 renderSidebar() called - isAuthenticated:', State.isAuthenticated, 'allChats:', State.allChats.length);

        let html = '';

        // Auth buttons
        if (State.isAuthenticated) {
            html += `
                <div style="padding: 12px; border-bottom: 1px solid #3d3d3d;">
                    <div style="font-size: 10px; color: #4CAF50; margin-bottom: 8px; word-break: break-all; line-height: 1.4; font-family: monospace;">
                        ✅ ${State.principal}
                    </div>
                    <button data-action="viewMemory" class="rainbow-border-btn" style="margin-bottom: 6px;">
                        Memory (${State.userMemory?.facts?.length || 0})
                    </button>
                    <button data-action="exportKey" class="rainbow-border-btn" style="margin-bottom: 6px;">
                        Export Key
                    </button>
                    <button data-action="logout" class="rainbow-border-btn">
                        Logout
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

            // Filter active (non-archived) chats
            const sortedChats = [...State.allChats]
                .filter(chat => !chat.isArchived)
                .sort((a, b) => b.lastUpdated - a.lastUpdated);
            
            if (sortedChats.length > 0) {
                sortedChats.forEach(chat => {
                    html += `
                        <div class="chat-item" data-chat-id="${chat.chatId}" style="position: relative; padding: 8px; margin-bottom: 4px; background: #2d2d2d; border-radius: 6px; cursor: pointer; transition: background 0.2s;">
                            <div data-action="loadChat" data-chat-id="${chat.chatId}">
                                <div style="font-size: 13px; color: white; margin-bottom: 2px;">${chat.title || 'Untitled'}</div>
                                <div style="font-size: 10px; color: #888;">${new Date(chat.lastUpdated).toLocaleDateString()}</div>
                            </div>
                            <button class="archive-btn" data-action="archiveChat" data-chat-id="${chat.chatId}" style="display: none; position: absolute; top: 6px; right: 6px; background: #9333ea; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 10px; font-weight: 600;">
                                Archive
                            </button>
                        </div>
                    `;
                });
            } else {
                html += `<div style="color: #666; font-size: 12px; text-align: center; padding: 20px;">No chats yet</div>`;
            }

            // Archived chats section
            const archivedChats = [...State.allChats]
                .filter(chat => chat.isArchived)
                .sort((a, b) => b.archivedAt - a.archivedAt);
            
            if (archivedChats.length > 0) {
                html += `<div style="color: #9c27b0; font-size: 12px; margin: 20px 0 8px 0; font-weight: 600; border-top: 1px solid #3d3d3d; padding-top: 12px;">ARCHIVED CHATS (${archivedChats.length}/10)</div>`;
                archivedChats.forEach(chat => {
                    html += `
                        <div class="chat-item archived" data-action="loadChat" data-chat-id="${chat.chatId}" style="position: relative; padding: 8px; margin-bottom: 4px; background: #2d2d2d; border-radius: 6px; cursor: pointer; transition: background 0.2s; border-left: 3px solid #9c27b0;">
                            <div style="font-size: 13px; color: #bbb; margin-bottom: 2px;">${chat.title || 'Untitled'}</div>
                            <div style="font-size: 10px; color: #888;">Archived ${new Date(chat.archivedAt).toLocaleDateString()}</div>
                        </div>
                    `;
                });
            }

            html += '</div>';
        }

        sidebarContent.innerHTML = html;
    }
};

export default Sidebar;

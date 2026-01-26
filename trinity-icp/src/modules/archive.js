// ============================================================================
// Trinity Frontend - Archive Module
// ============================================================================
// Archive functionality for Filecoin permanent storage
// - Individual chat archiving with immediate Pinata upload
// - Master bundle system (one CID = access to all archives)
// - Auto-recovery on login via principal ID
// ============================================================================

export const Archive = {
    async initiateArchive(chatId) {
        // Access globals
        const { State, API, UI, Actions } = window;

        const confirmed = await UI.showConfirmDialog(
            'Archive this chat to Filecoin?',
            'Your chat will be permanently stored on Filecoin/IPFS and can be recovered on any device using your principal ID. Limit: 10 archived chats max.'
        );

        if (!confirmed) return;

        try {
            UI.setLoading(true, State);
            const response = await API.archiveChat(chatId);

            if (response.success) {
                console.log('✅ Chat archived to Filecoin:', chatId, 'CID:', response.cid);

                // Show success with CID info - include clickable IPFS link
                const shortCid = response.cid ? response.cid.slice(0, 12) + '...' : 'unknown';
                const ipfsUrl = response.cid ? `https://gateway.lighthouse.storage/ipfs/${response.cid}` : null;
                
                // Show detailed success notification
                UI.showSuccess(
                    `Archived to Filecoin! (${response.archivedCount}/10)\n` +
                    `CID: ${shortCid}`,
                    { 
                        duration: 8000,
                        link: ipfsUrl,
                        linkText: 'View on IPFS'
                    }
                );

                // If this was the active chat, start a new chat
                if (State.currentChatId === chatId) {
                    await Actions.loadChats();
                    Actions.newChat();
                } else {
                    await Actions.loadChats();
                }
            }
        } catch (error) {
            console.error('❌ Archive failed:', error);

            // Handle specific errors
            if (error.message && error.message.includes('Maximum 10')) {
                UI.showError('Archive limit reached: You can only have 10 archived chats. Please delete an archived chat first.');
            } else if (error.message && error.message.includes('API key')) {
                UI.showError('Filecoin not configured on backend. Contact administrator.');
            } else {
                UI.showError('Failed to archive chat: ' + error.message);
            }
        } finally {
            UI.setLoading(false, State);
        }
    },

    // Download and view a specific archived chat by CID
    async viewArchivedChat(cid, chatId) {
        const { API, UI, State, Actions } = window;

        try {
            UI.setLoading(true, State);
            console.log('📥 Downloading archived chat:', cid);

            const response = await API.getArchivedChat(cid);

            if (response.success && response.chat) {
                // Load the recovered chat into the current view
                const chat = response.chat;
                State.setChatHistory(chat.messages || []);
                State.setCurrentChatId(chat.chatId);

                // Render the chat
                UI.clearMessages();
                for (const msg of chat.messages || []) {
                    UI.showMessage(msg.role, msg.content, false);
                }

                console.log('✅ Archived chat loaded:', chatId);
            }
        } catch (error) {
            console.error('❌ Failed to load archived chat:', error);
            UI.showError('Failed to load archived chat: ' + error.message);
        } finally {
            UI.setLoading(false, State);
        }
    }
};

export default Archive;

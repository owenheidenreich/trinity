// ============================================================================
// Trinity Frontend - Archive Module
// ============================================================================
// Archive functionality for IPFS permanent storage
// - Individual chat archiving (marks chat as permanent)
// - Recovery on login via principal ID
// Learn more: https://docs.ipfs.tech/concepts/what-is-ipfs/
// ============================================================================

export const Archive = {
    async initiateArchive(chatId) {
        // Access globals
        const { State, API, UI, Actions } = window;

        const confirmed = await UI.showConfirmDialog(
            'Archive this chat to IPFS?',
            'Your chat will be permanently stored on IPFS (InterPlanetary File System) and can be recovered on any device using your principal ID. Limit: 10 archived chats max.'
        );

        if (!confirmed) return;

        try {
            UI.setLoading(true, State);
            const response = await API.archiveChat(chatId);

            if (response.success) {
                console.log('✅ Chat archived to IPFS:', chatId, 'CID:', response.cid);
                console.log(`🔗 Verify: https://gateway.lighthouse.storage/ipfs/${response.cid}`);

                // Show success notification with shortened CID
                const shortCid = response.cid.substring(0, 12) + '...' + response.cid.slice(-6);
                UI.showSuccess(`Archived! CID: ${shortCid} (${response.archivedCount}/10)`);

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
                UI.showError('IPFS storage not configured on backend. Contact administrator.');
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

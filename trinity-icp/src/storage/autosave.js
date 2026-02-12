/**
 * Autosave Module
 * Handles automatic chat persistence with debouncing and retry logic
 * 
 * Features:
 * - LOCAL-FIRST: Saves to IndexedDB immediately, then syncs to cloud
 * - Debounced saves (2s delay to batch rapid changes)
 * - Exponential backoff retry (up to 5 attempts)
 * - Pending sync queue for offline resilience
 */

import IndexedDBStorage from './indexedDB.js';

const AutosaveManager = {
    // Configuration
    timeoutId: null,
    pendingData: null,
    executeCallback: null,
    retryCount: 0,
    MAX_RETRIES: 5,
    DEBOUNCE_INTERVAL_MS: 2000,
    RETRY_INTERVAL_MS: 1000,
    RETRY_BACKOFF_MULTIPLIER: 2,
    MAX_RETRY_INTERVAL_MS: 60000,
    
    // Callback for reloading chats after successful save
    // Set by app.js to avoid circular dependency with Actions
    onSaveSuccess: null,

    /**
     * Schedule an autosave with debouncing
     * @param {Object} chatData - Chat data to save
     * @param {string} currentChatId - Current chat ID
     * @param {boolean} isAuthenticated - Whether user is authenticated
     * @param {Function} showIndicator - UI callback to show save indicator
     * @param {Function} executeCallback - Callback to execute autosave (breaks circular dependency)
     * @returns {boolean} Whether autosave was scheduled
     */
    scheduleAutosave(chatData, currentChatId, isAuthenticated, showIndicator, executeCallback) {
        if (!isAuthenticated) {
            console.log('⏭️ Autosave skipped - user not authenticated');
            return false;
        }

        console.log('📅 Autosave scheduled:', {
            chatId: currentChatId,
            messageCount: chatData?.messages?.length || 0,
            hasData: !!chatData
        });

        // Cancel pending timeout
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
        }

        // Store latest data and callback
        this.pendingData = chatData || {};
        this.executeCallback = executeCallback;

        // Schedule new save
        this.timeoutId = setTimeout(() => {
            if (this.executeCallback) {
                this.executeCallback();
            }
        }, this.DEBOUNCE_INTERVAL_MS);

        // Show indicator
        if (showIndicator) {
            showIndicator('saving');
        }
        
        return true;
    },

    /**
     * Execute the autosave operation
     * @param {Object} options - Options for autosave
     * @param {string} options.currentChatId - Current chat ID
     * @param {Array} options.chatHistory - Current chat history
     * @param {boolean} options.isAuthenticated - Authentication status
     * @param {boolean} options.testMode - Whether in test mode
     * @param {string} options.principal - User principal (for logging)
     * @param {Function} options.apiSave - API save function
     * @param {Function} options.mockSave - Mock storage save function
     * @param {Function} options.showIndicator - UI callback to show indicator
     * @param {Function} options.hideIndicator - UI callback to hide indicator
     * @param {Function} options.retryCallback - Function to call if retry is needed
     * @returns {Object} Result object {success, error}
     */
    async executeAutosave(options) {
        const {
            currentChatId,
            chatHistory,
            isAuthenticated,
            testMode,
            principal,
            apiSave,
            mockSave,
            showIndicator,
            hideIndicator,
            retryCallback
        } = options;
        
        if (!this.pendingData) {
            console.log('⏭️ Autosave skipped - no pending data');
            return { success: false, error: 'No pending data' };
        }

        console.log('💾 Executing autosave...', {
            chatId: currentChatId,
            messageCount: chatHistory?.length || 0,
            isAuthenticated,
            testMode
        });

        try {
            if (showIndicator) {
                showIndicator('saving');
            }
            
            // STEP 1: Save locally FIRST (instant, reliable)
            try {
                await IndexedDBStorage.saveChat(
                    currentChatId,
                    {
                        messages: chatHistory,
                        metadata: { title: this.generateChatTitle(), timestamp: Date.now() }
                    },
                    principal
                );
            } catch (localError) {
                console.warn('⚠️ IndexedDB save failed (continuing to cloud):', localError.message);
            }
            
            // STEP 2: Attempt cloud sync
            let response;
            if (testMode && mockSave) {
                // Use mock storage for test mode
                response = mockSave(currentChatId, {
                    ...this.pendingData,
                    title: this.generateChatTitle(),
                    timestamp: Date.now()
                });
            } else if (apiSave) {
                // Use real API for production
                response = await apiSave(this.pendingData);
            } else {
                throw new Error('No save function provided');
            }

            console.log('💾 Autosave response:', response);

            if (response.success) {
                console.log('✅ Chat autosaved successfully:', currentChatId);
                
                // STEP 3: Mark as synced (remove from pending queue)
                try {
                    await IndexedDBStorage.markSynced(currentChatId);
                } catch (syncError) {
                    console.warn('⚠️ Could not mark as synced:', syncError.message);
                }
                
                // Reset state
                this.retryCount = 0;
                this.pendingData = null;
                
                // Call success callback to reload chats
                if (this.onSaveSuccess) {
                    console.log('🔄 Reloading chat list after successful autosave...');
                    await this.onSaveSuccess();
                    console.log('✅ Chat list reloaded');
                }
                
                if (hideIndicator) {
                    hideIndicator();
                }
                
                return {
                    success: true,
                    autosaveStatus: 'idle',
                    unsavedChanges: false,
                    lastActivityTime: Date.now()
                };
            } else {
                console.error('❌ Autosave returned success=false:', response);
                throw new Error(response.error || 'Unknown error');
            }
        } catch (error) {
            console.error('❌ Autosave exception:', {
                message: error.message,
                stack: error.stack,
                chatId: currentChatId
            });
            
            return await this.handleAutosaveError(error, showIndicator, retryCallback);
        }
    },

    /**
     * Handle autosave errors with retry logic
     * @param {Error} error - The error that occurred
     * @param {Function} showIndicator - UI callback to show error indicator
     * @param {Function} retryCallback - Function to call after delay for retry
     * @returns {Object} Result object {success: false, error, autosaveStatus, shouldRetry}
     */
    async handleAutosaveError(error, showIndicator, retryCallback) {
        this.retryCount++;

        // Parse structured error message if available
        let userMessage = error.message;
        try {
            const parsed = JSON.parse(error.message.replace(/^HTTP \d+: /, ''));
            if (parsed?.error?.message) {
                userMessage = parsed.error.message;
            }
        } catch { /* use original message */ }

        if (this.retryCount <= this.MAX_RETRIES) {
            const delay = Math.min(
                this.RETRY_INTERVAL_MS * Math.pow(this.RETRY_BACKOFF_MULTIPLIER, this.retryCount - 1),
                this.MAX_RETRY_INTERVAL_MS
            );

            console.warn(`⚠️ Autosave retry ${this.retryCount}/${this.MAX_RETRIES} in ${delay}ms`);
            
            if (showIndicator) {
                showIndicator('error');
            }

            // Show user-facing notification on first retry
            if (this.retryCount === 1 && typeof window !== 'undefined') {
                // Dispatch event for notifications module to catch
                window.dispatchEvent(new CustomEvent('autosave-error', {
                    detail: { message: userMessage, retryCount: this.retryCount, delay }
                }));
            }

            // Schedule retry with callback
            if (retryCallback) {
                setTimeout(() => retryCallback(), delay);
            }
            
            return {
                success: false,
                error: error.message,
                autosaveStatus: 'error',
                shouldRetry: true,
                retryDelay: delay,
                retryCount: this.retryCount
            };
        } else {
            console.error('❌ Autosave failed after max retries - queued for sync');
            
            if (showIndicator) {
                showIndicator('error');
            }

            // Notify user that save failed but data is preserved locally
            if (typeof window !== 'undefined') {
                window.dispatchEvent(new CustomEvent('autosave-error', {
                    detail: {
                        message: 'Save failed after multiple retries. Your chat is saved locally and will sync when connection is restored.',
                        final: true
                    }
                }));
            }
            
            // Queue for sync retry when back online
            try {
                await IndexedDBStorage.queueForSync(this.pendingData?.chatId, this.pendingData);
            } catch (queueError) {
                console.warn('⚠️ Could not queue for sync:', queueError.message);
            }
            
            return {
                success: false,
                error: error.message,
                autosaveStatus: 'error',
                shouldRetry: false,
                maxRetriesExceeded: true,
                queuedForSync: true
            };
        }
    },

    /**
     * Generate a chat title from the first message
     * @returns {string} Generated title
     */
    generateChatTitle() {
        if (this.pendingData?.messages && this.pendingData.messages.length > 0) {
            const firstMessage = this.pendingData.messages[0];
            let title = firstMessage.content || 'Untitled Chat';
            if (title.length > 50) {
                title = title.substring(0, 50) + '...';
            }
            return title;
        }
        return 'Untitled Chat';
    },

    /**
     * Retry syncing any pending chats (called on app load after auth)
     * @param {Function} apiSave - API save function
     * @returns {Promise<{synced: number, failed: number}>}
     */
    async retryPendingSync(apiSave) {
        if (!apiSave) {
            console.warn('⚠️ No API save function provided for sync retry');
            return { synced: 0, failed: 0 };
        }

        const pending = await IndexedDBStorage.getPendingSync();
        
        if (pending.length === 0) {
            console.log('✅ No pending syncs');
            return { synced: 0, failed: 0 };
        }

        console.log(`🔄 Retrying ${pending.length} pending sync(s)...`);
        
        let synced = 0;
        let failed = 0;

        for (const item of pending) {
            // Skip items with too many attempts
            if (item.attempts >= 10) {
                console.warn(`⏭️ Skipping ${item.chatId.slice(0, 8)}... - too many attempts`);
                failed++;
                continue;
            }

            try {
                const response = await apiSave(item.chatData);
                
                if (response.success) {
                    await IndexedDBStorage.markSynced(item.chatId);
                    console.log(`✅ Synced: ${item.chatId.slice(0, 8)}...`);
                    synced++;
                } else {
                    console.warn(`❌ Sync failed: ${item.chatId.slice(0, 8)}...`);
                    failed++;
                }
            } catch (error) {
                console.error(`❌ Sync error: ${item.chatId.slice(0, 8)}...`, error.message);
                failed++;
            }
        }

        console.log(`🔄 Sync complete: ${synced} synced, ${failed} failed`);
        return { synced, failed };
    }
};

export default AutosaveManager;

/**
 * Autosave Module
 * Handles automatic chat persistence with debouncing and retry logic
 * 
 * Features:
 * - Debounced saves (2s delay to batch rapid changes)
 * - Exponential backoff retry (up to 5 attempts)
 * - State mutation avoided (returns result objects)
 * - Dependency injection for chat reloading
 */

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
            testMode,
            principal: principal?.substring(0, 20)
        });

        try {
            if (showIndicator) {
                showIndicator('saving');
            }
            
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
            
            return this.handleAutosaveError(error, showIndicator, retryCallback);
        }
    },

    /**
     * Handle autosave errors with retry logic
     * @param {Error} error - The error that occurred
     * @param {Function} showIndicator - UI callback to show error indicator
     * @param {Function} retryCallback - Function to call after delay for retry
     * @returns {Object} Result object {success: false, error, autosaveStatus, shouldRetry}
     */
    handleAutosaveError(error, showIndicator, retryCallback) {
        this.retryCount++;

        if (this.retryCount <= this.MAX_RETRIES) {
            const delay = Math.min(
                this.RETRY_INTERVAL_MS * Math.pow(this.RETRY_BACKOFF_MULTIPLIER, this.retryCount - 1),
                this.MAX_RETRY_INTERVAL_MS
            );

            console.warn(`⚠️ Autosave retry ${this.retryCount}/${this.MAX_RETRIES} in ${delay}ms`);
            
            if (showIndicator) {
                showIndicator('error');
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
            console.error('❌ Autosave failed after max retries - storing offline');
            
            if (showIndicator) {
                showIndicator('error');
            }
            
            // TODO: Store in IndexedDB for sync when online
            
            return {
                success: false,
                error: error.message,
                autosaveStatus: 'error',
                shouldRetry: false,
                maxRetriesExceeded: true
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
    }
};

export default AutosaveManager;

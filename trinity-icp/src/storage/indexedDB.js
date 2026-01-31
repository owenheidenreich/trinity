// ============================================================================
// Trinity Frontend - IndexedDB Storage Module
// ============================================================================
// Local-first persistence layer for offline resilience
// Saves chats locally FIRST, then syncs to cloud
// ============================================================================

const DB_NAME = 'TrinityChats';
const DB_VERSION = 1;
const STORES = {
    CHATS: 'chats',
    PENDING_SYNC: 'pendingSync'
};

let dbInstance = null;

/**
 * IndexedDB Storage for local-first chat persistence
 */
export const IndexedDBStorage = {
    /**
     * Initialize IndexedDB connection
     * @returns {Promise<IDBDatabase>}
     */
    async init() {
        if (dbInstance) return dbInstance;

        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onerror = () => {
                console.error('❌ IndexedDB open failed:', request.error);
                reject(request.error);
            };

            request.onsuccess = () => {
                dbInstance = request.result;
                console.log('🗄️ IndexedDB initialized');
                resolve(dbInstance);
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                // Main chat store
                if (!db.objectStoreNames.contains(STORES.CHATS)) {
                    const chatStore = db.createObjectStore(STORES.CHATS, { keyPath: 'chatId' });
                    chatStore.createIndex('principal', 'principal', { unique: false });
                    chatStore.createIndex('lastUpdated', 'lastUpdated', { unique: false });
                }

                // Pending sync queue
                if (!db.objectStoreNames.contains(STORES.PENDING_SYNC)) {
                    const syncStore = db.createObjectStore(STORES.PENDING_SYNC, { keyPath: 'chatId' });
                    syncStore.createIndex('timestamp', 'timestamp', { unique: false });
                }

                console.log('🗄️ IndexedDB schema created');
            };
        });
    },

    /**
     * Save chat locally (called BEFORE cloud sync)
     * @param {string} chatId
     * @param {Object} chatData - { messages, metadata }
     * @param {string} principal - User's principal ID
     * @returns {Promise<boolean>}
     */
    async saveChat(chatId, chatData, principal) {
        try {
            const db = await this.init();

            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORES.CHATS, 'readwrite');
                const store = tx.objectStore(STORES.CHATS);

                const record = {
                    chatId,
                    messages: chatData.messages || [],
                    metadata: {
                        ...chatData.metadata,
                        updatedAt: Date.now()
                    },
                    principal,
                    lastUpdated: Date.now()
                };

                store.put(record);

                tx.oncomplete = () => {
                    console.log('💾 Saved to IndexedDB:', chatId.slice(0, 8) + '...');
                    resolve(true);
                };

                tx.onerror = () => {
                    console.error('❌ IndexedDB save failed:', tx.error);
                    reject(tx.error);
                };
            });
        } catch (error) {
            console.error('❌ IndexedDB saveChat error:', error);
            return false;
        }
    },

    /**
     * Queue chat for sync retry (when cloud save fails)
     * @param {string} chatId
     * @param {Object} chatData
     * @returns {Promise<boolean>}
     */
    async queueForSync(chatId, chatData) {
        try {
            const db = await this.init();

            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORES.PENDING_SYNC, 'readwrite');
                const store = tx.objectStore(STORES.PENDING_SYNC);

                store.put({
                    chatId,
                    chatData,
                    timestamp: Date.now(),
                    attempts: 0
                });

                tx.oncomplete = () => {
                    console.log('📤 Queued for sync:', chatId.slice(0, 8) + '...');
                    resolve(true);
                };

                tx.onerror = () => reject(tx.error);
            });
        } catch (error) {
            console.error('❌ IndexedDB queueForSync error:', error);
            return false;
        }
    },

    /**
     * Mark chat as synced (remove from pending queue)
     * @param {string} chatId
     * @returns {Promise<boolean>}
     */
    async markSynced(chatId) {
        try {
            const db = await this.init();

            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORES.PENDING_SYNC, 'readwrite');
                tx.objectStore(STORES.PENDING_SYNC).delete(chatId);

                tx.oncomplete = () => resolve(true);
                tx.onerror = () => reject(tx.error);
            });
        } catch (error) {
            console.error('❌ IndexedDB markSynced error:', error);
            return false;
        }
    },

    /**
     * Get all pending sync items
     * @returns {Promise<Array<{chatId, chatData, timestamp, attempts}>>}
     */
    async getPendingSync() {
        try {
            const db = await this.init();

            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORES.PENDING_SYNC, 'readonly');
                const request = tx.objectStore(STORES.PENDING_SYNC).getAll();

                request.onsuccess = () => resolve(request.result || []);
                request.onerror = () => reject(request.error);
            });
        } catch (error) {
            console.error('❌ IndexedDB getPendingSync error:', error);
            return [];
        }
    },

    /**
     * Load chat from local storage
     * @param {string} chatId
     * @returns {Promise<Object|null>}
     */
    async loadChat(chatId) {
        try {
            const db = await this.init();

            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORES.CHATS, 'readonly');
                const request = tx.objectStore(STORES.CHATS).get(chatId);

                request.onsuccess = () => resolve(request.result || null);
                request.onerror = () => reject(request.error);
            });
        } catch (error) {
            console.error('❌ IndexedDB loadChat error:', error);
            return null;
        }
    },

    /**
     * List all local chats for a principal
     * @param {string} principal
     * @returns {Promise<Array>}
     */
    async listChats(principal) {
        try {
            const db = await this.init();

            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORES.CHATS, 'readonly');
                const index = tx.objectStore(STORES.CHATS).index('principal');
                const request = index.getAll(principal);

                request.onsuccess = () => {
                    const chats = request.result || [];
                    // Sort by lastUpdated descending
                    chats.sort((a, b) => b.lastUpdated - a.lastUpdated);
                    resolve(chats);
                };
                request.onerror = () => reject(request.error);
            });
        } catch (error) {
            console.error('❌ IndexedDB listChats error:', error);
            return [];
        }
    },

    /**
     * Delete chat from local storage
     * @param {string} chatId
     * @returns {Promise<boolean>}
     */
    async deleteChat(chatId) {
        try {
            const db = await this.init();

            return new Promise((resolve, reject) => {
                const tx = db.transaction([STORES.CHATS, STORES.PENDING_SYNC], 'readwrite');
                tx.objectStore(STORES.CHATS).delete(chatId);
                tx.objectStore(STORES.PENDING_SYNC).delete(chatId);

                tx.oncomplete = () => resolve(true);
                tx.onerror = () => reject(tx.error);
            });
        } catch (error) {
            console.error('❌ IndexedDB deleteChat error:', error);
            return false;
        }
    },

    /**
     * Clear all data (for logout)
     * @returns {Promise<boolean>}
     */
    async clearAll() {
        try {
            const db = await this.init();

            return new Promise((resolve, reject) => {
                const tx = db.transaction([STORES.CHATS, STORES.PENDING_SYNC], 'readwrite');
                tx.objectStore(STORES.CHATS).clear();
                tx.objectStore(STORES.PENDING_SYNC).clear();

                tx.oncomplete = () => {
                    console.log('🗄️ IndexedDB cleared');
                    resolve(true);
                };
                tx.onerror = () => reject(tx.error);
            });
        } catch (error) {
            console.error('❌ IndexedDB clearAll error:', error);
            return false;
        }
    }
};

export default IndexedDBStorage;

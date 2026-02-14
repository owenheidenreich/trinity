/**
 * IndexedDB storage — local-first persistence.
 * Ported from storage/indexedDB.js with types.
 */
import Logger from './logger';
import type { ChatMessage } from '../types';

const DB_NAME = 'TrinityChats';
const DB_VERSION = 1;
const STORE_CHATS = 'chats';
const STORE_PENDING = 'pendingSync';

let dbInstance: IDBDatabase | null = null;

interface ChatRecord {
  chatId: string;
  principal: string;
  title: string;
  messages: ChatMessage[];
  metadata: Record<string, unknown>;
  lastUpdated: number;
}

interface PendingSyncRecord {
  chatId: string;
  data: Record<string, unknown>;
  timestamp: number;
  attempts: number;
}

async function getDB(): Promise<IDBDatabase> {
  if (dbInstance) return dbInstance;

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;

      if (!db.objectStoreNames.contains(STORE_CHATS)) {
        const chatStore = db.createObjectStore(STORE_CHATS, { keyPath: 'chatId' });
        chatStore.createIndex('principal', 'principal', { unique: false });
        chatStore.createIndex('lastUpdated', 'lastUpdated', { unique: false });
      }

      if (!db.objectStoreNames.contains(STORE_PENDING)) {
        const pendingStore = db.createObjectStore(STORE_PENDING, { keyPath: 'chatId' });
        pendingStore.createIndex('timestamp', 'timestamp', { unique: false });
      }
    };

    request.onsuccess = (event) => {
      dbInstance = (event.target as IDBOpenDBRequest).result;
      resolve(dbInstance);
    };

    request.onerror = () => reject(request.error);
  });
}

function txStore(
  db: IDBDatabase,
  storeName: string,
  mode: IDBTransactionMode
): IDBObjectStore {
  return db.transaction(storeName, mode).objectStore(storeName);
}

function wrapRequest<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export const IndexedDBStorage = {
  async init(): Promise<IDBDatabase> {
    return getDB();
  },

  async saveChat(
    chatId: string,
    chatData: Omit<ChatRecord, 'chatId' | 'lastUpdated'>,
    principal: string
  ): Promise<boolean> {
    try {
      const db = await getDB();
      const store = txStore(db, STORE_CHATS, 'readwrite');
      await wrapRequest(
        store.put({ ...chatData, chatId, principal, lastUpdated: Date.now() })
      );
      return true;
    } catch (err) {
      Logger.error('IndexedDB saveChat failed:', err);
      return false;
    }
  },

  async queueForSync(
    chatId: string,
    chatData: Record<string, unknown>
  ): Promise<boolean> {
    try {
      const db = await getDB();
      const store = txStore(db, STORE_PENDING, 'readwrite');
      await wrapRequest(
        store.put({
          chatId,
          data: chatData,
          timestamp: Date.now(),
          attempts: 0,
        } satisfies PendingSyncRecord)
      );
      return true;
    } catch (err) {
      Logger.error('IndexedDB queueForSync failed:', err);
      return false;
    }
  },

  async markSynced(chatId: string): Promise<boolean> {
    try {
      const db = await getDB();
      const store = txStore(db, STORE_PENDING, 'readwrite');
      await wrapRequest(store.delete(chatId));
      return true;
    } catch (err) {
      Logger.error('IndexedDB markSynced failed:', err);
      return false;
    }
  },

  async getPendingSync(): Promise<PendingSyncRecord[]> {
    try {
      const db = await getDB();
      const store = txStore(db, STORE_PENDING, 'readonly');
      return wrapRequest(store.getAll());
    } catch (err) {
      Logger.error('IndexedDB getPendingSync failed:', err);
      return [];
    }
  },

  async loadChat(chatId: string): Promise<ChatRecord | null> {
    try {
      const db = await getDB();
      const store = txStore(db, STORE_CHATS, 'readonly');
      const result = await wrapRequest(store.get(chatId));
      return (result as ChatRecord) ?? null;
    } catch (err) {
      Logger.error('IndexedDB loadChat failed:', err);
      return null;
    }
  },

  async listChats(principal: string): Promise<ChatRecord[]> {
    try {
      const db = await getDB();
      const store = txStore(db, STORE_CHATS, 'readonly');
      const index = store.index('principal');
      const results = await wrapRequest(index.getAll(principal));
      return (results as ChatRecord[]).sort(
        (a, b) => b.lastUpdated - a.lastUpdated
      );
    } catch (err) {
      Logger.error('IndexedDB listChats failed:', err);
      return [];
    }
  },

  async deleteChat(chatId: string): Promise<boolean> {
    try {
      const db = await getDB();
      const tx = db.transaction([STORE_CHATS, STORE_PENDING], 'readwrite');
      tx.objectStore(STORE_CHATS).delete(chatId);
      tx.objectStore(STORE_PENDING).delete(chatId);
      return new Promise((resolve, reject) => {
        tx.oncomplete = () => resolve(true);
        tx.onerror = () => reject(tx.error);
      });
    } catch (err) {
      Logger.error('IndexedDB deleteChat failed:', err);
      return false;
    }
  },

  async clearAll(): Promise<boolean> {
    try {
      const db = await getDB();
      const tx = db.transaction([STORE_CHATS, STORE_PENDING], 'readwrite');
      tx.objectStore(STORE_CHATS).clear();
      tx.objectStore(STORE_PENDING).clear();
      return new Promise((resolve, reject) => {
        tx.oncomplete = () => resolve(true);
        tx.onerror = () => reject(tx.error);
      });
    } catch (err) {
      Logger.error('IndexedDB clearAll failed:', err);
      return false;
    }
  },
} as const;

export default IndexedDBStorage;

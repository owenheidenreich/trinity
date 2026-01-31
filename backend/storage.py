"""
Trinity Backend - File Storage Module
User directory, metadata, and memory management
"""

import json
import time
import logging
from pathlib import Path
from typing import Dict

from config import CHATS_DIR

logger = logging.getLogger(__name__)


def get_user_dir(principal_id: str) -> Path:
    """Get user's chat directory"""
    user_dir = Path(CHATS_DIR) / principal_id
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_metadata_path(principal_id: str) -> Path:
    """Get metadata file path for user"""
    return get_user_dir(principal_id) / 'metadata.json'


def get_user_memory_path(principal_id: str) -> Path:
    """Get user memory file path"""
    return get_user_dir(principal_id) / 'user_memory.json'


def load_user_memory(principal_id: str) -> Dict:
    """Load user's persistent memory"""
    path = get_user_memory_path(principal_id)
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return {
        'principalId': principal_id,
        'version': '1.0',
        'facts': [],
        'preferences': {},
        'createdAt': int(time.time() * 1000),
        'lastUpdated': int(time.time() * 1000)
    }


def save_user_memory(principal_id: str, memory: Dict):
    """Save user's persistent memory"""
    memory['lastUpdated'] = int(time.time() * 1000)
    with open(get_user_memory_path(principal_id), 'w') as f:
        json.dump(memory, f, indent=2)


def load_metadata(principal_id: str) -> Dict:
    """Load user's metadata"""
    path = get_metadata_path(principal_id)
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return {
        'principalId': principal_id,
        'version': '1.0',
        'chats': [],
        'createdAt': int(time.time() * 1000),
        'lastLogin': int(time.time() * 1000),
        'currentBundleCID': None,
        'lastBundleVersion': 0,
        'lastSyncedAt': None
    }


def save_metadata(principal_id: str, metadata: Dict):
    """Save user's metadata"""
    metadata['lastLogin'] = int(time.time() * 1000)
    with open(get_metadata_path(principal_id), 'w') as f:
        json.dump(metadata, f, indent=2)

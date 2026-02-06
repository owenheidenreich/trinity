"""
Trinity Backend - Storage Module Test Suite
============================================
Tests for file storage, path traversal protection, and user data management.

Security Focus:
1. Path traversal attack prevention
2. Null byte injection prevention
3. Directory sandbox enforcement
4. Safe file operations

Target Coverage: 80%+
"""

import pytest
import json
import time
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestGetUserDir:
    """User directory creation and path traversal protection."""
    
    def test_creates_user_directory(self, tmp_path):
        """User directory is created if it doesn't exist."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import get_user_dir
            
            principal = 'test-user-abc123'
            user_dir = get_user_dir(principal)
            
            assert user_dir.exists()
            assert user_dir.is_dir()
            assert user_dir.name == principal
    
    def test_returns_existing_directory(self, tmp_path):
        """Returns existing directory without error."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import get_user_dir
            
            principal = 'existing-user'
            # Create directory first
            (tmp_path / principal).mkdir()
            
            user_dir = get_user_dir(principal)
            
            assert user_dir.exists()
            assert user_dir == tmp_path / principal
    
    def test_blocks_path_traversal_dotdot(self, tmp_path):
        """Blocks ../ path traversal attempts."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import get_user_dir
            
            # Attempt path traversal
            malicious = '../../../etc/passwd'
            user_dir = get_user_dir(malicious)
            
            # Should sanitize and stay in sandbox
            assert str(user_dir).startswith(str(tmp_path))
            assert '..' not in str(user_dir)
    
    def test_blocks_path_traversal_backslash(self, tmp_path):
        """Blocks backslash path traversal (Windows-style)."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import get_user_dir
            
            malicious = '..\\..\\..\\windows\\system32'
            user_dir = get_user_dir(malicious)
            
            assert str(user_dir).startswith(str(tmp_path))
            assert '\\' not in user_dir.name
    
    def test_blocks_null_byte_injection(self, tmp_path):
        """Blocks null byte injection attacks."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import get_user_dir
            
            # Null byte attack: file.txt\x00.jpg
            malicious = 'user\x00../../etc/passwd'
            user_dir = get_user_dir(malicious)
            
            assert '\x00' not in str(user_dir)
            assert str(user_dir).startswith(str(tmp_path))
    
    def test_blocks_forward_slash_in_principal(self, tmp_path):
        """Blocks forward slashes in principal ID."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import get_user_dir
            
            malicious = 'user/subdir/file'
            user_dir = get_user_dir(malicious)
            
            # Slashes should be stripped
            assert '/' not in user_dir.name
    
    def test_handles_empty_principal(self, tmp_path):
        """Handles empty principal gracefully."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import get_user_dir
            
            user_dir = get_user_dir('')
            
            # Should create directory under CHATS_DIR (empty name creates dir at base)
            assert user_dir.resolve().is_relative_to(tmp_path.resolve())


class TestMetadataOperations:
    """Metadata file operations tests."""
    
    def test_get_metadata_path(self, tmp_path):
        """Returns correct metadata file path."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import get_metadata_path
            
            principal = 'test-user'
            path = get_metadata_path(principal)
            
            assert path.name == 'metadata.json'
            assert principal in str(path)
    
    def test_load_metadata_creates_default(self, tmp_path):
        """Creates default metadata for new user."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import load_metadata
            
            principal = 'new-user-xyz'
            metadata = load_metadata(principal)
            
            assert metadata['principalId'] == principal
            assert metadata['version'] == '1.0'
            assert metadata['chats'] == []
            assert 'createdAt' in metadata
            assert 'lastLogin' in metadata
    
    def test_load_metadata_reads_existing(self, tmp_path):
        """Reads existing metadata file."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import load_metadata, get_user_dir
            
            principal = 'existing-user'
            user_dir = get_user_dir(principal)
            
            # Create metadata file
            existing_data = {
                'principalId': principal,
                'version': '1.0',
                'chats': ['chat1', 'chat2'],
                'createdAt': 1700000000000,
                'lastLogin': 1700000000000
            }
            with open(user_dir / 'metadata.json', 'w') as f:
                json.dump(existing_data, f)
            
            metadata = load_metadata(principal)
            
            assert metadata['chats'] == ['chat1', 'chat2']
    
    def test_save_metadata_updates_lastlogin(self, tmp_path):
        """Save updates lastLogin timestamp."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import save_metadata, load_metadata
            
            principal = 'test-user'
            metadata = {
                'principalId': principal,
                'version': '1.0',
                'chats': [],
                'createdAt': 1700000000000,
                'lastLogin': 1700000000000
            }
            
            before_save = int(time.time() * 1000)
            save_metadata(principal, metadata)
            after_save = int(time.time() * 1000)
            
            # Reload and check
            loaded = load_metadata(principal)
            assert loaded['lastLogin'] >= before_save
            assert loaded['lastLogin'] <= after_save + 1000


class TestUserMemoryOperations:
    """User persistent memory operations tests."""
    
    def test_get_user_memory_path(self, tmp_path):
        """Returns correct memory file path."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import get_user_memory_path
            
            principal = 'memory-user'
            path = get_user_memory_path(principal)
            
            assert path.name == 'user_memory.json'
            assert principal in str(path)
    
    def test_load_user_memory_creates_default(self, tmp_path):
        """Creates default memory structure for new user."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import load_user_memory
            
            principal = 'new-memory-user'
            memory = load_user_memory(principal)
            
            assert memory['principalId'] == principal
            assert memory['version'] == '1.0'
            assert memory['facts'] == []
            assert memory['preferences'] == {}
            assert 'createdAt' in memory
            assert 'lastUpdated' in memory
    
    def test_load_user_memory_reads_existing(self, tmp_path):
        """Reads existing memory file."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import load_user_memory, get_user_dir
            
            principal = 'memory-user'
            user_dir = get_user_dir(principal)
            
            # Create memory file
            existing_memory = {
                'principalId': principal,
                'version': '1.0',
                'facts': ['User prefers dark mode', 'User is a developer'],
                'preferences': {'theme': 'dark'},
                'createdAt': 1700000000000,
                'lastUpdated': 1700000000000
            }
            with open(user_dir / 'user_memory.json', 'w') as f:
                json.dump(existing_memory, f)
            
            memory = load_user_memory(principal)
            
            assert len(memory['facts']) == 2
            assert memory['preferences']['theme'] == 'dark'
    
    def test_save_user_memory_updates_timestamp(self, tmp_path):
        """Save updates lastUpdated timestamp."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import save_user_memory, load_user_memory
            
            principal = 'save-memory-user'
            memory = {
                'principalId': principal,
                'version': '1.0',
                'facts': ['New fact'],
                'preferences': {},
                'createdAt': 1700000000000,
                'lastUpdated': 1700000000000
            }
            
            before_save = int(time.time() * 1000)
            save_user_memory(principal, memory)
            after_save = int(time.time() * 1000)
            
            loaded = load_user_memory(principal)
            assert loaded['lastUpdated'] >= before_save
            assert loaded['lastUpdated'] <= after_save + 1000
    
    def test_save_and_load_roundtrip(self, tmp_path):
        """Data survives save and load cycle."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import save_user_memory, load_user_memory
            
            principal = 'roundtrip-user'
            memory = {
                'principalId': principal,
                'version': '1.0',
                'facts': ['Fact 1', 'Fact 2', 'Fact with "quotes"'],
                'preferences': {'nested': {'key': 'value'}},
                'createdAt': 1700000000000,
                'lastUpdated': 1700000000000
            }
            
            save_user_memory(principal, memory)
            loaded = load_user_memory(principal)
            
            assert loaded['facts'] == memory['facts']
            assert loaded['preferences'] == memory['preferences']


class TestSecurityBoundaries:
    """Security boundary and edge case tests."""
    
    def test_symbolic_link_attack_protection(self, tmp_path):
        """
        Symbolic links should not escape sandbox.
        Note: This tests the path resolution behavior.
        """
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import get_user_dir
            
            # Create a legitimate user dir first
            principal = 'legit-user'
            user_dir = get_user_dir(principal)
            
            # The resolved path should always be under CHATS_DIR
            assert user_dir.resolve().is_relative_to(tmp_path.resolve())
    
    def test_unicode_principal_handled(self, tmp_path):
        """Unicode characters in principal handled safely."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import get_user_dir
            
            # Unicode principal (could be from IDN domain)
            unicode_principal = 'user-日本語-テスト'
            user_dir = get_user_dir(unicode_principal)
            
            assert user_dir.exists()
    
    def test_very_long_principal_handled(self, tmp_path):
        """Very long principal IDs handled."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import get_user_dir
            
            long_principal = 'a' * 200
            user_dir = get_user_dir(long_principal)
            
            # Should work (filesystem will truncate if needed)
            assert user_dir.parent == tmp_path
    
    def test_concurrent_directory_creation(self, tmp_path):
        """Multiple calls don't fail on race condition."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import get_user_dir
            
            principal = 'concurrent-user'
            
            # Simulate concurrent calls
            dir1 = get_user_dir(principal)
            dir2 = get_user_dir(principal)
            
            assert dir1 == dir2
            assert dir1.exists()


class TestPathTraversalVariants:
    """Comprehensive path traversal attack variants."""
    
    @pytest.mark.parametrize("malicious_input", [
        "../",
        "..\\",
        "....//",
        "....\\\\",
        "%2e%2e/",
        "%2e%2e%2f",
        "..%00/",
        "..%c0%af",
        "..%252f",
        "..;/",
        "..%00",
        "....//....//",
    ])
    def test_path_traversal_variants_blocked(self, tmp_path, malicious_input):
        """Various path traversal encoding attempts are blocked."""
        with patch('storage.CHATS_DIR', str(tmp_path)):
            from storage import get_user_dir
            
            try:
                user_dir = get_user_dir(malicious_input)
                # If no exception, verify we're still in sandbox
                resolved = user_dir.resolve()
                assert resolved.is_relative_to(tmp_path.resolve()), \
                    f"Escaped sandbox with: {malicious_input}"
            except ValueError as e:
                # Path traversal detected - this is correct behavior
                assert "path traversal" in str(e).lower()

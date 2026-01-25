#!/usr/bin/env python3
"""
Trinity Filecoin Integration Test
Tests archive and recovery with Pinata IPFS
"""

import sys
import os
import json
import time
import requests
from datetime import datetime

# Add deployment to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'deployment', 'scripts'))

# Test backend URL
BACKEND_URL = "http://localhost:8000"

def test_health():
    """Test backend health endpoint"""
    print("\n" + "="*80)
    print("🏥 Testing Backend Health")
    print("="*80)
    
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=5)
        if r.status_code == 200:
            health = r.json()
            print(f"✅ Backend is healthy")
            print(f"   Provider: {health.get('provider_id')}")
            print(f"   Model: {health.get('model')}")
            print(f"   Ollama: {'✅' if health.get('ollama_connected') else '❌'}")
            print(f"   Uptime: {health['metrics']['uptime_seconds']:.1f}s")
            return True
        else:
            print(f"❌ Health check failed: {r.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to backend: {e}")
        return False

def test_filecoin_api_key():
    """Test that Filecoin API key is configured"""
    print("\n" + "="*80)
    print("🔑 Testing Filecoin API Key Configuration")
    print("="*80)
    
    pinata_jwt_path = os.path.expanduser("~/.pinata_jwt")
    
    if os.path.exists(pinata_jwt_path):
        with open(pinata_jwt_path, 'r') as f:
            jwt = f.read().strip()
            if jwt and jwt.startswith('eyJ'):
                print(f"✅ Pinata JWT found at {pinata_jwt_path}")
                print(f"   Length: {len(jwt)} characters")
                print(f"   Starts with: {jwt[:20]}...")
                return True
            else:
                print(f"❌ Invalid JWT format in {pinata_jwt_path}")
                return False
    else:
        print(f"❌ Pinata JWT not found at {pinata_jwt_path}")
        return False

def create_test_principal():
    """Generate a test Ed25519 keypair and principal"""
    print("\n" + "="*80)
    print("🔐 Creating Test Identity")
    print("="*80)
    
    try:
        from nacl.signing import SigningKey
        from nacl.encoding import HexEncoder
        import hashlib
        
        # Generate Ed25519 keypair
        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        
        # Create principal (SHA-224 hash of public key + suffix)
        public_key_bytes = bytes(verify_key)
        hash_bytes = hashlib.sha224(public_key_bytes).digest()
        principal = hash_bytes.hex()
        
        public_key_hex = verify_key.encode(encoder=HexEncoder).decode('ascii')
        private_key_hex = signing_key.encode(encoder=HexEncoder).decode('ascii')
        
        print(f"✅ Generated test identity")
        print(f"   Principal: {principal[:16]}...")
        print(f"   Public Key: {public_key_hex[:20]}...")
        
        return {
            'principal': principal,
            'public_key': public_key_hex,
            'private_key': private_key_hex,
            'signing_key': signing_key
        }
    except ImportError:
        print("⚠️  PyNaCl not installed, using mock identity")
        return {
            'principal': 'test_principal_' + str(int(time.time())),
            'public_key': 'test_public_key',
            'private_key': 'test_private_key',
            'signing_key': None
        }

def sign_request(method, path, timestamp, signing_key):
    """Sign a request for authentication"""
    if signing_key is None:
        return "mock_signature"
    
    from nacl.encoding import HexEncoder
    message = f"{method}:{path}:{timestamp}"
    signature = signing_key.sign(message.encode('utf-8'))
    return signature.signature.hex()

def test_archive_endpoint(identity):
    """Test the /chat/{chatId}/archive endpoint"""
    print("\n" + "="*80)
    print("📦 Testing Archive Endpoint (Pinata Upload)")
    print("="*80)
    
    chat_id = f"test_chat_{int(time.time())}"
    test_messages = [
        {"role": "user", "content": "Test message 1"},
        {"role": "assistant", "content": "Test response 1"},
        {"role": "user", "content": "Test message 2 for Filecoin"},
        {"role": "assistant", "content": "Test response 2 with more content"}
    ]
    
    # First, create/save the chat using autosave endpoint
    timestamp_save = str(int(time.time() * 1000))
    save_path = f"/chat/autosave"
    save_signature = sign_request("POST", save_path, timestamp_save, identity.get('signing_key'))
    
    save_headers = {
        'Content-Type': 'application/json',
        'ICP-Principal': identity['principal'],
        'ICP-PublicKey': identity['public_key'],
        'ICP-Timestamp': timestamp_save,
        'ICP-Signature': save_signature
    }
    
    save_payload = {
        "chatId": chat_id,
        "messages": test_messages,
        "title": "Test Filecoin Archive"
    }
    
    print(f"Creating chat: {chat_id}")
    print(f"Messages: {len(test_messages)}")
    
    try:
        save_r = requests.post(
            f"{BACKEND_URL}{save_path}",
            headers=save_headers,
            json=save_payload,
            timeout=10
        )
        
        if save_r.status_code != 200:
            print(f"⚠️  Chat save returned: {save_r.status_code} - {save_r.text[:100]}")
    except Exception as e:
        print(f"⚠️  Chat save error: {e}")
    
    time.sleep(1)  # Wait for save to complete
    
    # Now archive it
    timestamp = str(int(time.time() * 1000))
    path = f"/chat/{chat_id}/archive"
    signature = sign_request("POST", path, timestamp, identity.get('signing_key'))
    
    headers = {
        'Content-Type': 'application/json',
        'ICP-Principal': identity['principal'],
        'ICP-PublicKey': identity['public_key'],
        'ICP-Timestamp': timestamp,
        'ICP-Signature': signature
    }
    
    payload = {
        "messages": test_messages,
        "title": "Test Filecoin Archive"
    }
    
    print(f"\nArchiving chat to Pinata...")
    
    try:
        r = requests.post(
            f"{BACKEND_URL}{path}",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        print(f"\nResponse Status: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            print(f"✅ Archive successful!")
            print(f"   Response: {json.dumps(data, indent=2)}")
            
            cid = data.get('cid')
            filepoint_id = data.get('filepointId')
            
            if cid:
                print(f"   CID: {cid}")
            if filepoint_id:
                print(f"   Filepoint ID: {filepoint_id[:50]}...")
            
            # Construct IPFS URL
            if cid:
                ipfs_url = f"https://gateway.pinata.cloud/ipfs/{cid}"
                print(f"   IPFS Gateway: {ipfs_url}")
            
            return {
                'success': True,
                'cid': cid,
                'filepoint_id': filepoint_id,
                'chat_id': chat_id
            }
        else:
            print(f"❌ Archive failed: {r.text[:200]}")
            return {'success': False}
            
    except Exception as e:
        print(f"❌ Archive request failed: {e}")
        return {'success': False}

def test_recovery_endpoint(filepoint_id, identity):
    """Test the /chat/archive-recover/{filepointId} endpoint"""
    print("\n" + "="*80)
    print("🔄 Testing Recovery Endpoint (IPFS Download)")
    print("="*80)
    
    if not filepoint_id:
        print("❌ No filepoint ID to test recovery")
        return False
    
    # Create headers
    timestamp = str(int(time.time() * 1000))
    path = f"/chat/archive-recover/{filepoint_id}"
    signature = sign_request("GET", path, timestamp, identity.get('signing_key'))
    
    headers = {
        'ICP-Principal': identity['principal'],
        'ICP-PublicKey': identity['public_key'],
        'ICP-Timestamp': timestamp,
        'ICP-Signature': signature
    }
    
    print(f"Recovering filepoint: {filepoint_id}")
    
    try:
        r = requests.get(
            f"{BACKEND_URL}{path}",
            headers=headers,
            timeout=30
        )
        
        print(f"\nResponse Status: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            print(f"✅ Recovery successful!")
            print(f"   Chat ID: {data.get('chat_id', 'N/A')}")
            print(f"   Title: {data.get('title', 'N/A')}")
            print(f"   Messages: {len(data.get('messages', []))}")
            print(f"   Created: {data.get('created_at', 'N/A')}")
            
            # Verify message content
            messages = data.get('messages', [])
            if len(messages) > 0:
                print(f"\n   First message: {messages[0].get('content', '')[:50]}...")
                
            return True
        else:
            print(f"❌ Recovery failed: {r.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ Recovery request failed: {e}")
        return False

def main():
    print("\n" + "="*80)
    print("🧪 Trinity Filecoin Integration Test Suite")
    print("="*80)
    print(f"Backend: {BACKEND_URL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        'health': False,
        'api_key': False,
        'archive': False,
        'recovery': False
    }
    
    # Test 1: Backend Health
    results['health'] = test_health()
    if not results['health']:
        print("\n❌ Backend not running. Start with: ./deployment/start-local.sh")
        return 1
    
    # Test 2: API Key Configuration
    results['api_key'] = test_filecoin_api_key()
    
    # Test 3: Create test identity
    identity = create_test_principal()
    
    # Test 4: Archive (Upload to Pinata)
    archive_result = test_archive_endpoint(identity)
    results['archive'] = archive_result.get('success', False)
    
    # Test 5: Recovery (Download from IPFS)
    if results['archive'] and archive_result.get('filepoint_id'):
        time.sleep(2)  # Wait for IPFS propagation
        results['recovery'] = test_recovery_endpoint(
            archive_result['filepoint_id'],
            identity
        )
    
    # Summary
    print("\n" + "="*80)
    print("📊 Test Results Summary")
    print("="*80)
    
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}  {test.upper()}")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All Filecoin integration tests passed!")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check logs for details.")
        return 1

if __name__ == '__main__':
    sys.exit(main())

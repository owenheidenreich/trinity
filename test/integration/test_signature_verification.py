"""
Test ICP Signature Verification with Real Test Vectors
"""

import sys
sys.path.append('/Users/owenheidenreich/Documents/Trinity/Trinity/deployment')

from icp_auth import verify_icp_signature
import json

def test_signature_verification():
    """
    Test signature verification with values from frontend test
    
    Steps:
    1. Run test-signing.html in browser
    2. Generate identity and sign messages
    3. Export test vectors
    4. Paste JSON below
    """
    
    # TODO: Replace with actual test vectors from frontend
    # Get these by running: http://localhost:8081/test-signing.html
    test_vectors = None
    
    if not test_vectors:
        print("⚠️  No test vectors provided")
        print("\nTo generate test vectors:")
        print("1. Open http://localhost:8081/test-signing.html")
        print("2. Click 'Generate Identity'")
        print("3. Click 'Sign 5 Different Messages'")
        print("4. Click 'Export for Backend Testing'")
        print("5. Copy the JSON and paste it in this file")
        return
    
    print("🧪 Testing ICP Signature Verification")
    print("=" * 80)
    
    principal = test_vectors['principal']
    public_key = test_vectors['publicKey']
    signatures = test_vectors['signatures']
    
    print(f"\nPrincipal: {principal}")
    print(f"Public Key: {public_key[:32]}...")
    print(f"\nTesting {len(signatures)} signatures:\n")
    
    passed = 0
    failed = 0
    
    for i, sig_data in enumerate(signatures, 1):
        message = sig_data['message']
        signature = sig_data['signature']
        
        # Extract timestamp and endpoint from message
        parts = message.split(':')
        if len(parts) >= 3:
            timestamp = parts[1]
            endpoint = ':'.join(parts[2:])  # In case endpoint contains ':'
        else:
            print(f"❌ Test {i}: Invalid message format")
            failed += 1
            continue
        
        print(f"Test {i}: {endpoint}")
        print(f"  Message: {message[:60]}...")
        print(f"  Signature: {signature[:32]}...")
        
        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=signature,
            timestamp=timestamp,
            endpoint=endpoint,
            public_key_hex=public_key
        )
        
        if success:
            print(f"  ✅ PASSED\n")
            passed += 1
        else:
            print(f"  ❌ FAILED: {error}\n")
            failed += 1
    
    print("=" * 80)
    print(f"\nResults: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("✅ All signature verifications passed!")
    else:
        print("❌ Some verifications failed")

if __name__ == '__main__':
    test_signature_verification()

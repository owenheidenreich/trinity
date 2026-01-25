#!/usr/bin/env python3
"""
Trinity Auth Test Backend
Simple Flask server to test request signature verification
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sys
import os

# Add deployment directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'deployment'))

from icp_auth import verify_icp_signature, verify_request_auth, require_auth

app = Flask(__name__)
CORS(app)  # Allow requests from localhost:8081

@app.route('/test/echo-headers', methods=['POST', 'GET'])
def echo_headers():
    """Echo back all received headers for debugging"""
    headers_dict = dict(request.headers)
    
    # Extract ICP headers
    icp_headers = {
        'ICP-Principal': request.headers.get('ICP-Principal'),
        'ICP-Signature': request.headers.get('ICP-Signature'),
        'ICP-Timestamp': request.headers.get('ICP-Timestamp'),
        'ICP-PublicKey': request.headers.get('ICP-PublicKey')
    }
    
    print("\n" + "="*80)
    print("📥 Received Request")
    print("="*80)
    print(f"Method: {request.method}")
    print(f"Path: {request.path}")
    print(f"ICP-Principal: {icp_headers['ICP-Principal']}")
    print(f"ICP-Signature: {icp_headers['ICP-Signature'][:32] if icp_headers['ICP-Signature'] else None}...")
    print(f"ICP-Timestamp: {icp_headers['ICP-Timestamp']}")
    print(f"ICP-PublicKey: {icp_headers['ICP-PublicKey'][:32] if icp_headers['ICP-PublicKey'] else None}...")
    print("="*80 + "\n")
    
    return jsonify({
        'success': True,
        'receivedHeaders': icp_headers,
        'message': 'Headers received successfully'
    })

@app.route('/test/verify', methods=['POST', 'GET'])
def test_verify():
    """Test endpoint with actual signature verification"""
    print("\n" + "="*80)
    print("🔐 Verifying Request Signature")
    print("="*80)
    
    success, principal, error = verify_request_auth()
    
    if not success:
        print(f"❌ Verification Failed: {error}")
        print("="*80 + "\n")
        return jsonify({
            'success': False,
            'error': error
        }), 401
    
    print(f"✅ Signature Verified!")
    print(f"Principal: {principal}")
    print("="*80 + "\n")
    
    return jsonify({
        'success': True,
        'message': 'Signature verified successfully!',
        'principal': principal,
        'endpoint': request.path
    })

@app.route('/test/protected', methods=['POST'])
@require_auth
def test_protected():
    """Test endpoint using @require_auth decorator"""
    # Principal is available as request.principal after auth
    return jsonify({
        'success': True,
        'message': 'You accessed a protected endpoint!',
        'principal': request.principal,
        'data': 'This is protected data'
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'trinity-auth-test'})

if __name__ == '__main__':
    print("\n" + "="*80)
    print("🧪 Trinity Auth Test Backend with Verification")
    print("="*80)
    print("Running on http://localhost:5001")
    print("Test endpoints:")
    print("  - POST/GET /test/echo-headers (echo all headers)")
    print("  - POST/GET /test/verify (verify signature)")
    print("  - POST /test/protected (protected with @require_auth)")
    print("  - GET /health (health check)")
    print("="*80 + "\n")
    
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)


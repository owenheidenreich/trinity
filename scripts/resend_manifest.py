#!/usr/bin/env python3
"""Resend manifest to Akash to force container restart with latest image."""
import re, tempfile, subprocess, os, sys

sys.path.insert(0, os.path.dirname(__file__))
from akash_deploy import inject_env_values

DSEQ = '25575579'
PROVIDER = 'akash1ut3m97h62tty06qdq9lds85r34dxe3snjj0xfe'
WALLET_NAME = 'trinity-wallet'
AKASH_NODE = 'https://rpc.akashnet.net:443'
YAML_PATH = os.path.join(os.path.dirname(__file__), '..', 'deploy', 'akash', 'deploy-production.yaml')

with open(YAML_PATH) as f:
    yaml_content = f.read()

yaml_content = re.sub(r'gdubx/trinity-inference:[^\s]*', 'gdubx/trinity-inference:latest', yaml_content)
yaml_content = inject_env_values(yaml_content)

with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
    f.write(yaml_content)
    temp_yaml = f.name

print(f'Temp YAML: {temp_yaml}')
print('Sending manifest to force container restart...')

cmd = (
    f'provider-services send-manifest {temp_yaml} --dseq {DSEQ} '
    f'--provider {PROVIDER} --from {WALLET_NAME} --keyring-backend os '
    f'--node {AKASH_NODE} 2>&1'
)
result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
print(f'Exit: {result.returncode}')
print(result.stdout + result.stderr)
os.unlink(temp_yaml)

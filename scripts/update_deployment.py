#!/usr/bin/env python3
"""Quick deployment update - sends new manifest to existing Akash deployment"""
import re, tempfile, subprocess, os, sys, time

sys.path.insert(0, os.path.dirname(__file__))
from akash_deploy import inject_env_values

WALLET_NAME = 'trinity-wallet'
AKASH_NODE = 'https://rpc.akashnet.net:443'
AKASH_CHAIN_ID = 'akashnet-2'
DSEQ = '25575579'
PROVIDER = 'akash1ut3m97h62tty06qdq9lds85r34dxe3snjj0xfe'
YAML_PATH = os.path.join(os.path.dirname(__file__), '..', 'deploy', 'akash', 'deploy-production.yaml')

# Read and prepare YAML
with open(YAML_PATH) as f:
    yaml_content = f.read()

yaml_content = re.sub(r'gdubx/trinity-inference:[^\s]*', 'gdubx/trinity-inference:latest', yaml_content)
yaml_content = inject_env_values(yaml_content)

# Write temp YAML
with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
    f.write(yaml_content)
    temp_yaml = f.name

print(f'Temp YAML: {temp_yaml}')

# Step 1: Update deployment
print('\n=== Updating deployment ===')
cmd = (
    f'provider-services tx deployment update {temp_yaml} --dseq {DSEQ} '
    f'--from {WALLET_NAME} --keyring-backend os '
    f'--node {AKASH_NODE} --chain-id {AKASH_CHAIN_ID} '
    f'--gas auto --gas-adjustment 1.5 --gas-prices 0.025uakt '
    f'--yes 2>&1'
)
result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
print(f'Exit: {result.returncode}')
output = result.stdout + result.stderr
print(output[-800:] if len(output) > 800 else output)

if result.returncode != 0:
    os.unlink(temp_yaml)
    sys.exit(1)

print('Waiting 10s for update to propagate...')
time.sleep(10)

# Step 2: Send manifest
print('\n=== Sending manifest ===')
cmd = (
    f'provider-services send-manifest {temp_yaml} --dseq {DSEQ} '
    f'--provider {PROVIDER} --from {WALLET_NAME} --keyring-backend os '
    f'--node {AKASH_NODE} 2>&1'
)
result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
print(f'Exit: {result.returncode}')
output = result.stdout + result.stderr
print(output[-800:] if len(output) > 800 else output)

os.unlink(temp_yaml)
print('\nDone!')

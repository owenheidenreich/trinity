/**
 * ICP Canister Client — typed interface for the username registry.
 *
 * Uses @dfinity/agent to call the trinity_backend canister's username
 * registry endpoints (register_username, lookup_username, is_username_available).
 *
 * Query calls (lookup, availability check) are free and fast.
 * Update calls (register) cost cycles and require consensus.
 */
import { Actor, HttpAgent, type ActorSubclass } from '@dfinity/agent';

// Backend canister ID (matches .env / dfx.json deployment)
const BACKEND_CANISTER_ID = 'au5zq-2qaaa-aaaal-qtowa-cai';

// ICP network host
function getICPHost(): string {
  if (typeof window === 'undefined') return 'https://ic0.app';
  const hostname = window.location.hostname;
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'http://localhost:4943';
  }
  return 'https://ic0.app';
}

// ============================================================================
// IDL Factory — username registry subset of the canister interface
// ============================================================================

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const usernameRegistryIdlFactory = ({ IDL }: any) => {
  const Result_Unit = IDL.Variant({
    Ok: IDL.Null,
    Err: IDL.Text,
  });

  const Result_Bool = IDL.Variant({
    Ok: IDL.Bool,
    Err: IDL.Text,
  });

  return IDL.Service({
    // Update call — costs cycles, requires consensus
    register_username: IDL.Func(
      [IDL.Text, IDL.Text, IDL.Text, IDL.Text, IDL.Text],
      [Result_Unit],
      [],
    ),
    // Query calls — free, fast
    lookup_username: IDL.Func([IDL.Text], [IDL.Opt(IDL.Text)], ['query']),
    is_username_available: IDL.Func([IDL.Text], [Result_Bool], ['query']),
    get_username_for_principal: IDL.Func([IDL.Text], [IDL.Opt(IDL.Text)], ['query']),
  });
};

// ============================================================================
// Actor singleton
// ============================================================================

let _agent: HttpAgent | null = null;
let _actor: ActorSubclass | null = null;

async function getActor(): Promise<ActorSubclass> {
  if (_actor) return _actor;

  const host = getICPHost();
  _agent = new HttpAgent({ host });

  // Fetch root key for local development only
  if (host.includes('localhost')) {
    await _agent.fetchRootKey();
  }

  _actor = Actor.createActor(usernameRegistryIdlFactory, {
    agent: _agent,
    canisterId: BACKEND_CANISTER_ID,
  });

  return _actor;
}

// ============================================================================
// Public API
// ============================================================================

/**
 * Register a username → principal mapping on-chain.
 * Requires Ed25519 signature proving ownership of the keypair.
 *
 * @throws Error if username taken, principal already registered, or signature invalid
 */
export async function registerUsername(
  username: string,
  principal: string,
  publicKeyHex: string,
  signatureHex: string,
  timestamp: string,
): Promise<void> {
  const actor = await getActor();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result = await (actor as any).register_username(
    username,
    principal,
    publicKeyHex,
    signatureHex,
    timestamp,
  );

  if ('Err' in result) {
    throw new Error(result.Err);
  }
}

/**
 * Look up the principal for a given username.
 * Returns null if username not found.
 * Query call — free, no cycles.
 */
export async function lookupUsername(username: string): Promise<string | null> {
  const actor = await getActor();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result = await (actor as any).lookup_username(username);
  // Candid Opt returns [] for None, [value] for Some
  if (Array.isArray(result) && result.length > 0) {
    return result[0];
  }
  return null;
}

/**
 * Check if a username is available for registration.
 * Query call — free, no cycles.
 *
 * @throws Error if username format is invalid
 */
export async function isUsernameAvailable(username: string): Promise<boolean> {
  const actor = await getActor();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result = await (actor as any).is_username_available(username);
  if ('Err' in result) {
    throw new Error(result.Err);
  }
  return result.Ok;
}

/**
 * Get the username for a given principal (reverse lookup).
 * Returns null if principal has no username.
 * Query call — free, no cycles.
 */
export async function getUsernameForPrincipal(principal: string): Promise<string | null> {
  const actor = await getActor();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result = await (actor as any).get_username_for_principal(principal);
  if (Array.isArray(result) && result.length > 0) {
    return result[0];
  }
  return null;
}

/** Reset the actor (useful after errors or for testing). */
export function resetCanisterClient(): void {
  _agent = null;
  _actor = null;
}

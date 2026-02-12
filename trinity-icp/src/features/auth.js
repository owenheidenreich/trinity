// ============================================================================
// FEATURE: AUTH — Authentication flows
// ============================================================================
// Handles: identity creation, login, logout, key export, auth gates.
// ============================================================================

import AuthManager from '../auth/authManager.js';
import State from '../state/store.js';
import UI from '../ui/index.js';
import { loadUserDataInBackground } from './chatManagement.js';

/**
 * Initialize authentication (mandatory gate).
 * Restores cached credentials or forces login.
 */
export async function initAuth() {
    console.log('🔐 Starting authentication initialization...');

    try {
        const result = await AuthManager.initialize();

        if (result && result.isAuthenticated) {
            State.setAuthenticated(result.principal, result.authenticatedSince);
            console.log('✅ Identity restored from cache:', result.principal);

            UI.renderSidebar(State);
            loadUserDataInBackground();
        } else {
            console.log('🚫 No cached session - authentication required');
            UI.renderSidebar(State);
            await requireAuthentication();
        }
    } catch (err) {
        console.error('❌ Auth initialization error:', err);
        UI.renderSidebar(State);
        await requireAuthentication();
    }
}

/**
 * Require authentication (loops until successful).
 */
export async function requireAuthentication() {
    console.log('🔒 Authentication required - showing modal...');

    while (!State.isAuthenticated) {
        try {
            await handleAuthenticationFlow();

            if (!State.isAuthenticated) {
                console.log('⚠️ Authentication incomplete, retrying...');
                await new Promise(resolve => setTimeout(resolve, 500));
            }
        } catch (error) {
            console.error('❌ Authentication flow error:', error);
            await new Promise(resolve => setTimeout(resolve, 500));
        }
    }

    console.log('✅ Authentication successful!');
}

/**
 * Handle authentication flow (returns only when authenticated).
 */
async function handleAuthenticationFlow() {
    const { default: Modals } = await import('../ui/modals.js');

    const choice = await Modals.showAuthChoiceModal();

    if (choice === 'create') {
        await createNewIdentity();
    } else if (choice === 'login') {
        await loginWithCredentials();
    }
}

/**
 * Create new identity with automatic login after credentials shown.
 */
async function createNewIdentity() {
    try {
        const result = await AuthManager.login();
        console.log('🔑 New identity created:', result.principal?.substring(0, 20) + '...');

        if (!result.success) {
            console.error('❌ Identity creation failed');
            return;
        }

        const { default: Modals } = await import('../ui/modals.js');

        // Show credentials warning
        await Modals.showKeyWarningModal(result.principal, result.privateKeyHex);

        // Set auth state
        State.setAuthenticated(result.principal, result.authenticatedSince);
        console.log('🔐 Auth state set. isAuthenticated:', State.isAuthenticated, 'principal:', State.principal?.substring(0, 15) + '...');

        if (!State.isAuthenticated) {
            console.error('❌ CRITICAL: State.setAuthenticated failed to update state!');
            State.setAuthenticated(result.principal, result.authenticatedSince);
        }

        Modals.removeAllModals();
        UI.renderSidebar(State);
        console.log('✅ New user authenticated! Final check - isAuthenticated:', State.isAuthenticated);

        loadUserDataInBackground();

    } catch (error) {
        console.error('❌ Create identity error:', error);
    }
}

/**
 * Login with existing credentials.
 */
export async function loginWithCredentials() {
    const { default: Modals } = await import('../ui/modals.js');

    try {
        const credentials = await Modals.showLoginModal();
        if (!credentials) {
            console.log('🚫 Login cancelled by user');
            return;
        }

        const result = await AuthManager.importKey(credentials.password);

        if (!result.success) {
            throw new Error(result.error || 'Import failed');
        }

        if (result.principal !== credentials.username) {
            throw new Error('Username does not match the provided password');
        }

        State.setAuthenticated(result.principal, result.authenticatedSince);
        Modals.removeAllModals();

        console.log('✅ Identity restored:', result.principal);
        UI.showNotification('✅ Welcome back!', 'success');
        UI.renderSidebar(State);

        loadUserDataInBackground();

    } catch (error) {
        console.error('❌ Login failed:', error);
        UI.showNotification('❌ Invalid credentials. Please try again.', 'error');
    }
}

/**
 * Logout and require re-authentication.
 */
export async function logout() {
    await AuthManager.logout();
    State.clearAuthentication();
    State.reset();
    UI.clearMessages();
    UI.renderSidebar(State);

    await requireAuthentication();
}

/**
 * Export current key (show credentials modal).
 */
export async function exportKey() {
    const result = AuthManager.exportKey();

    if (result.success) {
        const { default: Modals } = await import('../ui/modals.js');
        await Modals.showKeyWarningModal(result.principal, result.privateKeyHex);
    } else {
        UI.showNotification('❌ No identity to export', 'error');
    }
}

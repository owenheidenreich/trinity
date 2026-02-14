// ============================================================================
// FEATURE: AUTH — Authentication flows
// ============================================================================
// Handles: identity creation, login, logout, key export, auth gates.
// ============================================================================

import AuthManager from '../auth/authManager.js';
import Logger from '../core/logger.js';
import State from '../state/store.js';
import UI from '../ui/index.js';
import { loadUserDataInBackground } from './chatManagement.js';

/**
 * Initialize authentication (mandatory gate).
 * Restores cached credentials or forces login.
 */
export async function initAuth() {
    Logger.debug('Starting authentication initialization...');

    try {
        const result = await AuthManager.initialize();

        if (result && result.isAuthenticated) {
            State.setAuthenticated(result.principal, result.authenticatedSince);
            Logger.debug('Identity restored from cache:', result.principal?.slice(0, 10));

            UI.renderSidebar(State);
            loadUserDataInBackground();
        } else {
            Logger.debug('No cached session - authentication required');
            UI.renderSidebar(State);
            await requireAuthentication();
        }
    } catch (err) {
        Logger.error('Auth initialization error:', err);
        UI.renderSidebar(State);
        await requireAuthentication();
    }
}

/**
 * Require authentication (loops until successful).
 */
export async function requireAuthentication() {
    Logger.debug('Authentication required - showing modal...');

    while (!State.isAuthenticated) {
        try {
            await handleAuthenticationFlow();

            if (!State.isAuthenticated) {
                Logger.debug('Authentication incomplete, retrying...');
                await new Promise(resolve => setTimeout(resolve, 500));
            }
        } catch (error) {
            Logger.error('Authentication flow error:', error);
            await new Promise(resolve => setTimeout(resolve, 500));
        }
    }

    Logger.debug('Authentication successful');
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
        Logger.debug('New identity created');

        if (!result.success) {
            Logger.error('Identity creation failed');
            return;
        }

        const { default: Modals } = await import('../ui/modals.js');

        // Show credentials warning
        await Modals.showKeyWarningModal(result.principal, result.privateKeyHex);

        // Set auth state
        State.setAuthenticated(result.principal, result.authenticatedSince);
        Logger.debug('Auth state set. isAuthenticated:', State.isAuthenticated);

        if (!State.isAuthenticated) {
            Logger.error('CRITICAL: State.setAuthenticated failed to update state!');
            State.setAuthenticated(result.principal, result.authenticatedSince);
        }

        Modals.removeAllModals();
        UI.renderSidebar(State);
        Logger.debug('New user authenticated');

        loadUserDataInBackground();

    } catch (error) {
        Logger.error('Create identity error:', error);
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
            Logger.debug('Login cancelled by user');
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

        Logger.debug('Identity restored');
        UI.showNotification('Welcome back!', 'success');
        UI.renderSidebar(State);

        loadUserDataInBackground();

    } catch (error) {
        Logger.error('Login failed:', error);
        UI.showNotification('Invalid credentials. Please try again.', 'error');
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

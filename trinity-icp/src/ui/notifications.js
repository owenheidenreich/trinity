// notifications.js - Toast notifications and indicators
// Responsible for autosave indicators, success/error toasts, and summarization indicators

const Notifications = {
    showAutosaveIndicator(status) {
        let indicator = document.getElementById('autosave-indicator');
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.id = 'autosave-indicator';
            indicator.className = 'autosave-indicator';
            document.body.appendChild(indicator);
        }

        indicator.classList.remove('saving', 'error', 'success', 'hidden');
        if (status === 'saving') {
            indicator.classList.add('saving');
            indicator.innerHTML = '<span class="wave">⤴️ Saving...</span>';
        } else if (status === 'error') {
            indicator.classList.add('error');
            indicator.innerHTML = '<span>⚠️ Save failed</span>';
        } else if (status === 'success') {
            indicator.classList.add('success');
            indicator.innerHTML = '<span>✓ Saved</span>';
        }
        indicator.style.display = 'block';
    },

    hideAutosaveIndicator() {
        const indicator = document.getElementById('autosave-indicator');
        if (indicator) {
            indicator.classList.add('hidden');
            setTimeout(() => {
                indicator.style.display = 'none';
            }, 500);
        }
    },

    showSummarizationIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'summarization-toast';
        indicator.innerHTML = '🗜️ Compressing conversation history...';
        indicator.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            font-size: 14px;
            z-index: 10000;
            animation: slideIn 0.3s ease;
        `;
        
        document.body.appendChild(indicator);
        
        setTimeout(() => {
            indicator.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => indicator.remove(), 300);
        }, 2000);
    },

    showError(message) {
        this.showNotification(message, 'error');
    },

    showSuccess(message, options = {}) {
        this.showNotification(message, 'success', options);
    },

    showWarning(message) {
        this.showNotification(message, 'warning');
    },

    showNotification(message, type = 'info', options = {}) {
        const { duration = 3000, link = null, linkText = 'View' } = options;
        
        const notif = document.createElement('div');
        notif.className = `notification ${type}`;
        
        // Build notification content
        let content = message.replace(/\n/g, '<br>');
        if (link) {
            content += `<br><a href="${link}" target="_blank" class="notification-link">${linkText} ↗</a>`;
        }
        notif.innerHTML = content;
        document.body.appendChild(notif);

        setTimeout(() => {
            notif.classList.add('show');
        }, 10);

        setTimeout(() => {
            notif.classList.remove('show');
            setTimeout(() => notif.remove(), 300);
        }, duration);
    },

    /**
     * Show a live countdown toast when rate-limited.
     * Auto-removes when countdown finishes and shows "Ready" notification.
     */
    showRateLimitCountdown(seconds) {
        // Remove any existing countdown
        const existing = document.getElementById('rate-limit-countdown');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.id = 'rate-limit-countdown';
        toast.className = 'notification warning';
        toast.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 10001; min-width: 280px;';
        document.body.appendChild(toast);

        let remaining = seconds;
        const update = () => {
            if (remaining <= 0) {
                toast.classList.remove('show');
                setTimeout(() => toast.remove(), 300);
                this.showSuccess('Ready to continue!');
                return;
            }
            toast.textContent = `Too many requests. Try again in ${remaining}s`;
            toast.classList.add('show');
            remaining--;
            setTimeout(update, 1000);
        };
        update();
    }
};

export default Notifications;

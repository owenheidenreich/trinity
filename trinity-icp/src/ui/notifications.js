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

    showSuccess(message) {
        this.showNotification(message, 'success');
    },

    showWarning(message) {
        this.showNotification(message, 'warning');
    },

    showNotification(message, type = 'info') {
        const notif = document.createElement('div');
        notif.className = `notification ${type}`;
        notif.innerHTML = message;
        document.body.appendChild(notif);

        setTimeout(() => {
            notif.classList.add('show');
        }, 10);

        setTimeout(() => {
            notif.classList.remove('show');
            setTimeout(() => notif.remove(), 300);
        }, 3000);
    }
};

export default Notifications;

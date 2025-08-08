// Main JavaScript for Trading Bot Dashboard

class TradingDashboard {
    constructor() {
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.initializeCharts();
        this.startRealTimeUpdates();
        this.setupNotifications();
    }

    setupEventListeners() {
        // Navigation
        document.addEventListener('DOMContentLoaded', () => {
            this.setupNavigation();
            this.setupMobileMenu();
            this.setupThemeToggle();
        });

        // Form submissions
        const forms = document.querySelectorAll('form');
        forms.forEach(form => {
            form.addEventListener('submit', (e) => this.handleFormSubmit(e));
        });

        // Modal interactions
        this.setupModals();
    }

    setupNavigation() {
        const navLinks = document.querySelectorAll('.nav-links a');
        navLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                if (link.getAttribute('href').startsWith('#')) {
                    e.preventDefault();
                    this.navigateToSection(link.getAttribute('href').substring(1));
                }
            });
        });
    }

    setupMobileMenu() {
        const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
        const mobileMenu = document.querySelector('.mobile-menu');
        
        if (mobileMenuBtn && mobileMenu) {
            mobileMenuBtn.addEventListener('click', () => {
                mobileMenu.classList.toggle('active');
            });
        }
    }

    setupThemeToggle() {
        const themeToggle = document.querySelector('.theme-toggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', () => {
                this.toggleTheme();
            });
        }
    }

    toggleTheme() {
        const body = document.body;
        const currentTheme = body.getAttribute('data-theme') || 'light';
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        
        body.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        
        // Update theme toggle button
        const themeToggle = document.querySelector('.theme-toggle');
        if (themeToggle) {
            themeToggle.innerHTML = newTheme === 'light' ? '🌙' : '☀️';
        }
    }

    setupModals() {
        const modalTriggers = document.querySelectorAll('[data-modal]');
        const modals = document.querySelectorAll('.modal');
        const modalCloses = document.querySelectorAll('.modal-close');

        modalTriggers.forEach(trigger => {
            trigger.addEventListener('click', (e) => {
                e.preventDefault();
                const modalId = trigger.getAttribute('data-modal');
                this.openModal(modalId);
            });
        });

        modalCloses.forEach(close => {
            close.addEventListener('click', () => {
                this.closeAllModals();
            });
        });

        // Close modal on outside click
        modals.forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.closeAllModals();
                }
            });
        });

        // Close modal on escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeAllModals();
            }
        });
    }

    openModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
    }

    closeAllModals() {
        const modals = document.querySelectorAll('.modal');
        modals.forEach(modal => {
            modal.classList.remove('active');
        });
        document.body.style.overflow = '';
    }

    async handleFormSubmit(e) {
        e.preventDefault();
        const form = e.target;
        const formData = new FormData(form);
        const submitBtn = form.querySelector('button[type="submit"]');
        
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = 'Processing...';
        }

        try {
            const response = await fetch(form.action, {
                method: form.method,
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            const result = await response.json();
            
            if (result.success) {
                this.showNotification(result.message || 'Success!', 'success');
                if (result.redirect) {
                    window.location.href = result.redirect;
                }
            } else {
                this.showNotification(result.message || 'An error occurred', 'error');
            }
        } catch (error) {
            console.error('Form submission error:', error);
            this.showNotification('An error occurred while processing your request', 'error');
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = submitBtn.getAttribute('data-original-text') || 'Submit';
            }
        }
    }

    initializeCharts() {
        // Initialize trading charts if Chart.js is available
        if (typeof Chart !== 'undefined') {
            this.setupTradingCharts();
        }
    }

    setupTradingCharts() {
        const chartElements = document.querySelectorAll('[data-chart]');
        
        chartElements.forEach(element => {
            const chartType = element.getAttribute('data-chart');
            const ctx = element.getContext('2d');
            
            if (chartType === 'price') {
                this.createPriceChart(ctx);
            } else if (chartType === 'volume') {
                this.createVolumeChart(ctx);
            } else if (chartType === 'performance') {
                this.createPerformanceChart(ctx);
            }
        });
    }

    createPriceChart(ctx) {
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: this.generateTimeLabels(24),
                datasets: [{
                    label: 'Price',
                    data: this.generateRandomData(24, 100, 200),
                    borderColor: '#2563eb',
                    backgroundColor: 'rgba(37, 99, 235, 0.1)',
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: false
                    }
                }
            }
        });
    }

    createVolumeChart(ctx) {
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: this.generateTimeLabels(24),
                datasets: [{
                    label: 'Volume',
                    data: this.generateRandomData(24, 0, 1000),
                    backgroundColor: '#10b981'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }

    createPerformanceChart(ctx) {
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Wins', 'Losses', 'Pending'],
                datasets: [{
                    data: [65, 25, 10],
                    backgroundColor: ['#10b981', '#ef4444', '#f59e0b']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }

    generateTimeLabels(count) {
        const labels = [];
        const now = new Date();
        for (let i = count - 1; i >= 0; i--) {
            const time = new Date(now.getTime() - i * 60 * 60 * 1000);
            labels.push(time.toLocaleTimeString('en-US', { 
                hour: '2-digit', 
                minute: '2-digit' 
            }));
        }
        return labels;
    }

    generateRandomData(count, min, max) {
        return Array.from({ length: count }, () => 
            Math.floor(Math.random() * (max - min + 1)) + min
        );
    }

    startRealTimeUpdates() {
        // Set up WebSocket connection for real-time data
        this.setupWebSocket();
        
        // Fallback to polling if WebSocket is not available
        setInterval(() => {
            this.updateDashboardData();
        }, 5000); // Update every 5 seconds
    }

    setupWebSocket() {
        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;
            
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
            };
            
            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                // Attempt to reconnect after 5 seconds
                setTimeout(() => this.setupWebSocket(), 5000);
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        } catch (error) {
            console.log('WebSocket not available, using polling');
        }
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'price_update':
                this.updatePriceDisplay(data.price);
                break;
            case 'trade_update':
                this.updateTradeHistory(data.trade);
                break;
            case 'balance_update':
                this.updateBalanceDisplay(data.balance);
                break;
            case 'status_update':
                this.updateBotStatus(data.status);
                break;
        }
    }

    async updateDashboardData() {
        try {
            const response = await fetch('/api/dashboard-data');
            const data = await response.json();
            
            this.updatePriceDisplay(data.current_price);
            this.updateBalanceDisplay(data.balance);
            this.updateTradeHistory(data.recent_trades);
            this.updateBotStatus(data.bot_status);
        } catch (error) {
            console.error('Failed to update dashboard data:', error);
        }
    }

    updatePriceDisplay(price) {
        const priceElement = document.querySelector('.current-price');
        if (priceElement) {
            priceElement.textContent = `$${price.toFixed(2)}`;
        }
    }

    updateBalanceDisplay(balance) {
        const balanceElement = document.querySelector('.account-balance');
        if (balanceElement) {
            balanceElement.textContent = `$${balance.toFixed(2)}`;
        }
    }

    updateTradeHistory(trades) {
        const tradeTable = document.querySelector('.trade-history tbody');
        if (tradeTable && trades.length > 0) {
            const newRow = this.createTradeRow(trades[0]);
            tradeTable.insertBefore(newRow, tradeTable.firstChild);
            
            // Remove old rows if more than 10
            const rows = tradeTable.querySelectorAll('tr');
            if (rows.length > 10) {
                rows[rows.length - 1].remove();
            }
        }
    }

    createTradeRow(trade) {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${trade.symbol}</td>
            <td>${trade.type}</td>
            <td>$${trade.price.toFixed(2)}</td>
            <td>${trade.quantity}</td>
            <td><span class="status status-${trade.status}">${trade.status}</span></td>
            <td>${new Date(trade.timestamp).toLocaleString()}</td>
        `;
        return row;
    }

    updateBotStatus(status) {
        const statusElement = document.querySelector('.bot-status');
        if (statusElement) {
            statusElement.textContent = status;
            statusElement.className = `bot-status status-${status.toLowerCase()}`;
        }
    }

    setupNotifications() {
        // Create notification container if it doesn't exist
        if (!document.querySelector('.notification-container')) {
            const container = document.createElement('div');
            container.className = 'notification-container';
            document.body.appendChild(container);
        }
    }

    showNotification(message, type = 'info', duration = 5000) {
        const container = document.querySelector('.notification-container');
        if (!container) return;

        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <span class="notification-message">${message}</span>
                <button class="notification-close">&times;</button>
            </div>
        `;

        container.appendChild(notification);

        // Auto remove after duration
        setTimeout(() => {
            notification.remove();
        }, duration);

        // Manual close
        const closeBtn = notification.querySelector('.notification-close');
        closeBtn.addEventListener('click', () => {
            notification.remove();
        });
    }

    navigateToSection(sectionId) {
        const section = document.getElementById(sectionId);
        if (section) {
            section.scrollIntoView({ behavior: 'smooth' });
        }
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.tradingDashboard = new TradingDashboard();
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TradingDashboard;
}

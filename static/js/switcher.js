// Switcher JavaScript for Trading Bot Dashboard

class DashboardSwitcher {
    constructor() {
        this.currentView = 'dashboard';
        this.currentTheme = 'light';
        this.init();
    }

    init() {
        this.loadSavedSettings();
        this.setupViewSwitchers();
        this.setupThemeSwitcher();
        this.setupLayoutSwitcher();
        this.setupDataRefreshSwitcher();
    }

    loadSavedSettings() {
        // Load saved theme
        const savedTheme = localStorage.getItem('dashboard-theme');
        if (savedTheme) {
            this.currentTheme = savedTheme;
            this.applyTheme(savedTheme);
        }

        // Load saved view
        const savedView = localStorage.getItem('dashboard-view');
        if (savedView) {
            this.currentView = savedView;
            this.switchView(savedView);
        }

        // Load saved layout
        const savedLayout = localStorage.getItem('dashboard-layout');
        if (savedLayout) {
            this.applyLayout(savedLayout);
        }

        // Load saved refresh rate
        const savedRefreshRate = localStorage.getItem('dashboard-refresh-rate');
        if (savedRefreshRate) {
            this.setRefreshRate(parseInt(savedRefreshRate));
        }
    }

    setupViewSwitchers() {
        const viewSwitchers = document.querySelectorAll('[data-view-switch]');
        viewSwitchers.forEach(switcher => {
            switcher.addEventListener('click', (e) => {
                e.preventDefault();
                const view = switcher.getAttribute('data-view-switch');
                this.switchView(view);
            });
        });
    }

    switchView(view) {
        // Hide all view containers
        const viewContainers = document.querySelectorAll('.view-container');
        viewContainers.forEach(container => {
            container.classList.remove('active');
        });

        // Show selected view
        const targetContainer = document.querySelector(`.view-container[data-view="${view}"]`);
        if (targetContainer) {
            targetContainer.classList.add('active');
        }

        // Update active switcher
        const viewSwitchers = document.querySelectorAll('[data-view-switch]');
        viewSwitchers.forEach(switcher => {
            switcher.classList.remove('active');
        });

        const activeSwitcher = document.querySelector(`[data-view-switch="${view}"]`);
        if (activeSwitcher) {
            activeSwitcher.classList.add('active');
        }

        this.currentView = view;
        localStorage.setItem('dashboard-view', view);

        // Trigger view-specific initialization
        this.initializeView(view);
    }

    initializeView(view) {
        switch (view) {
            case 'dashboard':
                this.initializeDashboard();
                break;
            case 'trades':
                this.initializeTradesView();
                break;
            case 'analytics':
                this.initializeAnalyticsView();
                break;
            case 'settings':
                this.initializeSettingsView();
                break;
        }
    }

    initializeDashboard() {
        // Initialize dashboard-specific components
        this.loadDashboardData();
        this.setupDashboardCharts();
    }

    initializeTradesView() {
        // Initialize trades view
        this.loadTradeHistory();
        this.setupTradeFilters();
    }

    initializeAnalyticsView() {
        // Initialize analytics view
        this.loadAnalyticsData();
        this.setupAnalyticsCharts();
    }

    initializeSettingsView() {
        // Initialize settings view
        this.loadSettings();
    }

    setupThemeSwitcher() {
        const themeSwitchers = document.querySelectorAll('[data-theme-switch]');
        themeSwitchers.forEach(switcher => {
            switcher.addEventListener('click', (e) => {
                e.preventDefault();
                const theme = switcher.getAttribute('data-theme-switch');
                this.switchTheme(theme);
            });
        });

        // Auto theme switcher
        const autoThemeSwitcher = document.querySelector('[data-theme-switch="auto"]');
        if (autoThemeSwitcher) {
            autoThemeSwitcher.addEventListener('click', () => {
                this.enableAutoTheme();
            });
        }
    }

    switchTheme(theme) {
        if (theme === 'auto') {
            this.enableAutoTheme();
            return;
        }

        this.currentTheme = theme;
        this.applyTheme(theme);
        localStorage.setItem('dashboard-theme', theme);

        // Update theme switchers
        const themeSwitchers = document.querySelectorAll('[data-theme-switch]');
        themeSwitchers.forEach(switcher => {
            switcher.classList.remove('active');
        });

        const activeSwitcher = document.querySelector(`[data-theme-switch="${theme}"]`);
        if (activeSwitcher) {
            activeSwitcher.classList.add('active');
        }
    }

    applyTheme(theme) {
        const body = document.body;
        body.setAttribute('data-theme', theme);

        // Update CSS variables for theme
        const root = document.documentElement;
        if (theme === 'dark') {
            root.style.setProperty('--primary-color', '#3b82f6');
            root.style.setProperty('--secondary-color', '#94a3b8');
            root.style.setProperty('--dark-color', '#f8fafc');
            root.style.setProperty('--light-color', '#1e293b');
            root.style.setProperty('--border-color', '#334155');
        } else {
            root.style.setProperty('--primary-color', '#2563eb');
            root.style.setProperty('--secondary-color', '#64748b');
            root.style.setProperty('--dark-color', '#1e293b');
            root.style.setProperty('--light-color', '#f8fafc');
            root.style.setProperty('--border-color', '#e2e8f0');
        }
    }

    enableAutoTheme() {
        // Check system preference
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const theme = prefersDark ? 'dark' : 'light';
        
        this.switchTheme(theme);
        localStorage.setItem('dashboard-theme', 'auto');

        // Listen for system theme changes
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            const newTheme = e.matches ? 'dark' : 'light';
            this.applyTheme(newTheme);
        });
    }

    setupLayoutSwitcher() {
        const layoutSwitchers = document.querySelectorAll('[data-layout-switch]');
        layoutSwitchers.forEach(switcher => {
            switcher.addEventListener('click', (e) => {
                e.preventDefault();
                const layout = switcher.getAttribute('data-layout-switch');
                this.switchLayout(layout);
            });
        });
    }

    switchLayout(layout) {
        const dashboard = document.querySelector('.dashboard-container');
        if (dashboard) {
            // Remove existing layout classes
            dashboard.classList.remove('layout-grid', 'layout-list', 'layout-compact');
            
            // Add new layout class
            dashboard.classList.add(`layout-${layout}`);
        }

        localStorage.setItem('dashboard-layout', layout);

        // Update layout switchers
        const layoutSwitchers = document.querySelectorAll('[data-layout-switch]');
        layoutSwitchers.forEach(switcher => {
            switcher.classList.remove('active');
        });

        const activeSwitcher = document.querySelector(`[data-layout-switch="${layout}"]`);
        if (activeSwitcher) {
            activeSwitcher.classList.add('active');
        }
    }

    applyLayout(layout) {
        const dashboard = document.querySelector('.dashboard-container');
        if (dashboard) {
            dashboard.classList.remove('layout-grid', 'layout-list', 'layout-compact');
            dashboard.classList.add(`layout-${layout}`);
        }
    }

    setupDataRefreshSwitcher() {
        const refreshSwitchers = document.querySelectorAll('[data-refresh-switch]');
        refreshSwitchers.forEach(switcher => {
            switcher.addEventListener('click', (e) => {
                e.preventDefault();
                const rate = parseInt(switcher.getAttribute('data-refresh-switch'));
                this.setRefreshRate(rate);
            });
        });
    }

    setRefreshRate(seconds) {
        // Clear existing interval
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }

        // Set new interval
        if (seconds > 0) {
            this.refreshInterval = setInterval(() => {
                this.refreshData();
            }, seconds * 1000);
        }

        localStorage.setItem('dashboard-refresh-rate', seconds);

        // Update refresh switchers
        const refreshSwitchers = document.querySelectorAll('[data-refresh-switch]');
        refreshSwitchers.forEach(switcher => {
            switcher.classList.remove('active');
        });

        const activeSwitcher = document.querySelector(`[data-refresh-switch="${seconds}"]`);
        if (activeSwitcher) {
            activeSwitcher.classList.add('active');
        }
    }

    async refreshData() {
        try {
            const response = await fetch('/api/dashboard-data');
            const data = await response.json();
            
            // Update dashboard data
            this.updateDashboardData(data);
            
            // Show refresh notification
            this.showRefreshNotification();
        } catch (error) {
            console.error('Failed to refresh data:', error);
        }
    }

    updateDashboardData(data) {
        // Update various dashboard elements
        if (data.current_price) {
            const priceElement = document.querySelector('.current-price');
            if (priceElement) {
                priceElement.textContent = `$${data.current_price.toFixed(2)}`;
            }
        }

        if (data.balance) {
            const balanceElement = document.querySelector('.account-balance');
            if (balanceElement) {
                balanceElement.textContent = `$${data.balance.toFixed(2)}`;
            }
        }

        if (data.bot_status) {
            const statusElement = document.querySelector('.bot-status');
            if (statusElement) {
                statusElement.textContent = data.bot_status;
                statusElement.className = `bot-status status-${data.bot_status.toLowerCase()}`;
            }
        }
    }

    showRefreshNotification() {
        const notification = document.createElement('div');
        notification.className = 'refresh-notification';
        notification.textContent = 'Data refreshed';
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 2000);
    }

    async loadDashboardData() {
        try {
            const response = await fetch('/api/dashboard-data');
            const data = await response.json();
            this.updateDashboardData(data);
        } catch (error) {
            console.error('Failed to load dashboard data:', error);
        }
    }

    async loadTradeHistory() {
        try {
            const response = await fetch('/api/trade-history');
            const trades = await response.json();
            this.updateTradeHistory(trades);
        } catch (error) {
            console.error('Failed to load trade history:', error);
        }
    }

    async loadAnalyticsData() {
        try {
            const response = await fetch('/api/analytics-data');
            const analytics = await response.json();
            this.updateAnalyticsData(analytics);
        } catch (error) {
            console.error('Failed to load analytics data:', error);
        }
    }

    async loadSettings() {
        try {
            const response = await fetch('/api/settings');
            const settings = await response.json();
            this.updateSettingsForm(settings);
        } catch (error) {
            console.error('Failed to load settings:', error);
        }
    }

    updateTradeHistory(trades) {
        const tradeTable = document.querySelector('.trade-history tbody');
        if (tradeTable) {
            tradeTable.innerHTML = '';
            trades.forEach(trade => {
                const row = this.createTradeRow(trade);
                tradeTable.appendChild(row);
            });
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

    updateAnalyticsData(analytics) {
        // Update analytics charts and data
        if (analytics.performance_chart) {
            this.updatePerformanceChart(analytics.performance_chart);
        }
        
        if (analytics.revenue_data) {
            this.updateRevenueData(analytics.revenue_data);
        }
    }

    updateSettingsForm(settings) {
        // Populate settings form with current values
        Object.keys(settings).forEach(key => {
            const input = document.querySelector(`[name="${key}"]`);
            if (input) {
                input.value = settings[key];
            }
        });
    }

    setupDashboardCharts() {
        // Initialize dashboard-specific charts
        const chartElements = document.querySelectorAll('[data-chart]');
        chartElements.forEach(element => {
            const chartType = element.getAttribute('data-chart');
            this.initializeChart(element, chartType);
        });
    }

    setupTradeFilters() {
        // Setup trade history filters
        const filterInputs = document.querySelectorAll('.trade-filter input');
        filterInputs.forEach(input => {
            input.addEventListener('input', (e) => {
                this.filterTrades(e.target.value);
            });
        });
    }

    setupAnalyticsCharts() {
        // Initialize analytics-specific charts
        const analyticsCharts = document.querySelectorAll('[data-analytics-chart]');
        analyticsCharts.forEach(element => {
            const chartType = element.getAttribute('data-analytics-chart');
            this.initializeAnalyticsChart(element, chartType);
        });
    }

    filterTrades(searchTerm) {
        const tradeRows = document.querySelectorAll('.trade-history tbody tr');
        tradeRows.forEach(row => {
            const text = row.textContent.toLowerCase();
            const matches = text.includes(searchTerm.toLowerCase());
            row.style.display = matches ? '' : 'none';
        });
    }

    initializeChart(element, type) {
        // Initialize chart based on type
        if (typeof Chart !== 'undefined') {
            const ctx = element.getContext('2d');
            // Chart initialization logic here
        }
    }

    initializeAnalyticsChart(element, type) {
        // Initialize analytics chart based on type
        if (typeof Chart !== 'undefined') {
            const ctx = element.getContext('2d');
            // Analytics chart initialization logic here
        }
    }

    updatePerformanceChart(data) {
        // Update performance chart with new data
        console.log('Updating performance chart:', data);
    }

    updateRevenueData(data) {
        // Update revenue display with new data
        console.log('Updating revenue data:', data);
    }
}

// Initialize switcher when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.dashboardSwitcher = new DashboardSwitcher();
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DashboardSwitcher;
}

/**
 * URL登録画面のJavaScript
 */

class RegisterManager {
    constructor() {
        this.api = new ApiClient();
        this.currentPageId = null;
        this.statusCheckInterval = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadRecentPages();
    }

    setupEventListeners() {
        const form = document.getElementById('registerForm');
        form.addEventListener('submit', (e) => this.handleSubmit(e));
    }

    async handleSubmit(event) {
        event.preventDefault();
        
        const submitBtn = document.getElementById('submitBtn');
        const spinner = document.getElementById('spinner');
        const url = document.getElementById('url').value.trim();
        const memo = document.getElementById('memo').value.trim();

        if (!url) {
            this.showResult('error', 'URLを入力してください');
            return;
        }

        // ボタン状態変更
        submitBtn.disabled = true;
        spinner.classList.remove('d-none');

        try {
            const response = await this.api.processUrl(url, memo || null);
            
            if (response.status === 'already_exists') {
                this.showResult('warning', `このURLは既に登録済みです（ID: ${response.page_id}）`);
            } else if (['queued', 'prepared', 'processing'].includes(response.status)) {
                this.currentPageId = response.page_id;
                this.showResult('success', 'URL登録が完了しました。処理を開始します...');
                this.startStatusCheck();
            } else {
                this.showResult('success', 'URL登録が完了しました');
            }

            // フォームリセット
            document.getElementById('registerForm').reset();
            
            // 最近の登録を更新
            setTimeout(() => this.loadRecentPages(), 1000);

        } catch (error) {
            console.error('Registration error:', error);
            this.showResult('error', `登録に失敗しました: ${error.message}`);
        } finally {
            submitBtn.disabled = false;
            spinner.classList.add('d-none');
        }
    }

    showResult(type, message) {
        const resultArea = document.getElementById('resultArea');
        const resultAlert = document.getElementById('resultAlert');
        
        resultArea.classList.remove('d-none');
        resultAlert.className = `alert alert-${type === 'error' ? 'danger' : type === 'warning' ? 'warning' : 'success'}`;
        resultAlert.textContent = message;

        if (type === 'success' && this.currentPageId) {
            document.getElementById('processingInfo').classList.remove('d-none');
        } else {
            document.getElementById('processingInfo').classList.add('d-none');
        }
    }

    startStatusCheck() {
        if (!this.currentPageId) return;

        this.stopStatusCheck(false);
        this.updateProgress(10, '処理待ちです...', 'queued');

        this.statusCheckInterval = setInterval(async () => {
            try {
                const status = await this.api.getPageDetail(this.currentPageId);
                this.updateProcessingStatus(status);
            } catch (error) {
                console.error('Status check error:', error);
                this.updateProgress(0, `処理状況を取得できませんでした: ${error.message}`, 'unknown');
                this.stopStatusCheck();
            }
        }, 2000);
    }

    updateProcessingStatus(status) {
        const state = status.status;

        if (state === 'queued') {
            this.updateProgress(10, '処理待ちです...', state);
            return;
        }

        if (state === 'processing') {
            const steps = {
                downloaded: [50, 'AI要約を生成中...'],
                llm_processed: [75, 'ベクトル化処理中...'],
                vectorized: [90, '処理を完了しています...']
            };
            const [percent, text] = steps[status.last_success_step]
                || [25, 'コンテンツを取得中...'];
            this.updateProgress(percent, text, state);
            return;
        }

        if (state === 'completed') {
            this.updateProgress(100, '処理完了！', state);
        } else if (state === 'failed') {
            const reason = status.error_message || '理由を取得できませんでした';
            this.updateProgress(0, `処理に失敗しました: ${reason}`, state);
        } else if (state === 'cancelled') {
            this.updateProgress(0, '処理はキャンセルされました', state);
        } else {
            this.updateProgress(0, `不明な処理状態です: ${state || '値なし'}`, 'unknown');
        }

        this.stopStatusCheck();
    }

    updateProgress(percent, text, state = 'processing') {
        const progressBar = document.getElementById('progressBar');
        const statusText = document.getElementById('statusText');
        
        progressBar.style.width = `${percent}%`;
        progressBar.setAttribute('aria-valuenow', String(percent));
        progressBar.className = `progress-bar progress-bar-striped progress-state-${state}`;
        statusText.textContent = text;

        if (state === 'queued' || state === 'processing') {
            progressBar.classList.add('progress-bar-animated');
        }
    }

    stopStatusCheck(clearPageId = true) {
        if (this.statusCheckInterval) {
            clearInterval(this.statusCheckInterval);
            this.statusCheckInterval = null;
        }
        if (clearPageId) this.currentPageId = null;
    }

    async loadRecentPages() {
        try {
            const response = await this.api.getPages(1, 0, 'created_at', 'desc');
            this.displayRecentPages(response.pages || []);
        } catch (error) {
            console.error('Failed to load recent pages:', error);
            document.getElementById('recentPages').innerHTML = 
                '<div class="text-muted">最近の登録を読み込めませんでした</div>';
        }
    }

    displayRecentPages(pages) {
        const container = document.getElementById('recentPages');
        
        if (pages.length === 0) {
            container.innerHTML = '<div class="text-muted">まだ登録されたページがありません</div>';
            return;
        }

        const recentPages = pages.slice(0, 5);
        container.innerHTML = recentPages.map(page => `
            <div class="d-flex justify-content-between align-items-center border-bottom py-2">
                <div class="flex-grow-1">
                    <div class="fw-medium">${this.escapeHtml(page.title)}</div>
                    <small class="text-muted">${this.escapeHtml(page.url)}</small>
                </div>
                <div class="text-end">
                    <span class="badge bg-${this.getStatusColor(page.status)}">${this.getStatusText(page.status)}</span>
                    <br>
                    <small class="text-muted">${this.formatDate(page.created_at)}</small>
                </div>
            </div>
        `).join('');
    }

    getStatusColor(status) {
        switch (status) {
            case 'completed': return 'success';
            case 'queued': return 'secondary';
            case 'processing': return 'warning';
            case 'failed': return 'danger';
            case 'cancelled': return 'dark';
            default: return 'secondary';
        }
    }

    getStatusText(status) {
        switch (status) {
            case 'completed': return '完了';
            case 'queued': return '待機中';
            case 'processing': return '処理中';
            case 'failed': return '失敗';
            case 'cancelled': return 'キャンセル';
            default: return '不明';
        }
    }

    formatDate(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / (1000 * 60));
        const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffMins < 1) return 'たった今';
        if (diffMins < 60) return `${diffMins}分前`;
        if (diffHours < 24) return `${diffHours}時間前`;
        if (diffDays < 7) return `${diffDays}日前`;
        
        return date.toLocaleDateString('ja-JP');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// ページ読み込み時に初期化
document.addEventListener('DOMContentLoaded', () => {
    new RegisterManager();
});

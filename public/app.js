// =============================================
// LinkedInOS — Dashboard App (Supabase Client)
// =============================================

const API_BASE = '';  // Same origin — api_server.py serves both

const SUPABASE_URL = 'https://zrjnudehpsdjvkkwlurm.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpyam51ZGVocHNkanZra3dsdXJtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI2NTA1NjksImV4cCI6MjA4ODIyNjU2OX0.x26mBSUSkbUnGFzGALFXw_tRDQip7xYbQISeACIHT4g';

// The UMD CDN creates window.supabase with createClient on it
let sb;
try {
    sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
    console.log('[INIT] Supabase client OK');
} catch (e) {
    console.error('[FATAL]', e);
    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('contentArea').innerHTML =
            '<div style="padding:40px;color:#f87171;text-align:center;"><h3>Supabase Init Failed</h3><p>' + e.message + '</p></div>';
    });
}

// ---- STATE ----
let currentClient = null;
let currentTopTab = 'dashboard';
let currentSideTab = 'overview';
let clients = [];
let realtimeChannel = null;

// ---- TAB CONFIG ----
const TOP_TABS = [
    { id: 'dashboard', label: 'Dashboard', icon: 'layout-dashboard' },
    { id: 'competitors', label: 'Competitors', icon: 'users' },
    { id: 'posts', label: 'Scraped Posts', icon: 'file-text' },
    { id: 'drafts', label: 'Drafts', icon: 'edit-3' },
    { id: 'approvals', label: 'Approvals', icon: 'check-circle' },
    { id: 'analytics', label: 'Analytics', icon: 'bar-chart-2' }
];

const SIDE_TABS = {
    'dashboard': [
        { id: 'overview', label: 'Overview' },
        { id: 'clients', label: 'All Clients' },
        { id: 'jobs', label: 'Scrape Jobs' },
        { id: 'settings', label: 'Settings' }
    ],
    'competitors': [
        { id: 'all', label: 'All Competitors' },
        { id: 'add', label: 'Add Competitor' }
    ],
    'posts': [
        { id: 'feed', label: 'Post Feed' },
        { id: 'top', label: 'Top Performers' }
    ],
    'drafts': [
        { id: 'pending', label: 'Pending Review' },
        { id: 'approved', label: 'Approved' },
        { id: 'rejected', label: 'Rejected' },
        { id: 'scheduled', label: 'Scheduled' }
    ],
    'approvals': [
        { id: 'history', label: 'Approval History' }
    ],
    'analytics': [
        { id: 'engagement', label: 'Engagement' },
        { id: 'trends', label: 'Trends' }
    ]
};

// ---- INIT ----
async function init() {
    console.log('[INIT] Starting...');
    try {
        buildTopTabs();
        buildSideTabs();
        console.log('[INIT] Tabs built, loading clients...');
        await loadClients();
        console.log('[INIT] Clients loaded, loading content...');
        await loadContent();
        console.log('[INIT] Content loaded');
        lucide.createIcons();
        setupRealtime();
    } catch (err) {
        console.error('[INIT] Fatal error:', err);
        document.getElementById('contentArea').innerHTML = `
            <div class="empty-state">
                <h3>Connection Error</h3>
                <p>${err.message}</p>
                <p style="font-size:12px;color:var(--text-muted)">Check browser console for details</p>
            </div>`;
    }
}

// ---- REALTIME ----
function setupRealtime() {
    if (realtimeChannel) sb.removeChannel(realtimeChannel);

    realtimeChannel = sb
        .channel('dashboard-updates')
        .on('postgres_changes', { event: '*', schema: 'public', table: 'drafts' }, (payload) => {
            console.log('[REALTIME] Draft update:', payload);
            if (currentTopTab === 'drafts' || currentTopTab === 'dashboard') {
                loadContent();
            }
        })
        .on('postgres_changes', { event: '*', schema: 'public', table: 'approvals' }, (payload) => {
            console.log('[REALTIME] Approval update:', payload);
            if (currentTopTab === 'approvals' || currentTopTab === 'dashboard') {
                loadContent();
            }
        })
        .subscribe();
}

// ---- BUILD UI ----
function buildTopTabs() {
    const container = document.getElementById('topTabs');
    container.innerHTML = TOP_TABS.map(tab => `
        <button onclick="switchTopTab('${tab.id}')" 
            class="top-tab ${tab.id === currentTopTab ? 'active' : ''}">
            <i data-lucide="${tab.icon}" class="icon-sm"></i>
            ${tab.label}
        </button>
    `).join('');
    lucide.createIcons();
}

function buildSideTabs() {
    const container = document.getElementById('sideTabs');
    const tabs = SIDE_TABS[currentTopTab] || [];
    document.getElementById('sidebarTitle').textContent = currentTopTab.toUpperCase();

    container.innerHTML = tabs.map(tab => `
        <button onclick="switchSideTab('${tab.id}')" 
            class="side-tab ${tab.id === currentSideTab ? 'active' : ''}">
            ${tab.label}
        </button>
    `).join('');
}

// ---- NAVIGATION ----
function switchTopTab(tabId) {
    currentTopTab = tabId;
    currentSideTab = SIDE_TABS[tabId]?.[0]?.id || 'overview';
    buildTopTabs();
    buildSideTabs();
    loadContent();
}

function switchSideTab(tabId) {
    currentSideTab = tabId;
    buildSideTabs();
    loadContent();
}

// ---- CLIENT SELECTOR ----
async function loadClients() {
    try {
        const { data, error } = await sb.from('clients').select('*').order('created_at', { ascending: false });
        if (error) { console.error('[loadClients] Supabase error:', error); return; }
        console.log('[loadClients] Loaded', (data || []).length, 'clients');
        clients = data || [];

        const selector = document.getElementById('clientSelector');
        selector.innerHTML = '<option value="">Select Client...</option>' +
            clients.map(c => `<option value="${c.id}">${c.name}${c.niche ? ' (' + c.niche + ')' : ''}</option>`).join('');
    } catch (err) {
        console.error('[loadClients] Exception:', err);
    }
}

function selectClient(clientId) {
    currentClient = clients.find(c => c.id === clientId) || null;
    loadContent();
}

// ---- CONTENT LOADING ----
async function loadContent() {
    const contentArea = document.getElementById('contentArea');
    const pageTitle = document.getElementById('pageTitle');
    const pageActions = document.getElementById('pageActions');

    contentArea.innerHTML = '<div class="loading-state"><div class="spinner"></div><span>Loading...</span></div>';

    const sideTab = SIDE_TABS[currentTopTab]?.find(t => t.id === currentSideTab);
    pageTitle.textContent = sideTab?.label || currentTopTab;
    pageActions.innerHTML = '';

    try {
        if (currentTopTab === 'dashboard') await loadDashboardContent();
        else if (currentTopTab === 'competitors') await loadCompetitorsContent();
        else if (currentTopTab === 'posts') await loadPostsContent();
        else if (currentTopTab === 'drafts') await loadDraftsContent();
        else if (currentTopTab === 'approvals') await loadApprovalsContent();
        else if (currentTopTab === 'analytics') await loadAnalyticsContent();
    } catch (err) {
        contentArea.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${err.message}</p></div>`;
    }

    lucide.createIcons();
}

// ---- DASHBOARD ----
async function loadDashboardContent() {
    const contentArea = document.getElementById('contentArea');

    if (currentSideTab === 'overview') {
        const [clientsRes, competitorsRes, postsRes, draftsRes, jobsRes] = await Promise.all([
            sb.from('clients').select('id', { count: 'exact', head: true }),
            sb.from('competitors').select('id', { count: 'exact', head: true }),
            sb.from('posts').select('id', { count: 'exact', head: true }),
            sb.from('drafts').select('*'),
            sb.from('scrape_jobs').select('*').order('started_at', { ascending: false }).limit(5)
        ]);

        const drafts = draftsRes.data || [];
        const pendingDrafts = drafts.filter(d => d.status === 'pending').length;
        const approvedDrafts = drafts.filter(d => d.status === 'approved').length;

        contentArea.innerHTML = `
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-card-inner">
                        <div class="stat-icon blue"><i data-lucide="building" class="icon-md"></i></div>
                        <div><div class="stat-value">${clientsRes.count || 0}</div><div class="stat-label">Active Clients</div></div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-inner">
                        <div class="stat-icon violet"><i data-lucide="users" class="icon-md"></i></div>
                        <div><div class="stat-value">${competitorsRes.count || 0}</div><div class="stat-label">Competitors Tracked</div></div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-inner">
                        <div class="stat-icon yellow"><i data-lucide="file-text" class="icon-md"></i></div>
                        <div><div class="stat-value">${postsRes.count || 0}</div><div class="stat-label">Posts Scraped</div></div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-inner">
                        <div class="stat-icon orange"><i data-lucide="clock" class="icon-md"></i></div>
                        <div><div class="stat-value">${pendingDrafts}</div><div class="stat-label">Pending Drafts</div></div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-inner">
                        <div class="stat-icon green"><i data-lucide="check-circle" class="icon-md"></i></div>
                        <div><div class="stat-value">${approvedDrafts}</div><div class="stat-label">Approved</div></div>
                    </div>
                </div>
            </div>

            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">Recent Scrape Jobs</span>
                    <span class="panel-link" onclick="switchTopTab('dashboard'); switchSideTab('jobs');">View all →</span>
                </div>
                <div class="panel-body">
                    ${(jobsRes.data || []).length ? (jobsRes.data || []).map(j => `
                        <div class="table-row">
                            <div style="display:flex;align-items:center;gap:8px;">
                                <span class="badge ${j.status === 'completed' ? 'green' : j.status === 'running' ? 'yellow' : j.status === 'failed' ? 'red' : 'blue'}">${j.status}</span>
                                <span style="font-size:var(--text-sm);color:var(--text-secondary)">${j.actor_id || 'Unknown actor'}</span>
                            </div>
                            <span style="font-size:var(--text-xs);color:var(--text-muted)">${j.posts_found || 0} posts · ${new Date(j.started_at).toLocaleString()}</span>
                        </div>
                    `).join('') : '<div class="table-row" style="justify-content:center;color:var(--text-muted);">No scrape jobs yet</div>'}
                </div>
            </div>

            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">Recent Drafts</span>
                    <span class="panel-link" onclick="switchTopTab('drafts')">View all →</span>
                </div>
                <div class="panel-body">
                    ${drafts.slice(0, 5).length ? drafts.slice(0, 5).map(d => `
                        <div class="table-row">
                            <div style="display:flex;align-items:center;gap:8px;">
                                <span class="badge ${d.status === 'approved' ? 'green' : d.status === 'pending' ? 'yellow' : d.status === 'rejected' ? 'red' : 'blue'}">${d.status}</span>
                                <span style="font-size:var(--text-sm);color:var(--text-secondary)">${(d.caption || '').substring(0, 80)}...</span>
                            </div>
                            <span style="font-size:var(--text-xs);color:var(--text-muted)">${new Date(d.created_at).toLocaleString()}</span>
                        </div>
                    `).join('') : '<div class="table-row" style="justify-content:center;color:var(--text-muted);">No drafts yet</div>'}
                </div>
            </div>
        `;
    } else if (currentSideTab === 'clients') {
        document.getElementById('pageActions').innerHTML = `
            <button class="btn-primary" onclick="showModal('newClient')">
                <i data-lucide="plus" class="icon-sm"></i> New Client
            </button>`;

        const { data: clientsList } = await sb.from('clients').select('*').order('created_at', { ascending: false });

        if (!clientsList?.length) {
            contentArea.innerHTML = `
                <div class="empty-state">
                    <i data-lucide="folder-plus" class="empty-icon"></i>
                    <h3>No clients yet</h3>
                    <p>Add your first client to get started</p>
                    <button class="btn-primary" onclick="showModal('newClient')">+ Add Client</button>
                </div>`;
        } else {
            contentArea.innerHTML = `
                <div class="panel">
                    <div class="panel-body">
                        ${clientsList.map(c => `
                            <div class="table-row" style="cursor:pointer" onclick="document.getElementById('clientSelector').value='${c.id}'; selectClient('${c.id}');">
                                <div style="display:flex;align-items:center;gap:12px;">
                                    <div class="avatar">${(c.name || '?')[0].toUpperCase()}</div>
                                    <div>
                                        <div style="font-size:var(--text-sm);font-weight:600;color:white">${c.name}</div>
                                        <div style="font-size:var(--text-xs);color:var(--text-muted)">${c.niche || 'No niche set'}</div>
                                    </div>
                                </div>
                                <span class="badge violet">${c.linkedin_url ? 'LinkedIn ✓' : 'No URL'}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>`;
        }
    } else if (currentSideTab === 'jobs') {
        const { data: jobs } = await sb.from('scrape_jobs').select('*').order('started_at', { ascending: false });

        contentArea.innerHTML = `
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">All Scrape Jobs</span>
                </div>
                <div class="panel-body">
                    ${(jobs || []).length ? jobs.map(j => `
                        <div class="table-row">
                            <div style="display:flex;align-items:center;gap:10px;">
                                <span class="badge ${j.status === 'completed' ? 'green' : j.status === 'running' ? 'yellow' : j.status === 'failed' ? 'red' : 'blue'}">${j.status}</span>
                                <div>
                                    <div style="font-size:var(--text-sm);color:white">${j.actor_id || 'Actor'}</div>
                                    <div style="font-size:var(--text-xs);color:var(--text-muted)">${j.error_message || `${j.posts_found || 0} posts found`}</div>
                                </div>
                            </div>
                            <div style="text-align:right">
                                <div style="font-size:var(--text-xs);color:var(--text-muted)">${new Date(j.started_at).toLocaleString()}</div>
                                ${j.completed_at ? `<div style="font-size:var(--text-xs);color:var(--text-muted)">Completed: ${new Date(j.completed_at).toLocaleString()}</div>` : ''}
                            </div>
                        </div>
                    `).join('') : '<div class="table-row" style="justify-content:center;color:var(--text-muted);">No scrape jobs yet. Run <code>python execution/scrape_apify.py --test</code> to start.</div>'}
                </div>
            </div>`;
    } else if (currentSideTab === 'settings') {
        await loadSettingsContent();
    }
}

// ---- SETTINGS (Templates) ----
async function loadSettingsContent() {
    const contentArea = document.getElementById('contentArea');
    if (!currentClient) {
        contentArea.innerHTML = `<div class="empty-state"><h3>Template Settings</h3><p>Select a client first</p></div>`;
        return;
    }

    const { data: templates } = await sb.from('design_templates').select('*').eq('client_id', currentClient.id).order('created_at', { ascending: true });

    contentArea.innerHTML = `
        <div class="panel" style="max-width: 800px;">
            <div class="panel-header">
                <span class="panel-title">Design Templates for ${escapeHtml(currentClient.name)}</span>
            </div>
            <div class="panel-body">
                <p style="color:#9CA3AF;font-size:13px;margin-bottom:20px;">
                    Customize the text prompts and reference images passed to Gemini for image generation.
                </p>
                ${(templates || []).length ? templates.map(t => `
                    <div style="background:#0D1117;border:1px solid #1F2937;border-radius:10px;padding:16px;margin-bottom:16px;">
                        <h4 style="color:#E5E7EB;margin:0 0 12px 0;font-size:15px;">${escapeHtml(t.name)}</h4>
                        <div class="form-group">
                            <label class="form-label" style="font-size:12px;">Style Prompt (Text instructions for Gemini)</label>
                            <textarea id="tpl_text_${t.id}" class="form-input" rows="3" style="font-size:13px;">${escapeHtml(t.style_prompt || '')}</textarea>
                        </div>
                        <div class="form-group" style="margin-top:12px;">
                            <label class="form-label" style="font-size:12px;">Reference Image URL (Optional - passed to Gemini Vision)</label>
                            <input type="text" id="tpl_img_${t.id}" class="form-input" placeholder="https://example.com/reference.jpg" value="${escapeHtml(t.reference_image_url || '')}" style="font-size:13px;">
                            ${t.reference_image_url ? `<div style="margin-top:8px;"><img src="${escapeHtml(t.reference_image_url)}" style="max-height:80px;border-radius:6px;border:1px solid #374151;"></div>` : ''}
                        </div>
                        <button class="btn-primary btn-sm" onclick="saveTemplate('${t.id}')" style="margin-top:8px;" id="btn_save_${t.id}">
                            Save Changes
                        </button>
                    </div>
                `).join('') : '<div class="empty-state"><p>No templates generated yet.</p></div>'}
            </div>
        </div>
    `;
}

// Global func to handle saving template edits
window.saveTemplate = async function (templateId) {
    const textVal = document.getElementById(`tpl_text_${templateId}`).value.trim();
    const imgVal = document.getElementById(`tpl_img_${templateId}`).value.trim();
    const btn = document.getElementById(`btn_save_${templateId}`);

    btn.disabled = true;
    btn.textContent = 'Saving...';

    const { error } = await sb.from('design_templates').update({
        style_prompt: textVal || null,
        reference_image_url: imgVal || null,
        updated_at: new Date().toISOString()
    }).eq('id', templateId);

    if (error) {
        showToast('❌ Error saving template: ' + error.message, 'error');
        btn.disabled = false;
        btn.textContent = 'Save Changes';
    } else {
        showToast('✅ Template updated successfully!', 'success');
        loadSettingsContent(); // reload to show the image preview
    }
}

// ---- COMPETITORS ----
async function loadCompetitorsContent() {
    const contentArea = document.getElementById('contentArea');

    if (currentSideTab === 'add') {
        document.getElementById('pageTitle').textContent = 'Add Competitor';
        contentArea.innerHTML = `
            <div style="max-width:520px;">
                <div class="panel">
                    <div class="panel-header"><span class="panel-title">Add a Competitor</span></div>
                    <div style="padding:24px;">
                        ${!currentClient ? '<div class="badge yellow" style="margin-bottom:16px;">⚠ Select a client first</div>' : ''}
                        <div class="form-group">
                            <label class="form-label">Competitor Name</label>
                            <input type="text" id="comp_name" class="form-input" placeholder="e.g. Gary Vaynerchuk">
                        </div>
                        <div class="form-group">
                            <label class="form-label">LinkedIn Profile URL</label>
                            <input type="text" id="comp_url" class="form-input" placeholder="https://www.linkedin.com/in/garyvaynerchuk/">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Niche</label>
                            <input type="text" id="comp_niche" class="form-input" placeholder="e.g. marketing, entrepreneurship">
                        </div>
                        <button class="btn-primary" onclick="addCompetitor()" ${!currentClient ? 'disabled style="opacity:0.5"' : ''}>
                            <i data-lucide="plus" class="icon-sm"></i> Add Competitor
                        </button>
                    </div>
                </div>
            </div>`;
    } else {
        let query = sb.from('competitors').select('*').order('created_at', { ascending: false });
        if (currentClient) query = query.eq('client_id', currentClient.id);
        const { data: comps } = await query;

        document.getElementById('pageActions').innerHTML = `
            <button class="btn-primary" onclick="switchSideTab('add')">
                <i data-lucide="plus" class="icon-sm"></i> Add Competitor
            </button>`;

        if (!comps?.length) {
            contentArea.innerHTML = `
                <div class="empty-state">
                    <i data-lucide="users" class="empty-icon"></i>
                    <h3>No competitors tracked</h3>
                    <p>Add competitors to start scraping their top posts</p>
                    <button class="btn-primary" onclick="switchSideTab('add')">+ Add Competitor</button>
                </div>`;
        } else {
            contentArea.innerHTML = `
                <div class="panel">
                    <div class="panel-body">
                        ${comps.map(c => `
                            <div class="table-row">
                                <div style="display:flex;align-items:center;gap:12px;">
                                    <div class="avatar" style="background:linear-gradient(135deg,#3B82F6,#8B5CF6)">${(c.name || '?')[0].toUpperCase()}</div>
                                    <div>
                                        <div style="font-size:var(--text-sm);font-weight:600;color:white">${c.name}</div>
                                        <div style="font-size:var(--text-xs);color:var(--text-muted)">${c.linkedin_url || 'No URL'}</div>
                                    </div>
                                </div>
                                <div style="display:flex;align-items:center;gap:8px;">
                                    <span class="badge violet">${c.niche || 'No niche'}</span>
                                    <div style="display:flex;align-items:center;background:#1F2937;border-radius:4px;padding:2px;border:1px solid #374151;">
                                        <input type="number" id="limit_${c.id}" value="20" title="Max posts to fetch" style="width:40px;background:transparent;border:none;color:white;font-size:12px;outline:none;text-align:center;" min="1" max="100">
                                    </div>
                                    <button class="btn-secondary btn-sm" onclick="scrapeCompetitor(this, '${c.id}', '${c.linkedin_url}', '${c.client_id}', document.getElementById('limit_${c.id}').value)">
                                        <i data-lucide="download" class="icon-xs"></i> Scrape
                                    </button>
                                    <button class="btn-secondary btn-sm" onclick="showPostSelector('${c.id}', '${c.client_id}')" style="border-color:#10B981;color:#10B981;">
                                        <i data-lucide="check-square" class="icon-xs"></i> Select Posts
                                    </button>
                                    <button class="btn-primary btn-sm" onclick="fullPipeline(this, '${c.id}', '${c.linkedin_url}', '${c.client_id}', document.getElementById('limit_${c.id}').value)">
                                        <i data-lucide="sparkles" class="icon-xs"></i> Full Pipeline
                                    </button>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>`;
        }
    }
}

async function addCompetitor() {
    if (!currentClient) { alert('Please select a client first'); return; }
    const name = document.getElementById('comp_name').value.trim();
    const url = document.getElementById('comp_url').value.trim();
    const niche = document.getElementById('comp_niche').value.trim();
    if (!name || !url) { alert('Name and LinkedIn URL are required'); return; }

    const { error } = await sb.from('competitors').insert({
        client_id: currentClient.id,
        name, linkedin_url: url, niche
    });

    if (error) { alert('Error: ' + error.message); return; }
    switchSideTab('all');
}

async function scrapeCompetitor(btn, compId, linkedinUrl, clientId, maxPosts = 20) {
    if (!confirm(`Scrape posts from ${linkedinUrl}?`)) return;

    const originalText = btn.innerHTML;
    btn.innerHTML = '<div class="spinner"></div> Scraping...';
    btn.disabled = true;

    showToast('🔄 Scraping posts... this takes ~30s', 'info');

    try {
        const resp = await fetch(`${API_BASE}/api/scrape`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                profile_url: linkedinUrl,
                client_id: clientId,
                competitor_id: compId,
                max_items: parseInt(maxPosts) || 20
            })
        });
        const data = await resp.json();
        if (data.success) {
            showToast(`✅ Scraped ${data.posts_scraped} posts, inserted ${data.posts_inserted}`, 'success');
            loadContent();
        } else {
            showToast(`❌ ${data.error}`, 'error');
        }
    } catch (err) {
        showToast(`❌ Scrape failed: ${err.message}`, 'error');
    }

    btn.innerHTML = originalText;
    btn.disabled = false;
}

// ---- POSTS ----
async function loadPostsContent() {
    const contentArea = document.getElementById('contentArea');

    let query = sb.from('posts').select('*');
    if (currentClient) query = query.eq('client_id', currentClient.id);
    if (currentSideTab === 'top') {
        query = query.order('engagement_score', { ascending: false }).limit(20);
    } else {
        query = query.order('scraped_at', { ascending: false }).limit(50);
    }

    const { data: posts } = await query;

    if (!posts?.length) {
        contentArea.innerHTML = `
            <div class="empty-state">
                <i data-lucide="file-text" class="empty-icon"></i>
                <h3>No posts scraped yet</h3>
                <p>Run the scraper to fetch competitor posts</p>
            </div>`;
        return;
    }

    contentArea.innerHTML = `
        <div class="post-feed">
            ${posts.map(p => `
                <div class="post-card">
                    <div class="post-card-header">
                        <div class="post-card-author-avatar">${(p.author_name || '?')[0].toUpperCase()}</div>
                        <div>
                            <div class="post-card-author-name">${p.author_name || 'Unknown'}</div>
                            <div class="post-card-author-meta">${p.post_date ? new Date(p.post_date).toLocaleDateString() : 'Date unknown'} · ${p.post_type || 'text'}</div>
                        </div>
                    </div>
                    <div class="post-card-body">
                        <div class="post-card-content">${escapeHtml(p.content || 'No content')}</div>
                        ${p.media_url ? `<img class="post-card-image" src="${p.media_url}" alt="Post media" onerror="this.style.display='none'">` : ''}
                    </div>
                    <div class="post-card-footer">
                        <div class="post-metrics">
                            <span class="post-metric"><i data-lucide="thumbs-up" class="icon-xs"></i> ${p.likes || 0}</span>
                            <span class="post-metric"><i data-lucide="message-circle" class="icon-xs"></i> ${p.comments || 0}</span>
                            <span class="post-metric"><i data-lucide="share-2" class="icon-xs"></i> ${p.shares || 0}</span>
                            <span class="post-metric"><i data-lucide="zap" class="icon-xs"></i> ${Math.round(p.engagement_score || 0)}</span>
                        </div>
                        <div class="post-actions">
                            <button class="btn-secondary btn-sm" onclick="generateDraftFromPost('${p.id}')">
                                <i data-lucide="sparkles" class="icon-xs"></i> Generate Draft
                            </button>
                        </div>
                    </div>
                </div>
            `).join('')}
        </div>`;
}

async function generateDraftFromPost(postId) {
    if (!currentClient) { showToast('⚠️ Select a client first', 'error'); return; }
    showToast('🤖 Generating AI draft + image... this takes ~30s', 'info');

    try {
        const resp = await fetch(`${API_BASE}/api/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                post_id: postId,
                client_id: currentClient.id
            })
        });
        const data = await resp.json();
        if (data.success) {
            showToast(`✅ Draft created! ${data.has_image ? '(with image)' : '(text only)'}`, 'success');
            switchTopTab('drafts');
        } else {
            showToast(`❌ ${data.error}`, 'error');
        }
    } catch (err) {
        showToast(`❌ Generation failed: ${err.message}`, 'error');
    }
}

// ---- DRAFTS ----
async function loadDraftsContent() {
    const contentArea = document.getElementById('contentArea');

    let query = sb.from('drafts').select('*');
    if (currentClient) query = query.eq('client_id', currentClient.id);
    if (currentSideTab !== 'pending') {
        const statusMap = { 'approved': 'approved', 'rejected': 'rejected', 'scheduled': 'scheduled' };
        if (statusMap[currentSideTab]) query = query.eq('status', statusMap[currentSideTab]);
    } else {
        query = query.eq('status', 'pending');
    }
    query = query.order('created_at', { ascending: false });

    const { data: drafts } = await query;

    if (!drafts?.length) {
        contentArea.innerHTML = `
            <div class="empty-state">
                <i data-lucide="edit-3" class="empty-icon"></i>
                <h3>No ${currentSideTab} drafts</h3>
                <p>Generate drafts from scraped posts to review them here</p>
            </div>`;
        return;
    }

    contentArea.innerHTML = `
        <div class="post-feed">
            ${drafts.map(d => `
                <div class="draft-card">
                    <div class="draft-card-body">
                        <div class="draft-caption">${escapeHtml(d.caption || '')}</div>
                        ${d.image_url ? `<img class="post-card-image" src="${d.image_url}" alt="Generated image" style="margin-top:12px;" onerror="this.style.display='none'">` : ''}
                    </div>
                    <div class="draft-card-footer">
                        <span class="draft-status ${d.status}">${d.status}</span>
                        <div style="display:flex;gap:6px;">
                            ${d.status === 'pending' ? `
                                <button class="btn-secondary btn-sm" onclick="showRepurposeView('${d.id}')" style="border-color:#818CF8;color:#818CF8;">
                                    <i data-lucide="eye" class="icon-xs"></i> View
                                </button>
                                <button class="btn-approve" onclick="approveDraft('${d.id}')">
                                    <i data-lucide="thumbs-up" class="icon-xs"></i> Approve
                                </button>
                                <button class="btn-reject" onclick="rejectDraft('${d.id}')">
                                    <i data-lucide="thumbs-down" class="icon-xs"></i> Reject
                                </button>
                                <button class="btn-secondary btn-sm" onclick="commentOnDraft('${d.id}')">
                                    <i data-lucide="message-circle" class="icon-xs"></i>
                                </button>
                            ` : d.status === 'approved' ? `
                                <button class="btn-primary btn-sm" onclick="scheduleDraft('${d.id}')">
                                    <i data-lucide="send" class="icon-xs"></i> Schedule
                                </button>
                                <button class="btn-secondary btn-sm" onclick="markAsPosted('${d.id}')" style="border-color:#10B981;color:#10B981;">
                                    <i data-lucide="check" class="icon-xs"></i> Mark Posted
                                </button>
                            ` : ''}
                            <button class="btn-secondary btn-sm" onclick="copyDraftText('${d.id}')" title="Copy Text" style="margin-left:auto;">
                                <i data-lucide="copy" class="icon-xs"></i>
                            </button>
                            ${d.image_url ? `
                            <button class="btn-secondary btn-sm" onclick="downloadImage('${d.image_url}')" title="Download Image">
                                <i data-lucide="download" class="icon-xs"></i>
                            </button>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `).join('')}
        </div>`;
}

async function approveDraft(draftId) {
    await sb.from('drafts').update({ status: 'approved', updated_at: new Date().toISOString() }).eq('id', draftId);
    await sb.from('approvals').insert({ draft_id: draftId, action: 'approve' });
    loadContent();
}

async function rejectDraft(draftId) {
    const reason = prompt('Reason for rejection (optional):');
    await sb.from('drafts').update({ status: 'rejected', updated_at: new Date().toISOString() }).eq('id', draftId);
    await sb.from('approvals').insert({ draft_id: draftId, action: 'reject', comment: reason || null });
    loadContent();
}

async function commentOnDraft(draftId) {
    const comment = prompt('Add a comment:');
    if (!comment) return;
    await sb.from('approvals').insert({ draft_id: draftId, action: 'comment', comment });
    alert('Comment added!');
}

async function markAsPosted(draftId) {
    if (!confirm('Mark this draft as posted?')) return;
    await sb.from('drafts').update({ status: 'posted', updated_at: new Date().toISOString() }).eq('id', draftId);
    showToast('✅ Marked as posted', 'success');
    loadContent();
}

async function copyDraftText(draftId) {
    const { data } = await sb.from('drafts').select('caption').eq('id', draftId).single();
    if (data && data.caption) {
        navigator.clipboard.writeText(data.caption);
        showToast('✅ Text copied to clipboard', 'success');
    }
}

function downloadImage(url) {
    // Open image in new tab to download (fixes CORS cross-origin download issues)
    window.open(url, '_blank');
}

function scheduleDraft(draftId) {
    showToast('📅 Scheduling is coming soon (configure Make.com webhook)', 'info');
}

// ---- APPROVALS ----
async function loadApprovalsContent() {
    const contentArea = document.getElementById('contentArea');

    const { data: approvalsList } = await sb
        .from('approvals')
        .select('*, drafts(caption, status)')
        .order('created_at', { ascending: false })
        .limit(50);

    if (!approvalsList?.length) {
        contentArea.innerHTML = `
            <div class="empty-state">
                <i data-lucide="check-circle" class="empty-icon"></i>
                <h3>No approvals yet</h3>
                <p>Approve or reject drafts to see the history here</p>
            </div>`;
        return;
    }

    contentArea.innerHTML = `
        <div class="panel">
            <div class="panel-header"><span class="panel-title">Approval History</span></div>
            <div class="panel-body">
                ${approvalsList.map(a => `
                    <div class="table-row">
                        <div style="display:flex;align-items:center;gap:10px;">
                            <span class="badge ${a.action === 'approve' ? 'green' : a.action === 'reject' ? 'red' : 'blue'}">
                                ${a.action === 'approve' ? '👍' : a.action === 'reject' ? '👎' : '💬'} ${a.action}
                            </span>
                            <span style="font-size:var(--text-sm);color:var(--text-secondary)">${(a.drafts?.caption || '').substring(0, 80)}...</span>
                        </div>
                        <div style="text-align:right">
                            ${a.comment ? `<div style="font-size:var(--text-xs);color:var(--text-muted);font-style:italic">"${a.comment}"</div>` : ''}
                            <div style="font-size:var(--text-xs);color:var(--text-muted)">${new Date(a.created_at).toLocaleString()}</div>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>`;
}

// ---- ANALYTICS ----
async function loadAnalyticsContent() {
    const contentArea = document.getElementById('contentArea');

    let query = sb.from('posts').select('likes, comments, shares, engagement_score, post_date, post_type');
    if (currentClient) query = query.eq('client_id', currentClient.id);
    const { data: posts } = await query;

    if (!posts?.length) {
        contentArea.innerHTML = `
            <div class="empty-state">
                <i data-lucide="bar-chart-2" class="empty-icon"></i>
                <h3>No data yet</h3>
                <p>Scrape some posts to see engagement analytics</p>
            </div>`;
        return;
    }

    const totalLikes = posts.reduce((s, p) => s + (p.likes || 0), 0);
    const totalComments = posts.reduce((s, p) => s + (p.comments || 0), 0);
    const avgEngagement = posts.reduce((s, p) => s + (p.engagement_score || 0), 0) / posts.length;

    const typeCounts = {};
    posts.forEach(p => { typeCounts[p.post_type || 'text'] = (typeCounts[p.post_type || 'text'] || 0) + 1; });

    contentArea.innerHTML = `
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-card-inner">
                    <div class="stat-icon blue"><i data-lucide="thumbs-up" class="icon-md"></i></div>
                    <div><div class="stat-value">${totalLikes.toLocaleString()}</div><div class="stat-label">Total Likes</div></div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-card-inner">
                    <div class="stat-icon violet"><i data-lucide="message-circle" class="icon-md"></i></div>
                    <div><div class="stat-value">${totalComments.toLocaleString()}</div><div class="stat-label">Total Comments</div></div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-card-inner">
                    <div class="stat-icon green"><i data-lucide="zap" class="icon-md"></i></div>
                    <div><div class="stat-value">${Math.round(avgEngagement).toLocaleString()}</div><div class="stat-label">Avg. Engagement Score</div></div>
                </div>
            </div>
        </div>

        <div class="chart-container">
            <div class="chart-title">Post Type Distribution</div>
            <canvas id="typeChart" height="200"></canvas>
        </div>

        <div class="chart-container">
            <div class="chart-title">Engagement by Post</div>
            <canvas id="engagementChart" height="200"></canvas>
        </div>
    `;

    // Render charts
    setTimeout(() => {
        // Type distribution doughnut
        const typeCtx = document.getElementById('typeChart')?.getContext('2d');
        if (typeCtx) {
            new Chart(typeCtx, {
                type: 'doughnut',
                data: {
                    labels: Object.keys(typeCounts),
                    datasets: [{
                        data: Object.values(typeCounts),
                        backgroundColor: ['#8B5CF6', '#3B82F6', '#34D399', '#FBBF24', '#FB923C'],
                        borderWidth: 0
                    }]
                },
                options: {
                    plugins: { legend: { labels: { color: '#9CA3AF', font: { family: 'Plus Jakarta Sans' } } } },
                    cutout: '65%'
                }
            });
        }

        // Engagement bar chart (top 15 posts)
        const engCtx = document.getElementById('engagementChart')?.getContext('2d');
        if (engCtx) {
            const sorted = [...posts].sort((a, b) => (b.engagement_score || 0) - (a.engagement_score || 0)).slice(0, 15);
            new Chart(engCtx, {
                type: 'bar',
                data: {
                    labels: sorted.map((_, i) => `Post ${i + 1}`),
                    datasets: [{
                        label: 'Engagement Score',
                        data: sorted.map(p => p.engagement_score || 0),
                        backgroundColor: 'rgba(139, 92, 246, 0.6)',
                        borderColor: '#8B5CF6',
                        borderWidth: 1,
                        borderRadius: 4,
                    }]
                },
                options: {
                    scales: {
                        y: { ticks: { color: '#6B7280' }, grid: { color: '#1F2937' } },
                        x: { ticks: { color: '#6B7280' }, grid: { display: false } }
                    },
                    plugins: { legend: { labels: { color: '#9CA3AF', font: { family: 'Plus Jakarta Sans' } } } }
                }
            });
        }
    }, 100);
}

// ---- MODAL ----
function showModal(type, extraData) {
    const overlay = document.getElementById('modalOverlay');
    const content = document.getElementById('modalContent');
    overlay.classList.add('visible');

    if (type === 'newClient') {
        content.innerHTML = `
            <div class="modal-header">
                <span class="modal-title">New Client</span>
                <button class="modal-close" onclick="closeModal()">
                    <i data-lucide="x" class="icon-sm"></i>
                </button>
            </div>
            <div class="modal-body" style="max-height:70vh;overflow-y:auto;">
                <div class="form-group">
                    <label class="form-label">Client Name <span style="color:#f87171">*</span></label>
                    <input type="text" id="new_client_name" class="form-input" placeholder="e.g. John's Marketing Agency">
                </div>
                <div class="form-group">
                    <label class="form-label">LinkedIn URL</label>
                    <input type="text" id="new_client_linkedin" class="form-input" placeholder="https://www.linkedin.com/in/johndoe/">
                </div>
                <div class="form-group">
                    <label class="form-label">Niche <span style="color:#f87171">*</span></label>
                    <input type="text" id="new_client_niche" class="form-input" placeholder="e.g. SaaS growth marketing, B2B sales coaching">
                </div>

                <div style="border-top:1px solid #1F2937;margin:20px 0;padding-top:16px;">
                    <label class="form-label" style="margin-bottom:8px;">
                        <i data-lucide="mic" class="icon-sm" style="display:inline;vertical-align:middle;margin-right:4px;"></i>
                        Sample Posts (2 min, 5 max — for voice analysis)
                    </label>
                    <p style="color:#6B7280;font-size:12px;margin-bottom:12px;">
                        Paste their LinkedIn posts so we can analyze their writing style. These are optional but improve caption quality significantly.
                    </p>
                    <div id="samplePostsContainer">
                        <div class="form-group" style="margin-bottom:8px;">
                            <textarea class="form-input sample-post-input" rows="3" placeholder="Paste post 1 here..."></textarea>
                        </div>
                        <div class="form-group" style="margin-bottom:8px;">
                            <textarea class="form-input sample-post-input" rows="3" placeholder="Paste post 2 here..."></textarea>
                        </div>
                    </div>
                    <button class="btn-secondary" onclick="addSamplePostField()" style="font-size:12px;padding:4px 12px;">
                        + Add another post
                    </button>
                </div>

                <div style="border-top:1px solid #1F2937;margin:20px 0;padding-top:16px;">
                    <label class="form-label" style="margin-bottom:8px;">
                        <i data-lucide="palette" class="icon-sm" style="display:inline;vertical-align:middle;margin-right:4px;"></i>
                        Design Template
                    </label>
                    <div style="display:flex;gap:8px;flex-wrap:wrap;">
                        <label class="template-option" style="display:flex;align-items:center;gap:6px;padding:8px 14px;border:1px solid #374151;border-radius:8px;cursor:pointer;font-size:13px;">
                            <input type="radio" name="template_choice" value="generate" checked> Generate templates for me
                        </label>
                        <label class="template-option" style="display:flex;align-items:center;gap:6px;padding:8px 14px;border:1px solid #374151;border-radius:8px;cursor:pointer;font-size:13px;">
                            <input type="radio" name="template_choice" value="skip"> Skip for now
                        </label>
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn-secondary" onclick="closeModal()">Cancel</button>
                <button class="btn-primary" onclick="createClient()" id="createClientBtn">
                    <i data-lucide="sparkles" class="icon-sm"></i> Create & Discover Competitors
                </button>
            </div>`;
    } else if (type === 'competitors') {
        showCompetitorDiscoveryModal(extraData);
        return;
    } else if (type === 'repurpose') {
        showRepurposeView(extraData);
        return;
    }

    lucide.createIcons();
}

function addSamplePostField() {
    const container = document.getElementById('samplePostsContainer');
    const count = container.querySelectorAll('.sample-post-input').length;
    if (count >= 5) { showToast('Maximum 5 sample posts', 'error'); return; }
    const div = document.createElement('div');
    div.className = 'form-group';
    div.style.marginBottom = '8px';
    div.innerHTML = `<textarea class="form-input sample-post-input" rows="3" placeholder="Paste post ${count + 1} here..."></textarea>`;
    container.appendChild(div);
}

function closeModal() {
    document.getElementById('modalOverlay').classList.remove('visible');
}

async function createClient() {
    const name = document.getElementById('new_client_name').value.trim();
    const linkedin = document.getElementById('new_client_linkedin').value.trim();
    const niche = document.getElementById('new_client_niche').value.trim();
    const templateChoice = document.querySelector('input[name="template_choice"]:checked')?.value || 'skip';

    if (!name) { showToast('Client name is required', 'error'); return; }
    if (!niche) { showToast('Niche is required for competitor discovery', 'error'); return; }

    // Collect sample posts
    const postInputs = document.querySelectorAll('.sample-post-input');
    const samplePosts = Array.from(postInputs).map(el => el.value.trim()).filter(t => t.length > 20);

    // Disable button
    const btn = document.getElementById('createClientBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Creating...';

    try {
        // Step 1: Insert client
        const { data, error } = await sb.from('clients').insert({
            name,
            linkedin_url: linkedin || null,
            niche: niche || null,
            sample_posts: samplePosts.length >= 2 ? samplePosts : null,
        }).select();

        if (error) { showToast('Error: ' + error.message, 'error'); btn.disabled = false; btn.textContent = 'Retry'; return; }
        const clientId = data[0].id;

        // Step 2: Voice analysis (if 2+ posts provided)
        if (samplePosts.length >= 2) {
            btn.innerHTML = '<span class="spinner"></span> Analyzing voice...';
            try {
                const voiceResp = await fetch(`${API_BASE}/api/analyze-voice`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ client_id: clientId, sample_posts: samplePosts })
                });
                const voiceData = await voiceResp.json();
                if (voiceData.success) showToast('✅ Voice analyzed: ' + (voiceData.voice_summary?.tone || 'done'), 'success');
            } catch (e) { console.warn('Voice analysis failed:', e); }
        }

        // Step 3: Generate templates (if selected)
        if (templateChoice === 'generate') {
            btn.innerHTML = '<span class="spinner"></span> Generating templates...';
            try {
                const tplResp = await fetch(`${API_BASE}/api/generate-templates`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ niche, client_id: clientId })
                });
                const tplData = await tplResp.json();
                if (tplData.success) showToast(`✅ ${tplData.templates.length} design templates created`, 'success');
            } catch (e) { console.warn('Template generation failed:', e); }
        }

        // Step 4: Update app state
        closeModal();
        await loadClients();
        document.getElementById('clientSelector').value = clientId;
        selectClient(clientId);

        // Step 5: Auto-trigger competitor discovery
        showToast('🔍 Discovering competitors...', 'info');
        const discoverResp = await fetch(`${API_BASE}/api/discover-competitors`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ niche, sample_posts: samplePosts, limit: 12 })
        });
        const discoverData = await discoverResp.json();
        if (discoverData.success && discoverData.candidates?.length) {
            showToast(`🟢 Found ${discoverData.count} competitor candidates`, 'success');
            showModal('competitors', { candidates: discoverData.candidates, clientId, niche });
        } else {
            showToast('No competitors found — try adding them manually', 'error');
            loadContent();
        }
    } catch (err) {
        showToast('❌ Error: ' + err.message, 'error');
        btn.disabled = false;
        btn.textContent = 'Retry';
    }
}

// ---- COMPETITOR DISCOVERY MODAL ----
function showCompetitorDiscoveryModal(data) {
    const { candidates, clientId, niche } = data;
    const overlay = document.getElementById('modalOverlay');
    const content = document.getElementById('modalContent');
    overlay.classList.add('visible');

    const qualityBadge = (q) => {
        const colors = { high: '#10B981', medium: '#F59E0B', low: '#EF4444' };
        const icons = { high: '🟢', medium: '🟡', low: '🔴' };
        return `<span style="color:${colors[q]};font-size:11px;font-weight:600;">${icons[q]} ${q.toUpperCase()}</span>`;
    };

    content.innerHTML = `
        <div class="modal-header">
            <span class="modal-title">Suggested Competitors — ${niche}</span>
            <button class="modal-close" onclick="closeModal()">
                <i data-lucide="x" class="icon-sm"></i>
            </button>
        </div>
        <div class="modal-body" style="max-height:65vh;overflow-y:auto;">
            <p style="color:#9CA3AF;font-size:13px;margin-bottom:16px;">
                Select competitors to track. We'll scrape their top posts for repurposing.
            </p>
            <div style="margin-bottom:12px;">
                <button class="btn-secondary" onclick="toggleAllCompetitors(true)" style="font-size:12px;padding:4px 10px;margin-right:6px;">Select All</button>
                <button class="btn-secondary" onclick="toggleAllCompetitors(false)" style="font-size:12px;padding:4px 10px;">Deselect All</button>
            </div>
            <div id="competitorCandidates" style="display:grid;gap:10px;">
                ${candidates.map((c, i) => `
                    <label style="display:flex;align-items:flex-start;gap:12px;padding:12px;background:#0D1117;border:1px solid #1F2937;border-radius:10px;cursor:pointer;transition:border-color 0.2s;"
                           onmouseenter="this.style.borderColor='#6366F1'"
                           onmouseleave="this.style.borderColor='#1F2937'">
                        <input type="checkbox" class="comp-checkbox" value="${i}" data-url="${c.linkedin_url}" checked style="margin-top:3px;">
                        <div style="flex:1;min-width:0;">
                            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                                <span style="font-weight:600;font-size:14px;color:#F3F4F6;">${escapeHtml(c.title_from_google || c.linkedin_username)}</span>
                                ${qualityBadge(c.quality || 'medium')}
                            </div>
                            <div style="font-size:12px;color:#6B7280;margin-bottom:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                                ${escapeHtml((c.description_from_google || '').substring(0, 120))}
                            </div>
                            <div style="font-size:11px;color:#4B5563;">
                                ${(c.reasons || []).map(r => `<span style="background:#1F2937;padding:2px 6px;border-radius:4px;margin-right:4px;">${escapeHtml(r)}</span>`).join('')}
                            </div>
                            <a href="${c.linkedin_url}" target="_blank" style="font-size:11px;color:#6366F1;text-decoration:none;">
                                ${escapeHtml(c.linkedin_url)}
                            </a>
                        </div>
                    </label>
                `).join('')}
            </div>
        </div>
        <div class="modal-footer">
            <button class="btn-secondary" onclick="closeModal()">Skip</button>
            <button class="btn-primary" onclick="saveSelectedCompetitors('${clientId}')" id="saveCompBtn">
                <i data-lucide="check-circle" class="icon-sm"></i> Save & Analyse Selected
            </button>
        </div>`;

    // Store candidates for reference
    window._discoveredCandidates = candidates;
    lucide.createIcons();
}

function toggleAllCompetitors(checked) {
    document.querySelectorAll('.comp-checkbox').forEach(cb => cb.checked = checked);
}

async function saveSelectedCompetitors(clientId) {
    const checkboxes = document.querySelectorAll('.comp-checkbox:checked');
    if (!checkboxes.length) { showToast('Select at least one competitor', 'error'); return; }

    const btn = document.getElementById('saveCompBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Saving competitors...';

    const candidates = window._discoveredCandidates || [];
    let saved = 0;

    for (const cb of checkboxes) {
        const idx = parseInt(cb.value);
        const c = candidates[idx];
        if (!c) continue;

        const { error } = await sb.from('competitors').insert({
            client_id: clientId,
            name: c.title_from_google || c.linkedin_username,
            linkedin_url: c.linkedin_url,
            niche: c.source_query || ''
        });
        if (!error) saved++;
    }

    showToast(`✅ ${saved} competitors saved!`, 'success');
    closeModal();
    loadContent();
}

// ---- POST SELECTOR (for repurposing) ----
async function showPostSelector(competitorId, clientId, sortBy = 'engagement') {
    const contentArea = document.getElementById('contentArea');

    // Fetch posts for this competitor
    let query = sb.from('posts').select('*').eq('competitor_id', competitorId).limit(50);
    if (sortBy === 'engagement') query = query.order('engagement_score', { ascending: false });
    else query = query.order('post_date', { ascending: false });

    const { data: posts } = await query;

    if (!posts?.length) {
        showToast('No posts found. Scrape this competitor first.', 'error');
        return;
    }

    contentArea.innerHTML = `
        <div class="panel" style="padding:24px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
                <div>
                    <h2 style="font-size:18px;font-weight:700;color:#F3F4F6;">Select Posts to Repurpose</h2>
                    <p style="color:#6B7280;font-size:13px;">${posts.length} posts retrieved</p>
                </div>
                <div style="display:flex;gap:12px;align-items:center;">
                    <select onchange="showPostSelector('${competitorId}', '${clientId}', this.value)" style="background:#111827;border:1px solid #374151;color:white;padding:6px 10px;border-radius:6px;font-size:13px;outline:none;">
                        <option value="engagement" ${sortBy === 'engagement' ? 'selected' : ''}>🔥 Sort by Engagement</option>
                        <option value="recent" ${sortBy === 'recent' ? 'selected' : ''}>⏱️ Sort by Recent</option>
                    </select>
                    <button class="btn-secondary" onclick="selectTopPosts(5)" style="font-size:12px;">Select Top 5</button>
                    <button class="btn-primary" onclick="repurposeSelected('${clientId}')" id="repurposeBtn">
                        <i data-lucide="sparkles" class="icon-sm"></i> Repurpose Selected
                    </button>
                </div>
            </div>
            <div style="display:grid;gap:10px;">
                ${posts.map(p => `
                    <label style="display:flex;align-items:flex-start;gap:12px;padding:14px;background:#0D1117;border:1px solid #1F2937;border-radius:10px;cursor:pointer;">
                        <input type="checkbox" class="post-select-cb" value="${p.id}" style="margin-top:3px;">
                        <div style="flex:1;min-width:0;">
                            <p style="color:#D1D5DB;font-size:13px;line-height:1.5;margin-bottom:8px;">
                                ${escapeHtml((p.content || '').substring(0, 200))}${(p.content || '').length > 200 ? '...' : ''}
                            </p>
                            <div style="display:flex;gap:16px;font-size:11px;color:#6B7280;">
                                <span>👍 ${p.likes || 0}</span>
                                <span>💬 ${p.comments || 0}</span>
                                <span>🔄 ${p.shares || 0}</span>
                                <span style="color:#10B981;font-weight:600;">Score: ${(p.engagement_score || 0).toFixed(1)}</span>
                                <span>${p.post_type || 'post'}</span>
                            </div>
                        </div>
                    </label>
                `).join('')}
            </div>
        </div>`;

    lucide.createIcons();
}

function selectTopPosts(n) {
    const cbs = document.querySelectorAll('.post-select-cb');
    cbs.forEach((cb, i) => cb.checked = i < n);
}

async function repurposeSelected(clientId) {
    const selected = Array.from(document.querySelectorAll('.post-select-cb:checked')).map(cb => cb.value);
    if (!selected.length) { showToast('Select at least one post', 'error'); return; }

    const btn = document.getElementById('repurposeBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Generating...';
    showToast(`🔮 Generating ${selected.length} draft(s)...`, 'info');

    let created = 0;
    for (const postId of selected) {
        try {
            const resp = await fetch(`${API_BASE}/api/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ post_id: postId, client_id: clientId })
            });
            const data = await resp.json();
            if (data.success) created++;
        } catch (e) { console.error('Generate error:', e); }
    }

    showToast(`✅ ${created} drafts created!`, 'success');
    switchTopTab('drafts');
}

// ---- REPURPOSE VIEW (side-by-side with refresh) ----
async function showRepurposeView(draftId) {
    const contentArea = document.getElementById('contentArea');

    const { data: drafts } = await sb.from('drafts').select('*').eq('id', draftId);
    if (!drafts?.length) { showToast('Draft not found', 'error'); return; }
    const draft = drafts[0];

    const { data: posts } = await sb.from('posts').select('*').eq('id', draft.source_post_id);
    const sourcePost = posts?.[0] || {};

    // Fetch templates for this client
    const { data: templates } = await sb.from('design_templates').select('*').eq('client_id', draft.client_id);

    contentArea.innerHTML = `
        <div class="panel" style="padding:24px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
                <h2 style="font-size:18px;font-weight:700;color:#F3F4F6;">Repurpose Draft</h2>
                <div style="display:flex;gap:8px;">
                    <button class="btn-secondary" onclick="loadContent()">← Back</button>
                    <button class="btn-primary" onclick="approveDraft('${draftId}')">
                        <i data-lucide="thumbs-up" class="icon-sm"></i> Approve
                    </button>
                    <button class="btn-secondary" style="border-color:#EF4444;color:#EF4444;" onclick="rejectDraft('${draftId}')">
                        <i data-lucide="thumbs-down" class="icon-sm"></i> Reject
                    </button>
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
                <!-- Original -->
                <div style="background:#0D1117;border:1px solid #1F2937;border-radius:12px;padding:16px;">
                    <h3 style="font-size:14px;font-weight:600;color:#9CA3AF;margin-bottom:12px;">ORIGINAL POST</h3>
                    <p style="color:#D1D5DB;font-size:13px;line-height:1.7;white-space:pre-wrap;">${escapeHtml(sourcePost.content || 'Source post not available')}</p>
                    <div style="margin-top:12px;font-size:11px;color:#6B7280;">
                        👍 ${sourcePost.likes || 0} · 💬 ${sourcePost.comments || 0} · 🔄 ${sourcePost.shares || 0}
                    </div>
                </div>
                <!-- Your Version -->
                <div style="background:#0D1117;border:1px solid #6366F1;border-radius:12px;padding:16px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <h3 style="font-size:14px;font-weight:600;color:#818CF8;">YOUR VERSION</h3>
                        <button class="btn-secondary" onclick="refreshCaption('${draftId}')" id="refreshCaptionBtn" style="font-size:11px;padding:4px 10px;">
                            🔄 Refresh Text
                        </button>
                    </div>
                    <div id="draftCaptionArea" style="color:#F3F4F6;font-size:13px;line-height:1.7;white-space:pre-wrap;">${escapeHtml(draft.caption || '')}</div>
                </div>
            </div>
            <!-- Image Row -->
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:20px;">
                <div style="background:#0D1117;border:1px solid #1F2937;border-radius:12px;padding:16px;text-align:center;">
                    <h3 style="font-size:14px;font-weight:600;color:#9CA3AF;margin-bottom:12px;">ORIGINAL IMAGE</h3>
                    ${sourcePost.image_url
            ? `<img src="${sourcePost.image_url}" style="max-width:100%;border-radius:8px;" />`
            : '<p style="color:#4B5563;padding:40px;">No image</p>'
        }
                </div>
                <div style="background:#0D1117;border:1px solid #6366F1;border-radius:12px;padding:16px;text-align:center;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <h3 style="font-size:14px;font-weight:600;color:#818CF8;">GENERATED IMAGE</h3>
                        <div style="display:flex;gap:6px;align-items:center;">
                            ${templates?.length ? `
                                <select id="templateSelector" style="background:#1F2937;color:#D1D5DB;border:1px solid #374151;border-radius:6px;padding:3px 8px;font-size:11px;">
                                    <option value="">Default style</option>
                                    ${templates.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('')}
                                </select>
                            ` : ''}
                            <button class="btn-secondary" onclick="refreshImage('${draftId}')" id="refreshImageBtn" style="font-size:11px;padding:4px 10px;">
                                🔄 Refresh Image
                            </button>
                        </div>
                    </div>
                    <div id="draftImageArea">
                        ${draft.image_url
            ? `<img src="${draft.image_url}" style="max-width:100%;border-radius:8px;" />`
            : '<p style="color:#4B5563;padding:40px;">No image generated</p>'
        }
                    </div>
                </div>
            </div>
        </div>`;

    lucide.createIcons();
}

async function refreshCaption(draftId) {
    const btn = document.getElementById('refreshCaptionBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>';
    try {
        const resp = await fetch(`${API_BASE}/api/refresh-caption`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ draft_id: draftId })
        });
        const data = await resp.json();
        if (data.success) {
            document.getElementById('draftCaptionArea').textContent = data.caption;
            showToast('✅ Caption refreshed!', 'success');
        } else {
            showToast('❌ ' + data.error, 'error');
        }
    } catch (e) { showToast('❌ ' + e.message, 'error'); }
    btn.disabled = false;
    btn.innerHTML = '🔄 Refresh Text';
}

async function refreshImage(draftId) {
    const btn = document.getElementById('refreshImageBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>';
    const templateId = document.getElementById('templateSelector')?.value || '';
    try {
        const resp = await fetch(`${API_BASE}/api/refresh-image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ draft_id: draftId, template_id: templateId || undefined })
        });
        const data = await resp.json();
        if (data.success && data.image_url) {
            document.getElementById('draftImageArea').innerHTML = `<img src="${data.image_url}" style="max-width:100%;border-radius:8px;" />`;
            showToast('✅ Image refreshed!', 'success');
        } else {
            showToast('❌ ' + (data.error || 'Image generation failed'), 'error');
        }
    } catch (e) { showToast('❌ ' + e.message, 'error'); }
    btn.disabled = false;
    btn.innerHTML = '🔄 Refresh Image';
}

// ---- HELPERS ----
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ---- TOAST NOTIFICATIONS ----
function showToast(message, type = 'info') {
    // Remove existing toast
    const existing = document.getElementById('toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.id = 'toast';
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${message}</span><button onclick="this.parentElement.remove()" style="background:none;border:none;color:white;cursor:pointer;font-size:18px;margin-left:12px;">×</button>`;
    document.body.appendChild(toast);

    // Auto-remove after 8s
    setTimeout(() => { if (document.getElementById('toast')) toast.remove(); }, 8000);
}

// ---- FULL PIPELINE: Scrape + Generate from competitor ----
async function fullPipeline(btn, compId, linkedinUrl, clientId, maxPosts = 20) {
    if (!confirm(`Run full pipeline?\n\n1. Scrape top posts from ${linkedinUrl}\n2. Generate AI drafts from top 3 posts\n\nThis may take 1-2 minutes.`)) return;

    const originalText = btn.innerHTML;
    btn.innerHTML = '<div class="spinner"></div> Running...';
    btn.disabled = true;

    showToast('🚀 Running full pipeline (scrape → generate)... ~60s', 'info');

    try {
        const resp = await fetch(`${API_BASE}/api/scrape-and-generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                profile_url: linkedinUrl,
                client_id: clientId,
                competitor_id: compId,
                max_items: parseInt(maxPosts) || 20,
                top_n: 3
            })
        });
        const data = await resp.json();
        if (data.success) {
            showToast(`✅ ${data.posts_scraped} posts scraped, ${data.drafts_created} drafts generated!`, 'success');
            switchTopTab('drafts');
        } else {
            showToast(`❌ ${data.error}`, 'error');
        }
    } catch (err) {
        showToast(`❌ Pipeline failed: ${err.message}`, 'error');
    }

    btn.innerHTML = originalText;
    btn.disabled = false;
}

// ---- BOOT ----
document.addEventListener('DOMContentLoaded', init);


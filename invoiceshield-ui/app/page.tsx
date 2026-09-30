'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Upload, Menu, X, BarChart3, FileText, TrendingUp, TrendingDown, CheckCircle, AlertCircle, XCircle, Zap, Clock, DollarSign, RotateCcw, ChevronDown, ChevronUp } from 'lucide-react';

// 127.0.0.1 (not "localhost") avoids the Windows IPv6/IPv4 mismatch
const API = 'http://127.0.0.1:8000';
const POLL_MS = 2000;

// DESIGN TOKENS - BLUE & BLACK
const COLORS = {
  primary: '#1E40AF',
  accent: '#DC2626',
  success: '#059669',
  warning: '#D97706',
  white: '#FFFFFF',
  light: '#F3F4F6',
  dark: '#0F172A',
  text: '#1F2937',
  muted: '#6B7280',
  lightBlue: '#EFF6FF',
};

const AGENTS = [
  { id: 1, name: 'Vendor Verification', icon: '🏢', time: 100 },
  { id: 2, name: 'GST Validation', icon: '📋', time: 110 },
  { id: 3, name: 'Amount Check', icon: '💰', time: 90 },
  { id: 4, name: 'PO Verification', icon: '📑', time: 100 },
  { id: 5, name: 'HSN Validation', icon: '🔍', time: 100 },
  { id: 6, name: 'GST Rate Check', icon: '📊', time: 110 },
  { id: 7, name: 'ITC Eligibility', icon: '✅', time: 90 },
  { id: 8, name: 'Duplicate Check', icon: '🔄', time: 90 },
  { id: 9, name: 'Audit Trail', icon: '📈', time: 100 },
  { id: 10, name: 'Price Cop Alert', icon: '🚨', time: 110 },
];
const STAGGER = 80;
const ANIM_TOTAL = 30 + 9 * STAGGER + 110; // ms until last agent finishes

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const inr = (n: any) => (typeof n === 'number' ? n.toLocaleString('en-IN') : '0');

const statusColor = (s?: string) =>
  s === 'FAIL' ? COLORS.accent : s === 'WARN' ? COLORS.warning : COLORS.success;
const statusLabel = (s?: string) =>
  s === 'FAIL' ? '✕ FAILED' : s === 'WARN' ? '⚠ WARNING' : '✓ PASSED';

// KPI CARD (outside the page component so it is not re-created on every refresh)
const KPICard = ({ icon: Icon, label, value, subtext, trend, color }: any) => (
  <div className="p-6 rounded-2xl border-2 transition-all hover:shadow-lg" style={{ borderColor: color, backgroundColor: `${color}08` }}>
    <div className="flex items-start justify-between">
      <div>
        <p className="text-sm font-semibold text-gray-600" style={{ color: COLORS.muted }}>{label}</p>
        <p className="text-4xl font-bold mt-3" style={{ color }}>{value}</p>
        {subtext && <p className="text-xs text-gray-500 mt-2">{subtext}</p>}
      </div>
      <Icon className="w-10 h-10" style={{ color, opacity: 0.7 }} />
    </div>
    {trend !== undefined && trend !== null && (
      <div className="mt-4 flex items-center gap-1 text-xs">
        {trend > 0 ? <TrendingUp className="w-4 h-4 text-green-600" /> : <TrendingDown className="w-4 h-4 text-red-600" />}
        <span style={{ color: trend > 0 ? '#059669' : '#DC2626' }}>{Math.abs(trend)}%</span>
      </div>
    )}
  </div>
);

export default function InvoiceShieldApp() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [invoiceHistory, setInvoiceHistory] = useState<any[]>([]);
  const [systemStats, setSystemStats] = useState<any>(null);
  const [agentsRunning, setAgentsRunning] = useState<boolean[]>(Array(10).fill(false));
  const [agentsCompleted, setAgentsCompleted] = useState<boolean[]>(Array(10).fill(false));
  const [agentResults, setAgentResults] = useState<any[]>([]);
  const [expandedSections, setExpandedSections] = useState<{ [key: string]: boolean }>({});

  const fileInputRef = useRef<HTMLInputElement>(null);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const fetchingRef = useRef(false);

  // ---------------------------------------------------------------- DATA FETCH
  const fetchData = useCallback(async () => {
    if (fetchingRef.current) return; // never overlap requests
    fetchingRef.current = true;
    try {
      const [statsRes, histRes] = await Promise.all([
        fetch(`${API}/system-stats`, { cache: 'no-store' }),
        fetch(`${API}/invoice-history`, { cache: 'no-store' }),
      ]);
      if (statsRes.ok) {
        const s = await statsRes.json();
        setSystemStats((prev: any) => (JSON.stringify(prev) === JSON.stringify(s) ? prev : s));
      }
      if (histRes.ok) {
        const d = await histRes.json();
        const list = Array.isArray(d) ? d : Array.isArray(d?.invoices) ? d.invoices : [];
        setInvoiceHistory((prev) => (JSON.stringify(prev) === JSON.stringify(list) ? prev : list));
      }
    } catch (err) {
      console.error('Fetch error:', err);
    } finally {
      fetchingRef.current = false;
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => {
      if (!document.hidden) fetchData();
    }, POLL_MS);
    const onVisible = () => { if (!document.hidden) fetchData(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
      timersRef.current.forEach(clearTimeout);
    };
  }, [fetchData]);

  const clearTimers = () => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  };

  const resetPipeline = () => {
    clearTimers();
    setAgentsRunning(Array(10).fill(false));
    setAgentsCompleted(Array(10).fill(false));
    setAgentResults([]);
  };

  // ---------------------------------------------------------------- RESET
  const resetSystem = async () => {
    try {
      const response = await fetch(`${API}/reset-system`, { method: 'POST' });
      if (response.ok) {
        setFile(null);
        setResult(null);
        setError('');
        setInvoiceHistory([]);
        resetPipeline();
        setActiveTab('dashboard');
        setExpandedSections({});
        if (fileInputRef.current) fileInputRef.current.value = '';
        fetchData();
        alert('✅ System reset successfully!');
      }
    } catch (err) {
      alert('❌ Failed to reset system. Is the backend running on port 8000?');
      console.error('Reset error:', err);
    }
  };

  // ---------------------------------------------------------------- AGENT ANIMATION
  const simulateAgentExecution = useCallback(() => {
    clearTimers();
    setAgentsRunning(Array(10).fill(false));
    setAgentsCompleted(Array(10).fill(false));
    setAgentResults([]);

    AGENTS.forEach((agent, idx) => {
      const start = 30 + idx * STAGGER;
      timersRef.current.push(setTimeout(() => {
        setAgentsRunning((prev) => { const n = [...prev]; n[idx] = true; return n; });
      }, start));
      timersRef.current.push(setTimeout(() => {
        setAgentsRunning((prev) => { const n = [...prev]; n[idx] = false; return n; });
        setAgentsCompleted((prev) => { const n = [...prev]; n[idx] = true; return n; });
      }, start + agent.time));
    });
  }, []);

  // ---------------------------------------------------------------- UPLOAD
  const pickFile = (f: File | undefined | null) => {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith('.pdf')) {
      setFile(null);
      setError('❌ Only PDF files are supported');
      return;
    }
    setFile(f);
    setError('');
  };

  const handleUpload = async () => {
    if (!file) {
      setError('❌ Please select a PDF file first');
      return;
    }
    setLoading(true);
    setError('');
    setResult(null);
    setExpandedSections({});
    setActiveTab('agents');
    simulateAgentExecution();

    try {
      const formData = new FormData();
      formData.append('file', file);

      // request and animation run in parallel -> results appear as soon as both are done
      const request = fetch(`${API}/upload-invoice`, { method: 'POST', body: formData }).then(async (res) => {
        const body = await res.json().catch(() => null);
        if (!res.ok) throw new Error(body?.error || `Upload failed (${res.status})`);
        return body;
      });
      const [data] = await Promise.all([request, sleep(ANIM_TOTAL + 40)]);

      setResult(data);
      setAgentResults(Array.isArray(data.agent_results) ? data.agent_results : []);
      fetchData(); // refresh KPIs + history immediately
      await sleep(350); // let the user see final agent colours
      setActiveTab('results');
    } catch (err: any) {
      clearTimers();
      setAgentsRunning(Array(10).fill(false));
      setAgentsCompleted(Array(10).fill(false));
      const msg = err instanceof TypeError
        ? 'Cannot reach backend. Start FastAPI: python src/fastapi_server.py (http://127.0.0.1:8000)'
        : err?.message || 'Upload failed';
      setError(`❌ ${msg}`);
      setActiveTab('upload');
    } finally {
      setLoading(false);
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(e.type !== 'dragleave');
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    pickFile(e.dataTransfer.files?.[0]);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    pickFile(e.target.files?.[0]);
    e.target.value = ''; // lets the same file be selected again
  };

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => ({ ...prev, [section]: !prev[section] }));
  };

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: BarChart3 },
    { id: 'upload', label: 'Upload', icon: Upload },
    { id: 'agents', label: 'Pipeline', icon: Zap },
    { id: 'results', label: 'Results', icon: CheckCircle },
    { id: 'history', label: 'History', icon: FileText },
  ];

  // ---------------------------------------------------------------- DASHBOARD
  const DashboardTab = () => {
    const total = systemStats?.invoices_processed || 0;
    const pct = (n: number) => (total ? Math.round(((n || 0) / total) * 100) : 0);
    const topVendors: any[] = systemStats?.top_vendors || [];
    const avgMs = systemStats?.avg_processing_ms || 0;
    return (
      <div className="space-y-8 animate-fadeIn">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <KPICard icon={AlertCircle} label="Pending" value={systemStats?.human_review || 0} subtext="Awaiting human review" color={COLORS.warning} />
          <KPICard icon={CheckCircle} label="Processed" value={total} color={COLORS.success} />
          <KPICard icon={DollarSign} label="Total Value" value={`₹${((systemStats?.total_value || 0) / 100000).toFixed(1)}L`} color={COLORS.primary} />
          <KPICard icon={Clock} label="Avg Process" value={total ? `${(avgMs / 1000).toFixed(2)}s` : '—'} subtext="Per invoice" color={COLORS.primary} />
          <KPICard icon={TrendingUp} label="Success" value={total ? `${systemStats?.success_rate ?? 0}%` : '—'} color={COLORS.success} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white p-6 rounded-2xl border-2 border-gray-200 shadow-sm">
            <h3 className="text-xl font-bold text-gray-900 mb-6">Approval Distribution</h3>
            <div className="space-y-5">
              {[
                { label: 'Auto Approve', count: systemStats?.auto_approved || 0, color: COLORS.success },
                { label: 'Human Review', count: systemStats?.human_review || 0, color: COLORS.warning },
                { label: 'Auto Reject', count: systemStats?.auto_rejected || 0, color: COLORS.accent },
              ].map((item, idx) => (
                <div key={idx}>
                  <div className="flex justify-between mb-2">
                    <span className="text-sm font-semibold text-gray-700">{item.label} ({item.count})</span>
                    <span className="text-sm font-bold text-gray-900">{pct(item.count)}%</span>
                  </div>
                  <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="h-full transition-all" style={{ width: `${pct(item.count)}%`, backgroundColor: item.color }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white p-6 rounded-2xl border-2 border-gray-200 shadow-sm">
            <h3 className="text-xl font-bold text-gray-900 mb-6">Top Vendors</h3>
            {topVendors.length === 0 ? (
              <p className="text-gray-500 text-sm">No invoices processed yet</p>
            ) : (
              <div className="space-y-4">
                {topVendors.map((vendor, idx) => (
                  <div key={idx} className="flex items-center justify-between p-3 rounded-lg hover:bg-blue-50 transition">
                    <div>
                      <p className="text-sm font-bold text-gray-900">{vendor.name}</p>
                      <p className="text-xs text-gray-500">{vendor.invoices} invoices</p>
                    </div>
                    <p className="text-sm font-bold text-gray-900">₹{(vendor.amount / 100000).toFixed(1)}L</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  // ---------------------------------------------------------------- UPLOAD
  const UploadTab = () => (
    <div className="max-w-2xl mx-auto animate-fadeIn">
      <div className="bg-white p-8 rounded-2xl border-2 border-gray-200 shadow-sm">
        <h3 className="text-3xl font-bold text-gray-900 mb-2">Upload Invoice PDF</h3>
        <p className="text-gray-600 text-lg mb-8">Drag and drop or click to select</p>

        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          className={`border-3 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all ${
            dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-blue-400'
          }`}
        >
          <Upload className="w-16 h-16 mx-auto mb-4 text-blue-500" />
          <p className="text-gray-900 font-bold text-xl mb-2">Drop your invoice here</p>
          <p className="text-base text-gray-600 mb-6">or click to browse</p>
          <input ref={fileInputRef} type="file" accept=".pdf,application/pdf" onChange={handleFileChange} className="hidden" id="file-input" />
          <label htmlFor="file-input" className="inline-block px-8 py-3 rounded-lg font-bold text-white text-lg transition-all cursor-pointer" style={{ backgroundColor: COLORS.primary }}>
            Choose File
          </label>
        </div>

        {file && (
          <div className="mt-6 p-4 rounded-lg" style={{ backgroundColor: `${COLORS.success}15`, borderLeft: `4px solid ${COLORS.success}` }}>
            <p className="text-sm text-gray-600 font-semibold">Selected file:</p>
            <p className="font-bold text-gray-900 text-lg">{file.name}</p>
            <p className="text-xs text-gray-500 mt-1">{(file.size / 1024).toFixed(1)} KB</p>
          </div>
        )}

        <button onClick={handleUpload} disabled={!file || loading} className="w-full mt-8 py-4 rounded-lg font-bold text-white text-lg transition-all disabled:opacity-50" style={{ backgroundColor: COLORS.primary }}>
          {loading ? '⏳ Processing...' : '📤 Upload & Validate'}
        </button>

        {error && (
          <div className="mt-4 p-4 rounded-lg text-red-700 font-semibold" style={{ backgroundColor: `${COLORS.accent}15`, borderLeft: `4px solid ${COLORS.accent}` }}>
            {error}
          </div>
        )}

        <div className="mt-8 p-4 rounded-lg" style={{ backgroundColor: COLORS.lightBlue, borderLeft: `4px solid ${COLORS.primary}` }}>
          <p className="text-sm font-bold text-gray-900 mb-1">📋 Sample Files:</p>
          <p className="text-xs text-gray-600 mb-3">Any text-based invoice PDF is read live and validated on its own data.</p>
          <div className="grid grid-cols-2 gap-2 text-sm text-gray-700">
            {['invoice_normal.pdf', 'invoice_blacklisted.pdf', 'invoice_high_value.pdf', 'invoice_priya_again.pdf', 'invoice_duplicate_po.pdf', 'invoice_invalid_hsn.pdf'].map((f) => (
              <div key={f} className="text-gray-800">✅ {f}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );

  // ---------------------------------------------------------------- AGENTS
  const AgentsTab = () => (
    <div className="max-w-4xl mx-auto animate-fadeIn">
      <div className="bg-white p-8 rounded-2xl border-2 border-gray-200 shadow-sm">
        <h3 className="text-3xl font-bold text-gray-900 mb-2">🤖 AI Agent Pipeline</h3>
        <p className="text-gray-600 text-lg mb-8">10 specialized agents validating your invoice...</p>

        <div className="space-y-3">
          {AGENTS.map((agent, idx) => {
            const real = agentResults[idx];
            const done = agentsCompleted[idx];
            const running = agentsRunning[idx];
            const col = done ? (real ? statusColor(real.status) : COLORS.success) : running ? COLORS.primary : '#D1D5DB';
            return (
              <div key={agent.id} className="p-5 rounded-xl border-2 transition-all" style={{
                borderColor: done ? col : running ? COLORS.primary : '#E5E7EB',
                backgroundColor: done ? `${col}08` : running ? `${COLORS.primary}08` : '#F9FAFB',
              }}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <span className="text-4xl">{agent.icon}</span>
                    <div>
                      <p className="font-bold text-gray-900 text-lg">Agent {agent.id}: {agent.name}</p>
                      <p className="text-xs text-gray-500">{real?.message || `${agent.time}ms`}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-4 h-4 rounded-full" style={{
                      backgroundColor: col,
                      animation: running ? 'pulse 1.5s infinite' : 'none',
                    }} />
                    <span className="font-bold text-sm" style={{ color: done ? col : running ? COLORS.primary : COLORS.muted }}>
                      {done ? (real ? statusLabel(real.status) : '✓ PASSED') : running ? '⚙️ RUNNING' : '○ WAITING'}
                    </span>
                  </div>
                </div>
                <div className="mt-3 h-2 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full" style={{
                    width: done ? '100%' : running ? '75%' : '0%',
                    backgroundColor: done ? col : COLORS.primary,
                    transition: 'width 0.25s ease-out',
                  }} />
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-8 p-4 rounded-lg" style={{ backgroundColor: COLORS.lightBlue, borderLeft: `4px solid ${COLORS.primary}` }}>
          <p className="text-sm text-gray-900"><span className="font-bold text-lg">{agentsCompleted.filter(Boolean).length}/10</span> agents completed</p>
          {agentsCompleted.every(Boolean) && <p className="text-green-700 font-bold mt-2">✅ All validations complete!</p>}
        </div>
      </div>
    </div>
  );

  // ---------------------------------------------------------------- RESULTS
  const Section = ({ id, title, color, children, count }: any) => (
    <div className="bg-white rounded-2xl border-2 shadow-sm overflow-hidden" style={{ borderColor: color || '#E5E7EB' }}>
      <button onClick={() => toggleSection(id)} className="w-full p-6 flex items-center justify-between hover:bg-gray-50 transition">
        <h3 className="text-2xl font-bold" style={{ color: color || '#111827' }}>{title}{count !== undefined ? ` (${count})` : ''}</h3>
        {expandedSections[id] ? <ChevronUp className="w-6 h-6 text-blue-600" /> : <ChevronDown className="w-6 h-6 text-gray-500" />}
      </button>
      {expandedSections[id] && <div className="px-6 pb-6 border-t-2 border-gray-200 pt-4">{children}</div>}
    </div>
  );

  const ResultsTab = () => (
    <div className="max-w-4xl mx-auto space-y-6 animate-fadeIn">
      {result ? (
        <>
          {/* DECISION BANNER */}
          <div
            className="p-8 rounded-2xl border-3 shadow-md"
            style={{
              borderColor: result.decision === 'AUTO_APPROVE' ? COLORS.success : result.decision === 'AUTO_REJECT' ? COLORS.accent : COLORS.warning,
              backgroundColor: result.decision === 'AUTO_APPROVE' ? `${COLORS.success}10` : result.decision === 'AUTO_REJECT' ? `${COLORS.accent}10` : `${COLORS.warning}10`,
            }}
          >
            <div className="flex items-center gap-6">
              {result.decision === 'AUTO_APPROVE' ? <CheckCircle className="w-20 h-20" style={{ color: COLORS.success }} /> : result.decision === 'AUTO_REJECT' ? <XCircle className="w-20 h-20" style={{ color: COLORS.accent }} /> : <AlertCircle className="w-20 h-20" style={{ color: COLORS.warning }} />}
              <div>
                <p className="text-5xl font-black text-gray-900">
                  {result.decision === 'AUTO_APPROVE' ? '✅ AUTO APPROVED' : result.decision === 'AUTO_REJECT' ? '❌ AUTO REJECTED' : '⚠️ HUMAN REVIEW'}
                </p>
                <p className="text-gray-700 mt-3 text-lg">Approval Level: <span className="font-bold text-xl">{result.approval_level}</span></p>
                <p className="text-gray-500 mt-1 text-sm">
                  {result.agents_executed} agents • {result.processing_ms} ms • {result.pages} page(s) read
                </p>
              </div>
            </div>
          </div>

          {result.fallback_fields?.length > 0 && (
            <div className="p-4 rounded-lg text-sm text-gray-800" style={{ backgroundColor: `${COLORS.warning}15`, borderLeft: `4px solid ${COLORS.warning}` }}>
              ⚠️ Not found in PDF text, filled from sample data: <span className="font-bold">{result.fallback_fields.join(', ')}</span>
            </div>
          )}

          {/* INVOICE DETAILS */}
          <Section id="details" title="📋 Invoice Details">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { label: 'Invoice #', value: result.invoice_number || 'N/A' },
                { label: 'Vendor', value: result.vendor || 'N/A' },
                { label: 'Amount', value: result.amount != null ? `₹${inr(result.amount)}` : 'N/A' },
                { label: 'PO #', value: result.po || 'N/A' },
                { label: 'GST', value: result.gst || 'N/A' },
                { label: 'HSN', value: result.hsn || 'N/A' },
                { label: 'GST Rate', value: result.gst_rate != null ? `${result.gst_rate}%` : 'N/A' },
                { label: 'Date', value: result.date || 'N/A' },
                { label: 'ITC Eligible', value: result.itc_eligible ? `✅ Yes (₹${inr(result.itc_amount)})` : '❌ No' },
                { label: 'Confidence', value: `${(result.confidence_score * 100).toFixed(0)}%` },
              ].map((item, idx) => (
                <div key={idx} className="p-4 rounded-lg bg-blue-50 border-l-4 border-blue-600">
                  <p className="text-xs font-bold text-gray-600 mb-2 uppercase">{item.label}</p>
                  <p className="text-lg font-bold text-gray-900 break-words">{item.value}</p>
                </div>
              ))}
            </div>
          </Section>

          {/* AGENT REPORT */}
          <Section id="report" title="🤖 Agent Report" count={result.agent_results?.length}>
            <div className="space-y-3">
              {(result.agent_results || []).map((a: any) => (
                <div key={a.id} className="p-4 rounded-lg border-l-4 bg-gray-50" style={{ borderColor: statusColor(a.status) }}>
                  <div className="flex items-center justify-between">
                    <p className="font-bold text-gray-900">Agent {a.id}: {a.name}</p>
                    <span className="text-xs font-bold" style={{ color: statusColor(a.status) }}>{statusLabel(a.status)}</span>
                  </div>
                  <p className="text-sm text-gray-700 mt-1">{a.message}</p>
                </div>
              ))}
            </div>
          </Section>

          {/* VENDOR AUDIT */}
          <Section id="audit" title="🔍 Vendor Audit">
            <div className="p-4 rounded-lg bg-gray-50 border-l-4 border-gray-400">
              <p className="text-sm font-bold text-gray-600 mb-2">AUDIT STATUS</p>
              <p className="text-2xl font-bold text-gray-900">{result.vendor_audit || 'CLEAN'}</p>
              <p className="text-xs text-gray-500 mt-2">Risk level assessment</p>
            </div>
          </Section>

          {/* ISSUES */}
          {result.issues_found?.length > 0 && (
            <Section id="issues" title="🚨 Issues Found" color="#dc2626" count={result.issues_found.length}>
              <div className="space-y-3">
                {result.issues_found.map((issue: any, idx: number) => (
                  <div key={idx} className="p-4 rounded-lg bg-red-50 border-l-4 border-red-600">
                    <p className="font-bold text-red-700 text-lg">{issue.type} <span className="text-xs">({issue.severity})</span></p>
                    <p className="text-gray-800 mt-2">{issue.message}</p>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* WARNINGS */}
          {result.warnings?.length > 0 && (
            <Section id="warnings" title="⚠️ Warnings" color="#d97706" count={result.warnings.length}>
              <div className="space-y-3">
                {result.warnings.map((w: any, idx: number) => (
                  <div key={idx} className="p-4 rounded-lg bg-yellow-50 border-l-4 border-yellow-600">
                    <p className="font-bold text-yellow-800 text-lg">{w.type} <span className="text-xs">({w.severity})</span></p>
                    <p className="text-gray-800 mt-2">{w.message}</p>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* PRICE COP */}
          {result.cost_warnings?.length > 0 && (
            <Section id="price" title="💰 Price Cop Alert" color="#c2410c" count={result.cost_warnings.length}>
              <div className="space-y-4">
                {result.cost_warnings.map((warning: any, idx: number) => (
                  <div key={idx} className="p-4 rounded-lg bg-orange-50 border-l-4 border-orange-600">
                    <p className="font-bold text-orange-700 text-lg">{warning.type}</p>
                    <p className="text-gray-800 mt-2">{warning.message}</p>
                    <div className="grid grid-cols-3 gap-3 mt-4">
                      <div className="p-3 bg-white rounded border border-gray-300">
                        <p className="text-xs font-bold text-gray-600">Previous Avg</p>
                        <p className="text-lg font-bold text-gray-900 mt-2">₹{inr(warning.previous_avg)}</p>
                      </div>
                      <div className="p-3 bg-white rounded border border-gray-300">
                        <p className="text-xs font-bold text-gray-600">Current</p>
                        <p className="text-lg font-bold text-gray-900 mt-2">₹{inr(warning.current)}</p>
                      </div>
                      <div className="p-3 bg-orange-100 rounded border-2 border-orange-600">
                        <p className="text-xs font-bold text-orange-700">Variance</p>
                        <p className="text-lg font-bold text-orange-700 mt-2">{warning.variance}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* EXTRACTED TEXT */}
          <Section id="text" title="📄 Text Read From PDF">
            <pre className="text-xs text-gray-700 bg-gray-50 p-4 rounded-lg overflow-x-auto whitespace-pre-wrap">{result.pdf_text_preview}</pre>
          </Section>

          <button
            onClick={() => {
              setFile(null);
              setResult(null);
              setError('');
              setActiveTab('upload');
              resetPipeline();
              setExpandedSections({});
              if (fileInputRef.current) fileInputRef.current.value = '';
            }}
            className="w-full py-4 rounded-lg font-bold text-white text-lg transition-all"
            style={{ backgroundColor: COLORS.primary }}
          >
            📤 Upload Another Invoice
          </button>
        </>
      ) : (
        <div className="text-center py-16">
          <FileText className="w-20 h-20 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-600 text-xl">Upload an invoice to see results</p>
        </div>
      )}
    </div>
  );

  // ---------------------------------------------------------------- HISTORY
  const HistoryTab = () => {
    const historyData = Array.isArray(invoiceHistory) ? invoiceHistory : [];
    return (
      <div className="bg-white rounded-2xl border-2 border-gray-200 shadow-sm overflow-hidden animate-fadeIn">
        <div className="p-6 border-b-2 border-gray-200">
          <h3 className="text-2xl font-bold text-gray-900">Invoice History</h3>
          <p className="text-base text-gray-600 mt-2">{historyData.length} invoices processed</p>
        </div>

        {historyData.length === 0 ? (
          <div className="p-12 text-center">
            <FileText className="w-16 h-16 mx-auto mb-4 text-gray-400" />
            <p className="text-gray-600 text-lg">No invoices processed yet</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-blue-50 border-b-2 border-gray-200">
                <tr>
                  <th className="px-6 py-4 text-left text-sm font-bold text-gray-900">Date</th>
                  <th className="px-6 py-4 text-left text-sm font-bold text-gray-900">Invoice</th>
                  <th className="px-6 py-4 text-left text-sm font-bold text-gray-900">Vendor</th>
                  <th className="px-6 py-4 text-left text-sm font-bold text-gray-900">Amount</th>
                  <th className="px-6 py-4 text-left text-sm font-bold text-gray-900">PO</th>
                  <th className="px-6 py-4 text-left text-sm font-bold text-gray-900">Status</th>
                </tr>
              </thead>
              <tbody>
                {historyData.map((inv, idx) => (
                  <tr key={idx} className="border-b border-gray-200 hover:bg-blue-50 transition">
                    <td className="px-6 py-4 text-sm text-gray-700 font-semibold">
                      {inv.uploaded_at ? new Date(inv.uploaded_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : 'N/A'}
                    </td>
                    <td className="px-6 py-4 text-sm font-bold text-gray-900">{inv.invoice_number || inv.filename || 'N/A'}</td>
                    <td className="px-6 py-4 text-sm font-bold text-gray-900">{inv.vendor || 'N/A'}</td>
                    <td className="px-6 py-4 text-sm font-bold text-gray-900">₹{inr(inv.amount)}</td>
                    <td className="px-6 py-4 text-sm text-gray-700">{inv.po || 'N/A'}</td>
                    <td className="px-6 py-4 text-sm">
                      <span
                        className="px-4 py-2 rounded-full text-xs font-bold"
                        style={{
                          color: inv.decision === 'AUTO_APPROVE' ? COLORS.success : inv.decision === 'AUTO_REJECT' ? COLORS.accent : COLORS.warning,
                          backgroundColor: inv.decision === 'AUTO_APPROVE' ? `${COLORS.success}25` : inv.decision === 'AUTO_REJECT' ? `${COLORS.accent}25` : `${COLORS.warning}25`,
                        }}
                      >
                        {inv.decision === 'AUTO_APPROVE' ? '✅ Approved' : inv.decision === 'AUTO_REJECT' ? '❌ Rejected' : '⏳ Review'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex h-screen bg-gray-50">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
        * { font-family: 'Inter', sans-serif; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
        .animate-fadeIn { animation: fadeIn 0.25s ease-out; }
      `}</style>

      {/* SIDEBAR */}
      <div className={`${sidebarOpen ? 'w-64' : 'w-20'} bg-gradient-to-b from-gray-900 to-gray-800 text-white transition-all duration-300 flex flex-col shadow-lg`}>
        <div className="p-4 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center font-bold text-xl" style={{ backgroundColor: COLORS.primary }}>🛡️</div>
            {sidebarOpen && <h1 className="font-black text-lg">InvoiceShield</h1>}
          </div>
        </div>

        <nav className="flex-1 p-4 space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button key={item.id} onClick={() => setActiveTab(item.id)} className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition font-semibold ${activeTab === item.id ? 'text-white' : 'text-gray-400 hover:bg-gray-700'}`} style={activeTab === item.id ? { backgroundColor: COLORS.primary } : {}} title={item.label}>
                <Icon className="w-5 h-5 flex-shrink-0" />
                {sidebarOpen && <span className="text-sm">{item.label}</span>}
              </button>
            );
          })}
        </nav>

        <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-4 text-gray-400 hover:bg-gray-700 transition border-t border-gray-700">
          {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* MAIN */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="bg-white border-b-2 border-gray-200 px-8 py-5 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-3xl font-black text-gray-900">{navItems.find((item) => item.id === activeTab)?.label}</h2>
              <p className="text-base text-gray-600 mt-2">Streamline your P2P invoicing</p>
            </div>
            <div className="flex items-center gap-4">
              <button
                onClick={resetSystem}
                className="flex items-center gap-2 px-5 py-2 rounded-lg font-bold text-sm transition-all"
                style={{ backgroundColor: `${COLORS.accent}20`, color: COLORS.accent }}
              >
                <RotateCcw className="w-4 h-4" />
                Reset System
              </button>
              <div className="text-right">
                <p className="text-sm text-gray-600 font-semibold">System</p>
                <p className="text-lg font-black text-green-600">✅ Live</p>
              </div>
            </div>
          </div>
        </div>

        {/* CONTENT - called as functions (not <Tag/>) so tabs never remount on refresh */}
        <div className="flex-1 overflow-auto p-8">
          {activeTab === 'dashboard' && DashboardTab()}
          {activeTab === 'upload' && UploadTab()}
          {activeTab === 'agents' && AgentsTab()}
          {activeTab === 'results' && ResultsTab()}
          {activeTab === 'history' && HistoryTab()}
        </div>
      </div>
    </div>
  );
}
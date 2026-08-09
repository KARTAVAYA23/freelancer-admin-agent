"""Visual theme — "Ledger": warm paper, oxblood accents, ruled lines.

An accounting-ledger aesthetic rather than the default SaaS blue-on-white, and
monospaced figures throughout because a column of amounts that does not align
is harder to scan than one that does.
"""

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400;1,600&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

:root {
  --bg-app:        #080C14;
  --bg-card:       #161F30;
  --bg-card-sub:   #0F172A;
  --bg-sidebar:    #0B0F19;
  --border-color:  #26334D;
  --border-light:  rgba(255, 255, 255, 0.08);
  --text-main:     #FFFFFF;
  --text-body:     #F1F5F9;
  --text-muted:    #94A3B8;
  --text-sub:      #CBD5E1;
  --primary:       #6366F1;
  --primary-hover: #4F46E5;
  --accent-blue:   #38BDF8;
  --accent-green:  #10B981;
  --accent-amber:  #F59E0B;
  --accent-red:    #EF4444;
  --shadow-lg:     0 10px 30px -5px rgba(0, 0, 0, 0.5);
}

/* ── Base Reset & App Shell ── */
.stApp {
  background: var(--bg-app) !important;
  color: var(--text-body) !important;
}

.stApp::before {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0; opacity: .5;
  background-image:
    radial-gradient(circle at 10% 10%, rgba(99, 102, 241, 0.15) 0%, transparent 40%),
    radial-gradient(circle at 90% 80%, rgba(56, 189, 248, 0.1) 0%, transparent 45%);
}

html, body, .stMarkdown, p, div, label, input, textarea, button {
  font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
  color: var(--text-body);
}

span:not([class*="material"]):not([data-testid="stIconMaterial"]) {
  font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
}

.block-container {
  padding-top: 2rem;
  padding-bottom: 6rem;
  max-width: 960px;
  position: relative;
  z-index: 1;
}

/* ── Masthead ─────────────────────────────────────────── */
.masthead {
  background: linear-gradient(135deg, rgba(22, 31, 48, 0.85) 0%, rgba(15, 23, 42, 0.95) 100%);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  padding: 2.2rem 2.4rem;
  margin: 0 0 1.6rem;
  box-shadow: var(--shadow-lg);
  backdrop-filter: blur(16px);
  position: relative;
  overflow: hidden;
  animation: rise .6s cubic-bezier(.2,.7,.3,1) both;
}

.masthead::before {
  content: "";
  position: absolute;
  top: -50%;
  right: -20%;
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, transparent 70%);
  pointer-events: none;
}

.masthead .kicker {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: .72rem;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: #818CF8;
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(129, 140, 248, 0.3);
  padding: 0.35rem 0.8rem;
  border-radius: 20px;
  margin: 0 0 1rem;
}

.masthead h1 {
  font-size: 2.25rem;
  font-weight: 800;
  letter-spacing: -.03em;
  line-height: 1.15;
  margin: 0 0 0.6rem;
  color: var(--text-main);
}

.masthead h1 em {
  font-style: normal;
  background: linear-gradient(135deg, #818CF8 0%, #C084FC 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  font-weight: 800;
}

.masthead .dek {
  font-size: 0.98rem;
  color: var(--text-sub);
  margin: 0;
  max-width: 65ch;
  line-height: 1.6;
}

/* ── Stat strip ───────────────────────────────────────── */
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.9rem;
  margin: 1.4rem 0 1.8rem;
  animation: rise .6s .08s cubic-bezier(.2,.7,.3,1) both;
}

.stat {
  background: linear-gradient(135deg, rgba(22, 31, 48, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  padding: 1.1rem 1.2rem;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
  backdrop-filter: blur(10px);
  transition: transform 0.2s ease, border-color 0.2s ease;
}

.stat:hover {
  transform: translateY(-2px);
  border-color: rgba(99, 102, 241, 0.4);
}

.stat .k {
  font-family: 'JetBrains Mono', monospace;
  font-size: .68rem;
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.stat .v {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.55rem;
  font-weight: 700;
  color: var(--text-main);
  margin-top: .35rem;
  letter-spacing: -.02em;
}

.stat .v.owed { color: #F87171; }
.stat .v.clear { color: #34D399; }

/* ── Chat Messages & Avatars (FIXED OVERLAP BUG) ────────── */
[data-testid="stChatMessage"] {
  background: transparent !important;
  border: 0 !important;
  padding: 0.6rem 0 !important;
  gap: 1rem !important;
  animation: rise .45s cubic-bezier(.2,.7,.3,1) both;
}

[data-testid="stChatMessage"] [data-testid="stChatMessageContent"] {
  background: var(--bg-card) !important;
  border: 1px solid var(--border-color) !important;
  border-radius: 14px !important;
  padding: 1.1rem 1.4rem !important;
  color: var(--text-main) !important;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
}

[data-testid="stChatMessage"] [data-testid="stChatMessageContent"] p {
  color: var(--text-body) !important;
  font-size: 0.98rem !important;
  line-height: 1.65 !important;
  margin-bottom: 0.5rem;
}

/* Avatar Containers - Clean Icon Styling */
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatMessageAvatar"] {
  width: 38px !important;
  height: 38px !important;
  min-width: 38px !important;
  min-height: 38px !important;
  border-radius: 12px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  font-size: 0 !important;
  overflow: hidden !important;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3) !important;
  position: relative !important;
}

/* Hide overflowing raw material text inside avatars */
[data-testid="stChatMessageAvatarUser"] *,
[data-testid="stChatMessageAvatarAssistant"] *,
[data-testid="stChatMessageAvatar"] * {
  display: none !important;
  visibility: hidden !important;
}

[data-testid="stChatMessageAvatarUser"] {
  background: linear-gradient(135deg, #6366F1 0%, #4F46E5 100%) !important;
}

[data-testid="stChatMessageAvatarUser"]::after {
  content: "👤";
  font-size: 1.1rem !important;
  line-height: 1 !important;
}

[data-testid="stChatMessageAvatarAssistant"] {
  background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%) !important;
}

[data-testid="stChatMessageAvatarAssistant"]::after {
  content: "⚡";
  font-size: 1.15rem !important;
  line-height: 1 !important;
}

/* ── Cards & Artifacts ── */
.doc-card {
  background: var(--bg-card-sub);
  border: 1px solid var(--border-color);
  border-left: 4px solid var(--primary);
  border-radius: 12px;
  padding: 1.5rem 1.7rem;
  margin: 0.8rem 0;
  box-shadow: var(--shadow-lg);
  animation: rise .5s cubic-bezier(.2,.7,.3,1) both;
}

.doc-card h2, .doc-card h3 {
  font-weight: 700;
  font-size: 1.15rem;
  color: var(--accent-blue);
  margin: 1.2rem 0 .5rem;
  letter-spacing: -.01em;
}

.doc-card h2:first-child, .doc-card h3:first-child { margin-top: 0; }
.doc-card p, .doc-card li { font-size: 0.95rem; line-height: 1.65; color: var(--text-body); }
.doc-card strong { color: var(--text-main); font-weight: 700; }
.doc-card ul { margin: .4rem 0 .7rem; padding-left: 1.2rem; }

.email-card {
  background: var(--bg-card-sub);
  border: 1px solid var(--border-color);
  border-left: 4px solid var(--accent-amber);
  border-radius: 12px;
  padding: 1.4rem 1.6rem;
  margin: 0.8rem 0;
  box-shadow: var(--shadow-lg);
  animation: rise .5s cubic-bezier(.2,.7,.3,1) both;
}

.email-head {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 0.75rem;
  margin-bottom: 0.9rem;
  line-height: 1.7;
}

.email-head b { color: var(--text-main); font-weight: 700; }
.email-body { white-space: pre-wrap; font-size: .95rem; line-height: 1.68; color: var(--text-body); }

.ledger-block {
  background: #060911;
  border: 1px solid #1E293B;
  border-radius: 10px;
  padding: 1.2rem 1.4rem;
  margin: 0.8rem 0;
  overflow-x: auto;
  box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.5);
  animation: rise .5s cubic-bezier(.2,.7,.3,1) both;
}

.ledger-block pre {
  font-family: 'JetBrains Mono', monospace;
  font-size: .84rem;
  line-height: 1.75;
  color: #38BDF8;
  margin: 0;
  white-space: pre;
}

.tier-chip {
  display: inline-block;
  font-family: 'JetBrains Mono', monospace;
  font-size: .65rem;
  letter-spacing: .12em;
  text-transform: uppercase;
  padding: .3rem .7rem;
  border-radius: 6px;
  margin-bottom: .8rem;
  font-weight: 700;
}

.tier-gentle { background: rgba(16, 185, 129, 0.15); color: #34D399; border: 1px solid rgba(52, 211, 153, 0.3); }
.tier-firm   { background: rgba(245, 158, 11, 0.15); color: #FBBF24; border: 1px solid rgba(251, 191, 36, 0.3); }
.tier-urgent { background: rgba(239, 68, 68, 0.15);  color: #F87171; border: 1px solid rgba(248, 113, 113, 0.3); }

/* ── Buttons & Action Controls ─────────────────────────── */
.stButton > button, .stDownloadButton > button {
  font-family: 'Plus Jakarta Sans', sans-serif !important;
  font-weight: 600 !important;
  font-size: 0.88rem !important;
  border-radius: 10px !important;
  border: 1px solid var(--border-color) !important;
  background: var(--bg-card) !important;
  color: var(--text-main) !important;
  padding: 0.6rem 1.25rem !important;
  transition: all .2s ease !important;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2) !important;
  cursor: pointer !important;
}

.stButton > button:hover, .stDownloadButton > button:hover {
  background: #26334D !important;
  border-color: #3B4D71 !important;
  color: #FFFFFF !important;
  transform: translateY(-1px) !important;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35) !important;
}

.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #6366F1 0%, #4F46E5 100%) !important;
  border-color: #6366F1 !important;
  color: #FFFFFF !important;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4) !important;
}

.stButton > button[kind="primary"]:hover {
  background: linear-gradient(135deg, #4F46E5 0%, #4338CA 100%) !important;
  border-color: #4F46E5 !important;
  box-shadow: 0 6px 18px rgba(99, 102, 241, 0.5) !important;
}

/* ── Inputs & Labels ──────────────────────────────────── */
.stTextInput > label, .stTextArea > label, label {
  color: #F8FAFC !important;
  font-size: 0.86rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.01em !important;
  margin-bottom: 0.4rem !important;
}

.stTextInput input, .stTextArea textarea {
  font-family: 'Plus Jakarta Sans', sans-serif !important;
  border-radius: 10px !important;
  border: 1px solid var(--border-color) !important;
  background: #0F172A !important;
  color: #FFFFFF !important;
  font-size: 0.92rem !important;
  padding: 0.65rem 0.9rem !important;
  transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}

.stTextInput input::placeholder, .stTextArea textarea::placeholder {
  color: var(--text-muted) !important;
  opacity: 1 !important;
  font-weight: 400 !important;
}

.stTextInput input:focus, .stTextArea textarea:focus {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.3) !important;
  outline: none !important;
}

/* ── Bottom Fixed Chat Input ───────────────────────────── */
[data-testid="stChatInput"] {
  background: var(--bg-card) !important;
  border: 1px solid var(--border-color) !important;
  border-radius: 14px !important;
  padding: 0.4rem !important;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5) !important;
}

[data-testid="stChatInput"] textarea {
  background: transparent !important;
  color: #FFFFFF !important;
  font-size: 0.95rem !important;
}

[data-testid="stChatInput"] textarea::placeholder {
  color: var(--text-muted) !important;
  opacity: 1 !important;
}

[data-testid="stChatInput"] button {
  background: linear-gradient(135deg, #6366F1, #4F46E5) !important;
  color: #FFFFFF !important;
  border-radius: 10px !important;
  border: 0 !important;
}

/* ── Sidebar Styling ──────────────────────────────────── */
[data-testid="stSidebar"] {
  background: var(--bg-sidebar) !important;
  border-right: 1px solid var(--border-color) !important;
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2, 
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
  color: var(--text-main) !important;
  font-weight: 700 !important;
  font-size: 1.05rem !important;
  letter-spacing: -.01em !important;
  margin-top: 0.5rem !important;
  margin-bottom: 0.8rem !important;
}

.side-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin: 1.4rem 0 .5rem;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: .4rem;
}

.side-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  padding: 0.45rem 0;
  border-bottom: 1px dashed var(--border-color);
}

.side-row .n { color: var(--text-sub); }
.side-row .a { font-weight: 700; color: var(--text-main); }
.side-row .a.late { color: #F87171; }

.pill {
  display: inline-block;
  font-family: 'JetBrains Mono', monospace;
  font-size: .65rem;
  font-weight: 700;
  padding: .25rem .6rem;
  border-radius: 4px;
  letter-spacing: .08em;
}

.pill-ok   { background: rgba(16, 185, 129, 0.15); color: #34D399; border: 1px solid rgba(52, 211, 153, 0.3); }
.pill-warn { background: rgba(239, 68, 68, 0.15);  color: #F87171; border: 1px solid rgba(248, 113, 113, 0.3); }

.notice {
  border-left: 4px solid var(--accent-red);
  background: rgba(239, 68, 68, 0.1);
  color: var(--text-main);
  padding: 0.95rem 1.2rem;
  border-radius: 8px;
  font-size: 0.9rem;
  line-height: 1.6;
  margin: .6rem 0;
}

.notice.ok {
  border-left-color: var(--accent-green);
  background: rgba(16, 185, 129, 0.1);
}

.stExpander {
  background: var(--bg-card-sub) !important;
  border: 1px solid var(--border-color) !important;
  border-radius: 10px !important;
}

.stExpander [data-testid="stExpanderToggleHeader"] {
  color: var(--text-main) !important;
  font-weight: 600 !important;
}

@keyframes rise {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}

@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}

#MainMenu, footer, header { visibility: hidden; }
</style>
"""


def masthead(name: str = "") -> str:
    who = f" · {name}" if name else ""
    return f"""
<div class="masthead">
  <div class="kicker">⚡ Freelance Admin Desk{who}</div>
  <h1>Proposals, Invoices &amp; <em>Getting Paid</em></h1>
  <p class="dek">Describe what you need in plain language. Draft proposals, generate professional invoices, or create &amp; email payment reminders seamlessly.</p>
</div>"""


def stat_strip(clients: int, outstanding: str, overdue_count: int, paid_count: int) -> str:
    tone = "owed" if overdue_count else "clear"
    return f"""
<div class="stats">
  <div class="stat"><div class="k">Active Clients</div><div class="v">{clients}</div></div>
  <div class="stat"><div class="k">Outstanding</div><div class="v {tone}">{outstanding}</div></div>
  <div class="stat"><div class="k">Overdue</div><div class="v {tone}">{overdue_count}</div></div>
  <div class="stat"><div class="k">Settled Invoices</div><div class="v clear">{paid_count}</div></div>
</div>"""



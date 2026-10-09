import React, {useMemo, useState} from 'react';
import {
  Activity, ArrowDownRight, ArrowRight, ArrowUpRight, BookOpen, Braces, Check,
  CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, Clipboard,
  Clock3, Code2, Compass, Copy, ExternalLink, Eye, FileClock, Fingerprint,
  GitBranch, Github, Handshake, HeartHandshake, KeyRound, Layers3, Link2,
  LockKeyhole, Menu, MessageCircle, Network, Play, Plus, Radio, RotateCcw,
  Route, ScanEye, Shield, ShieldAlert, ShieldCheck, Sparkles, Workflow, X, Zap
} from 'lucide-react';
import {actions, inspectProposal, illustrativeScopes} from './policy.js';

const REPO='https://github.com/MichaelWave369/FieldAccord';
const nav=[
  {id:'overview',label:'Overview',icon:Compass,description:'The shared field'},
  {id:'protocol',label:'Protocol Lab',icon:Workflow,description:'Inspect a proposal'},
  {id:'continuity',label:'Work Continuity',icon:GitBranch,description:'Follow a work thread'},
  {id:'bridges',label:'Ecosystem Bridges',icon:Network,description:'Connected by contracts'},
  {id:'principles',label:'Core Principles',icon:ShieldCheck,description:'The seven laws'}
];
const bridges=[
  {id:'vessie',name:'SuperPhiVessel',short:'Vessie',role:'Cognition & context',status:'Metadata-only adapter',version:'FA-05 / 07 / 08',icon:Sparkles,tone:'mint',url:'https://github.com/MichaelWave369/SuperPhiVessel',
   description:'FieldAccord has offline Vessie DLAM export inspection and metadata-only producer adapters. The protocol excludes raw prompt and memory content. Native hooks are not automatically activated.',
   boundary:'A sealed context packet is not a grant, model-memory admission, or deployed live connection.'},
  {id:'phios',name:'PhiOS',short:'PhiOS',role:'Authority & verification',status:'Read-only observation',version:'FA-05 / 07 / 08',icon:Shield,tone:'blue',url:'https://github.com/MichaelWave369/PhiOS',
   description:'Adapters validate native PhiVessel BRIDGE_STATUS observations without invoking PhiOS execution or creating a lease.',
   boundary:'BRIDGE_STATUS is evidence to inspect, never permission to act.'},
  {id:'fielddeck',name:'FieldDeck',short:'FieldDeck',role:'Human-reviewed tools',status:'Pinned public read',version:'FA-03 / 04',icon:Layers3,tone:'gold',url:'https://github.com/MichaelWave369/FieldDeck',
   description:'A reviewed GitHub source pin can be fetched explicitly and inspected for limited action metadata in a WorkIntent-bound review path.',
   boundary:'A listed ready action is not execution approval, and the fetch performs no writes.'},
  {id:'nbg',name:'NestedBubbleGear',short:'NBG',role:'Evidence-linked memory',status:'Offline adapter',version:'FA-03',icon:Fingerprint,tone:'violet',url:'https://github.com/MichaelWave369/NestedBubbleGear',
   description:'An offline snapshot adapter extracts bounded epistemic metadata and evidence identifiers. Free-text memory content does not become trusted policy.',
   boundary:'Memory references and source claims cannot elevate authority.'},
  {id:'cloud',name:'FieldCloudWorker',short:'Cloud Worker',role:'Public task observation',status:'Opt-in public read',version:'FA-CW01 / CW02',icon:Radio,tone:'coral',url:'https://github.com/MichaelWave369/FieldCloudWorker',
   description:'The opt-in command can read consistent public GitHub task-status and history records with run metadata. Offline admission requires independently pinned source bytes.',
   boundary:'A current public observation does not prove author identity, independent pin custody, or task truth.'},
  {id:'budget',name:'BudgetGenius',short:'BudgetGenius',role:'Cognitive resource routing',status:'Ecosystem role',version:'Future integration',icon:Activity,tone:'mint',url:'https://github.com/MichaelWave369/BudgetGenius',
   description:'A companion system for cognitive resource decisions, named in the FieldAccord architectural map. No live adapter is claimed by this showcase.',
   boundary:'A routing preference is not permission to spend, execute, or share secrets.'},
  {id:'commonline',name:'Commonline',short:'Commonline',role:'Attention & presence',status:'Ecosystem role',version:'Future integration',icon:MessageCircle,tone:'blue',url:'https://github.com/MichaelWave369/Commonline',
   description:'A companion concept for human-agent attention, calls, and presence. FieldAccord attention advice is not a working notification dispatcher.',
   boundary:'An attention lease or candidate remains advice, not consent to contact anyone.'}
];
const laws=[
  {title:'GOAL ≠ GRANT',detail:'A shared goal defines what success means. It never mints a permission or authorizes a tool call.',icon:Compass},
  {title:'CAPABILITY ≠ AUTHORITY',detail:'A declared ability is advisory metadata. The trusted executor must independently verify actual permission.',icon:KeyRound},
  {title:'OBSERVATION ≠ INFERENCE',detail:'An observed record and a conclusion about it are different things. Evidence keeps its source and confidence boundaries.',icon:Eye},
  {title:'MEMORY ≠ AUTHORIZATION',detail:'Past conversations, recorded preferences, or recalled context cannot approve a new external action.',icon:FileClock},
  {title:'ATTENTION ≠ PERMISSION',detail:'Requesting a reminder or surfacing a review candidate does not give an agent permission to send a message.',icon:Clock3},
  {title:'PROPOSAL ≠ EXECUTION',detail:'Proposals and receipts can be considered and inspected without touching real devices, files, or accounts.',icon:ShieldAlert},
  {title:'HASH ≠ TRUST',detail:'A matching digest supports consistency checking but does not prove identity, consent, or authorship.',icon:Fingerprint}
];
const seedTimeline=[
  {id:1,kind:'INTENT',text:'Synthetic WorkIntent established',note:'A bounded goal is recorded',state:'OPEN'},
  {id:2,kind:'PROPOSAL',text:'Candidate summary received',note:'No authority is inherited',state:'NEEDS_REVIEW'}
];
const timelineActions=[
  {type:'CHECKPOINT',label:'Add checkpoint',icon:Plus,text:'Context checkpoint added',note:'Continuity recorded in temporary demo state'},
  {type:'NEEDS_REVIEW',label:'Request review',icon:Eye,text:'Human review requested',note:'Advisory only; no person was notified'},
  {type:'BLOCKED',label:'Block workflow',icon:ShieldAlert,text:'Work marked blocked',note:'No tool or external action was invoked'},
  {type:'CLOSED',label:'Close thread',icon:Check,text:'Review thread closed',note:'Closed does not mean the task executed'}
];

function AccordLogo({size=48}){return <span className="accord-logo" style={{width:size,height:size}}><svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="21" cy="32" r="11" fill="none" stroke="#e2b88d" strokeWidth="3"/><circle cx="43" cy="32" r="11" fill="none" stroke="#78d0b5" strokeWidth="3"/><path d="M31 32h2" stroke="#f8f3e8" strokeWidth="3" strokeLinecap="round"/><path d="M32 13v9m0 20v9" stroke="#78909e" strokeWidth="1.5" strokeDasharray="2 3"/></svg></span>;}
function Eyebrow({children}){return <span className="eyebrow"><span className="eyebrow-dot"/>{children}</span>;}
function Intro({kicker,title,accent,copy}){return <div className="page-intro"><Eyebrow>{kicker}</Eyebrow><h1>{title} <em>{accent}</em></h1><p>{copy}</p></div>;}
function Status({value}){const tone=value==='BLOCKED'?'danger':value==='REVIEW_REQUIRED'||value==='NEEDS_REVIEW'?'amber':'mint';return <span className={'status '+tone}><span className="status-dot"/>{value.replaceAll('_',' ')}</span>;}

function OrbitArt(){return <div className="orbit-art" aria-label="Human and agent meet through a contract, without an authority transfer" role="img">
  <div className="orbit-ring orbit-ring-one"/><div className="orbit-ring orbit-ring-two"/>
  <div className="orbit-node human"><span><HeartHandshake size={25}/></span><strong>HUMAN</strong><small>Goal & oversight</small></div>
  <div className="orbit-node protocol-center"><AccordLogo size={100}/><strong>THE ACCORD</strong><small>Shared intent</small></div>
  <div className="orbit-node agent"><span><Code2 size={25}/></span><strong>AGENT</strong><small>Capabilities & proposals</small></div>
  <div className="orbit-link orbit-link-left"><span>intent</span></div><div className="orbit-link orbit-link-right"><span>review</span></div>
  <div className="orbit-particle particle-a"/><div className="orbit-particle particle-b"/><div className="orbit-particle particle-c"/>
  <div className="orbit-footer"><ShieldCheck size={15}/> No implicit authority transfer</div>
</div>;}
function Stat({value,label,accent}){return <div className="metric"><strong className={accent}>{value}</strong><span>{label}</span></div>;}
function Overview({go}){
  return <>
    <section className="hero"><div className="hero-content"><Eyebrow>HUMAN × SILICON COLLABORATION</Eyebrow><h1>A shared field<br/>of <em>intent.</em></h1><p className="lead">Technology should carry the complexity, not the human.</p><p className="hero-detail">FieldAccord is a coordination protocol for people and agents to describe goals, inspect continuity, and review evidence without silently inheriting permission.</p><div className="hero-actions"><button className="button primary" onClick={()=>go('protocol')}>Enter Protocol Lab <ArrowRight size={17}/></button><button className="button ghost" onClick={()=>go('principles')}>Explore the seven laws <ArrowUpRight size={17}/></button></div><div className="hero-micro"><span><ShieldCheck size={15}/> Review first</span><span><Eye size={15}/> Evidence-aware</span><span><LockKeyhole size={15}/> No execution authority</span></div></div><OrbitArt/></section>
    <div className="mission-strap"><span className="strap-sign">∿</span><p>GOAL ≠ GRANT <span>·</span> CAPABILITY ≠ AUTHORITY <span>·</span> PROPOSAL ≠ EXECUTION</p><span>FIELD ACCORD / 001</span></div>
    <div className="metrics"><Stat value="10" label="Documented protocol rungs" accent="cream"/><Stat value="7" label="Core boundary laws" accent="mint-text"/><Stat value="0" label="Execution rights conferred" accent="gold-text"/><Stat value="100%" label="Synthetic site interactions" accent="cream"/></div>
    <div className="section-label"><div><Eyebrow>EXPLORE THE SYSTEM</Eyebrow><h2>Built for collaboration.<br/><em>Governed by design.</em></h2></div><span className="quiet-micro">An interactive tour of the current experimental protocol</span></div>
    <div className="feature-grid">
      <button className="feature-card" onClick={()=>go('protocol')}><div className="feature-icon mint"><Workflow/></div><span className="feature-number">01 / CONTRACTS</span><h3>Make intentions explicit.</h3><p>Inspect example WorkIntents, proposed actions, and blocked or review-only decisions.</p><span className="feature-go">Open Protocol Lab <ArrowRight size={16}/></span></button>
      <button className="feature-card" onClick={()=>go('continuity')}><div className="feature-icon blue"><GitBranch/></div><span className="feature-number">02 / CONTINUITY</span><h3>Keep a thread of work.</h3><p>Explore a synthetic WorkEvent trail, checkpoints, and state transitions across a handoff.</p><span className="feature-go">View Work Continuity <ArrowRight size={16}/></span></button>
      <button className="feature-card" onClick={()=>go('bridges')}><div className="feature-icon gold"><Network/></div><span className="feature-number">03 / ECOSYSTEM</span><h3>Connect without surrender.</h3><p>See which evidence bridges exist today and which ecosystem roles are only planned.</p><span className="feature-go">Explore bridges <ArrowRight size={16}/></span></button>
    </div>
    <section className="closing-statement"><div><Eyebrow>THE CENTRAL COMMITMENT</Eyebrow><h2>The human stays <em>in the loop.</em></h2><p>A proposal can become clearer. Evidence can become stronger. A work thread can survive a model swap. None of those things creates an independent permission to act.</p></div><a className="button secondary" href={REPO+'/blob/main/README.md'} target="_blank" rel="noreferrer">Read the architecture <ExternalLink size={16}/></a></section>
  </>;
}
function Protocol({title,setTitle,action,setAction,claims,setClaims,receipt,setReceipt}){
  const selected=actions.find(a=>a.id===action)||actions[0];
  return <>
    <Intro kicker="FA-01 / NO-AUTHORITY CONTRACTS" title="Make a proposal." accent="Keep the boundary." copy="Inspect a deliberately simplified, browser-only example of FieldAccord's blocked and review-required decisions. This is not the production Python policy engine."/>
    <div className="lab-grid"><section className="panel lab-form"><div className="panel-header"><span className="panel-index">01</span><div><h2>WorkIntent</h2><p>What is the human asking the team to accomplish?</p></div><span className="panel-corner"><Braces size={18}/></span></div>
      <label className="field-label" htmlFor="intent-title">Human goal</label><textarea id="intent-title" maxLength={160} rows={3} value={title} onChange={e=>{setTitle(e.target.value);setReceipt(null);}}/>
      <div className="intent-scope"><div><LockKeyhole size={16}/> SYNTHETIC ALLOWED SCOPE</div><span>Read pinned evidence metadata</span><span>Draft an advisory summary</span></div>
      <div className="form-divider"/><div className="panel-header compact"><span className="panel-index">02</span><div><h2>ActionProposal</h2><p>What does the fictional agent propose doing?</p></div></div>
      <label className="field-label" htmlFor="action-select">Proposed action</label><select id="action-select" value={action} onChange={e=>{setAction(e.target.value);setReceipt(null);}}>{actions.map(a=><option value={a.id} key={a.id}>{a.label}</option>)}</select>
      <p className="selection-help">{selected.description}</p>
      <label className="claim-label"><input type="checkbox" checked={claims} onChange={e=>{setClaims(e.target.checked);setReceipt(null);}}/><span><strong>Agent claims “I already have approval”</strong><small>Try this. A self-reported claim cannot establish consent.</small></span></label>
      <button className="button primary inspect-button" onClick={()=>setReceipt(inspectProposal({title,action,claimsApproval:claims}))}><ScanEye size={17}/> Inspect proposal <ArrowRight size={17}/></button>
      </section>
      <section className="panel lab-result"><div className="panel-header"><span className="panel-index">03</span><div><h2>Review-only receipt</h2><p>What this illustrative assessment returns</p></div><span className="panel-corner"><FileClock size={18}/></span></div>
        {!receipt?<div className="empty-receipt"><div className="empty-symbol"><Shield size={38}/></div><h3>Awaiting an inspection</h3><p>Choose an action and inspect it to generate a synthetic, non-authorizing receipt. Nothing executes.</p><span>FA / SANDBOX MODE</span></div>:<>
          <div className={'decision-card '+(receipt.disposition==='BLOCKED'?'is-blocked':'is-review')}><span>ILLUSTRATIVE DISPOSITION</span><Status value={receipt.disposition}/><h3>{receipt.disposition==='BLOCKED'?'Outside the line.':'Needs a human decision.'}</h3><p>{receipt.reason}</p></div>
          <div className="receipt-flags">{[['Authority granted','authority_granted'],['Action executed','action_executed'],['Identity authenticated','identity_authenticated'],['Durable receipt created','durable_receipt']].map(([label,key])=><div key={key}><span>{label}</span><strong><X size={14}/> NO</strong></div>)}</div>
          <details className="receipt-details"><summary><Code2 size={15}/> Inspect example JSON <ChevronDown size={16}/></summary><pre>{JSON.stringify(receipt,null,2)}</pre></details>
        </>}
        <div className="non-authority-note"><ShieldAlert size={19}/><p><strong>Important:</strong> This is a local teaching simulation, not a signed WorkReceipt, a verification of anyone's identity, a live adapter, or permission to run tools.</p></div>
      </section>
    </div>
    <div className="explain-strip"><span><ShieldCheck size={19}/></span><div><strong>Why does an in-scope proposal still say REVIEW REQUIRED?</strong><p>Because a capability declaration only describes what an agent says it can do. An independent trusted executor and verified operator grant are still needed for real actions.</p></div></div>
  </>;
}
function Continuity({events,setEvents,attention,setAttention}){
  const current=events[events.length-1].state;const closed=current==='CLOSED';
  function append(action){if(closed)return;setEvents(previous=>[...previous,{id:previous.length+1,kind:action.type,text:action.text,note:action.note,state:action.type==='CHECKPOINT'?previous[previous.length-1].state:action.type}]);}
  return <>
    <Intro kicker="FA-02 / REPLAYABLE WORKSTATE" title="Keep the context." accent="Not the control." copy="A WorkEvent trail can help agents and humans resume a task after a handoff. Explore the state machine with synthetic, in-memory events."/>
    <div className="continuity-grid"><section className="panel"><div className="panel-header"><span className="panel-index">01</span><div><h2>Example event thread</h2><p>Temporary browser state; no hash or identity attestation</p></div></div><div className="thread-meta"><span>WORK / DEMO-001</span><Status value={current}/></div><div className="timeline">{events.map((ev,i)=><div className="timeline-event" key={ev.id}><div className="timeline-marker">{i===events.length-1?<GitBranch size={16}/>:<Check size={14}/>}</div><div><span className="timeline-small">EVENT {String(i+1).padStart(2,'0')} · {ev.kind.replaceAll('_',' ')}</span><h3>{ev.text}</h3><p>{ev.note}</p></div></div>)}</div><div className="timeline-actions">{timelineActions.map((action)=><button key={action.type} disabled={closed} className="action-chip" onClick={()=>append(action)}><action.icon size={15}/>{action.label}</button>)}</div><button className="reset-link" onClick={()=>setEvents(seedTimeline)}><RotateCcw size={14}/> Reset thread</button></section>
      <aside className="continuity-side"><section className="panel state-panel"><Eyebrow>CURRENT WORKSTATE</Eyebrow><Status value={current}/><p>State is derived from this illustrative event sequence. <strong>Closed</strong> means the thread ended, not that any external work succeeded.</p><div className="state-rail"><span>OPEN</span><ArrowRight size={14}/><span>REVIEW</span><ArrowRight size={14}/><span>BLOCKED / CLOSED</span></div></section>
      <section className="panel attention-panel"><div className="attention-head"><div className="feature-icon blue"><Clock3 size={22}/></div><span>ADVISORY ATTENTION</span></div><h3>Should this appear in someone's review queue?</h3><p>Try the synthetic attention preference. Nothing is sent to anyone.</p><label className="toggle-label"><input type="checkbox" checked={attention} onChange={e=>setAttention(e.target.checked)}/><span>Allow review candidate</span></label><div className="attention-outcome"><span>ADVICE</span><strong>{attention?'REVIEW_CANDIDATE':'HOLD'}</strong><small>No notification dispatched · No consent established</small></div></section>
      </aside></div>
  </>;
}
function Bridges({active,setActive}){
  const chosen=bridges.find(b=>b.id===active)||bridges[0];const Icon=chosen.icon;
  return <>
    <Intro kicker="FA-03 TO FA-CW02 / EVIDENCE BOUNDARIES" title="An ecosystem of tools." accent="A protocol of limits." copy="See the documented bridges and adjacent ecosystem roles. Selecting a node only explains its boundary; it never calls the system."/>
    <div className="bridge-layout"><div className="bridge-list">{bridges.map((b)=><button className={'bridge-tile '+(active===b.id?'active':'')} key={b.id} onClick={()=>setActive(b.id)}><span className={'bridge-icon '+b.tone}><b.icon size={20}/></span><span><strong>{b.name}</strong><small>{b.role}</small></span><ChevronRight size={16}/></button>)}</div>
      <article className="panel bridge-detail"><div className="bridge-hero"><div className={'bridge-big-icon '+chosen.tone}><Icon size={39}/></div><div><Eyebrow>SELECTED ECOSYSTEM NODE</Eyebrow><h2>{chosen.name}</h2><p>{chosen.role}</p></div></div><div className="bridge-tags"><span>{chosen.version}</span><span>{chosen.status}</span></div><div className="bridge-copy"><h3>What exists</h3><p>{chosen.description}</p><h3>The boundary</h3><div className="boundary"><LockKeyhole size={18}/><p>{chosen.boundary}</p></div></div><a className="button secondary" href={chosen.url} target="_blank" rel="noreferrer">Explore source repository <ArrowUpRight size={16}/></a></article>
    </div>
    <div className="bridge-caution"><Eye size={20}/><div><strong>Reading is not connecting.</strong><p>This site uses authored explanations only. It does not fetch evidence, discover models, communicate with agents, contact people, or inherit authority from another project.</p></div></div>
  </>;
}
function Principles({expanded,setExpanded}){return <>
  <Intro kicker="FIELD ACCORD / NON-NEGOTIABLES" title="The seven laws." accent="One clear promise." copy="Every capability boundary begins here. Explore why coordination and verification must stay separate from permission."/>
  <div className="laws-layout"><div className="laws-list">{laws.map((law,i)=>{const Icon=law.icon;const isOpen=expanded===i;return <article className={'law-card '+(isOpen?'expanded':'')} key={law.title}><button aria-expanded={isOpen} onClick={()=>setExpanded(isOpen?-1:i)}><span className="law-no">{String(i+1).padStart(2,'0')}</span><span className="law-icon"><Icon size={19}/></span><strong>{law.title}</strong><ChevronDown size={19} className="law-chevron"/></button>{isOpen&&<div className="law-explanation"><p>{law.detail}</p></div>}</article>})}</div><aside className="principles-card"><AccordLogo size={93}/><Eyebrow>THE FIELD'S CENTER</Eyebrow><h2>Trust is not a side effect.</h2><p>Evidence can be inspected. Intent can be replayed. Models can disagree. Permission still has to come from an independent, verified human-governed authority boundary.</p><a href={REPO+'/blob/main/AGENTS.md'} target="_blank" rel="noreferrer">Read the agent invariants <ArrowUpRight size={16}/></a></aside></div>
</>;}
export default function App(){
 const [page,setPage]=useState('overview'),[mobile,setMobile]=useState(false);
 const [title,setTitle]=useState('Review the latest deployment evidence');
 const [action,setAction]=useState('inspect'),[claims,setClaims]=useState(false),[receipt,setReceipt]=useState(null);
 const [events,setEvents]=useState(seedTimeline),[attention,setAttention]=useState(false);
 const [activeBridge,setActiveBridge]=useState('vessie'),[expanded,setExpanded]=useState(0);
 const current=nav.find(n=>n.id===page)||nav[0];
 function go(id){setPage(id);setMobile(false);window.scrollTo({top:0,behavior:'smooth'});}
 return <div className="app-shell">
    <aside className={'sidebar '+(mobile?'sidebar-open':'')}>
      <div className="sidebar-top"><button className="brand" onClick={()=>go('overview')} aria-label="FieldAccord home"><AccordLogo size={43}/><span><strong>FIELD<span>ACCORD</span></strong><small>THE HUMAN × SILICON PROTOCOL</small></span></button><button className="sidebar-close" onClick={()=>setMobile(false)} aria-label="Close menu"><X size={21}/></button></div>
      <div className="sidebar-label">FIELD NAVIGATION</div><nav aria-label="Main site navigation">{nav.map(item=><button key={item.id} className={'nav-item '+(page===item.id?'selected':'')} onClick={()=>go(item.id)} aria-current={page===item.id?'page':undefined}><item.icon size={19}/><span><strong>{item.label}</strong><small>{item.description}</small></span>{page===item.id&&<span className="nav-selected-dot"/>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-note"><span className="live-pulse"/><strong>PUBLIC PROTOCOL PREVIEW</strong><p>Illustrative and read-only. No live authority, agent access, or account connection.</p></div><a href={REPO} target="_blank" rel="noreferrer" className="sidebar-github"><Github size={18}/> Source repository <ArrowUpRight size={15}/></a></div>
    </aside>
    {mobile&&<button className="scrim" onClick={()=>setMobile(false)} aria-label="Close menu"/>}
    <div className="main-column">
      <header className="topbar"><div className="topbar-left"><button className="mobile-menu" onClick={()=>setMobile(true)} aria-label="Open menu"><Menu size={22}/></button><span>FIELD / 369</span><ChevronRight size={14}/><strong>{current.label}</strong></div><div className="topbar-right"><span className="topbar-pill"><span/> SYNTHETIC DEMO</span><a href={REPO} target="_blank" rel="noreferrer" aria-label="FieldAccord on GitHub"><Github size={20}/></a></div></header>
      <div className="preview-banner"><ShieldCheck size={16}/><strong>Governed by design</strong><span>Everything interactive here runs in your browser with synthetic data. Nothing is authorized, executed, or saved.</span></div>
      <main id="main" className="content">
      {page==='overview'&&<Overview go={go}/>}
      {page==='protocol'&&<Protocol {...{title,setTitle,action,setAction,claims,setClaims,receipt,setReceipt}}/>}
      {page==='continuity'&&<Continuity {...{events,setEvents,attention,setAttention}}/>}
      {page==='bridges'&&<Bridges active={activeBridge} setActive={setActiveBridge}/>}
      {page==='principles'&&<Principles {...{expanded,setExpanded}}/>}
      <footer className="footer"><div><AccordLogo size={30}/><span><strong>FIELDACCORD</strong><small>Enter the Field. Carbon and silicon, building together.</small></span></div><span>Experimental protocol · Public showcase · No external effects</span><a href={REPO} target="_blank" rel="noreferrer">GitHub <ArrowUpRight size={14}/></a></footer>
      </main>
    </div>
  </div>;
}

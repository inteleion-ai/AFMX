import { useState } from 'react'
import { Card, ErrorState } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { useExecuteMutation } from '../hooks/useApi'
import { api } from '../api'
import { useApiKeyStore, toast } from '../store'
import { fmtMs } from '../utils/fmt'
import type { ValidateResponse, ExecutionRecord } from '../types'

/* ── Built-in matrix templates ── */
const TEMPLATES: Record<string, Record<string, unknown>> = {
  echo: {
    name: 'echo-pipeline', mode: 'SEQUENTIAL',
    nodes: [
      { id: 'n1', name: 'echo',  type: 'TOOL', handler: 'echo'  },
      { id: 'n2', name: 'upper', type: 'TOOL', handler: 'upper' },
    ],
    edges: [{ from: 'n1', to: 'n2' }],
  },
  agent: {
    name: 'agent-chain', mode: 'SEQUENTIAL',
    nodes: [
      { id: 'n1', name: 'analyst',  type: 'AGENT', handler: 'analyst_agent'  },
      { id: 'n2', name: 'writer',   type: 'AGENT', handler: 'writer_agent'   },
      { id: 'n3', name: 'reviewer', type: 'AGENT', handler: 'reviewer_agent' },
    ],
    edges: [{ from: 'n1', to: 'n2' }, { from: 'n2', to: 'n3' }],
  },
  parallel: {
    name: 'parallel-fan', mode: 'PARALLEL',
    nodes: [
      { id: 'n1', name: 'branch-a', type: 'TOOL', handler: 'echo' },
      { id: 'n2', name: 'branch-b', type: 'TOOL', handler: 'echo' },
      { id: 'n3', name: 'merge',    type: 'TOOL', handler: 'concat' },
    ],
    edges: [{ from: 'n1', to: 'n3' }, { from: 'n2', to: 'n3' }],
  },
  retry: {
    name: 'retry-fallback', mode: 'SEQUENTIAL',
    nodes: [
      { id: 'n1', name: 'flaky',    type: 'TOOL', handler: 'flaky',             retry_policy: { retries: 3, backoff_factor: 1.5 } },
      { id: 'n2', name: 'fallback', type: 'TOOL', handler: 'fallback_recovery' },
    ],
    edges: [{ from: 'n1', to: 'n2' }],
  },
  // v1.2: Cross-domain templates — each uses a different industry vocabulary

  // Tech / SRE  (default domain)
  cognitive: {
    name: 'cognitive-sre-matrix',
    mode: 'DIAGONAL',
    nodes: [
      { id: 'p1', name: 'alert-ingestor',  type: 'TOOL',  handler: 'echo',           cognitive_layer: 'PERCEIVE',  agent_role: 'OPS' },
      { id: 'p2', name: 'log-ingestor',    type: 'TOOL',  handler: 'echo',           cognitive_layer: 'PERCEIVE',  agent_role: 'ANALYST' },
      { id: 'r1', name: 'log-retriever',   type: 'TOOL',  handler: 'enrich',         cognitive_layer: 'RETRIEVE',  agent_role: 'OPS' },
      { id: 'r2', name: 'knowledge-fetch', type: 'TOOL',  handler: 'enrich',         cognitive_layer: 'RETRIEVE',  agent_role: 'RESEARCHER' },
      { id: 'a1', name: 'root-cause',      type: 'AGENT', handler: 'analyst_agent',  cognitive_layer: 'REASON',    agent_role: 'ANALYST' },
      { id: 'a2', name: 'risk-score',      type: 'AGENT', handler: 'analyst_agent',  cognitive_layer: 'REASON',    agent_role: 'COMPLIANCE' },
      { id: 'pl', name: 'runbook-gen',     type: 'AGENT', handler: 'writer_agent',   cognitive_layer: 'PLAN',      agent_role: 'OPS' },
      { id: 'ac', name: 'remediate',       type: 'AGENT', handler: 'analyst_agent',  cognitive_layer: 'ACT',       agent_role: 'OPS' },
      { id: 'ev', name: 'verify-fix',      type: 'AGENT', handler: 'reviewer_agent', cognitive_layer: 'EVALUATE',  agent_role: 'VERIFIER' },
      { id: 'rp', name: 'incident-report', type: 'TOOL',  handler: 'summarize',      cognitive_layer: 'REPORT',    agent_role: 'OPS' },
    ],
    edges: [
      { from: 'p1', to: 'r1' }, { from: 'p2', to: 'r2' },
      { from: 'r1', to: 'a1' }, { from: 'r2', to: 'a2' },
      { from: 'a1', to: 'pl' }, { from: 'a2', to: 'pl' },
      { from: 'pl', to: 'ac' },
      { from: 'ac', to: 'ev' },
      { from: 'ev', to: 'rp' },
    ],
  },

  // Finance / Capital Markets domain (FinanceRole vocabulary)
  finance: {
    name: 'cognitive-risk-matrix',
    mode: 'DIAGONAL',
    nodes: [
      { id: 'p1', name: 'market-signals',   type: 'TOOL',  handler: 'echo',           cognitive_layer: 'PERCEIVE',  agent_role: 'ANALYST' },
      { id: 'r1', name: 'price-retrieval',  type: 'TOOL',  handler: 'enrich',         cognitive_layer: 'RETRIEVE',  agent_role: 'QUANT' },
      { id: 'r2', name: 'model-lookup',     type: 'TOOL',  handler: 'enrich',         cognitive_layer: 'RETRIEVE',  agent_role: 'ANALYST' },
      { id: 'a1', name: 'quant-analysis',   type: 'AGENT', handler: 'analyst_agent',  cognitive_layer: 'REASON',    agent_role: 'QUANT' },
      { id: 'a2', name: 'risk-scoring',     type: 'AGENT', handler: 'analyst_agent',  cognitive_layer: 'REASON',    agent_role: 'RISK_MANAGER' },
      { id: 'pl', name: 'portfolio-plan',   type: 'AGENT', handler: 'writer_agent',   cognitive_layer: 'PLAN',      agent_role: 'PORTFOLIO_MANAGER' },
      { id: 'ac', name: 'execute-trade',    type: 'AGENT', handler: 'analyst_agent',  cognitive_layer: 'ACT',       agent_role: 'TRADER' },
      { id: 'ev', name: 'compliance-check', type: 'AGENT', handler: 'reviewer_agent', cognitive_layer: 'EVALUATE',  agent_role: 'COMPLIANCE_OFFICER' },
      { id: 'rp', name: 'risk-report',      type: 'TOOL',  handler: 'summarize',      cognitive_layer: 'REPORT',    agent_role: 'AUDITOR' },
    ],
    edges: [
      { from: 'p1', to: 'r1' }, { from: 'p1', to: 'r2' },
      { from: 'r1', to: 'a1' }, { from: 'r2', to: 'a2' },
      { from: 'a1', to: 'pl' }, { from: 'a2', to: 'pl' },
      { from: 'pl', to: 'ac' }, { from: 'ac', to: 'ev' }, { from: 'ev', to: 'rp' },
    ],
  },

  // Healthcare / Clinical domain (HealthcareRole vocabulary)
  healthcare: {
    name: 'cognitive-clinical-matrix',
    mode: 'DIAGONAL',
    nodes: [
      { id: 'p1', name: 'symptom-intake',    type: 'TOOL',  handler: 'echo',           cognitive_layer: 'PERCEIVE',  agent_role: 'NURSE' },
      { id: 'r1', name: 'record-retrieval',  type: 'TOOL',  handler: 'enrich',         cognitive_layer: 'RETRIEVE',  agent_role: 'NURSE' },
      { id: 'r2', name: 'guideline-lookup',  type: 'TOOL',  handler: 'enrich',         cognitive_layer: 'RETRIEVE',  agent_role: 'RESEARCHER' },
      { id: 'a1', name: 'diagnosis',         type: 'AGENT', handler: 'analyst_agent',  cognitive_layer: 'REASON',    agent_role: 'CLINICIAN' },
      { id: 'pl', name: 'treatment-plan',    type: 'AGENT', handler: 'writer_agent',   cognitive_layer: 'PLAN',      agent_role: 'CLINICIAN' },
      { id: 'a2', name: 'medication-check',  type: 'AGENT', handler: 'analyst_agent',  cognitive_layer: 'PLAN',      agent_role: 'PHARMACIST' },
      { id: 'ac', name: 'administer',        type: 'AGENT', handler: 'analyst_agent',  cognitive_layer: 'ACT',       agent_role: 'NURSE' },
      { id: 'ev', name: 'outcome-assess',    type: 'AGENT', handler: 'reviewer_agent', cognitive_layer: 'EVALUATE',  agent_role: 'ASSESSOR' },
      { id: 'rp', name: 'clinical-notes',    type: 'TOOL',  handler: 'summarize',      cognitive_layer: 'REPORT',    agent_role: 'CLINICIAN' },
    ],
    edges: [
      { from: 'p1', to: 'r1' }, { from: 'p1', to: 'r2' },
      { from: 'r1', to: 'a1' }, { from: 'r2', to: 'a1' },
      { from: 'a1', to: 'pl' }, { from: 'a1', to: 'a2' },
      { from: 'pl', to: 'ac' }, { from: 'a2', to: 'ac' },
      { from: 'ac', to: 'ev' }, { from: 'ev', to: 'rp' },
    ],
  },

  // Legal domain (LegalRole vocabulary)
  legal: {
    name: 'cognitive-legal-matrix',
    mode: 'DIAGONAL',
    nodes: [
      { id: 'p1', name: 'fact-gather',       type: 'TOOL',  handler: 'echo',           cognitive_layer: 'PERCEIVE',  agent_role: 'PARALEGAL' },
      { id: 'r1', name: 'precedent-search',  type: 'TOOL',  handler: 'enrich',         cognitive_layer: 'RETRIEVE',  agent_role: 'PARALEGAL' },
      { id: 'a1', name: 'legal-analysis',    type: 'AGENT', handler: 'analyst_agent',  cognitive_layer: 'REASON',    agent_role: 'ASSOCIATE' },
      { id: 'pl', name: 'strategy',          type: 'AGENT', handler: 'writer_agent',   cognitive_layer: 'PLAN',      agent_role: 'PARTNER' },
      { id: 'ac', name: 'file-brief',        type: 'AGENT', handler: 'analyst_agent',  cognitive_layer: 'ACT',       agent_role: 'CLERK' },
      { id: 'ev', name: 'outcome-assess',    type: 'AGENT', handler: 'reviewer_agent', cognitive_layer: 'EVALUATE',  agent_role: 'PARTNER' },
      { id: 'rp', name: 'client-memo',       type: 'TOOL',  handler: 'summarize',      cognitive_layer: 'REPORT',    agent_role: 'ASSOCIATE' },
    ],
    edges: [
      { from: 'p1', to: 'r1' }, { from: 'r1', to: 'a1' },
      { from: 'a1', to: 'pl' }, { from: 'pl', to: 'ac' },
      { from: 'ac', to: 'ev' }, { from: 'ev', to: 'rp' },
    ],
  },
}

/* ── Helpers ── */
function tryParseJson(s: string): unknown {
  try { return JSON.parse(s) } catch { return undefined }
}

/* ─────────────────────────────────────────────────────────────
   RunMatrix page
───────────────────────────────────────────────────────────── */
export default function RunMatrix() {
  const [matrixJson,  setMatrixJson]  = useState('')
  const [inputJson,   setInputJson]   = useState('')
  const [varsJson,    setVarsJson]    = useState('')
  const [triggeredBy, setTriggeredBy] = useState('dashboard')
  const [result,      setResult]      = useState<ExecutionRecord | null>(null)
  const [asyncResult, setAsyncResult] = useState<{ execution_id: string } | null>(null)
  const [validateRes, setValidateRes] = useState<ValidateResponse | null>(null)
  const [error,       setError]       = useState('')

  const syncMut  = useExecuteMutation(false)
  const asyncMut = useExecuteMutation(true)
  const apiKey   = useApiKeyStore(s => s.apiKey) || undefined

  /* JSON validation state */
  const matrixValid = matrixJson.trim() === '' ? null : tryParseJson(matrixJson) !== undefined
  const inputValid  = inputJson.trim()  === '' ? null : tryParseJson(inputJson)  !== undefined
  const varsValid   = varsJson.trim()   === '' ? null : tryParseJson(varsJson)   !== undefined

  const buildPayload = () => {
    const matrix = JSON.parse(matrixJson)
    const input  = inputJson.trim()  ? JSON.parse(inputJson)  : undefined
    const vars   = varsJson.trim()   ? JSON.parse(varsJson)   : undefined
    return {
      matrix,
      input,
      variables:    vars,
      triggered_by: triggeredBy || 'dashboard',
    }
  }

  const clearResults = () => {
    setError(''); setResult(null); setAsyncResult(null); setValidateRes(null)
  }

  const runSync = async () => {
    clearResults()
    try {
      const res = await syncMut.mutateAsync(buildPayload()) as ExecutionRecord
      setResult(res)
      toast.success(`${res.status} in ${fmtMs(res.duration_ms)}`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const runAsync = async () => {
    clearResults()
    try {
      const res = await asyncMut.mutateAsync(buildPayload()) as { execution_id: string }
      setAsyncResult(res)
      toast.info(`Queued → ${res.execution_id.slice(0, 8)}`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const validate = async () => {
    clearResults()
    try {
      const matrix = JSON.parse(matrixJson)
      const vr = await api.validate(matrix, apiKey)
      setValidateRes(vr)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const loadTemplate = (name: string) => {
    setMatrixJson(JSON.stringify(TEMPLATES[name], null, 2))
    setInputJson(JSON.stringify({ query: 'hello afmx' }, null, 2))
    clearResults()
  }

  const canRun = matrixJson.trim().length > 0 && matrixValid === true

  return (
    <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* ── Template chips ── */}
      <div>
        <div style={{ fontSize: 10.5, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', fontWeight: 600, marginBottom: 8 }}>
          Quick templates
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {Object.keys(TEMPLATES).map(name => (
            <button
              key={name}
              onClick={() => loadTemplate(name)}
              style={{
                padding:      '4px 12px',
                borderRadius: 'var(--r-full)',
                background:   'var(--bg-elevated)',
                border:       '1px solid var(--border-med)',
                fontSize:     12,
                color:        'var(--text-2)',
                cursor:       'pointer',
                fontWeight:   500,
                transition:   'all var(--t-fast)',
              }}
            >
              {name}
            </button>
          ))}
        </div>
      </div>

      {/* ── Two-column editor / result ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>

        {/* Left: editor */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* Matrix JSON */}
          <div>
            <label style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)' }}>
                Matrix Definition <span style={{ color: 'var(--red)' }}>*</span>
              </span>
              {matrixJson.trim() && (
                <span style={{ fontSize: 11, color: matrixValid ? 'var(--green)' : 'var(--red)' }}>
                  {matrixValid ? '✓ valid JSON' : '✕ invalid JSON'}
                </span>
              )}
            </label>
            <textarea
              className="field-input mono"
              value={matrixJson}
              onChange={e => setMatrixJson(e.target.value)}
              placeholder={'{\n  "name": "my-flow",\n  "mode": "SEQUENTIAL",\n  "nodes": [],\n  "edges": []\n}'}
              style={{
                minHeight:   220,
                fontSize:    11.5,
                borderColor: matrixValid === false ? 'var(--red)' : undefined,
              }}
              spellCheck={false}
            />
          </div>

          {/* Input + Variables */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)' }}>Input (JSON)</span>
                {inputJson.trim() && (
                  <span style={{ fontSize: 11, color: inputValid ? 'var(--green)' : 'var(--red)' }}>
                    {inputValid ? '✓' : '✕'}
                  </span>
                )}
              </label>
              <input
                className="field-input mono"
                value={inputJson}
                onChange={e => setInputJson(e.target.value)}
                placeholder='{"query": "hello"}'
                style={{ fontSize: 12, borderColor: inputValid === false ? 'var(--red)' : undefined }}
                spellCheck={false}
              />
            </div>
            <div>
              <label style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)' }}>Variables</span>
                {varsJson.trim() && (
                  <span style={{ fontSize: 11, color: varsValid ? 'var(--green)' : 'var(--red)' }}>
                    {varsValid ? '✓' : '✕'}
                  </span>
                )}
              </label>
              <input
                className="field-input mono"
                value={varsJson}
                onChange={e => setVarsJson(e.target.value)}
                placeholder="{}"
                style={{ fontSize: 12, borderColor: varsValid === false ? 'var(--red)' : undefined }}
                spellCheck={false}
              />
            </div>
          </div>

          {/* Triggered By */}
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 6 }}>
              Triggered By
            </label>
            <input
              className="field-input"
              value={triggeredBy}
              onChange={e => setTriggeredBy(e.target.value)}
              placeholder="dashboard"
            />
          </div>

          {/* Action buttons */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <Button
              variant="primary"
              size="md"
              onClick={runSync}
              loading={syncMut.isPending}
              disabled={!canRun}
              icon={
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <polygon points="2.5 1.5 10.5 6 2.5 10.5" fill="currentColor"/>
                </svg>
              }
            >
              Run Sync
            </Button>
            <Button
              variant="secondary"
              size="md"
              onClick={runAsync}
              loading={asyncMut.isPending}
              disabled={!canRun}
            >
              Run Async
            </Button>
            <Button
              variant="ghost"
              size="md"
              onClick={validate}
              disabled={!matrixJson.trim()}
            >
              Validate
            </Button>
            {(result || asyncResult || validateRes || error) && (
              <Button variant="ghost" size="md" onClick={clearResults}>
                Clear
              </Button>
            )}
          </div>

          {/* Validate result */}
          {validateRes && (
            <div style={{
              padding:      '10px 14px',
              borderRadius: 'var(--r-md)',
              background:   validateRes.valid ? 'var(--green-dim)' : 'var(--red-dim)',
              border:       `1px solid ${validateRes.valid ? 'var(--green-ring)' : 'var(--red-ring)'}`,
              fontSize:     12.5,
              color:        validateRes.valid ? 'var(--green)' : 'var(--red)',
            }}>
              {validateRes.valid ? (
                <>
                  ✓ Valid — {validateRes.node_count} node{validateRes.node_count !== 1 ? 's' : ''} · {validateRes.edge_count} edge{validateRes.edge_count !== 1 ? 's' : ''}
                  {validateRes.execution_order.length > 0 && (
                    <div style={{ color: 'var(--text-3)', marginTop: 6, fontSize: 11.5 }}>
                      Order: {validateRes.execution_order.join(' → ')}
                    </div>
                  )}
                </>
              ) : (
                <>
                  ✕ Invalid
                  {validateRes.errors.map((e, i) => (
                    <div key={i} style={{ marginTop: 4, fontSize: 11.5 }}>· {e}</div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>

        {/* Right: result */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)' }}>Result</span>
            {result && (
              <Badge
                variant={
                  result.status === 'COMPLETED' ? 'green' :
                  result.status === 'FAILED'    ? 'red'   : 'amber'
                }
                dot
              >
                {result.status}
              </Badge>
            )}
          </div>

          {error && <ErrorState message={error} />}

          {asyncResult && (
            <div style={{ padding: '10px 14px', background: 'var(--brand-dim)', border: '1px solid var(--brand-ring)', borderRadius: 'var(--r-md)', fontSize: 12.5, color: 'var(--brand)' }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>Queued successfully</div>
              <div className="mono" style={{ fontSize: 11, color: 'var(--text-2)', wordBreak: 'break-all' }}>
                {asyncResult.execution_id}
              </div>
              <div style={{ marginTop: 6, fontSize: 11.5, color: 'var(--text-3)' }}>
                Go to Live Stream to watch in real-time, or Executions to see the result.
              </div>
            </div>
          )}

          {/* Node result summary */}
          {result && Object.keys(result.node_results).length > 0 && (
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 8 }}>
                Node Results
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {Object.values(result.node_results).map(n => (
                  <div
                    key={n.node_id}
                    style={{
                      display:      'flex',
                      alignItems:   'center',
                      gap:          8,
                      padding:      '6px 10px',
                      borderRadius: 'var(--r-md)',
                      background:   'var(--bg-muted)',
                      border:       '1px solid var(--border-light)',
                    }}
                  >
                    <span style={{ flex: 1, fontSize: 12.5, fontWeight: 500, color: 'var(--text-1)' }}>
                      {n.node_name}
                    </span>
                    <Badge
                      variant={n.status === 'SUCCESS' ? 'green' : n.status === 'FAILED' ? 'red' : 'muted'}
                      dot
                    >
                      {n.status}
                    </Badge>
                    <span className="mono" style={{ fontSize: 11, color: 'var(--text-3)', minWidth: 48, textAlign: 'right' }}>
                      {fmtMs(n.duration_ms)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Raw JSON viewer */}
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '.05em' }}>
              Raw Response
            </div>
            <pre style={{
              background:    'var(--bg-muted)',
              border:        '1px solid var(--border)',
              borderRadius:  'var(--r-lg)',
              padding:       '14px 16px',
              fontSize:      11.5,
              fontFamily:    'var(--mono)',
              lineHeight:    1.7,
              color:         'var(--text-2)',
              whiteSpace:    'pre-wrap',
              wordBreak:     'break-word',
              overflowY:     'auto',
              minHeight:     240,
              maxHeight:     500,
            }}>
              {result
                ? JSON.stringify(result, null, 2)
                : asyncResult
                ? JSON.stringify(asyncResult, null, 2)
                : <span style={{ color: 'var(--text-4)' }}>Run a matrix to see the response…</span>
              }
            </pre>
          </div>
        </div>
      </div>
    </div>
  )
}

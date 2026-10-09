/**
 * Showcase-only, illustrative decision model.
 * Not the canonical Python FieldAccord policy kernel.
 * No access to network, storage, agents, device tools, or authority grants.
 */
export const actions = Object.freeze([
  { id: 'inspect', label: 'Inspect pinned evidence metadata', capability: 'read_evidence', description: 'Read metadata from a previously pinned source.' },
  { id: 'summarize', label: 'Draft a summary for review', capability: 'summarize', description: 'Prepare an advisory summary without publishing it.' },
  { id: 'publish', label: 'Publish directly to a repository', capability: 'write_repo', description: 'Attempt a GitHub write.' },
  { id: 'notify', label: 'Send a message to a family member', capability: 'message_person', description: 'Attempt an external notification.' },
  { id: 'device', label: 'Run a device command', capability: 'control_device', description: 'Attempt an action on physical hardware.' },
]);
export const illustrativeScopes = Object.freeze(['read_evidence', 'summarize']);

export function inspectProposal({ title, action, claimsApproval = false }) {
  const trimmedTitle = String(title || '').trim();
  const proposal = actions.find(item => item.id === action);
  const boundedTitle = trimmedTitle.slice(0, 160);
  const scoped = Boolean(proposal && illustrativeScopes.includes(proposal.capability));
  const outcome = boundedTitle && scoped ? 'REVIEW_REQUIRED' : 'BLOCKED';
  const reason = !boundedTitle
    ? 'A work intent must name a goal before it can be reviewed.'
    : !proposal
      ? 'Unknown proposal: fail closed.'
      : !scoped
        ? 'This proposed action is outside the synthetic WorkIntent scope.'
        : 'Within the example scope. Human review is still required; no grant or execution exists.';
  return {
    schema: 'fieldaccord.showcase.receipt.v0',
    source: 'synthetic browser illustration',
    work_intent: boundedTitle,
    proposed_action: proposal ? proposal.id : 'UNKNOWN',
    scope: illustrativeScopes,
    disposition: outcome,
    reason,
    claims_approval: Boolean(claimsApproval),
    identity_authenticated: false,
    authority_granted: false,
    action_executed: false,
    external_effects: false,
    durable_receipt: false,
  };
}

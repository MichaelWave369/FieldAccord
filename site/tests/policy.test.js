import test from 'node:test';
import assert from 'node:assert/strict';
import {inspectProposal, actions} from '../src/policy.js';

test('in-scope proposal is review-only and never executes', () => {
  const r = inspectProposal({title:'Review a deployment log',action:'inspect'});
  assert.equal(r.disposition,'REVIEW_REQUIRED');
  assert.equal(r.authority_granted,false);
  assert.equal(r.action_executed,false);
  assert.equal(r.external_effects,false);
});
test('approval claim cannot elevate an action', () => {
  const r = inspectProposal({title:'Review a deployment log',action:'inspect',claimsApproval:true});
  assert.equal(r.claims_approval,true);
  assert.equal(r.disposition,'REVIEW_REQUIRED');
  assert.equal(r.authority_granted,false);
});
test('unsafe capabilities remain blocked even with approval claim', () => {
  for (const action of ['publish','notify','device']) {
    const r=inspectProposal({title:'Review a deployment log',action,claimsApproval:true});
    assert.equal(r.disposition,'BLOCKED');
    assert.equal(r.action_executed,false);
    assert.equal(r.authority_granted,false);
  }
});
test('missing intent and unknown proposal fail closed', () => {
  assert.equal(inspectProposal({title:'',action:'inspect'}).disposition,'BLOCKED');
  assert.equal(inspectProposal({title:'Task',action:'not-real'}).disposition,'BLOCKED');
});
test('no action choice produces an authorized state', () => {
  for(const a of actions){
    const r=inspectProposal({title:'Synthetic work',action:a.id});
    assert.notEqual(r.disposition,'APPROVED');
    assert.equal(r.durable_receipt,false);
  }
});

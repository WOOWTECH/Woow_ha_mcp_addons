"""Owner-approval gate of the GitHub-hosted release route (.github/workflows/release.yaml). Standard library only.

    python packaging/environment_gate.py gate                 gate job: GH_TOKEN = the run's GITHUB_TOKEN
    python packaging/environment_gate.py publish RECORD       publish job: also this run's approval history
    python3 -I packaging/environment_gate.py gate --anonymous  outside Actions: the same checks, unauthenticated

Review H1: GitHub creates a missing environment, without any protection, the first time a job names it, and a job in
an unprotected environment runs at once. So before anything is built, the gate job reads the public-release
environment through the REST API (https://api.github.com only, no redirects, no proxy) and stops unless:
  - it exists, and its name is public-release;
  - its protection rules are only required_reviewers, branch_policy and wait_timer, with exactly one required_reviewers
    rule whose only reviewer is the User with id 165237880 (WOOWTECH, compared by id, never by name);
  - can_admins_bypass is false (a missing field fails too);
  - deployment_branch_policy is exactly {"protected_branches": false, "custom_branch_policies": true}, and the only
    deployment branch policy is the branch pattern release/*.
prevent_self_review is not required: today the account that dispatches is also the only reviewer. When it is on and
the user who dispatched (GITHUB_ACTOR_ID) is that only reviewer, the gate stops, since nobody could ever approve. The
publish job repeats these checks, refuses any run attempt but the first (an approval binds one attempt; start again
with a new dispatch), and reads GET /actions/runs/<run>/approvals: there must be an approved review of public-release
by user id 165237880 and no rejected one. A missing approval is asked for again, about 10 s apart, three times in all;
a rejection fails at once. The publish record (RECORD, a new file in a 0700 directory) keeps the run id, attempt,
commit, actor, the environment's updated_at and the reviews (whether each has a comment and its length, never the
comment text: the evidence of a public repository is readable by any signed-in user), for the release record.

HTTP 403, 429, 5xx and network errors (including a broken connection or a short body) are retried once, after
Retry-After (at most 60 s), then fail with one line; any other error fails at once. The token is sent only as the
Authorization header and never printed. Limits (docs/operations/release.md): this reads settings and a review history,
it cannot prove who pressed the button, and it runs from the dispatched branch like every other step.
"""
from datetime import datetime, timezone
import http.client
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

API = 'https://api.github.com'
REPOSITORY = 'WOOWTECH/Woow_ha_mcp_addons'
ENVIRONMENT = 'public-release'
OWNER_ID = 165237880  # the WOOWTECH user account, the only reviewer
RULE_TYPES = ('required_reviewers', 'branch_policy', 'wait_timer')
BRANCH_POLICY = {'protected_branches': False, 'custom_branch_policies': True}
MAX_BODY = 1 << 20
RETRYABLE = (403, 429)


class Closed(Exception):
    pass


class NotFound(Closed):
    pass


def require(condition, message):
    if not condition:
        raise Closed(message)


def same(value, expected):
    """Equality that also compares types (True is not 1), recursively."""
    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(value) == set(expected) and all(same(value[key], expected[key]) for key in expected)
    if isinstance(expected, list):
        return len(value) == len(expected) and all(same(a, b) for a, b in zip(value, expected))
    return value == expected


def request(url, headers):
    """GET a fixed https://api.github.com URL: no proxy, and a redirect is an error, so the token never leaves."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(req, timeout=30)


def retry_after(headers):
    try:
        return max(0, min(int((headers or {}).get('Retry-After', '5')), 60))
    except (TypeError, ValueError):
        return 5


def fetch(path, token, sleep=time.sleep):
    require(path.startswith('/repos/' + REPOSITORY + '/'), 'unexpected API path')
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'woow-ha-mcp-addons-environment-gate'}
    if token is not None:
        headers['Authorization'] = 'Bearer ' + token
    for attempt in (1, 2):
        try:
            with request(API + path, headers) as response:
                body = response.read(MAX_BODY + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotFound(path + ': 404') from None
            if exc.code not in RETRYABLE and exc.code < 500:
                raise Closed('%s: HTTP %d' % (path, exc.code)) from None
            reason, wait = 'HTTP %d' % exc.code, retry_after(exc.headers)
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            # A broken connection or a short body (IncompleteRead) is a network error too.
            reason, wait = 'network error (%s)' % type(exc).__name__, 5
        else:
            require(len(body) <= MAX_BODY, path + ': response too large')
            try:
                return json.loads(body)
            except ValueError:
                raise Closed(path + ': response is not JSON') from None
        if attempt == 2:
            raise Closed('%s: %s twice; GitHub API unavailable' % (path, reason))
        sleep(wait)


def check_environment(environment, policies):
    """The facts the gate requires of public-release; returns what the record keeps."""
    require(isinstance(environment, dict) and environment.get('name') == ENVIRONMENT, 'the environment is not ' + ENVIRONMENT)
    rules = environment.get('protection_rules')
    require(isinstance(rules, list) and all(isinstance(rule, dict) for rule in rules), 'protection rules missing')
    unknown = sorted({str(rule.get('type')) for rule in rules} - set(RULE_TYPES))
    require(not unknown, 'unknown protection rule: ' + ', '.join(unknown))
    reviewer_rules = [rule for rule in rules if rule.get('type') == 'required_reviewers']
    require(len(reviewer_rules) == 1, 'public-release needs exactly one required-reviewers rule')
    reviewers = reviewer_rules[0].get('reviewers')
    require(isinstance(reviewers, list) and len(reviewers) == 1, 'the owner must be the only required reviewer')
    reviewer = reviewers[0]
    require(isinstance(reviewer, dict) and reviewer.get('type') == 'User' and isinstance(reviewer.get('reviewer'), dict)
            and type(reviewer['reviewer'].get('id')) is int and reviewer['reviewer']['id'] == OWNER_ID,
            'the required reviewer is not the owner (User id %d)' % OWNER_ID)
    require(environment.get('can_admins_bypass') is False,
            'administrators can bypass the protection rules (can_admins_bypass is not false)')
    require(same(environment.get('deployment_branch_policy'), BRANCH_POLICY),
            'deployment branches must be the custom policy (protected_branches false, custom_branch_policies true)')
    require(isinstance(policies, dict) and type(policies.get('total_count')) is int and policies['total_count'] == 1
            and isinstance(policies.get('branch_policies'), list) and len(policies['branch_policies']) == 1,
            'public-release needs exactly one deployment branch policy')
    policy = policies['branch_policies'][0]
    require(isinstance(policy, dict) and policy.get('name') == 'release/*' and policy.get('type') == 'branch',
            'the deployment branch policy must be the branch pattern release/*')
    waits = [rule.get('wait_timer') for rule in rules if rule.get('type') == 'wait_timer']
    return {'id': environment.get('id'), 'name': ENVIRONMENT, 'updated_at': environment.get('updated_at'),
            'can_admins_bypass': False, 'prevent_self_review': reviewer_rules[0].get('prevent_self_review'),
            'reviewers': [{'type': 'User', 'id': OWNER_ID, 'login': reviewer['reviewer'].get('login')}],
            'wait_timer': waits[0] if waits else None, 'branch_policies': [{'name': 'release/*', 'type': 'branch'}]}


class NotApproved(Closed):
    pass


def check_approvals(approvals):
    require(isinstance(approvals, list) and all(isinstance(entry, dict) for entry in approvals),
            'the run review history is not a list')
    require(not any(entry.get('state') == 'rejected' for entry in approvals), 'this run has a rejected review')

    def names(entry):
        return [item.get('name') for item in entry.get('environments') or [] if isinstance(item, dict)]
    approved = [entry for entry in approvals if entry.get('state') == 'approved' and isinstance(entry.get('user'), dict)
                and type(entry['user'].get('id')) is int and entry['user']['id'] == OWNER_ID
                and ENVIRONMENT in names(entry)]
    if not approved:
        raise NotApproved('no approval of %s by the owner (User id %d) on this run' % (ENVIRONMENT, OWNER_ID))
    # The review comment is the reviewer's free text and the evidence artifact of a public repository is readable by
    # any signed-in user: keep only whether there is one and its length (review round 2).
    return [{'state': entry.get('state'), 'environments': names(entry),
             'user': {'login': (entry.get('user') or {}).get('login'), 'id': (entry.get('user') or {}).get('id')},
             'comment_present': bool(entry.get('comment')),
             'comment_length': len(entry['comment']) if isinstance(entry.get('comment'), str) else 0}
            for entry in approvals]


def approved_reviews(run_id, token, sleep=time.sleep, attempts=3, pause=10):
    """The run's review history once it holds the owner's approval: the review can be recorded a moment after the job
    starts, so a missing approval is asked for again (about 10 s apart, three times in all); a rejection fails at once."""
    path = '/repos/%s/actions/runs/%s/approvals' % (REPOSITORY, run_id)
    for attempt in range(1, attempts + 1):
        try:
            return check_approvals(fetch(path, token, sleep))
        except NotApproved:
            if attempt == attempts:
                raise
            sleep(pause)


def no_self_review_deadlock(facts, env):
    """With Prevent self-reviews on, the user who dispatched cannot approve; when that user is also the only reviewer the
    publish job would wait for an approval that can never come, so the gate stops at once. The dispatcher is
    GITHUB_ACTOR_ID, the numeric id of github.actor: it is compared by id like the reviewer, and on the first attempt
    (the only one check_release.py admits) github.actor is the user who dispatched; GITHUB_TRIGGERING_ACTOR differs
    only on re-runs and carries no id."""
    if facts['prevent_self_review'] is not True:
        return
    actor = env.get('GITHUB_ACTOR_ID', '')
    require(re.fullmatch(r'[1-9][0-9]{0,19}', actor) is not None,
            'Prevent self-reviews is on but GITHUB_ACTOR_ID is missing: cannot tell who dispatched')
    require(int(actor) != OWNER_ID, 'Prevent self-reviews is on and the user who dispatched (id %s) is the only required '
            'reviewer: the publish job would wait for an approval that can never come. Turn it off, or dispatch from '
            'another account' % actor)


def environment_facts(token, sleep=time.sleep):
    base = '/repos/%s/environments/%s' % (REPOSITORY, ENVIRONMENT)
    try:
        environment = fetch(base, token, sleep)
    except NotFound:
        raise Closed('the public-release environment does not exist. Create it first (required reviewer, release/* '
                     'branch rule, no administrator bypass): otherwise GitHub creates an unprotected one the first time '
                     'the publish job runs, and that job runs without approval') from None
    return check_environment(environment, fetch(base + '/deployment-branch-policies', token, sleep))


def write_once(path, value):
    directory = path.parent
    if not directory.exists():
        directory.mkdir(mode=0o700, parents=True)
    require(directory.is_dir() and not directory.is_symlink(), 'record directory is not a plain directory')
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main(argv, env=None, sleep=time.sleep):
    env = os.environ if env is None else env
    anonymous = argv[1:] == ['--anonymous'] and argv[:1] == ['gate']
    require(argv == ['gate'] or anonymous or (len(argv) == 2 and argv[0] == 'publish'),
            'usage: environment_gate.py gate [--anonymous] | publish RECORD')
    in_actions = env.get('GITHUB_ACTIONS') == 'true'
    require(not (anonymous and in_actions), 'anonymous mode is for local checks only; the workflow sends GH_TOKEN')
    token = None
    if not anonymous:
        token = env.get('GH_TOKEN', '')
        require(bool(token) and not any(ch.isspace() for ch in token), 'GH_TOKEN (the run\'s GITHUB_TOKEN) is missing')
    if in_actions:
        require(env.get('GITHUB_REPOSITORY') == REPOSITORY, 'not a run of ' + REPOSITORY)
    if argv[0] == 'publish':
        require(in_actions, 'publish mode runs only in the workflow')
        require(env.get('GITHUB_RUN_ATTEMPT') == '1',
                'a re-run (attempt %s) cannot publish: an approval binds the first attempt; dispatch a new run'
                % env.get('GITHUB_RUN_ATTEMPT'))
        run_id = env.get('GITHUB_RUN_ID', '')
        require(re.fullmatch(r'[1-9][0-9]{0,19}', run_id) is not None, 'GITHUB_RUN_ID missing')
    facts = environment_facts(token, sleep)
    if in_actions:
        no_self_review_deadlock(facts, env)
    print('PASS: %s requires User %d (prevent_self_review %s), no administrator bypass, release/* only; updated_at %s'
          % (ENVIRONMENT, OWNER_ID, facts['prevent_self_review'], facts['updated_at']))
    if argv[0] != 'publish':
        return facts
    reviews = approved_reviews(run_id, token, sleep)
    record = {'repository': REPOSITORY, 'environment': facts, 'reviews': reviews,
              'run': {'id': int(run_id), 'attempt': 1, 'sha': env.get('GITHUB_SHA'), 'ref': env.get('GITHUB_REF'),
                      'actor': env.get('GITHUB_ACTOR'), 'triggering_actor': env.get('GITHUB_TRIGGERING_ACTOR')},
              'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    write_once(Path(argv[1]), record)
    print('PASS: run %s attempt 1 approved for %s by User %d' % (run_id, ENVIRONMENT, OWNER_ID))
    return record


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except Closed as exc:
        raise SystemExit('environment gate CLOSED: ' + str(exc)) from None
    except (OSError, ValueError, KeyError, TypeError, AttributeError, http.client.HTTPException) as exc:
        raise SystemExit('environment gate CLOSED: ' + type(exc).__name__) from None

# Sybil Queue Manual Dismissal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an authenticated Ops user soft-dismiss one pending Sybil notification while retaining the row and audit history.

**Architecture:** Add a constant-time shared-secret boundary to one new DELETE endpoint. The endpoint conditionally changes `pending` to `dismissed` and writes a `ConversationAction` in the same transaction; the existing digest query keeps selecting only `pending`. The Ops page keeps the secret only in JavaScript memory and refreshes the retained row after dismissal.

**Tech Stack:** FastAPI, SQLAlchemy async, SQLite/aiosqlite, static HTML/CSS/JavaScript, standalone Python tests.

---

## File Structure

- Create `tests/test_ops_sybil_dismissal.py`: isolated database, authentication, transition, audit, and UI-source regressions.
- Modify `config.py`: add the optional write secret setting.
- Modify `routes/ops.py`: authenticate and soft-dismiss one pending row.
- Modify `routes/static/ops.html`: pending-only remove command, confirmation, password prompt, and refresh.
- Modify `.env.example`: empty `OPS_WRITE_SECRET` example value only.
- Modify `README.md`, `CLAUDE.md`, and `record.md`: document behavior, security, and verification.
- Modify local untracked `.env`: set the operator-provided secret without staging or printing it.

## Working Tree Constraints

- Work in `/home/bobby/Front-Agent`, where `routes/ops.py` already contains an unrelated uncommitted `failed_items` change. Preserve it and stage only dismissal-related hunks.
- Do not stage or modify the existing unrelated changes in `tasks/scheduler.py` or `tests/test_routing.py`.
- Never write the real secret into a tracked file, test fixture, command output, log, or response.
- Do not deploy or restart production until the focused and full offline suites pass.

### Task 1: Write Secret Boundary and Soft-Dismiss Endpoint

**Files:**
- Create: `tests/test_ops_sybil_dismissal.py`
- Modify: `config.py`
- Modify: `routes/ops.py`
- Modify: `.env.example`

- [ ] **Step 1: Write failing authentication and transition tests**

Create `tests/test_ops_sybil_dismissal.py` with an isolated SQLite harness:

```python
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from database import Base
from models import ConversationAction, SybilNotification
import routes.ops as ops_module


async def _with_database(case):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        with patch.object(ops_module, "AsyncSessionLocal", sessions):
            await case(sessions)
    finally:
        await engine.dispose()


async def _insert_notification(sessions, *, status="pending"):
    async with sessions() as db:
        item = SybilNotification(
            conversation_id="cnv_sybil",
            message="education review",
            handoff_type="education_review",
            linear_url="https://linear.example/CUS-1",
            status=status,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item.id


def _assert_http_error(expected_status, call):
    try:
        asyncio.run(call())
    except HTTPException as exc:
        assert exc.status_code == expected_status
    else:
        raise AssertionError(f"expected HTTP {expected_status}")
```

Add tests:

```python
def test_missing_server_secret_disables_dismissal():
    async def call():
        with patch.object(settings, "ops_write_secret", ""):
            await ops_module.dismiss_sybil_notification(1, "anything")

    _assert_http_error(503, call)


def test_wrong_secret_does_not_mutate_pending_row():
def test_missing_request_header_does_not_mutate_pending_row():
    async def case(sessions):
        item_id = await _insert_notification(sessions)
        with patch.object(settings, "ops_write_secret", "correct"):
            try:
                await ops_module.dismiss_sybil_notification(item_id, None)
            except HTTPException as exc:
                assert exc.status_code == 403
            else:
                raise AssertionError("missing write secret must be rejected")
        async with sessions() as db:
            assert (await db.get(SybilNotification, item_id)).status == "pending"

    asyncio.run(_with_database(case))


    async def case(sessions):
        item_id = await _insert_notification(sessions)
        with patch.object(settings, "ops_write_secret", "correct"):
            try:
                await ops_module.dismiss_sybil_notification(item_id, "wrong")
            except HTTPException as exc:
                assert exc.status_code == 403
            else:
                raise AssertionError("wrong write secret must be rejected")
        async with sessions() as db:
            assert (await db.get(SybilNotification, item_id)).status == "pending"

    asyncio.run(_with_database(case))


def test_pending_row_is_retained_as_dismissed_with_one_audit_action():
    async def case(sessions):
        item_id = await _insert_notification(sessions)
        with patch.object(settings, "ops_write_secret", "correct"):
            response = await ops_module.dismiss_sybil_notification(item_id, "correct")
            repeated = await ops_module.dismiss_sybil_notification(item_id, "correct")

        assert response["item"]["status"] == "dismissed"
        assert repeated["item"]["status"] == "dismissed"
        async with sessions() as db:
            item = await db.get(SybilNotification, item_id)
            assert item is not None
            assert item.status == "dismissed"
            assert item.message == "education review"
            assert item.linear_url == "https://linear.example/CUS-1"
            actions = await db.execute(
                select(ConversationAction).where(
                    ConversationAction.conversation_id == "cnv_sybil",
                    ConversationAction.action_type == "sybil_dismiss",
                    ConversationAction.action_key == f"notification:{item_id}",
                )
            )
            rows = actions.scalars().all()
            assert len(rows) == 1
            assert rows[0].result == "dismissed"

    asyncio.run(_with_database(case))


def test_sent_row_cannot_be_dismissed():
    async def case(sessions):
        item_id = await _insert_notification(sessions, status="sent")
        with patch.object(settings, "ops_write_secret", "correct"):
            try:
                await ops_module.dismiss_sybil_notification(item_id, "correct")
            except HTTPException as exc:
                assert exc.status_code == 409
            else:
                raise AssertionError("sent notification must be immutable")
        async with sessions() as db:
            assert (await db.get(SybilNotification, item_id)).status == "sent"

    asyncio.run(_with_database(case))


def test_unknown_notification_returns_404():
    async def case(_sessions):
        with patch.object(settings, "ops_write_secret", "correct"):
            try:
                await ops_module.dismiss_sybil_notification(999, "correct")
            except HTTPException as exc:
                assert exc.status_code == 404
            else:
                raise AssertionError("unknown notification must return 404")

    asyncio.run(_with_database(case))
```

Add the standalone runner:

```python
def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("ops sybil dismissal tests passed")
```

- [ ] **Step 2: Run the focused suite and verify RED**

```bash
.venv/bin/python tests/test_ops_sybil_dismissal.py
```

Expected: FAIL because the setting and endpoint do not exist.

- [ ] **Step 3: Add configuration and constant-time authentication**

Add to `Settings` in `config.py`:

```python
    # Shared secret for authenticated Ops mutations. Read-only routes stay open.
    ops_write_secret: str = ""
```

Add an empty example to `.env.example`:

```text
OPS_WRITE_SECRET=
```

In `routes/ops.py`, add imports:

```python
import hmac

from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import func, or_, select, update
```

Add the boundary:

```python
def _require_ops_write_secret(provided: str | None) -> None:
    configured = settings.ops_write_secret
    if not configured:
        raise HTTPException(status_code=503, detail="Ops write operations are disabled")
    if not provided or not hmac.compare_digest(provided, configured):
        raise HTTPException(status_code=403, detail="Invalid Ops write secret")
```

- [ ] **Step 4: Implement the soft-dismiss endpoint**

Add after `list_sybil`:

```python
@router.delete("/ops/api/sybil/{notification_id}")
async def dismiss_sybil_notification(
    notification_id: int,
    x_ops_write_secret: str | None = Header(default=None, alias="X-Ops-Write-Secret"),
):
    _require_ops_write_secret(x_ops_write_secret)

    async with AsyncSessionLocal() as db:
        item = await db.get(SybilNotification, notification_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Sybil notification not found")
        if item.status == "dismissed":
            return {"item": _sybil_to_dict(item)}
        if item.status != "pending":
            raise HTTPException(status_code=409, detail="Only pending notifications can be dismissed")

        statement = (
            update(SybilNotification)
            .where(
                SybilNotification.id == notification_id,
                SybilNotification.status == "pending",
            )
            .values(status="dismissed")
        )
        result = await db.execute(statement)
        if result.rowcount != 1:
            await db.rollback()
            current = await db.get(SybilNotification, notification_id)
            if current is not None and current.status == "dismissed":
                return {"item": _sybil_to_dict(current)}
            raise HTTPException(status_code=409, detail="Notification status changed")

        db.add(
            ConversationAction(
                conversation_id=item.conversation_id,
                action_type="sybil_dismiss",
                action_key=f"notification:{notification_id}",
                result="dismissed",
            )
        )
        await db.commit()
        await db.refresh(item)
        return {"item": _sybil_to_dict(item)}
```

- [ ] **Step 5: Verify GREEN and commit only intended backend hunks**

```bash
.venv/bin/python tests/test_ops_sybil_dismissal.py
.venv/bin/python tests/test_routing.py
git diff --check
```

Expected: focused suite prints success and routing remains green.

Stage `config.py`, `.env.example`, and the new test normally. Stage only the
authentication/endpoint hunks from the already-dirty `routes/ops.py`, then
verify the pre-existing `failed_items` hunk remains unstaged.

```bash
git diff --cached --check
git diff --cached -- config.py .env.example routes/ops.py tests/test_ops_sybil_dismissal.py
git diff -- routes/ops.py
git commit -m "feat: soft dismiss pending sybil notifications"
```

### Task 2: Pending-Only Ops UI Command

**Files:**
- Modify: `routes/static/ops.html`
- Modify: `tests/test_ops_sybil_dismissal.py`

- [ ] **Step 1: Add failing UI-source assertions**

```python
def test_ops_ui_keeps_secret_in_memory_and_only_pending_rows_are_actionable():
    source = Path("routes/static/ops.html").read_text()
    assert "let opsWriteSecret=''" in source
    assert "X-Ops-Write-Secret" in source
    assert "sessionStorage.setItem" not in source
    assert "localStorage.setItem('ops_write" not in source
    assert "item.status==='pending'" in source
    assert "dismissSybil" in source
    assert "DELETE" in source
```

- [ ] **Step 2: Run and verify RED**

```bash
.venv/bin/python tests/test_ops_sybil_dismissal.py
```

Expected: FAIL on missing UI behavior.

- [ ] **Step 3: Add compact command styling and localized text**

Add a compact destructive command style using existing button conventions:

```css
.button.danger { color:var(--red); border-color:#f0b7b2; background:var(--red-soft); }
.button.danger:hover { border-color:#e28b83; background:#ffe6e2; }
.button.compact { min-height:28px; padding:4px 8px; font-size:12px; }
```

Add English and Chinese I18N keys for `remove`, `removeConfirm`,
`writePassword`, `dismissFailed`, and `action`.

- [ ] **Step 4: Add in-memory authentication and refresh behavior**

Near the UI state declaration add:

```javascript
let opsWriteSecret='';
```

Add:

```javascript
async function dismissSybil(id,conversationId){
  if(!window.confirm(`${t('removeConfirm')} ${conversationId}`))return;
  if(!opsWriteSecret)opsWriteSecret=window.prompt(t('writePassword'))||'';
  if(!opsWriteSecret)return;
  const response=await fetch(`/ops/api/sybil/${encodeURIComponent(id)}`,{
    method:'DELETE',
    headers:{'X-Ops-Write-Secret':opsWriteSecret},
  });
  if(response.status===403)opsWriteSecret='';
  if(!response.ok){
    let detail=t('dismissFailed');
    try{const body=await response.json();detail=body.detail||detail;}catch(_error){}
    throw new Error(detail);
  }
  await load();
}
```

Update `renderSybilTable` to add an action column and render a compact danger
button only when `item.status==='pending'`. The button calls
`dismissSybil(item.id,item.conversation_id).catch(showError)`. Use neutral badge
styling for dismissed, warning for pending, and success for sent. Keep dismissed
rows visible.

- [ ] **Step 5: Run focused tests and commit UI**

```bash
.venv/bin/python tests/test_ops_sybil_dismissal.py
git diff --check
git add routes/static/ops.html tests/test_ops_sybil_dismissal.py
git commit -m "feat: add sybil queue dismiss control"
```

### Task 3: Local Secret, Documentation, and Full Verification

**Files:**
- Modify untracked: `.env`
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `record.md`

- [ ] **Step 1: Configure the real secret only in local `.env`**

Set `OPS_WRITE_SECRET` to the operator-provided value without printing it. Verify:

```bash
git check-ignore -v .env
git status --short .env
```

Expected: `.env` is ignored and never appears as staged or untracked.

- [ ] **Step 2: Update tracked documentation without the real value**

Document:

```text
- OPS_WRITE_SECRET enables authenticated Ops mutations.
- DELETE /ops/api/sybil/{id} changes pending to dismissed; it does not delete the row.
- sent rows are immutable and dismissed rows remain visible/auditable.
- the browser keeps the write secret only in page memory.
- use HTTPS for remote Ops write operations.
```

Add `.venv/bin/python tests/test_ops_sybil_dismissal.py` to the verification
commands in README and CLAUDE.

Append to `record.md`:

```markdown
- [feat] add authenticated soft dismissal for individual pending Sybil queue records while retaining dismissed history and audit actions (config.py, routes/ops.py, routes/static/ops.html, tests/test_ops_sybil_dismissal.py)
- [docs] document the Ops write secret and Sybil dismissed-state semantics without committing the real secret (.env.example, README.md, CLAUDE.md)
```

- [ ] **Step 3: Run the complete offline suite**

```bash
.venv/bin/python tests/test_ops_sybil_dismissal.py
.venv/bin/python tests/test_runtime_boundaries.py
.venv/bin/python tests/test_routing.py
.venv/bin/python tests/test_skills.py
.venv/bin/python tests/test_draft_adoption.py
.venv/bin/python -m compileall -q agent services tasks tools webhooks routes tests config.py main.py models.py
.venv/bin/python -m pip check
git diff --check
```

Expected: every script prints success; compileall, pip check, and diff check
produce no errors.

- [ ] **Step 4: Review secret and dirty-worktree boundaries**

```bash
git diff --cached --check
git status --short
git diff -- routes/ops.py tasks/scheduler.py tests/test_routing.py
```

Expected: the real secret is absent from tracked diffs; original `failed_items`,
draft-adoption scheduler, and routing-test changes remain intact unless they
were committed separately by their owner.

- [ ] **Step 5: Commit documentation**

```bash
git add README.md CLAUDE.md record.md
git commit -m "docs: explain sybil queue dismissal"
```

Do not restart production or call the mutation endpoint until deployment is
explicitly approved after both ongoing feature branches are reconciled.

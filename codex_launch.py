"""Local admission for Codex tabs; no credentials or provider lock mutations."""
from contextlib import contextmanager, ExitStack
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)
import hashlib
import os
from pathlib import Path
import shlex
import subprocess

from olock import file_lock, LockTimeout


def resume_target(argv):
    for i, arg in enumerate(argv):
        if arg == 'resume' and i + 1 < len(argv) and not argv[i + 1].startswith('-'):
            return argv[i + 1]
    return ''


def _existing_cli(sid):
    """Include pre-fix launches on POSIX; uncertain probes never kill/rebind."""
    if not sid or os.name != 'posix':
        return False
    try:
        result = subprocess.run(['ps', '-axo', 'command='], capture_output=True,
                                text=True, encoding='utf-8', errors='replace',
                                timeout=2)
        if result.returncode:
            return False
        for line in result.stdout.splitlines():
            try:
                args = shlex.split(line)
            except ValueError:
                continue
            if not args:
                continue
            exe = os.path.basename(args[0])
            if exe == 'codex' or (exe == 'node' and len(args) > 1 and os.path.basename(args[1]) == 'codex'):
                if resume_target(args) == sid:
                    return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    return False


@contextmanager
def session_guard(brain, tab, argv, root=None):
    """Hold OS locks through exit, before project context/lifecycle side effects.

    Different tabs may run together; aliases of the same conversation may not.
    Locks release automatically on process death; never unlink a locked inode.
    """
    sid = resume_target(argv)
    directory = Path(root) if root else Path(_paths.state_dir(str(Path.home()))) / 'codex-launch'
    keys = []
    if tab:
        import sessions_registry
        keys.append('tab:' + os.path.realpath(brain) + ':' + sessions_registry._slug(tab))
    if sid:
        keys.append('sid:' + os.path.realpath(os.environ.get('CODEX_HOME') or str(Path.home() / '.codex')) + ':' + sid)
    with ExitStack() as stack:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            for key in sorted(keys):
                path = directory / hashlib.sha256(key.encode()).hexdigest()
                stack.enter_context(file_lock(str(path), timeout=0))
            if _existing_cli(sid):
                raise LockTimeout('existing Codex CLI')
        except LockTimeout:
            print('WORKSPACE: esta conversación ya está abierta. Cierra su instancia anterior antes de reanudarla; no se abrió otra copia.')
            admitted = False
        except OSError as exc:
            print('WORKSPACE: no pude reservar esta sesión (%s). Apertura cancelada.' % exc)
            admitted = False
        else:
            admitted = True
        yield admitted


def transcript_tab(path, brain, sid):
    """Read only the initial generated project context, never later chat text."""
    import json
    import re
    import sessions_registry as reg
    try:
        with Path(path).open(encoding='utf-8') as stream:
            first = stream.readline(2 * 1024 * 1024)
            meta = json.loads(first)
            payload = meta.get('payload') or {}
            if (meta.get('type') != 'session_meta'
                    or (payload.get('session_id') or payload.get('id')) != sid
                    or os.path.realpath(payload.get('cwd') or '') != os.path.realpath(brain)):
                return ''
            total = len(first)
            for _ in range(32):
                line = stream.readline(2 * 1024 * 1024)
                total += len(line)
                if not line or total > 2 * 1024 * 1024:
                    break
                item = json.loads(line)
                payload = item.get('payload') or {}
                if item.get('type') != 'response_item' or payload.get('role') != 'user':
                    continue
                for part in payload.get('content') or []:
                    text = part.get('text', '')
                    if 'WORKSPACE:SESSION start' not in text:
                        continue
                    names = set(re.findall(r'PESTAÑA ACTIVA: «([^»]+)»', text))
                    slugs = {reg._slug(name) for name in names}
                    if len(slugs) == 1:
                        return next(iter(slugs))
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return ''


def rollout_path(sid):
    from engines import codex
    if not sid:
        return ''
    for base, dirs, files in os.walk(codex._sessions_root()):
        dirs.sort(reverse=True)
        for name in files:
            if name.endswith('-' + sid + '.jsonl'):
                return str(Path(base) / name)
    return ''


def verified_resume(brain, tab, current):
    """Recover only a proven wrong-tab binding with one captured alternative."""
    import sessions_registry as reg
    import session_continuity
    expected = reg._slug(tab)
    owner = transcript_tab(rollout_path(current), brain, current)
    if not owner or owner == expected:
        return current
    matches = set()
    try:
        for row in session_continuity.receipts(brain).get('runs', {}).values():
            sid = row.get('session_id') or ''
            if (row.get('engine') != 'codex' or row.get('capture_state') != 'captured'
                    or reg._slug(row.get('tab') or '') != expected or sid == current):
                continue
            if (transcript_tab(row.get('backup') or '', brain, sid) == expected
                    and transcript_tab(rollout_path(sid), brain, sid) == expected):
                matches.add(sid)
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    if len(matches) == 1:
        return next(iter(matches))
    raise ValueError('El vínculo apunta a otra pestaña y no existe una recuperación única verificada; no se abrió esa conversación.')


def repair_resume(brain, agent, tab, previous, verified):
    """Backup + compare-and-swap; caller already holds tab and target-id lease."""
    import sessions_registry as reg
    if previous == verified:
        return
    # Revalidate provenance inside the reservation, before any mutation.
    if verified_resume(brain, tab, previous) != verified:
        raise ValueError('Cambió la evidencia de recuperación; apertura cancelada.')
    if not reg.bind(brain, agent, tab, 'codex', verified, expected_rid=previous,
                    preserve_before=True):
        raise ValueError('Cambió el vínculo o no se pudo respaldar; apertura cancelada.')
    print('WORKSPACE: vínculo de esta pestaña recuperado desde su captura verificada; respaldo guardado.')

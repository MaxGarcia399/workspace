"""Queries and explicit, reviewable version actions. Python 3.9 stdlib only."""
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}


def clean_text(text):
    # Render subprocess output as text, never as terminal control sequences.
    text = re.sub(r"\x1b\][^\x07]*(?:\x07|$)", "", str(text))
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"(https?://)[^/\s@]+@", r"\1", text)
    return ''.join(c for c in text if c in '\n\t' or (ord(c) >= 32 and ord(c) != 127))


def run(argv, repo, timeout=15):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GH_PROMPT_DISABLED='1')
    try:
        p = subprocess.run(argv, cwd=repo, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=timeout, **NO_WINDOW)
        return p.returncode, p.stdout, clean_text(p.stderr)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, '', clean_text(str(e))


def git(repo, *args):
    return run(['git', *args], repo)


def value(repo, *args):
    rc, out, err = git(repo, *args)
    return out.strip() if rc == 0 else ''


def sha(repo, ref):
    if not ref or ref.startswith('-'):
        return ''
    return value(repo, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}')


def top(repo):
    return value(os.path.abspath(os.path.expanduser(repo)), 'rev-parse', '--show-toplevel')


def changed_files(repo):
    rc, out, _ = git(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all')
    if rc:
        return None
    rows = out.split('\0')
    result, i = [], 0
    while i < len(rows):
        row = rows[i]
        i += 1
        if len(row) < 4:
            continue
        status, name = row[:2], row[3:]
        previous = ''
        if 'R' in status or 'C' in status:
            previous = rows[i] if i < len(rows) else ''
            i += 1
        result.append(dict(path=name, status=status, previous=previous,
                           conflict=status in ('DD', 'AU', 'UD', 'UA', 'DU', 'AA', 'UU')))
    return result


def branch_path(repo, branch):
    rc, out, _ = git(repo, 'worktree', 'list', '--porcelain')
    path = None
    for line in out.splitlines() if rc == 0 else []:
        if line.startswith('worktree '):
            path = line[9:]
        elif line == 'branch refs/heads/' + branch:
            return path
    return None


def github_repo(repo):
    url = value(repo, 'remote', 'get-url', 'origin')
    m = re.fullmatch(r'(?:git@github\.com:|https://github\.com/|ssh://git@github\.com/)([\w.-]+/[\w.-]+?)(?:\.git)?/?', url)
    return m.group(1) if m else ''


def remote(repo):
    return clean_text(value(repo, 'remote', 'get-url', 'origin'))


def local_status(repo, branch=''):
    rows = changed_files(repo)
    upstream = value(repo, 'rev-parse', '--abbrev-ref', '@{upstream}')
    branch = branch or value(repo, 'branch', '--show-current')
    reference = upstream if branch == value(repo, 'branch', '--show-current') and upstream else 'refs/remotes/origin/' + branch
    a = b = None
    if sha(repo, reference) and sha(repo, branch):
        counts = value(repo, 'rev-list', '--left-right', '--count', reference + '...' + branch).split()
        if len(counts) == 2:
            b, a = map(int, counts)
    merge = bool(value(repo, 'rev-parse', '-q', '--verify', 'MERGE_HEAD'))
    return dict(files=rows or [], known=rows is not None, branch=branch,
                current_branch=value(repo, 'branch', '--show-current'),
                ahead=a, behind=b, remote=remote(repo), upstream=reference,
                conflict=merge or any(r['conflict'] for r in rows or []),
                gh=bool(shutil.which('gh')), github=github_repo(repo))


def history(repo, ref, limit=60):
    target = sha(repo, ref)
    if not target:
        return []
    rc, out, _ = git(repo, 'log', '-%d' % limit,
                    '--format=%H%x1f%h%x1f%s%x1f%cr', target)
    result = []
    for line in out.splitlines() if rc == 0 else []:
        fields = line.split('\x1f')
        if len(fields) == 4:
            result.append(dict(sha=fields[0], short=fields[1], title=clean_text(fields[2]), ago=fields[3]))
    return result


def review(repo, ref):
    target = sha(repo, ref)
    if not target:
        return ['No se pudo resolver esta versión.']
    base = sha(repo, 'main')
    args = ['show', '--format=fuller', '--stat', '--patch', target] if base == target or not base else ['diff', base + '...' + target]
    rc, out, err = git(repo, *args)
    return clean_text(out if rc == 0 else err).splitlines()[:2500] or ['Sin diferencias para mostrar.']


def machine(repo):
    result = dict(system=platform.system(), python=platform.python_version(),
                  git=bool(shutil.which('git')), gh=bool(shutil.which('gh')))
    try:
        d = shutil.disk_usage(repo)
        result.update(free_gb=round(d.free / (1024 ** 3), 1), used_pct=round(100 * d.used / d.total))
    except OSError:
        pass
    try:
        result['load'] = os.getloadavg()[0]
    except (AttributeError, OSError):
        pass
    return result


def cloud(repo):
    ghrepo = github_repo(repo)
    if not ghrepo or not shutil.which('gh'):
        return dict(error='GitHub necesita un origin de github.com y GitHub CLI (gh).')
    data = dict(stamped=time.time(), github=ghrepo)
    rc, login, err = run(['gh', 'api', 'user', '--jq', '.login'], repo, timeout=15)
    if rc == 0:
        data['account'] = clean_text(login.strip())
    queries = {
        'prs': ['pr', 'list', '--state', 'open', '--limit', '30', '--json', 'number,title,headRefName,baseRefName,isDraft,headRefOid,url'],
        'runs': ['run', 'list', '--limit', '12', '--json', 'databaseId,displayTitle,headBranch,headSha,status,conclusion,url'],
        'releases': ['release', 'list', '--limit', '12', '--json', 'tagName,name,isDraft,isPrerelease,publishedAt'],
    }
    for key, args in queries.items():
        rc, out, err = run(['gh', *args, '--repo', ghrepo], repo, timeout=30)
        if rc:
            data[key] = []
            data.setdefault('errors', []).append(key + ': ' + (err or 'consulta fallida'))
        else:
            try:
                data[key] = json.loads(out)
            except ValueError:
                data[key] = []
                data.setdefault('errors', []).append(key + ': respuesta no válida')
    return data


def project_store():
    return Path(os.path.expanduser('~')) / '.claude' / 'workspace' / 'version-projects.json'


def projects(default):
    paths = [os.path.realpath(default)]
    try:
        data = json.loads(project_store().read_text())
        paths += [p for p in data if isinstance(p, str) and os.path.isdir(p)]
    except (OSError, ValueError, TypeError):
        pass
    return list(dict.fromkeys(paths))


def add_project(path, default):
    if not path.strip():
        raise ValueError('Escribe la carpeta del proyecto.')
    resolved = top(path)
    if not resolved:
        raise ValueError('Esta carpeta no contiene un proyecto Git. Elige la carpeta del proyecto.')
    paths = projects(default)
    if resolved not in paths:
        paths.append(resolved)
    p = project_store()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp-%d' % os.getpid())
    tmp.write_text(json.dumps(paths, ensure_ascii=False, indent=2))
    os.replace(str(tmp), str(p))
    return resolved


ACTIONS = [
    ('fetch', 'Consultar GitHub', 'Trae las referencias del servidor y consulta revisiones, pruebas y releases.'),
    ('commit', 'Guardar cambios', 'Crea un punto de guardado local con los archivos que elegiste en Cambios.'),
    ('pull', 'Traer cambios a esta rama', 'Actualiza su carpeta desde origin si avanza sin mezclar historias.'),
    ('push', 'Subir versión a GitHub', 'Sube la rama o el commit elegido a una rama de destino. No borra archivos locales.'),
    ('pr', 'Pedir revisión', 'Sube la rama y crea una solicitud de revisión en borrador (pull request).'),
    ('ready', 'Publicar solicitud de revisión', 'Convierte un pull request en borrador en una revisión abierta.'),
    ('review_pr', 'Revisar pull request', 'Muestra las diferencias de una revisión de GitHub, sin aprobar ni publicar nada.'),
    ('comment', 'Enviar review / comentario', 'Publica tu comentario de revisión en el pull request indicado.'),
    ('approve', 'Aprobar revisión', 'Registra tu aprobación del pull request indicado; no integra sus cambios.'),
    ('changes', 'Solicitar ajustes', 'Envía los cambios que pides antes de aprobar un pull request.'),
    ('merge', 'Integrar revisión', 'Une el pull request con su destino mediante GitHub y respeta sus reglas.'),
    ('release', 'Preparar release', 'Crea un release en borrador desde el commit exacto elegido, con notas automáticas.'),
    ('release_publish', 'Publicar release', 'Publica un release en borrador ya creado en GitHub.'),
    ('verify', 'Verificar proyecto', 'Ejecuta tests/run.py o unittest si el proyecto tiene tests; muestra el resultado.'),
    ('promote', 'Marcar main como estable', 'Ejecuta workspace promote: pruebas y avance de main a stable, localmente.'),
    ('publish', 'Publicar para el equipo', 'Sube main y stable juntas; el equipo recibe lo guardado al actualizar.'),
    ('dist', 'Publicar distribución', 'Ejecuta workspace release desde esta versión hacia el repositorio de distribución.'),
]
FORMS = {
    'commit': [('message', 'Nombre del punto de guardado', '')],
    'push': [('destination', 'Rama de destino en GitHub', '{branch}')],
    'pr': [('base', 'Rama que recibirá los cambios', 'main'), ('title', 'Título de la revisión', ''), ('body', 'Qué cambió / qué debe revisar el equipo', '')],
    'ready': [('pr', 'Número del pull request', '')],
    'review_pr': [('pr', 'Número del pull request', '')],
    'comment': [('pr', 'Número del pull request', ''), ('body', 'Tu comentario de revisión', '')],
    'approve': [('pr', 'Número del pull request', ''), ('body', 'Motivo de tu aprobación', '')],
    'changes': [('pr', 'Número del pull request', ''), ('body', 'Qué cambios necesitas', '')],
    'merge': [('pr', 'Número del pull request', '')],
    'release': [('tag', 'Versión nueva (ej. v0.2.0)', ''), ('title', 'Nombre del release', '')],
    'release_publish': [('tag', 'Versión del borrador que publicarás', '')],
    'dist': [('distribution', 'Carpeta del repo de distribución', os.path.expanduser('~/Desktop/workspace-harness'))],
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def valid_branch(repo, name):
    return bool(name and not name.startswith('-') and git(repo, 'check-ref-format', '--branch', name)[0] == 0)


def fingerprint(repo, files):
    h = hashlib.sha256()
    rc, out, err = git(repo, 'diff', '--cached', '--binary', '--', *files)
    _require(rc == 0, 'No pude comprobar los archivos preparados.')
    h.update(out.encode('utf-8'))
    for name in files:
        p = Path(repo) / name
        h.update(name.encode('utf-8'))
        if p.is_symlink():
            h.update(os.readlink(str(p)).encode('utf-8'))
        elif p.is_file():
            with p.open('rb') as f:
                for block in iter(lambda: f.read(65536), b''):
                    h.update(block)
        elif p.exists():
            raise ValueError('Selecciona archivos, no carpetas o submódulos: ' + name)
        else:
            h.update(b'deleted')
    return h.hexdigest()


def prepare(action, repo, branch, ref, fields=None, files=None, remote_data=None):
    """Read-only preflight. No write, no network. Freeze source/destination."""
    fields, files, remote_data = fields or {}, files or [], remote_data or {}
    _require(action in dict((a[0], a) for a in ACTIONS), 'Acción desconocida.')
    source = sha(repo, ref)
    _require(source or action == 'fetch', 'No encuentro esta versión. Refresca y vuelve a elegir.')
    head = sha(repo, 'HEAD')
    ghrepo = github_repo(repo)
    title = next(a[1] for a in ACTIONS if a[0] == action)
    description = next(a[2] for a in ACTIONS if a[0] == action)
    plan = dict(action=action, title=title, description=description, repo=repo,
                branch=branch, source=source, branch_tip=sha(repo, branch), head=head,
                root_branch=value(repo, 'symbolic-ref', '--short', '-q', 'HEAD'), fields=dict(fields),
                files=list(files), commands=[], cloud=False, created=time.time(), guards=[])
    def command(argv, cwd=None, body=None):
        plan['commands'].append(dict(argv=argv, cwd=cwd or repo, body=body))
    def need_remote():
        _require(remote(repo), 'Este proyecto no tiene origin. Conecta su repositorio remoto primero.')
    def need_gh():
        _require(shutil.which('gh'), 'GitHub CLI no está instalado. Instala gh y conecta tu cuenta con gh auth login.')
        _require(ghrepo, 'origin debe apuntar al repositorio de github.com que quieres administrar.')
        plan['github'] = ghrepo
    def need_clean(path):
        rows = changed_files(path)
        _require(rows is not None and not rows, 'Hay trabajo sin guardar en esta carpeta. Guárdalo antes de actualizarla.')
        plan['guards'].append(('clean', path))
        plan['guards'].append(('head', path, sha(path, 'HEAD'), value(path, 'symbolic-ref', '--short', '-q', 'HEAD')))
    def pr_number():
        number = fields.get('pr', '')
        _require(str(number).isdigit() and int(number) > 0, 'Escribe el número de la revisión, por ejemplo 12.')
        return str(number)
    if action == 'fetch':
        need_remote()
        command(['git', 'fetch', 'origin'])
        plan['cloud'] = True
    elif action == 'commit':
        path = branch_path(repo, branch)
        _require(path and sha(path, 'HEAD') == source, 'Para guardar, elige la rama abierta en esa carpeta, sin fijar un commit antiguo.')
        _require(files, 'En Cambios, marca con espacio los archivos que quieres guardar.')
        rows = changed_files(path)
        available = {name for r in rows or [] for name in (r['path'], r['previous']) if name}
        files = list(dict.fromkeys(files + [r['previous'] for r in rows or [] if r['path'] in files and r['previous']]))
        plan['files'] = files
        _require(all(f in available and not os.path.isabs(f) and '..' not in Path(f).parts for f in files), 'La lista de archivos cambió. Vuelve a Cambios.')
        _require(not any(r['conflict'] for r in rows or []), 'Hay un conflicto pendiente. Resuélvelo antes de guardar.')
        message = fields.get('message', '').strip()
        _require(message, 'Escribe un nombre que explique qué estás guardando.')
        plan['guards'].append(('fingerprint', path, list(files), fingerprint(path, files)))
        plan['guards'].append(('head', path, sha(path, 'HEAD'), value(path, 'symbolic-ref', '--short', '-q', 'HEAD')))
        for r in rows or []:
            if r['path'] in files and r['previous']:
                _require(r['previous'] in files, 'Un cambio de nombre debe incluir también su archivo anterior; guarda ese cambio con Git antes de continuar.')
        command(['git', 'add', '--', *files], path)
        command(['git', 'commit', '--only', '-m', message, '--', *files], path)
    elif action == 'pull':
        need_remote()
        path = branch_path(repo, branch)
        _require(path, 'Abre primero esta rama en una carpeta (Enter en el mapa).')
        _require(sha(path, 'HEAD') == source, 'Actualizar trabaja sobre la punta de la rama, no sobre un commit anterior.')
        need_clean(path)
        command(['git', 'pull', '--ff-only', 'origin', branch], path)
    elif action in ('push', 'pr'):
        need_remote()
        destination = fields.get('destination', branch) if action == 'push' else branch
        _require(valid_branch(repo, destination), 'El nombre de rama de destino no es válido.')
        command(['git', 'push', '--porcelain', 'origin', source + ':refs/heads/' + destination])
        plan['destination'] = destination
        if action == 'pr':
            need_gh()
            _require(sha(repo, branch) == source, 'Para pedir revisión elige la punta de la rama. Puedes subir un commit antiguo como otra rama.')
            base = fields.get('base', 'main')
            _require(valid_branch(repo, base) and base != branch, 'Elige una rama de destino distinta de la rama que revisas.')
            _require(fields.get('title', '').strip(), 'Escribe el título de la revisión.')
            command(['gh', 'pr', 'create', '--repo', ghrepo, '--draft', '--base', base, '--head', branch,
                     '--title', fields['title'], '--body-file', '{body-file}'], body=fields.get('body', ''))
    elif action in ('ready', 'review_pr', 'comment', 'approve', 'changes', 'merge'):
        need_gh()
        number = pr_number()
        plan['destination'] = 'PR #' + number
        if action == 'review_pr':
            command(['gh', 'pr', 'diff', number, '--repo', ghrepo])
        elif action == 'ready':
            command(['gh', 'pr', 'ready', number, '--repo', ghrepo])
        elif action == 'merge':
            pr = next((p for p in remote_data.get('prs', []) if str(p['number']) == number), None)
            _require(pr and pr.get('headRefOid'), 'Consulta GitHub primero para fijar la versión exacta de esta revisión.')
            _require(not pr.get('isDraft'), 'La revisión sigue en borrador. Publícala antes de integrarla.')
            plan['pr_head'] = pr['headRefOid']
            command(['gh', 'pr', 'merge', number, '--repo', ghrepo, '--merge', '--match-head-commit', pr['headRefOid']])
        else:
            _require(fields.get('body', '').strip(), 'Escribe tu comentario: se publicará con tu cuenta de GitHub.')
            flag = {'comment': '--comment', 'approve': '--approve', 'changes': '--request-changes'}[action]
            command(['gh', 'pr', 'review', number, '--repo', ghrepo, flag, '--body-file', '{body-file}'], body=fields['body'])
    elif action in ('release', 'release_publish'):
        need_gh()
        tag = fields.get('tag', '').strip()
        _require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,100}', tag) and
                 git(repo, 'check-ref-format', 'refs/tags/' + tag)[0] == 0, 'Usa una versión válida, por ejemplo v0.2.0.')
        plan['destination'] = tag
        if action == 'release':
            need_remote()
            command(['gh', 'release', 'create', tag, '--repo', ghrepo, '--target', source,
                     '--draft', '--generate-notes', '--title', fields.get('title') or tag])
            plan['check_new_tag'] = tag
            plan['guards'].append(('published', source))
        else:
            release = next((r for r in remote_data.get('releases', []) if r.get('tagName') == tag), None)
            _require(release and release.get('isDraft'), 'Consulta GitHub y elige una versión que esté en borrador.')
            command(['gh', 'release', 'edit', tag, '--repo', ghrepo, '--draft=false'])
    elif action == 'verify':
        path = branch_path(repo, branch)
        _require(path and sha(path, 'HEAD') == source, 'Verificar ejecuta las pruebas de una rama abierta, no de un commit antiguo.')
        plan['guards'].append(('head', path, source, branch))
        if os.path.isfile(os.path.join(path, 'tests', 'run.py')):
            command([sys.executable, os.path.join(path, 'tests', 'run.py')], path)
        else:
            _require(os.path.isdir(os.path.join(path, 'tests')), 'No hay carpeta tests en este proyecto. El panel no conoce un comando de pruebas para él.')
            command([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'], path)
        plan['guards'].append(('fingerprint', path, [r['path'] for r in changed_files(path) or []], fingerprint(path, [r['path'] for r in changed_files(path) or []])))
    elif action in ('promote', 'publish', 'dist'):
        _require(os.path.isfile(os.path.join(repo, 'make-dist.sh')) and os.path.isfile(os.path.join(repo, 'front.py')), 'Esta acción es propia del harness WORKSPACE; para este proyecto usa subir o release GitHub.')
        if action == 'promote':
            _require(branch == 'main' and source == sha(repo, 'main'), 'Elige la punta de main para marcarla estable.')
            need_clean(repo)
            _require(sha(repo, 'stable'), 'Este proyecto no tiene rama stable.')
            plan['guards'].append(('ref', 'stable', sha(repo, 'stable')))
            command([sys.executable, os.path.join(repo, 'front.py'), 'promote'])
        elif action == 'publish':
            need_remote()
            main, stable = sha(repo, 'main'), sha(repo, 'stable')
            _require(main and stable, 'Deben existir main y stable para publicar al equipo.')
            plan['guards'] += [('ref', 'main', main), ('ref', 'stable', stable)]
            command(['git', 'push', '--atomic', 'origin', main + ':refs/heads/main', stable + ':refs/heads/stable'])
            plan['destination'] = 'origin/main + origin/stable'
        else:
            dist = top(fields.get('distribution', ''))
            _require(dist and os.path.realpath(dist) != os.path.realpath(repo), 'Elige un repositorio de distribución separado.')
            need_clean(dist)
            _require(remote(dist), 'La distribución no tiene origin.')
            plan['guards'].append(('head', dist, sha(dist, 'HEAD'), value(dist, 'symbolic-ref', '--short', '-q', 'HEAD')))
            plan['guards'].append(('remote', dist, remote(dist)))
            _require(shutil.which('bash'), 'Esta distribución necesita bash (Git for Windows en Windows).')
            plan['distribution_remote'] = remote(dist)
            command([sys.executable, os.path.join(repo, 'front.py'), 'release', '--ref', source, '--dist', dist])
            plan['destination'] = dist
    plan['remote'] = remote(repo)
    return plan


def validate(plan):
    repo = plan['repo']
    _require(sha(repo, 'HEAD') == plan['head'], 'La rama abierta cambió desde la vista previa. Refresca antes de ejecutar.')
    _require(value(repo, 'symbolic-ref', '--short', '-q', 'HEAD') == plan['root_branch'], 'La rama abierta cambió desde la vista previa. Refresca antes de ejecutar.')
    _require(remote(repo) == plan['remote'], 'El destino origin cambió. Vuelve a preparar la acción.')
    _require(sha(repo, plan['branch']) == plan['branch_tip'], 'La rama cambió desde la vista previa. Vuelve a elegir la versión.')
    for guard in plan['guards']:
        if guard[0] == 'clean':
            rows = changed_files(guard[1])
            _require(rows is not None and not rows, 'Apareció trabajo sin guardar; no modifico esa carpeta.')
        elif guard[0] == 'fingerprint':
            _require(fingerprint(guard[1], guard[2]) == guard[3], 'Los archivos cambiaron desde la vista previa. Revisa el contenido actual.')
        elif guard[0] == 'ref':
            _require(sha(repo, guard[1]) == guard[2], 'La versión de ' + guard[1] + ' cambió desde la vista previa.')
        elif guard[0] == 'head':
            _require(sha(guard[1], 'HEAD') == guard[2] and value(guard[1], 'symbolic-ref', '--short', '-q', 'HEAD') == guard[3], 'La versión de la carpeta elegida cambió.')
        elif guard[0] == 'remote':
            _require(remote(guard[1]) == guard[2], 'El destino de distribución cambió. Vuelve a preparar la acción.')


def display_command(command):
    return clean_text(shlex.join(command['argv']).replace("'{body-file}'", '<texto de tu formulario>'))


class Job:
    """Commands run off the terminal thread; bounded output + truthful result."""
    def __init__(self, plan):
        self.plan = plan
        self.lines = deque(maxlen=3000)
        self.lock = threading.Lock()
        self.done = False
        self.ok = False
        self.error = ''
        self.cloud = None
        self.started = time.time()
        self.thread = threading.Thread(target=self._work, daemon=True)

    def log(self, text):
        with self.lock:
            self.lines.extend(clean_text(text).splitlines())

    def output(self):
        with self.lock:
            return list(self.lines)

    def start(self):
        self.thread.start()
        return self

    def _work(self):
        p = self.plan
        try:
            validate(p)
            for guard in p['guards']:
                if guard[0] == 'published':
                    rc, out, err = run(['git', 'fetch', 'origin'], p['repo'], 120)
                    _require(rc == 0, 'No pude consultar origin: ' + err)
                    refs = value(p['repo'], 'branch', '-r', '--contains', guard[1]).splitlines()
                    _require(any(r.strip().startswith('origin/') for r in refs), 'Sube esta versión a GitHub antes de preparar un release.')
            if p.get('check_new_tag'):
                rc, out, err = run(['git', 'ls-remote', '--tags', 'origin', 'refs/tags/' + p['check_new_tag']], p['repo'], 60)
                _require(rc == 0 and not out.strip(), 'Esta etiqueta ya existe en GitHub o no pude comprobarla. Elige otra versión.')
            for index, c in enumerate(p['commands']):
                self.log('Paso %d/%d · %s' % (index + 1, len(p['commands']), display_command(c)))
                argv = list(c['argv'])
                with tempfile.TemporaryDirectory(prefix='workspace-version-') as tmp:
                    if c.get('body') is not None:
                        body = os.path.join(tmp, 'body.md')
                        Path(body).write_text(c['body'], encoding='utf-8')
                        argv = [body if a == '{body-file}' else a for a in argv]
                    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GH_PROMPT_DISABLED='1', PYTHONDONTWRITEBYTECODE='1')
                    logpath = os.path.join(tmp, 'output.log')
                    with open(logpath, 'wb') as writer, open(logpath, 'rb') as output:
                        process = subprocess.Popen(argv, cwd=c['cwd'], env=env,
                                                   stdin=subprocess.DEVNULL, stdout=writer,
                                                   stderr=subprocess.STDOUT, **NO_WINDOW)
                        position, partial = 0, b''
                        deadline = time.monotonic() + (3600 if p['action'] in ('verify', 'promote', 'dist') else 180)
                        while True:
                            output.seek(position)
                            chunk = output.read()
                            position += len(chunk)
                            partial += chunk
                            while b'\n' in partial:
                                line, partial = partial.split(b'\n', 1)
                                self.log(line.decode('utf-8', 'replace'))
                            if process.poll() is not None:
                                output.seek(position)
                                partial += output.read()
                                if partial:
                                    self.log(partial.decode('utf-8', 'replace'))
                                break
                            if time.monotonic() > deadline:
                                process.terminate()
                                try:
                                    process.wait(timeout=5)
                                except subprocess.TimeoutExpired:
                                    process.kill()
                                    process.wait()
                                raise ValueError('El comando tardó demasiado. Revisa el estado antes de reintentar; pudo completar parte del trabajo.')
                            time.sleep(.1)
                    _require(process.returncode == 0, 'El paso %d falló (código %d). Los pasos anteriores pueden haberse completado; revisa la salida.' % (index + 1, process.returncode))
            if p.get('cloud'):
                self.cloud = cloud(p['repo'])
                self.log('Consulta GitHub completada.' if not self.cloud.get('error') and not self.cloud.get('errors') else 'Git local actualizado; GitHub tiene consultas pendientes o fallidas.')
            self.ok = True
            self.log('Completado · ' + p['title'])
        except Exception as e:
            self.error = clean_text(str(e))
            self.log('No completado · ' + self.error)
        finally:
            self.done = True

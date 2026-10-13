"""Version cockpit: plain language, explicit commands, GitHub and local projects."""
import os
import time
from pathlib import Path

import git_ops as O

VIEWS = ('Mapa', 'Resumen', 'Acciones', 'Historial', 'Cambios', 'GitHub', 'Proyectos', 'Ayuda')
#: id estable de cada vista (VIEWS es la etiqueta ES y se compara en código).
_VIEW_IDS = ('map', 'summary', 'actions', 'history', 'changes', 'github', 'projects', 'help')


def _t(key, es, **kw):
    """i18n lado cliente, falla-suave: `key` en el idioma activo (catálogo
    lang/<code>/versiones.py); sin i18n / clave faltante → el español inline
    `es` (paridad exacta). .format(**kw) falla-suave."""
    s = es
    try:
        import i18n
        v = i18n.t(key)
        if v != key:
            s = v
    except Exception:
        s = es
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


def _view_name(i):
    """Etiqueta VISIBLE de la vista i en el idioma activo."""
    return _t('versiones.p.view.' + _VIEW_IDS[i], VIEWS[i])


def _act_title(aid, es):
    """Título visible de una acción de git_ops.ACTIONS (por id)."""
    return _t('versiones.p.act.%s.t' % aid, es)


def _act_desc(aid, es):
    return _t('versiones.p.act.%s.d' % aid, es)


def _field_label(action, key, es):
    return _t('versiones.p.form.%s.%s' % (action, key), es)


def init(S, G):
    if S.get('panel'):
        return
    S.update(panel=True, view=0, cursor=0, scroll=0, selected_files=set(),
             cloud={}, job=None, plan=None, form=None, report=[], report_title='',
             target='', target_branch='', status={}, commits=[], sel_key=None,
             machine={}, project_paths=O.projects(S['D']['repo']), project_states={},
             default_repo=S['D']['repo'], repo_path=S['D']['repo'], last_read=0)
    reload(S, G)


def selection(S, G):
    its = G._items(S['D'])
    item = its[min(S['si'], len(its) - 1)] if its else None
    if item:
        branch = item[1]['name'] if item[0] == 'rama' else item[1]['branch']
    else:
        branch = S['D'].get('current', '')
    ref = S.get('target') if S.get('target_branch') == branch else branch
    return branch, ref or branch


def reload(S, G):
    """Relectura COMPLETA (snapshot + máquina + selección). Corre al entrar,
    con r, al cambiar de proyecto y al terminar un job — jamás por keypress:
    navegar el mapa no toca git (ver sync)."""
    if S.get('job') and not S['job'].done:
        return
    repo = S.get('repo_path') or S['D']['repo']
    S['D'] = G.snapshot(repo)
    S['diff'], S['recent'] = {}, {}
    S['si'] = min(S['si'], max(0, len(G._items(S['D'])) - 1))
    S['machine'] = O.machine(repo)
    S['sel_key'] = None
    sync(S, G)
    items = G._items(S['D'])
    if items and items[S['si']][0] == 'rama':
        selected = items[S['si']][1]
        G._diff_resumen(S, selected)
        S['recent'][selected['ref']] = G._recientes(selected['ref'], 4, repo)
    S['last_read'] = time.time()


def sync(S, G):
    """Las rebanadas que dependen de la rama SELECCIONADA (status, commits).
    Lazy + memoizada: corre al entrar a una vista que las lee (Tab/atajos) y
    se salta si la selección no cambió. El mapa navega sin subprocess."""
    if S.get('job') and not S['job'].done:
        return
    repo = S.get('repo_path') or S['D']['repo']
    branch, ref = selection(S, G)
    key = (repo, branch, ref)
    if S.get('sel_key') == key:
        return
    path = O.branch_path(repo, branch) or repo
    S['status'] = O.local_status(path, branch)
    S['work_path'] = path
    S['commits'] = O.history(repo, branch) if branch else []
    S['selected_files'].intersection_update(r['path'] for r in S['status'].get('files', []))
    S['sel_key'] = key


def poll(S, G):
    job = S.get('job')
    if job and job.done and not S.get('job_collected'):
        S['job_collected'] = True
        if job.cloud is not None:
            S['cloud'] = job.cloud
        elif job.plan['action'] not in ('commit', 'verify', 'promote'):
            # Do not present cloud data from before a remote mutation as current.
            S['cloud'] = {}
        S['msg'] = (_t('versiones.p.job.done', 'Completado: {t}',
                       t=_act_title(job.plan['action'], job.plan['title']))
                    if job.ok else job.error)
        reload(S, G)


def _rows(S, G):
    view = VIEWS[S['view']]
    if view == 'Acciones':
        return [_act_title(a[0], a[1]) for a in O.ACTIONS]
    if view == 'Historial':
        return [c['short'] + ' · ' + c['title'] for c in S['commits']]
    if view == 'Cambios':
        return [('● ' if r['path'] in S['selected_files'] else '○ ') + r['path'] for r in S['status'].get('files', [])]
    if view == 'GitHub':
        c = S['cloud']
        result = [_t('versiones.p.gh.pr_row', 'Revisión #{n} · {t}', n=p['number'], t=p['title'])
                  for p in c.get('prs', [])]
        result += [_t('versiones.p.gh.run_row', 'Prueba · {s} · {t}', s=r['conclusion'] or r['status'],
                      t=r['displayTitle']) for r in c.get('runs', [])]
        result += ['Release · %s · %s' % (r['tagName'], _t('versiones.p.draft', 'borrador') if r['isDraft']
                                          else _t('versiones.p.published', 'publicado'))
                   for r in c.get('releases', [])]
        return result
    if view == 'Proyectos':
        return [os.path.basename(p) + ((' · ' + _t('versiones.p.proj.open', 'abierto'))
                                       if p == S['D']['repo'] else '') for p in S['project_paths']]
    if view == 'Ayuda':
        return [_t('versiones.p.help.r%d' % i, es) for i, es in enumerate((
            'Rama = una línea de trabajo', 'Commit = un punto de guardado',
            'Push = subir lo guardado', 'Pull = traer lo de GitHub',
            'Revisión = propuesta de cambios', 'Stable = versión para el equipo',
            'Release = entrega con nombre', 'Worktree = carpeta separada'))]
    return []


def _summary(S, G):
    d, status, m, c = S['D'], S['status'], S['machine'], S['cloud']
    branch, ref = selection(S, G)
    pend = _t('versiones.p.pending', 'consulta pendiente')
    pend_fail = _t('versiones.p.pending_fail', 'consulta pendiente o fallida')
    avail = lambda ok: (_t('versiones.p.avail', 'disponible') if ok
                        else _t('versiones.p.absent', 'ausente'))
    rows = [_t('versiones.p.s.journey', 'tu recorrido') + ' ───',
            _t('versiones.p.s.local', 'Trabajo local · {n} archivos por guardar',
               n=len(status.get('files', []))),
            _t('versiones.p.s.saved', 'Guardado') + ' · ' + (
                (S['commits'][0]['short'] + ' ' + S['commits'][0]['title']) if S['commits']
                else _t('versiones.p.s.nohist', 'sin historial')),
            _t('versiones.p.s.pushed', 'Subido') + ' · ' + (
                _t('versiones.p.s.noorigin', 'sin origin conectado') if not status.get('remote') else
                pend if status.get('ahead') is None else
                _t('versiones.p.s.aheadbehind', '{a} commits por subir · {b} por traer',
                   a=status['ahead'], b=status['behind'])),
            _t('versiones.p.s.reviewed_n', 'Revisado · {n} solicitudes abiertas', n=len(c['prs']))
            if 'prs' in c and not any(e.startswith('prs:') for e in c.get('errors', []))
            else _t('versiones.p.s.reviewed', 'Revisado') + ' · ' + pend_fail,
            _t('versiones.p.s.delivery', 'Entrega') + ' · ' + (
                (c['releases'][0]['tagName'] + ' · ' + (
                    _t('versiones.p.draft', 'borrador') if c['releases'][0]['isDraft']
                    else _t('versiones.p.published_f', 'publicada')))
                if c.get('releases') else pend_fail
                if 'releases' not in c or any(e.startswith('releases:') for e in c.get('errors', []))
                else _t('versiones.p.s.norel', 'sin releases')),
            '', _t('versiones.p.s.machine', 'tu máquina') + ' ───',
            '%s · Python %s' % (m.get('system', '?'), m.get('python', '?')),
            _t('versiones.p.s.disk', 'Disco · {f} GB libres · {u}% utilizado',
               f=m.get('free_gb', '?'), u=m.get('used_pct', '?')),
            _t('versiones.p.s.tools', 'Herramientas · Git {g} · GitHub CLI {h}',
               g=avail(m.get('git')), h=avail(m.get('gh'))),
            '', _t('versiones.p.s.folders', 'carpetas de trabajo') + ' ───',
            _t('versiones.p.s.wts', '{n} separadas · {d} con trabajo sin guardar',
               n=len(d.get('wts', [])), d=sum(w['clean'] is False for w in d.get('wts', []))),
            _t('versiones.p.s.read', 'Local leído') + ' · '
            + time.strftime('%H:%M:%S', time.localtime(S['last_read'])),
            'GitHub · ' + (time.strftime('%H:%M:%S', time.localtime(c['stamped'])) if c.get('stamped')
                           else _t('versiones.p.s.notqueried', 'sin consultar en esta sesión')),
            '', _t('versiones.p.s.keys', 'r relee la máquina · f consulta GitHub')]
    if m.get('load') is not None:
        rows.insert(11, _t('versiones.p.s.load', 'Carga de máquina · {l} (promedio, no % CPU)',
                           l='%.2f' % m['load']))
    exact = S.get('target') or (S['commits'][0]['sha'] if S['commits'] else '')
    check = next((r for r in c.get('runs', []) if r.get('headSha') == exact), None)
    rows.insert(7, _t('versiones.p.s.tests', 'Pruebas GitHub') + ' · ' + (
        (check.get('conclusion') or check['status']) if check
        else _t('versiones.p.s.notests', 'sin resultado consultado para este commit')))
    next_step = (_t('versiones.p.next.conflict', 'Resolver el conflicto antes de guardar') if status.get('conflict') else
                 _t('versiones.p.next.save', 'Guardar los archivos elegidos en Cambios') if status.get('files') else
                 _t('versiones.p.next.pull', 'Traer novedades de GitHub') if status.get('behind') else
                 _t('versiones.p.next.push', 'Subir tus puntos de guardado') if status.get('ahead') else
                 _t('versiones.p.next.check', 'Consultar GitHub para confirmar el estado'))
    rows.insert(0, _t('versiones.p.next', 'Siguiente paso') + ' · ' + next_step)
    if status.get('current_branch') != branch:
        rows.insert(1, _t('versiones.p.s.otherdir',
                          'Archivos locales · carpeta abierta en {c}; abre {b} para editarla.',
                          c=status.get('current_branch') or _t('versiones.p.s.detached', 'un commit separado'),
                          b=branch))
    return rows


def _detail(S, G):
    view = VIEWS[S['view']]
    branch, ref = selection(S, G)
    cursor = S['cursor']
    if view == 'Acciones':
        a = O.ACTIONS[min(cursor, len(O.ACTIONS) - 1)]
        return [_act_title(a[0], a[1]), '', _act_desc(a[0], a[2]), '',
                _t('versiones.p.f.project', 'Proyecto') + ' · ' + S['D']['repo'],
                _t('versiones.p.f.branch', 'Rama') + ' · ' + branch,
                _t('versiones.p.f.version', 'Versión') + ' · ' + (ref or '?'), '',
                _t('versiones.p.a.l1', 'Enter prepara la acción.'),
                _t('versiones.p.a.l2', 'Primero verás el destino y los pasos.'),
                _t('versiones.p.a.l3', 'Se ejecuta solo al confirmar esa vista previa.'), '',
                _t('versiones.p.a.l4', 'Local sin guardar no se incluye en un push.'),
                _t('versiones.p.a.l5', 'Una publicación puede iniciar el despliegue del proyecto.')]
    if view == 'Historial':
        if not S['commits']:
            return [_t('versiones.p.h.none', 'No hay commits para mostrar.')]
        c = S['commits'][min(cursor, len(S['commits']) - 1)]
        return [c['title'], c['sha'], getattr(G, 'ago_text', str)(c['ago']), '',
                _t('versiones.p.h.l1', 'Enter revisa sus diferencias.'),
                _t('versiones.p.h.l2', 'c elige esta versión para subir o crear un release.'),
                _t('versiones.p.h.l3', 'Elegir una versión no mueve tu rama ni tus archivos.'),
                _t('versiones.p.h.l4', 't permite escribir cualquier commit o etiqueta.'),
                _t('versiones.p.h.l5', 'b vuelve a la punta de la rama.')]
    if view == 'Cambios':
        files = S['status'].get('files', [])
        path = S.get('work_path', S['D']['repo'])
        rows = [_t('versiones.p.c.files_in', 'Archivos en') + ' · ' + path, '',
                _t('versiones.p.c.marked', '{n} marcados para guardar', n=len(S['selected_files'])),
                _t('versiones.p.c.l1', 'Espacio marca/quita un archivo.'),
                _t('versiones.p.c.l2', 'Enter muestra qué cambió.'),
                _t('versiones.p.c.l3', 'g prepara un punto de guardado con los marcados.'),
                _t('versiones.p.c.l4', 'Los demás archivos preparados quedan aparte.')]
        if files:
            r = files[min(cursor, len(files) - 1)]
            state = (_t('versiones.p.c.new', 'nuevo') if r['status'] == '??' else
                     _t('versiones.p.c.conflict', 'conflicto') if r['conflict'] else
                     _t('versiones.p.c.deleted', 'eliminado') if 'D' in r['status'] else
                     _t('versiones.p.c.modified', 'modificado'))
            rows += ['', r['path'], _t('versiones.p.c.state', 'Estado') + ' · ' + state]
        return rows
    if view == 'GitHub':
        c = S['cloud']
        rows = [_t('versiones.p.g.l1', 'f consulta GitHub y actualiza origin.'),
                _t('versiones.p.g.account', 'Cuenta') + ' · ' + (
                    c.get('account') or _t('versiones.p.pending', 'consulta pendiente')),
                _t('versiones.p.g.l2', 'Los datos llevan la hora de su consulta.'),
                _t('versiones.p.g.l3', 'Acciones permite publicar y hacer review.'),
                _t('versiones.p.g.l4', 'La revisión del diff es manual; no ejecuta un modelo de IA.'), '']
        if c.get('error'):
            return rows + [c['error']]
        prs, runs, releases = c.get('prs', []), c.get('runs', []), c.get('releases', [])
        if cursor < len(prs):
            p = prs[cursor]
            rows += ['#%d · %s' % (p['number'], p['title']),
                     p['headRefName'] + ' → ' + p['baseRefName'],
                     _t('versiones.p.g.draft', 'Borrador') if p['isDraft']
                     else _t('versiones.p.g.open', 'Abierta para revisión'), p['url'],
                     _t('versiones.p.g.load_pr', 'Enter carga su número en el menú de acciones.')]
        elif cursor < len(prs) + len(runs):
            r = runs[cursor - len(prs)]
            rows += [r['displayTitle'], r['headBranch'], r['headSha'],
                     _t('versiones.p.g.result', 'Resultado') + ' · ' + (r.get('conclusion') or r['status']),
                     r['url'],
                     _t('versiones.p.g.ci', 'CI son pruebas del servidor; no reemplazan las pruebas locales.')]
        elif releases and cursor - len(prs) - len(runs) < len(releases):
            r = releases[cursor - len(prs) - len(runs)]
            rows += [r['tagName'], r.get('name') or '',
                     _t('versiones.p.draft', 'borrador') if r['isDraft']
                     else _t('versiones.p.published', 'publicado'),
                     _t('versiones.p.g.load_rel', 'Enter carga esta versión para publicarla.')]
        return rows + c.get('errors', [])
    if view == 'Proyectos':
        p = S['project_paths'][min(cursor, len(S['project_paths']) - 1)]
        st = S['project_states'].get(p, {})
        pend = _t('versiones.p.pending', 'consulta pendiente')
        return [p, '', _t('versiones.p.pr.l1', 'Enter abre el proyecto.'),
                _t('versiones.p.pr.l2', 'n conecta otra carpeta Git.'),
                _t('versiones.p.pr.l3', 'm consulta el estado de las carpetas registradas.'),
                _t('versiones.p.pr.l4', 'No se escanea todo el disco.'), '',
                _t('versiones.p.f.branch', 'Rama') + ' · ' + st.get('branch', pend),
                _t('versiones.p.pr.tosave', 'Archivos por guardar') + ' · '
                + (str(len(st['files'])) if 'files' in st else '?'),
                _t('versiones.p.f.dest', 'Destino') + ' · ' + (st.get('remote') or pend)]
    if view == 'Ayuda':
        explanations = [_t('versiones.p.help.x%d' % i, es) for i, es in enumerate((
            'Una rama es una línea de trabajo independiente. main suele ser la versión principal; feat/... es un cambio en desarrollo.',
            'Un commit guarda una versión en tu máquina. Los archivos editados después no forman parte de ese punto de guardado.',
            'Push envía commits al repositorio remoto. Si GitHub tiene cambios incompatibles, Git rechaza la subida y el panel explica el fallo.',
            'Pull trae cambios a una carpeta. Aquí solo avanza si puede hacerlo sin mezclar historias; si hay conflicto, conserva tu trabajo.',
            'Un pull request pide al equipo revisar una rama antes de unirla con otra. Borrador significa que aún estás preparando la revisión.',
            'Stable es el canal que recibe el equipo. Marcar estable verifica main; Publicar para el equipo sube main y stable.',
            'Un release da nombre y notas a un commit. Primero prepara un borrador y después publícalo. Distribución WORKSPACE es otro destino.',
            'Un worktree permite abrir otra rama en una carpeta separada sin interrumpir el trabajo de tu carpeta actual.',
        ))]
        return [explanations[min(cursor, len(explanations) - 1)], '',
                _t('versiones.p.help.k1', 'Tab cambia vista · ↑↓ elige · Enter abre'),
                _t('versiones.p.help.k2', 'a acciones · f GitHub · r máquina'),
                _t('versiones.p.help.k3', 'h historial · d cambios · p proyectos'),
                _t('versiones.p.help.k4', 't versión exacta · b punta de rama'),
                _t('versiones.p.help.k5', 'Esc vuelve · q sale')]
    return [_t('versiones.p.pick', 'Elige la rama en Mapa y abre Acciones.')]


def _body_view(S, G):
    if S.get('report_title'):
        return S['report_title'], S['report'], [_t('versiones.p.b.scroll', '↑↓ desplaza · Esc vuelve')]
    if S.get('job') and not S.get('job_collected'):
        job = S['job']
        return (_t('versiones.p.b.running', 'EJECUTANDO') + ' · '
                + _act_title(job.plan['action'], job.plan['title']),
                job.output()[-25:] or [_t('versiones.p.b.starting', 'Iniciando…')],
                [_t('versiones.p.b.live', 'La salida se actualiza mientras trabaja.'),
                 _t('versiones.p.b.wait', 'Espera el resultado antes de iniciar otra acción.')])
    if S.get('plan'):
        plan = S['plan']
        lines = [_act_desc(plan['action'], plan['description']), '',
                 _t('versiones.p.f.project', 'Proyecto') + ' · ' + plan['repo'],
                 _t('versiones.p.pl.src_branch', 'Rama de origen') + ' · ' + plan['branch'],
                 _t('versiones.p.pl.exact', 'Commit exacto') + ' · ' + plan['source'],
                 _t('versiones.p.f.dest', 'Destino') + ' · ' + (
                     plan.get('destination') or plan.get('remote')
                     or _t('versiones.p.pl.this_machine', 'esta máquina'))]
        if plan.get('distribution_remote'):
            lines += [_t('versiones.p.pl.dist', 'Repositorio de distribución') + ' · '
                      + plan['distribution_remote']]
        if plan.get('pr_head'):
            lines += [_t('versiones.p.pl.pr_head', 'Versión de la revisión') + ' · ' + plan['pr_head']]
        if plan['files']:
            lines += ['', _t('versiones.p.pl.only_files', 'Solo se guardan estos archivos:')] + plan['files']
        if plan['fields'].get('body'):
            lines += ['', _t('versiones.p.pl.your_text', 'Tu texto') + ' · ' + plan['fields']['body']]
        lines += ['', _t('versiones.p.pl.commands', 'Comandos que se ejecutarán:')] + [
            O.display_command(c) for c in plan['commands']]
        return (_t('versiones.p.pl.confirm', 'CONFIRMAR') + ' · '
                + _act_title(plan['action'], plan['title']), lines,
                [_t('versiones.p.pl.h1', 'Enter ejecuta estos pasos · Esc cancela'),
                 _t('versiones.p.pl.h2', '↑↓ desplaza la vista previa')])
    view = VIEWS[S['view']]
    if view == 'Resumen':
        return (_t('versiones.p.sum.title', 'ESTADO DEL PROYECTO'), _summary(S, G),
                [_t('versiones.p.sum.h1', 'Acciones para guardar, subir o publicar.'),
                 _t('versiones.p.sum.h2', 'Ayuda explica cada etapa sin comandos.')])
    rows = _rows(S, G)
    return _view_name(S['view']).upper(), rows, _detail(S, G)


def render(S, w, h, G, legacy):
    if not S.get('panel'):
        return legacy(S, w, h)
    K, H = G._K(), G.HL
    branch, ref = selection(S, G)
    tabs = ' · '.join(('[' + _view_name(i) + ']') if i == S['view'] else _view_name(i)
                      for i in range(len(VIEWS)))
    tabs = H.clip(tabs, w - 1)
    if S['view'] == 0 and not S.get('form') and not S.get('plan') and not S.get('report_title') and not (S.get('job') and not S.get('job_collected')):
        lines = legacy(S, w, h - 2)
        title_lines = H.big_title(K, w, h - 2, indent=' ', compact=h - 2 < 30, center=True)
        tab_row = 1 + len(title_lines)
        if len(title_lines) > 1:
            tab_row += len(H.title_reflection(K, w, indent=' ', center=True))
        lines.insert(tab_row, K['C'] + tabs + K['R'])
        line = ' ' + _t('versiones.p.r.maphint',
                        'a acciones · Tab vistas · h historial · d cambios · f GitHub · q vuelve')
        if S.get('target'):
            line = ' ' + _t('versiones.p.r.target',
                            'Versión elegida {v} · a acciones · b punta de rama · q vuelve',
                            v=S['target'][:12])
        lines.insert(tab_row + 1, H.clip(line, w - 1))
        return lines[:h - 1]
    if S.get('form'):
        _f = S['form']
        _fk, _fl = _f['fields'][_f['index']][0], _f['fields'][_f['index']][1]
        _ftitle = (_act_title(_f['action'], _f['title'])
                   if any(a[0] == _f['action'] for a in O.ACTIONS)
                   else _t('versiones.p.form.%s.title' % _f['action'], _f['title']))
    title, body, detail = _body_view(S, G) if not S.get('form') else (
        _ftitle, [_field_label(_f['action'], _fk, _fl), '', '❯ ' + _f['buffer'], '',
                  _t('versiones.p.fm.field', 'Campo {i}/{n}', i=_f['index'] + 1, n=len(_f['fields']))],
        [_t('versiones.p.fm.l1', 'Enter acepta el valor escrito.'),
         _t('versiones.p.fm.l2', 'Ctrl+U borra el campo.'),
         _t('versiones.p.fm.l3', 'Esc cancela sin ejecutar.'), '',
         _t('versiones.p.f.project', 'Proyecto') + ' · ' + S['D']['repo'],
         _t('versiones.p.f.branch', 'Rama') + ' · ' + branch,
         _t('versiones.p.f.version', 'Versión') + ' · ' + ref])
    special = bool(S.get('plan') or S.get('form') or S.get('report_title') or (S.get('job') and not S.get('job_collected')))
    lines = [''] + H.big_title(K, w, h, indent=' ', compact=h < 30, center=True)
    if len(lines) > 2:
        lines += H.title_reflection(K, w, indent=' ', center=True)
    lines += [K['C'] + tabs + K['R'], H.clip(' ' + _t('versiones.p.r.ctx', '{n} · rama {b} · versión {v}',
                                                     n=S['D'].get('nombre', '?'),
                                                     b=branch or _t('versiones.p.r.nobranch', 'sin rama'),
                                                     v=ref[:12] if ref else '?'), w - 1), '']
    available = max(4, h - 1 - len(lines) - 3)
    if special or w < 100 or S['view'] == 1:
        inner = w - 6
        content = []
        for row in body:
            content += G._wrap(O.clean_text(row), max(8, inner))
        offset = min(S.get('scroll', 0), max(0, len(content) - max(1, available - 2)))
        shown = content[offset:offset + available - 2]
        if S.get('plan') or S.get('report_title'):
            detail = list(detail) + [_t('versiones.p.r.lines', 'Líneas {a}–{b} de {n}', a=offset + 1,
                                        b=min(len(content), offset + len(shown)), n=len(content))]
        if not special and S['view'] != 1:
            # On narrow terminals, reserve a separate explanation panel.
            left_height = max(3, (available - 4) // 2)
            selected = min(S['cursor'], max(0, len(body) - 1))
            start = max(0, min(selected - left_height // 2, len(body) - left_height))
            menu = [('❯ ' if i == selected else '  ') + row for i, row in enumerate(body)]
            lines += [' ' + l for l in H.full_box(title, menu[start:start + left_height], K, w - 2, left_height, True, border=K['C'])]
            right_height = max(1, available - left_height - 4)
            wrapped = [part for row in detail for part in G._wrap(O.clean_text(row), inner)]
            lines += [' ' + l for l in H.full_box(_t('versiones.p.r.meaning', 'QUÉ SIGNIFICA'), wrapped, K,
                                                  w - 2, right_height, False, border=K['B2'])]
        else:
            lines += [' ' + l for l in H.full_box(title, shown, K, w - 2, available - 2, True, border=K['C'])]
    else:
        lw = max(35, (w - 4) * 45 // 100)
        rw = w - 4 - lw
        ih = available - 2
        selected = min(S['cursor'], max(0, len(body) - 1))
        start = max(0, min(selected - ih // 2, len(body) - ih))
        menu = [('❯ ' if i == selected else '  ') + row for i, row in enumerate(body)]
        left = H.full_box(title, menu[start:start + ih], K, lw, ih, True, border=K['C'])
        wrapped = [part for row in detail for part in G._wrap(O.clean_text(row), rw - 4)]
        right = H.full_box(_t('versiones.p.r.meaning', 'QUÉ SIGNIFICA'), wrapped, K, rw, ih, False,
                           border=K['B2'])
        lines += [' ' + H.pad(a, lw) + '  ' + b for a, b in zip(left, right)]
    msg = O.clean_text(S.get('msg', ''))
    if S.get('job') and S.get('job_collected') and not S.get('report_title'):
        msg = (_t('versiones.p.r.ok', 'Listo · {t} · l muestra salida',
                  t=_act_title(S['job'].plan['action'], S['job'].plan['title']))
               if S['job'].ok else
               _t('versiones.p.r.check', 'Revisa · {t} · l muestra salida',
                  t=_act_title(S['job'].plan['action'], S['job'].plan['title'])))
    hints = (_t('versiones.p.r.h.plan', 'Enter confirma · ↑↓ detalle · Esc cancela · q vuelve') if S.get('plan') else
             _t('versiones.p.r.h.form', 'Enter sigue · Esc cancela · q vuelve') if S.get('form') else
             _t('versiones.p.r.h.report', '↑↓ desplaza · Esc vuelve · q vuelve') if S.get('report_title') else
             _t('versiones.p.r.h.nav', '↑↓ elige · Enter abre · Tab vista · a acciones · r · q vuelve'))
    lines = lines[:h - 4]
    lines += [''] * max(0, h - 4 - len(lines))
    lines += [H.clip(' ' + msg, w - 1), H.clip(' ' + (detail[0] if special and detail else _t('versiones.p.r.foot', 'f GitHub · t versión · b punta · p proyectos · ? ayuda')), w - 1), H.clip(' ' + hints, w - 1)]
    return [H.clip(l, w - 1) for l in lines]


def _start_action(S, G, action):
    branch, ref = selection(S, G)
    fields = [(key, label, default.format(branch=branch)) for key, label, default in O.FORMS.get(action, [])]
    fields = [(k, l, S.get('pr_hint', '') if k == 'pr' else S.get('tag_hint', '') if k == 'tag' and action == 'release_publish' else d) for k, l, d in fields]
    if fields:
        S['form'] = dict(action=action, title=next(a[1] for a in O.ACTIONS if a[0] == action),
                         fields=fields, index=0, buffer=fields[0][2], values={})
    else:
        _prepare(S, G, action, {})


def _prepare(S, G, action, fields):
    branch, ref = selection(S, G)
    try:
        S['plan'] = O.prepare(action, S['D']['repo'], branch, ref, fields,
                              sorted(S['selected_files']), S['cloud'])
        S['scroll'] = 0
    except ValueError as e:
        S['msg'] = str(e)
        S['report_title'], S['report'], S['scroll'] = (
            _t('versiones.p.h.before', 'ANTES DE CONTINUAR'),
            [str(e), '', _t('versiones.p.h.esc_back', 'Esc vuelve sin ejecutar nada.')], 0)


def handle(S, key, G):
    """None delegates to the original branch-map controls; True/False handled."""
    init(S, G)
    poll(S, G)
    if not key:
        return True
    if S.get('job') and not S.get('job_collected'):
        S['msg'] = _t('versiones.p.m.working', 'Trabajando · puedes leer la salida; espera antes de salir.')
        return True
    if S.get('report_title'):
        if key in ('\x1b', 'q', 'Q'):
            S['report_title'], S['report'], S['scroll'] = '', [], 0
        elif key in ('up', 'down'):
            S['scroll'] = max(0, min(len(S['report']) - 1, S['scroll'] + (1 if key == 'down' else -1)))
        return True
    if S.get('plan'):
        if key in ('\x1b', 'q', 'Q'):
            S['plan'] = None
            S['msg'] = _t('versiones.p.m.cancel_plan', 'Cancelado · no se ejecutó la acción.')
        elif key in ('up', 'down'):
            S['scroll'] = max(0, S['scroll'] + (1 if key == 'down' else -1))
        elif key in ('\r', '\n'):
            plan, S['plan'] = S['plan'], None
            S['job_collected'] = False
            S['job'] = O.Job(plan).start()
        return True
    if S.get('form'):
        f = S['form']
        if key in ('\x1b', '\x03'):
            S['form'] = None
            S['msg'] = _t('versiones.p.m.cancel_form', 'Cancelado · sin cambios.')
        elif key == '\x15':
            f['buffer'] = ''
        elif key in ('\x7f', '\b', '\x08'):
            f['buffer'] = f['buffer'][:-1]
        elif key in ('\r', '\n'):
            field = f['fields'][f['index']][0]
            f['values'][field] = f['buffer'].strip()
            f['index'] += 1
            if f['index'] < len(f['fields']):
                f['buffer'] = f['fields'][f['index']][2]
            else:
                S['form'] = None
                if f['action'] == 'project':
                    try:
                        S['repo_path'] = O.add_project(f['values']['path'], S['default_repo'])
                        S['project_paths'] = O.projects(S['default_repo'])
                        S['si'], S['cursor'], S['target'] = 0, 0, ''
                        S['cloud'] = {}
                        reload(S, G)
                    except (ValueError, OSError) as e:
                        S['msg'] = str(e)
                elif f['action'] == 'target':
                    target = O.sha(S['D']['repo'], f['values']['ref'])
                    if target:
                        S['target'], S['target_branch'] = target, selection(S, G)[0]
                        reload(S, G)
                        S['msg'] = _t('versiones.p.m.chosen', 'Versión elegida · {v}', v=target[:12])
                    else:
                        S['msg'] = _t('versiones.p.m.notfound',
                                      'No encuentro ese commit o etiqueta. No moví tu rama.')
                else:
                    _prepare(S, G, f['action'], f['values'])
        elif len(key) == 1 and key.isprintable() and len(f['buffer']) < 1000:
            f['buffer'] += key
        return True
    if S.get('modo') in ('new', 'confirm'):
        return None
    if key in ('q', 'Q', '\x03'):
        return False
    if key == '\x1b':
        if S['view'] == 0:
            return False
        S['view'], S['cursor'] = 0, 0
        return True
    if key == 'tab':
        S['view'] = (S['view'] + 1) % len(VIEWS)
        S['cursor'], S['scroll'] = 0, 0
        sync(S, G)
        return True
    shortcuts = {'a': 2, 'h': 3, 'd': 4, 'p': 6, '?': 7, 's': 1}
    if key in shortcuts:
        S['view'], S['cursor'], S['scroll'] = shortcuts[key], 0, 0
        sync(S, G)
        return True
    if key in ('r', 'R'):
        reload(S, G)
        S['msg'] = _t('versiones.p.m.reread', 'Estado local releído; f consulta el servidor.')
        return True
    if key in ('f', 'F'):
        _start_action(S, G, 'fetch')
        return True
    if key == 'l' and S.get('job'):
        S['report'], S['report_title'], S['scroll'] = S['job'].output(), (
            _t('versiones.p.m.output', 'SALIDA') + ' · '
            + _act_title(S['job'].plan['action'], S['job'].plan['title'])), 0
        return True
    if key == 't':
        S['form'] = dict(action='target', title='Elegir versión exacta', fields=[('ref', 'Commit, rama o etiqueta', '')], index=0, buffer='', values={})
        return True
    if key == 'b':
        S['target'] = ''
        reload(S, G)
        S['msg'] = _t('versiones.p.m.tip', 'Acciones sobre la punta de la rama.')
        return True
    if S['view'] == 0:
        return None
    rows = _rows(S, G)
    if key in ('up', 'down'):
        S['cursor'] = max(0, min(max(0, len(rows) - 1), S['cursor'] + (1 if key == 'down' else -1)))
        if S['view'] == 1:
            S['scroll'] = max(0, S['scroll'] + (1 if key == 'down' else -1))
        return True
    cursor = S['cursor']
    if S['view'] == 2 and key in ('\r', '\n'):
        _start_action(S, G, O.ACTIONS[cursor][0])
    elif S['view'] == 3 and S['commits']:
        commit = S['commits'][cursor]
        if key == 'c':
            S['target'], S['target_branch'] = commit['sha'], selection(S, G)[0]
            S['msg'] = _t('versiones.p.m.chosen_a', 'Versión elegida · {v} · a abre acciones',
                          v=commit['short'])
        elif key in ('\r', '\n'):
            S['report'] = O.review(S['D']['repo'], commit['sha'])
            S['report_title'], S['scroll'] = _t('versiones.p.m.review', 'REVISAR') + ' · ' + commit['short'], 0
    elif S['view'] == 4:
        files = S['status'].get('files', [])
        if key == 'g':
            _start_action(S, G, 'commit')
        elif files and key == ' ':
            path = files[cursor]['path']
            if path in S['selected_files']:
                S['selected_files'].remove(path)
            else:
                S['selected_files'].add(path)
        elif files and key in ('\r', '\n'):
            branch, _ = selection(S, G)
            path = O.branch_path(S['D']['repo'], branch) or S['D']['repo']
            file = files[cursor]
            if file['status'] == '??':
                S['msg'] = _t('versiones.p.m.newfile',
                              'Archivo nuevo; ábrelo en tu editor para revisarlo antes de guardarlo.')
            else:
                rc, out, err = O.git(path, 'diff', 'HEAD', '--', file['path'])
                S['report'], S['report_title'], S['scroll'] = O.clean_text(out if rc == 0 else err).splitlines() or [_t('versiones.p.m.nodiff', 'Sin diferencias de texto.')], (
                    _t('versiones.p.m.change', 'CAMBIO') + ' · ' + file['path']), 0
    elif S['view'] == 5 and key in ('\r', '\n'):
        prs = S['cloud'].get('prs', [])
        releases = S['cloud'].get('releases', [])
        if cursor < len(prs):
            S['pr_hint'] = str(prs[cursor]['number'])
            S['view'], S['cursor'] = 2, next(i for i, a in enumerate(O.ACTIONS) if a[0] == 'review_pr')
        elif cursor >= len(prs) + len(S['cloud'].get('runs', [])) and releases:
            S['tag_hint'] = releases[cursor - len(prs) - len(S['cloud'].get('runs', []))]['tagName']
            S['view'], S['cursor'] = 2, next(i for i, a in enumerate(O.ACTIONS) if a[0] == 'release_publish')
    elif S['view'] == 6:
        if key == 'n':
            S['form'] = dict(action='project', title='Conectar proyecto', fields=[('path', 'Carpeta del proyecto Git', '')], index=0, buffer='', values={})
        elif key == 'm':
            S['project_states'] = {p: O.local_status(p) for p in S['project_paths']}
            S['msg'] = _t('versiones.p.m.projects', 'Estado local de tus proyectos actualizado.')
        elif key in ('\r', '\n') and S['project_paths']:
            S['repo_path'] = S['project_paths'][cursor]
            S['si'], S['cursor'], S['target'] = 0, 0, ''
            S['cloud'] = {}
            reload(S, G)
            S['view'] = 1
    return True

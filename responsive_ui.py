"""Shared compact terminal viewport: real bounds, focus and manual paging."""
import functools
import re
import hublayout as HL

ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
NOTICE = 'Pantalla completa: experiencia completa'
#: Mínimo REAL de una sección con la «cajita» (section_box, rediseño
#: 2026-10-14): la caja se acomoda sola a la ventana (cede wordmark → botones
#: → filas con ▲▼) y deja de servir debajo de esto. 60 columnas = la fila de
#: atajos esencial (moverse · i · salir) de la vista más ancha (Agregar agente
#: › cargar, 57) con aire para las traducciones; 14 filas = el piso de
#: section_box.frame (caja con ≥6 filas + atajos + aviso). Antes era 100×36:
#: bloqueaba la Terminal de Mac (80×24) y Windows Terminal (120×30). Las
#: pantallas con otro layout declaran el suyo: renderer(min_size=…).
SECTION_MIN_W = 60
SECTION_MIN_H = 14
#: Ventana ALTA y no tan ancha: las pantallas de dos paneles (calendario) los
#: apilan en vez de ponerlos lado a lado. Es un layout, no un mínimo.
VERTICAL_MIN_W = 72
VERTICAL_MIN_H = 50
WIDE_W = 100

def vertical(w, h):
    return VERTICAL_MIN_W <= w < WIDE_W and h >= VERTICAL_MIN_H

def supported(w, h, min_w=SECTION_MIN_W, min_h=SECTION_MIN_H):
    """¿Cabe la pantalla? `min_w`×`min_h` = el mínimo real de SU layout."""
    return w >= min_w and h >= min_h

def small(w, h):
    return w < 100 or h < 30

def plain(line):
    return ANSI.sub('', line)

def frame(lines, w, h, state=None, focus=None, title='WORKSPACE', exit_hint=None):
    """Bound a frame without losing content: auto-focus or explicit scroll."""
    state = state if state is not None else {}
    width, height = max(1, w - 1), max(1, h - 1)
    if height < 4:
        return [HL.clip(title, width)] + [''] * (height - 1)
    body = []
    anchor = 0
    for i, line in enumerate(lines):
        if focus == i:
            anchor = len(body)
        txt = plain(line).strip(' ║│┃')
        if txt and all(c in '═─╔╗╚╝╟╢┸┌┐└┘├┤┬┴┼╭╮╰╯┏┓┗┛━┠┨┯┷╓╖╙╜ ' for c in txt):
            continue
        if not txt and (not body or not body[-1]):
            continue
        # Reflow full content rather than letting terminal auto-wrap.
        chunk = ''
        for char in txt:
            if chunk and HL.vis(chunk + char) > width:
                body.append(chunk)
                chunk = ''
            chunk += char
        body.append(HL.clip(chunk, width))
    cap = height - 3
    state['_viewport_page'] = max(1, cap - 1)
    start = state.get('_viewport_offset')
    if start is None:
        start = max(0, anchor - cap // 2)
    start = min(max(0, start), max(0, len(body) - cap))
    state['_viewport_start'] = start
    rows = body[start:start + cap]
    rows += [''] * (cap - len(rows))
    if exit_hint is None:
        exit_hint = HL._t('hub.viewport.back', 'q vuelve')
    hint = '%s · %s · %d-%d/%d' % (exit_hint,
                                   HL._t('hub.viewport.scroll', 'Ctrl+B/F desplaza'),
                                   start + 1, min(len(body), start + cap), len(body))
    return ([HL.clip(title, width),
             HL.clip(HL._t('hub.fullscreen_notice', NOTICE), width)]
            + rows + [HL.clip(hint, width)])

def page_key(state, key):
    if key not in ('\x02', '\x06') or not state.get('_viewport_active'):
        return False
    delta = state.get('_viewport_page', 1) * (-1 if key == '\x02' else 1)
    state['_viewport_offset'] = max(0, state.get('_viewport_start', 0) + delta)
    return True

def action(fn, exit_result=True):
    @functools.wraps(fn)
    def wrapped(state, key, *args, **kwargs):
        if state.get('_size_blocked'):
            if key in ('q', '\x1b', '\x03'):
                # salir DESDE el aviso no es una decisión tomada en la
                # sección: quien llama lo distingue (el onboarding no la
                # cuenta como «saltado»)
                state['_size_exit'] = True
                return False if exit_result is True else 'exit'
            return exit_result
        if page_key(state, key):
            return exit_result
        state.pop('_viewport_offset', None)
        return fn(state, key, *args, **kwargs)
    return wrapped

def renderer(fn, title, min_size=None):
    """El render de una sección con su guarda de tamaño: por debajo de su
    mínimo real (`min_size` = (columnas, filas); default, el de la cajita)
    pinta el aviso de tamaño en vez de la sección."""
    min_w, min_h = min_size or (SECTION_MIN_W, SECTION_MIN_H)

    @functools.wraps(fn)
    def wrapped(state, w, h):
        w, h = max(1, int(w)), max(1, int(h))
        state['_viewport_active'] = False
        state['_size_blocked'] = not supported(w, h, min_w, min_h)
        if state['_size_blocked']:
            section = {'TONO': 'tono', 'CALENDARIO': 'calendario',
                       'ACTUALIZACIONES': 'actualizaciones',
                       'GITHUB': 'github', 'RAMAS': 'github', 'DEV': 'dev',
                       'ONBOARDING': 'onboarding', 'AGREGAR AGENTE': 'crear',
                       'ADD AGENT': 'crear'}.get(title)
            word = HL._t('section.title.' + section, title) if section else title
            return size_notice(word, w, h, min_w, min_h)
        return fn(state, w, h)

    wrapped.min_size = (min_w, min_h)
    return wrapped

_LAST_SIZE = [None]


def paint(tout, lines, first=False):
    """Pinta un frame completo. Al cambiar el tamaño de la ventana limpia
    todo (la terminal re-envuelve el frame viejo y deja basura), y recorta
    cada línea al ancho y el frame al alto: una línea que se envuelve o un
    frame más alto que la ventana hacen scroll y rompen el `\\033[H`."""
    import os
    try:
        ts = os.get_terminal_size()
        size = (ts.columns, ts.lines)
    except Exception:
        size = None
    changed = size is not None and _LAST_SIZE[0] not in (None, size)
    _LAST_SIZE[0] = size
    if size:
        cols, rows = size
        lines = [HL.clip(line, max(1, cols - 1)) for line in list(lines)[:max(1, rows)]]
    out = '\033[2J\033[3J\033[H' if (first or changed) else '\033[H'
    out += '\r\n'.join('\r\033[K' + line for line in lines)
    # Clear the old frame after shrinking or changing modes.
    tout.write(out + '\033[J')
    tout.flush()


def box(title, body, w, focused=False, title_align='left'):
    import tuitheme
    p = tuitheme.palette()
    color = p.C if focused else p.B2
    reset, bold = '\033[0m', '\033[1m'
    width = max(8, w)
    label = HL.clip(' ' + title + ' ', width - 4)
    fill = max(0, width - 3 - HL.vis(label))
    if title_align == 'center':
        # Título CENTRADO en el borde superior (greeter unificado). Los demás
        # consumidores (config, hub) conservan el título a la izquierda.
        lf = fill // 2
        top = (color + '╭' + '─' * (1 + lf) + bold + label + reset + color
               + '─' * (fill - lf) + '╮' + reset)
    else:
        top = color + '╭─' + bold + label + reset + color + '─' * fill + '╮' + reset
    rows = []
    # fila activa: el cursor del TEMA (❯, el mismo del hub) o el '>' llano
    ptr = ((getattr(p, 'GLYPHS', None) or {}).get('pointer') or '❯')
    for text in body:
        active = plain(text).lstrip().startswith(('>', ptr))
        value = (p.C + bold if active else p.WH) + text + reset
        rows.append(color + '│' + reset + ' ' + HL.pad(HL.clip(value, width - 4), width - 4) + ' ' + color + '│' + reset)
    return [top] + rows + [color + '╰' + '─' * (width - 2) + '╯' + reset]

def centered(lines, w, h):
    width = max(1, w - 1)
    rows = [HL.clip(line, width) for line in lines[:max(1, h - 1)]]
    left = max(0, (width - max((HL.vis(x) for x in rows), default=0)) // 2)
    top = max(0, (h - 1 - len(rows)) // 2)
    output = [''] * top + [' ' * left + line for line in rows]
    return output + [''] * max(0, h - 1 - len(output))

def size_notice(title, w, h, min_w=SECTION_MIN_W, min_h=SECTION_MIN_H):
    """El aviso de tamaño: el mínimo real de ESTA pantalla y el de la
    ventana, centrados en una caja."""
    pw = min(70, max(8, w - 5))
    _ = HL._t
    body = ['', _('hub.size.title', 'AJUSTA EL TAMAÑO DE LA VENTANA'), '',
            _('hub.size.minimum', 'Mínimo:     {w} columnas × {h} filas',
              w=min_w, h=min_h),
            _('hub.size.yours', 'Tu ventana: {w} columnas × {h} filas', w=w, h=h), '',
            _('hub.size.enlarge', 'Amplía la ventana o usa pantalla completa.'),
            _('hub.size.returns', 'La sección vuelve automáticamente al caber.'), '',
            _('hub.size.back_hub', 'q / Esc: volver al hub')]
    if h < 15:
        body = [_('hub.size.enlarge_short', 'Amplía la ventana'),
                _('hub.size.min_short', 'mínimo {w} × {h}', w=min_w, h=min_h),
                _('hub.size.back', 'q / Esc: volver')]
        body = body[:max(0, h - 3)]
    return centered(box(title, body, pw, True), w, h)


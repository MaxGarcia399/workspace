"""Read-only brain projection and folder graph, shared by setup and inspectors.

No network, model calls, execution or writes. Future journal paths are explicitly
labelled; a preview never claims a proposed skill is already installed.
"""
from pathlib import Path
import re

ROUTES = {
    'setup': ('COMPOSICIÓN', 'Formulario → plantilla → revisión → cerebro', 'Vista previa · nada creado todavía', 'C',''),
    'boot': ('ARRANQUE', 'CLAUDE.md → BOOT/ → STATE/MEMORY + INDEX + users/', 'wiki y skills completas: sólo cuando hacen falta', 'C', 'CLAUDE.md BOOT STATE'),
    'save': ('GUARDAR', 'Trabajo significativo → sessions/ + inbox/ → consolidación', 'Claude: respaldo al compactar; rastro al cerrar si faltó captura', 'OK', 'STATE'),
    'retrieve': ('RECUPERAR', 'INDEX.md → archivo · si falta: FTS5 → archivo · fallback: grep', 'Wiki: index.md → [[enlace]] → nota · sólo el detalle necesario', 'B', 'STATE wiki/'),
    'organize': ('ORGANIZAR', 'Capturas → consolidación → MEMORY + INDEX · Dream → DESTILADO', 'Dream propone; promoción humana → MEMORY · sin intervalo universal', 'B2', 'STATE'),
}


def clean(value):
    return ' '.join(str(value or '').split())


def projection(values, base, proposed, personalized, owner=''):
    """Facts match agent_admin seeding and the versioned template contract."""
    v=lambda k, default='por definir': clean(values.get(k)) or default
    profile=any(values.get(k) for k in ('dueño_quien','dueño_como','dueño_necesita'))
    owner=owner or v('dueño','socio')
    user_path='users/%s.md' % owner
    return {'name':v('visible', v('nombre','Tu agente')), 'preview':True,
            'identity':'IA: propuesta de redacción' if personalized else 'plantilla + semillas del formulario',
            'branches':[
                ('CLAUDE.md', [('Orden de lectura', 'BOOT → memoria → índices')]),
                ('BOOT/', [('00-SOUL.md', v('tono')+' · '+v('estilo')),
                           ('01-IDENTITY.md', v('rol')+' · '+v('proposito')),
                           ('03-RULES.md', v('limites')),
                           ('04-BRAIN-MAP.md', 'HOT → WARM → COLD')]),
                ('STATE/', [('MEMORY.md + INDEX.md','memoria + rutas'),
                            (user_path if profile else 'users/','perfil: '+v('dueño_quien') if profile else 'sin perfil sembrado'),
                            ('sessions/<socio>/<pestaña>.md','se crea al usar una pestaña'),
                            ('inbox/ + DESTILADO.md','capturas + candidatos; promoción revisada')]),
                ('wiki/', [('index.md → [[notas]]','conocimiento bajo demanda')]),
                ('skills/', [('INDEX-LITE.md → categoría/SKILL.md','%d base + %d propuestas' % (base,proposed) + (' · revisión pendiente' if proposed else '')),
                             ('_propuestas/','imports → oficiales/ o externas/')]),
                ('adapters/', [('claude-code.md','contrato del runtime; motor elegido aparte')]),
                ('.workspace/', [('agent.json','identidad + recibo de importación')]),
                ('.claude/', [('hooks + socio.local','configuración del motor')])],
            'base':base,'proposed':proposed}


def inspect(brain, max_files=4000):
    """Inspect an existing brain without following symlinks or mutating indexes.

    Reusable by other screens: actual paths/counts, bounded reads, no inferred
    profile, memory contents or installed skills from the creation form.
    """
    root=Path(brain)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('El cerebro debe ser una carpeta real')
    branches=[]; count=0
    for label in ('CLAUDE.md','BOOT','STATE','wiki','skills','adapters','.workspace','.claude'):
        path=root/label
        if path.is_symlink() or not path.exists():
            continue
        leaves=[]
        if path.is_file():
            leaves=[('Entrada','orden de lectura')]
        else:
            # scandir avoids following symlinked folders; bounded traversal.
            stack=[path]
            while stack and count<max_files:
                directory=stack.pop()
                for child in sorted(directory.iterdir(),key=lambda p:p.name):
                    if child.is_symlink():
                        continue
                    count+=1
                    if count>max_files: break
                    if child.is_dir(): stack.append(child)
                    elif child.suffix in ('.md','.json'):
                        leaves.append((str(child.relative_to(path)), '%d bytes' % child.stat().st_size))
            leaves=sorted(leaves)
        branches.append((label+('/' if path.is_dir() else ''),leaves))
    return {'name':root.name,'preview':False,'branches':branches,'truncated':count>=max_files}


def render(model, api, K, canvas_type, width, height, route='setup'):
    """Boxed nodes joined border-to-border; no floating or padded connectors."""
    canvas=canvas_type(api,K,width,height)
    route=route if route in ROUTES else 'setup'
    accent=K[ROUTES[route][3]]
    branches=model['branches']
    if height<5 or width<60:
        canvas.put(0,0,model['name']+' → BOOT/ · STATE/ · wiki/ · skills/',K['C']+K['BO'],width)
        return canvas.lines()
    graph_w=min(width,146); origin=max(0,(width-graph_w)//2)
    root_w=16 if graph_w>=100 else 11
    folder_w=18 if graph_w>=100 else 14
    fx=origin+root_w+5; tx=fx+folder_w+3
    trunk=fx-3
    # Full boxes require three lines. Smaller frames expose the selected route
    # first and state explicitly how many nodes remain below the viewport.
    count=min(len(branches),height//3)
    if count<len(branches):
        count=min(count,(height-1)//3)
    start=0
    if route in ('save','retrieve','organize') and count<3:
        start=2
    shown=branches[start:start+count]
    last=(len(shown)-1)*3+1; mid=max(1,last//2)
    def line(x1,y1,x2,y2,col):
        canvas.edge(x1,y1,x2,y2)
        if y1==y2:
            for x in range(min(x1,x2),max(x1,x2)+1):canvas.put(x,y1,'─',col)
        else:
            for y in range(min(y1,y2),max(y1,y2)+1):canvas.put(x1,y,'│',col)
    def box(x,y,w,label,col):
        canvas.put(x,y,'╭'+'─'*(w-2)+'╮',col)
        canvas.put(x,y+1,'│',col)
        canvas.put(x+w-1,y+1,'│',col)
        canvas.put(x+2,y+1,label,col+K['BO'],w-4)
        canvas.put(x,y+2,'╰'+'─'*(w-2)+'╯',col)
    line(trunk,1,trunk,last,K['B2'])
    line(origin+root_w,mid,trunk,mid,K['C'])
    box(origin,max(0,mid-1),root_w,model['name'],K['C'])
    canvas.put(origin+root_w-1,mid,'├',K['C'])
    canvas.put(trunk,mid,'┤',K['B2'])
    targets={'save':('sessions/','inbox/'), 'retrieve':('INDEX','index.md'),
             'organize':('MEMORY','INDEX','inbox/','DESTILADO'),
             'boot':('00-','01-','03-','04-','MEMORY','INDEX','users/')}
    for i,(folder,files) in enumerate(shown):
        y=i*3; is_active=route=='setup' or folder.split('/')[0] in ROUTES[route][4].split() or folder in ROUTES[route][4].split()
        key={'BOOT/':'C','STATE/':'B','wiki/':'B2','skills/':'OK'}.get(folder,'C')
        col=(K[key] if route=='setup' else accent) if is_active else K['DK']
        line(trunk,y+1,fx-1,y+1,col)
        canvas.put(trunk,y+1,'┬' if len(shown)==1 else '┌' if i==0 else '└' if i==len(shown)-1 else '├',col)
        box(fx,y,folder_w,folder,col)
        canvas.put(fx,y+1,'┤',col)
        line(fx+folder_w,y+1,tx-1,y+1,col)
        canvas.put(fx+folder_w-1,y+1,'├',col)
        # Keep files in the node's three-row band, with summaries alongside.
        ordered=files
        if route in ('save','organize') and folder=='STATE/':
            ordered=sorted(files,key=lambda f:not any(t in f[0] for t in targets[route]))
        leaves=ordered[:3]
        if leaves:
            offset=(3-len(leaves))//2
            line(tx-1,y+offset,tx-1,y+offset+len(leaves)-1,col)
        for j,(file,summary) in enumerate(leaves):
            yy=y+j+(3-len(leaves))//2
            active=is_active and (route=='setup' or folder=='CLAUDE.md' or any(t in file for t in targets.get(route,())))
            ink=col if active else K['DK']
            label=file
            canvas.put(tx-1,yy,'─' if len(leaves)==1 else '┌' if j==0 else '└' if j==len(leaves)-1 else '├',ink)
            canvas.put(tx,yy,label,ink+K['BO'],max(1,origin+graph_w-tx))
            sx=tx+min(api.HL.vis(label),max(1,origin+graph_w-tx))+2
            if sx<origin+graph_w:
                canvas.put(sx,yy,'· '+summary,K['WH'] if active else K['DK'],origin+graph_w-sx)
    return canvas.lines()


def main():
    """Read-only reuse for an existing agent, independent of creation form."""
    import argparse
    import shutil
    import add_agent_tui as api
    import agent_create_ui
    parser=argparse.ArgumentParser(description='Ver carpetas y rutas de un cerebro existente; sólo lectura.')
    parser.add_argument('--brain',required=True)
    parser.add_argument('--route',choices=tuple(ROUTES),default='boot')
    args=parser.parse_args()
    model=inspect(args.brain)
    w,h=shutil.get_terminal_size((130,44))
    K=api._K()
    lines=render(model,api,K,agent_create_ui._MapCanvas,max(60,w-4),max(20,h-4),args.route)
    print('\n'.join(lines))
    print('ESTADO ACTUAL · archivos reales · lectura sin modificar el cerebro')
    if model.get('truncated'): print('Inventario parcial: límite de archivos alcanzado')


if __name__=='__main__':
    main()

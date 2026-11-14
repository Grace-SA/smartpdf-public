"""Separate source-framed plots from data only with complete word ownership proof."""
import math
import re
from collections import Counter, defaultdict
from statistics import median

from layout_tables import LayoutError, physical_page
from layout_regions import candidates, recover_regions

NOTICE = ("Separately framed chart regions were excluded from record fields. Their native "
          "tokens are preserved below, not interpreted as table data. Token orientation and "
          "reading order are not reconstructed; plotted lines are not preserved. Check the original PDF.")


def inside(a, b, pad=0):
    return b[0]-pad <= a[0] <= a[2] <= b[2]+pad and b[1]-pad <= a[1] <= a[3] <= b[3]+pad


def geometry(obj):
    return [obj['x0'], obj['top'], obj['x1'], obj['bottom']]


def box(value):
    return (isinstance(value, (list, tuple)) and len(value)==4
            and all(isinstance(v,(int,float)) and math.isfinite(v) for v in value)
            and value[0]<value[2] and value[1]<value[3])


def series(curve, panel):
    points=curve.get('pts', [])
    if (not curve.get('stroke') or curve.get('fill') or not 12<=len(points)<=256
            or not inside(geometry(curve),panel)
            or curve['x1']-curve['x0'] < (panel[2]-panel[0])*.5
            or curve['bottom']-curve['top'] < (panel[3]-panel[1])*.05):
        return False
    if any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in points):
        return False
    dx=[b[0]-a[0] for a,b in zip(points,points[1:])]
    dy=[b[1]-a[1] for a,b in zip(points,points[1:])]
    return all(v>=0 for v in dx) and sum(a*b<0 for a,b in zip(dy,dy[1:]))>=2


def center(word):
    return ((word['x0']+word['x1'])/2, (word['top']+word['bottom'])/2)


class PixelEvidence:
    """One bounded final-page raster; source graphics declarations are not proof."""
    def __init__(self,page):
        if page.width*page.height*4>16000000:
            raise LayoutError('Chart evidence exceeds the raster budget.')
        try:
            rendered=page.to_image(resolution=144)
            self.image=rendered.original.convert('L')
            self.scale=rendered.scale
            self.origin=rendered.bbox
            self.pixels=self.image.load()
        except Exception as error:
            raise LayoutError('Chart visibility could not be verified.') from error
        self.samples=0

    def visible(self,points):
        if not 2<=len(points)<=256:
            return False
        # Vertices alone can lie on grid lines even when a series is invisible.
        # Also inspect the three interior quarter-points of every segment.
        probes=[points[0]]
        for a,b in zip(points,points[1:]):
            probes.extend((a[0]+(b[0]-a[0])*i/4,a[1]+(b[1]-a[1])*i/4) for i in range(1,5))
        self.samples+=len(probes)*33
        if self.samples>100000:
            raise LayoutError('Chart evidence exceeds the pixel budget.')
        visible=0
        for x,y in probes:
            x=round((x-self.origin[0])*self.scale)
            y=round((y-self.origin[1])*self.scale)
            if x<5 or y<5 or x+5>=self.image.width or y+5>=self.image.height:
                return False
            ink=min(self.pixels[xx,yy] for xx in range(x-2,x+3) for yy in range(y-2,y+3))
            background=max(self.pixels[x+dx,y+dy] for dx,dy in
                           ((-5,-5),(-5,0),(-5,5),(0,-5),(0,5),(5,-5),(5,0),(5,5)))
            visible+=ink<180 and background-ink>=40
        return visible>=len(probes)*.9


def plot_labels(page,panel,grids,words,pixels):
    """Every token must fit one simple axis/title/legend role, not an inset table."""
    axes=[g for g in grids if len(g.columns)==1 and len(g.rows)>=6
          and inside(g.bbox,panel) and g.bbox[2]-g.bbox[0]>(panel[2]-panel[0])*.5
          and g.bbox[3]-g.bbox[1]>(panel[3]-panel[1])*.5]
    if len(axes)!=1:
        return False
    axis=list(axes[0].bbox)
    selected=[]
    for w in words:
        x,y=center(w)
        if panel[0]<=x<=panel[2] and panel[1]<=y<=panel[3]:
            if not inside(geometry(w),panel):
                return False
            selected.append(w)
    tick_tokens=[w for w in selected if w['x1']<axis[0] and axis[1]-5<=center(w)[1]<=axis[3]+5
                 and re.fullmatch(r'[0-9.\-]+',w['text'])]
    tick_rows=[]
    for w in sorted(tick_tokens,key=lambda w:center(w)[1]):
        if not tick_rows or center(w)[1]-center(tick_rows[-1][0])[1]>1.5:
            tick_rows.append([])
        tick_rows[-1].append(w)
    ticks=[]
    for row in tick_rows:
        row.sort(key=lambda w:w['x0'])
        value=''.join(w['text'] for w in row)
        if (not re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?',value)
                or any(b['x0']-a['x1']>2 for a,b in zip(row,row[1:]))):
            return False
        ticks.append(dict(text=value,x0=min(w['x0'] for w in row),x1=max(w['x1'] for w in row)))
    if len(ticks)<6 or max(w['x1'] for w in ticks)-min(w['x1'] for w in ticks)>2:
        return False
    values=[float(w['text']) for w in ticks]
    steps=[b-a for a,b in zip(values,values[1:])]
    if not (all(v>0 for v in steps) or all(v<0 for v in steps)):
        return False
    used={id(w) for w in tick_tokens}
    titles=[w for w in selected if id(w) not in used and w['bottom']<axis[1]
            and w['x0']>=panel[0]]
    if (not titles or len(titles)>12
            or max(center(w)[1] for w in titles)-min(center(w)[1] for w in titles)>3):
        return False
    used.update(id(w) for w in titles)
    labels=[w for w in selected if id(w) not in used and axis[3]<center(w)[1]<axis[3]+15
            and axis[0]-5<=center(w)[0]<=axis[2]+5 and len(w['text'])<=3]
    if len(labels)<6 or max(center(w)[1] for w in labels)-min(center(w)[1] for w in labels)>3:
        return False
    used.update(id(w) for w in labels)
    units=[w for w in selected if id(w) not in used and w['x1']<min(w['x0'] for w in ticks)-2
           and axis[1]<=center(w)[1]<=axis[3]]
    if units and (sum(len(w['text']) for w in units)>12
                  or max(w['x0'] for w in units)-min(w['x0'] for w in units)>2):
        return False
    used.update(id(w) for w in units)
    legend=[w for w in selected if id(w) not in used]
    if not legend or max(center(w)[1] for w in legend)-min(center(w)[1] for w in legend)>3:
        return False
    if min(w['top'] for w in legend)<=max(w['bottom'] for w in labels)+3:
        return False
    groups=[]
    for w in sorted(legend,key=lambda w:w['x0']):
        if not groups or w['x0']-groups[-1][-1]['x1']>12:
            groups.append([])
        groups[-1].append(w)
    if not 2<=len(groups)<=6:
        return False
    for group in groups:
        first=group[0];cy=center(first)[1]
        swatches=[line for line in page.lines if line.get('stroke')
                  and abs(line['top']-line['bottom'])<.1 and abs(line['top']-cy)<3
                  and 0<first['x0']-line['x1']<6 and 8<line['x1']-line['x0']<40]
        if len(swatches)!=1:
            return False
        line=swatches[0]
        if not pixels.visible([(line['x0']+(line['x1']-line['x0'])*i/8,line['top']) for i in range(9)]):
            return False
    return True


def partitions(page, tables):
    if getattr(page,'rotation',0) or len(tables)!=1 or len(page.curves)>200:
        return []
    model=tables[0].get('bbox')
    if not box(model):
        return []
    grids=physical_page(page).find_tables()
    found=[];pixels=None
    words=page.extract_words(x_tolerance=2,y_tolerance=3)
    if len(words)>16000:
        return []
    for region in candidates(page):
        if not inside(region,model,3) or model[2]-region[2] < page.width*.15:
            continue
        for grid in grids:
            left=[list(c) for c in grid.cells if c and abs(c[0]-region[0])<=1
                  and abs(c[2]-region[2])<=1]
            # The data region must consist of complete cells of this same frame.
            if (len(left)<3 or not inside(region,grid.bbox,1)
                    or abs(min(c[1] for c in left)-region[1])>1
                    or not any(abs(c[3]-region[3])<=1 for c in left)):
                continue
            panels=[list(c) for c in grid.cells if c and abs(c[0]-region[2])<=1
                    and c[2]-c[0]>=page.width*.15 and c[3]-c[1]>=page.height*.15]
            if not 2<=len(panels)<=6 or any(not box(p) for p in panels):
                continue
            curves=[[curve for curve in page.curves if series(curve,p)] for p in panels]
            if any(len(cs)<2 for cs in curves):
                continue
            if not inside(grid.bbox,model,3) or any(not inside(p,model,3) for p in panels):
                raise LayoutError('Chart panels extend outside their predicted table.')
            if pixels is None:
                pixels=PixelEvidence(page)
            if any(sum(pixels.visible(c['pts']) for c in cs)<2 for cs in curves):
                raise LayoutError('Chart-series visibility is uncertain.')
            if any(len(g.columns)>=2 and inside(g.bbox,p) and g is not grid
                   for g in grids for p in panels):
                raise LayoutError('A chart panel contains a separate ruled table.')
            if any(not plot_labels(page,p,grids,words,pixels) for p in panels):
                raise LayoutError('A chart panel contains unclassified text or data.')
            ordered=sorted(panels,key=lambda p:p[1])
            if any(a[3]>b[1] for a,b in zip(ordered,ordered[1:])):
                raise LayoutError('Chart panels overlap.')
            found.append((region,panels,list(grid.bbox)))
    if len(found)>1:
        raise LayoutError('More than one physical chart/table partition is possible.')
    return found


def original_owners(table,words,region,panels,frame):
    cells=[c for c in table.get('cells',[]) if c.get('text','').strip()]
    if not cells or len(cells)*len(words)>500000:
        return False
    zones=[region]+panels
    footer=[region[0],region[3],region[2],frame[3]]
    if box(footer):
        zones.append(footer)
    for cell in cells:
        b=cell.get('sourceTextCandidate')
        if not box(b):
            return False
        selected=[w for w in words if min(b[2],w['x1'])>max(b[0],w['x0'])
                  and min(b[3],w['bottom'])>max(b[1],w['top'])]
        if not selected:
            return False
        owners=set()
        for w in selected:
            matches=[i for i,z in enumerate(zones) if inside(geometry(w),z)]
            if len(matches)!=1:
                return False
            owners.add(matches[0])
        if len(owners)!=1:
            return False
    return True


def verify_fields(table, words, region):
    """Each complete source token must have exactly one unchanged output owner."""
    cells=[c for c in table['cells'] if c['text'].strip()]
    if not cells or len(cells)>9000 or len(words)>16000 or len(cells)*len(words)>500000:
        return False
    selected=[]
    for i,w in enumerate(words):
        b=geometry(w);cx,cy=(b[0]+b[2])/2,(b[1]+b[3])/2
        if region[0]<=cx<=region[2] and region[1]<=cy<=region[3]:
            if not inside(b,region):
                return False
            selected.append((i,w))
    owners=Counter();row_bounds=defaultdict(list);row_cells=defaultdict(list)
    columns=defaultdict(list);cell_bounds=[]
    for c in cells:
        b=c.get('sourceTextCandidate')
        if (not box(b) or c['rs']!=1
                or any(type(c.get(key)) is not int for key in ('r','c','rs','cs'))
                or not 0<=c['c']<c['c']+c['cs']<=len(table['widths'])):
            return False
        ws=[(i,w) for i,w in selected if b[0]<=(w['x0']+w['x1'])/2<=b[2]
            and b[1]<=(w['top']+w['bottom'])/2<=b[3]]
        if not ws:
            return False
        ws.sort(key=lambda v:(round(v[1]['top']/3),v[1]['x0']))
        clean=lambda s:re.sub(r'\s+','',s)
        if clean(' '.join(w['text'] for _,w in ws))!=clean(c['text']):
            return False
        owners.update(i for i,_ in ws)
        row_bounds[c['r']].extend((w['top']+w['bottom'])/2 for _,w in ws)
        row_cells[c['r']].append((c['c'],min(w['x0'] for _,w in ws),max(w['x1'] for _,w in ws)))
        left,right=min(w['x0'] for _,w in ws),max(w['x1'] for _,w in ws)
        cell_bounds.append((c,left,right))
        if c['cs']==1:
            columns[c['c']].append((left,right))
    if set(owners)!=set(i for i,_ in selected) or any(v!=1 for v in owners.values()):
        return False
    # Row-local order does not establish field identity. Every output column
    # needs repeated, globally non-overlapping source evidence across records.
    if set(columns)!=set(range(len(table['widths']))) or any(len(v)<2 for v in columns.values()):
        return False
    bands=[(min(a for a,b in columns[col]),max(b for a,b in columns[col]))
           for col in range(len(table['widths']))]
    if any(a[1]>=b[0] for a,b in zip(bands,bands[1:])):
        return False
    edges=[region[0]]+[(a[1]+b[0])/2 for a,b in zip(bands,bands[1:])]+[region[2]]
    if any(left<edges[c['c']] or right>edges[c['c']+c['cs']] for c,left,right in cell_bounds):
        return False
    previous=None
    for row in sorted(row_bounds):
        ys=row_bounds[row]
        if max(ys)-min(ys)>3 or (previous is not None and min(ys)<=previous):
            return False
        previous=max(ys)
        ordered=sorted(row_cells[row])
        if any(a[2]>=b[1] for a,b in zip(ordered,ordered[1:])):
            return False
    return True


def context(words, region, panels):
    groups=[[] for _ in range(len(panels)+1)]
    for w in words:
        b=geometry(w)
        if inside(b,region):
            continue
        if not (b[2]<region[0] or b[0]>region[2] or b[3]<region[1] or b[1]>region[3]):
            raise LayoutError('A source token crosses the table/graphic boundary.')
        owners=[i for i,p in enumerate(panels) if inside(b,p)]
        if len(owners)>1:
            raise LayoutError('Graphic token ownership is ambiguous.')
        groups[owners[0] if owners else -1].append(w['text'])
    text=NOTICE
    for i,group in enumerate(groups):
        if group:
            text+='\n\n'+(f'Chart region {i+1}: native tokens' if i<len(panels) else 'Other source-page tokens')+'\n'+'\n'.join(group)
    from source_context import valid_context
    if len(text)>16000 or valid_context(text)!=text:
        raise LayoutError('Graphic source text exceeds the context budget or contains unsupported characters.')
    return text


def recover(source,index,page,tables,converter,budget):
    partitions_found=partitions(page,tables)
    if not partitions_found:
        return tables,0
    if budget<=0:
        raise LayoutError('Chart/table separation exceeds the region budget.')
    region,panels,frame=partitions_found[0]
    words=page.extract_words(x_tolerance=2,y_tolerance=3)
    if not original_owners(tables[0],words,region,panels,frame):
        raise LayoutError('Original model fields cross or escape the source regions.')
    recovered,attempted=recover_regions(source,index,page,converter,budget)
    words=page.extract_words(x_tolerance=2,y_tolerance=3)
    valid=[t for t in recovered if inside(t['bbox'],region,1) and verify_fields(t,words,region)]
    if len(valid)!=1:
        raise LayoutError('A table crossing separately framed plots needs source-field review.')
    table=dict(valid[0],method='layout-chart-separated',separatedChartPanels=len(panels))
    table['chartSourceContext']=context(words,region,panels)
    return [table],attempted

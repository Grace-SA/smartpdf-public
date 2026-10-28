"""Check selected native PDF table cells against synthetic source token positions."""
import json
from pathlib import Path
import pdfplumber

root=Path('.research/m13/gotenberg/noto-fonts')
checks=[]
def check(label,condition):
    checks.append({'check':label,'passed':bool(condition)})

with pdfplumber.open(root/'1-extended-chinese-merged-table.pdf') as d:
    grid=d.pages[0].find_tables()[0].extract()
    check('merged table six by four grid',len(grid)==6 and all(len(row)==4 for row in grid))
    check('title spans all four columns','MERGE-TITLE' in grid[0][0] and grid[0][1:]==[None]*3)
    check('vertical merge spans two rows','VERTICAL-MERGE' in grid[1][0] and grid[2][0] is None)
    check('horizontal merge spans two columns','HORIZONTAL-MERGE' in grid[1][1] and grid[1][2] is None)
    for row in range(3,6):
        for col in range(4):check(f'merged cell {row},{col}',f'CELL-{row}-{col}' in (grid[row][col] or ''))

with pdfplumber.open(root/'1-extended-nested-table.pdf') as d:
    grid=d.pages[0].find_tables()[0].extract()
    check('outer left and right cells','OUTER-A' in grid[0][0] and 'OUTER-B' in grid[0][-1] and 'OUTER-C' in grid[1][-1])
    for row in range(3):
        for col in range(2):check(f'nested cell {row},{col}',f'NESTED-{row}-{col}' in (grid[row+2][col+1] or ''))

with pdfplumber.open(root/'1-extended-landscape-wide-table.pdf') as d:
    grid=d.pages[0].find_tables()[0].extract()
    check('wide table twelve by eight grid',len(grid)==12 and all(len(row)==8 for row in grid))
    for row in range(12):
        for col in range(8):check(f'wide cell {row},{col}',f'WIDE-{row:02d}-{col}' in (grid[row][col] or ''))

with pdfplumber.open(root/'1-extended-chinese-long-table.pdf') as d:
    observed=[]
    for page in d.pages:
        grid=page.find_tables()[0].extract()
        check('long-table repeated header page '+str(page.page_number),'REPEATED-HEADER' in grid[0][0])
        for row in grid[1:]:
            observed.append(row[0])
            check('long-table right cell page '+str(page.page_number),'数量：十二' in (row[2] or ''))
    check('all hundred long-table rows keep order',observed==[f'LONGROW-{i:03d}' for i in range(1,101)])

with pdfplumber.open(root/'1-extended-long-row-split.pdf') as d:
    columns=[[],[]]
    for page in d.pages:
        grid=page.find_tables()[0].extract()
        check('split-row repeated header page '+str(page.page_number),'SPLIT-HEADER' in grid[0][0])
        for col in range(2):
            columns[col].extend(line.split()[0] for line in (grid[1][col] or '').splitlines())
    for col in range(2):check('split-row column '+str(col)+' sequence',columns[col]==[f'SPLIT-{col}-{i:03d}' for i in range(45)])

out={'checks':checks,'passed':sum(x['passed'] for x in checks),'total':len(checks)}
(root/'table-audit.json').write_text(json.dumps(out,indent=2),encoding='utf8')
print(json.dumps({'passed':out['passed'],'total':out['total'],'failures':[x for x in checks if not x['passed']]}))
raise SystemExit(0 if out['passed']==out['total'] else 1)

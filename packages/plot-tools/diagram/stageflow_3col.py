#!/usr/bin/env python3
"""stageflow-3col：分阶段流程框架图（左方法链 / 中彩色流程块 / 右阶段说明）。

    python3 stageflow_3col.py content.json -o out.drawio
    python3 stageflow_3col.py content.json --check

与 framework-3col 的区别：中栏每块有**实色标题条**和独立色系，左右栏是**竖排文字**
（左＝白底方框 + 粗箭头推进，右＝左向块箭头指入对应块）。段型见 references/stageflow-3col.md。
"""
import argparse
import html
import json
import pathlib
import sys
import unicodedata

W = 1000
FS, FS_T = 14, 16
LINE_H = 18
FONT = 'Microsoft YaHei,PingFang SC,Hiragino Sans GB,Helvetica'
INK = '#262626'
PINK, PINK_S = '#fbe4ec', '#d2679f'
RAIL_S, RAIL_ARROW = '#1f3f7f', '#1f3f7f'
RRAIL, RRAIL_S = '#a8c0ea', '#4060b0'
MID = (150, 800)                      # 中栏容器 x 范围
RAIL_L = (58, 130)                    # 左栏竖排盒
RAIL_R = (820, 960)                   # 右栏箭头

# 每块一个色系：(标题条底, 标题条描边, 深内容, 浅内容, 描边)
TONES = {
    'teal':   ('#1f6f6f', '#14504f', '#a8e0e0', '#d6f2f2', '#4a9a9a'),
    'green':  ('#3a5a22', '#2a4318', '#c8e8b0', '#e6f4dc', '#6a9a4a'),
    'olive':  ('#8a7a1a', '#665a12', '#f6e6a4', '#fbf3d2', '#b8a23a'),
    'orange': ('#d06818', '#a04e10', '#f8d0b0', '#fbe6d6', '#d98c50'),
    'blue':   ('#4060b0', '#2c4488', '#a8c0ea', '#cfdcf4', '#5f7fc8'),
}
cells, problems = [], []


def esc(t):
    return html.escape(str(t), quote=True)


def tw(line, fs=FS):
    return sum(fs if unicodedata.east_asian_width(c) in ('W', 'F') else fs / 2 for c in line)


def lines_of(v):
    if v is None:
        return ['']
    return [str(x) for x in v] if isinstance(v, (list, tuple)) else str(v).split('\n')


def fit(cid, ls, w, h, fs=FS):
    for ln in ls:
        usable = w - (8 if len(ln) > 1 else 2)
        if tw(ln, fs) > usable:
            problems.append(f'{cid}: "{ln}" 宽 {tw(ln, fs):.0f}px > 可用 {usable:.0f}px'
                            f'（约 {int(usable // fs)} 个汉字）')
    if len(ls) * (fs + 3) > h:
        problems.append(f'{cid}: {len(ls)} 行需 {len(ls) * (fs + 3)}px，槽高仅 {h:g}px')


def mk(ls):
    return '&lt;br&gt;'.join(esc(ln) for ln in ls)


def raw(cid, x, y, w, h, style, val=''):
    cells.append(f'        <mxCell id="{cid}" value="{val}" style="{style}" vertex="1" parent="1">\n'
                 f'          <mxGeometry x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}"'
                 f' as="geometry" />\n        </mxCell>')


def box(cid, x, y, w, h, text, fill, stroke, fs=FS, fc=INK, arc=12, bold=1, extra=''):
    ls = lines_of(text)
    fit(cid, ls, w, h, fs)
    raw(cid, x, y, w, h,
        f'rounded=1;arcSize={arc};whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};'
        f'strokeWidth=1.4;fontSize={fs};fontStyle={bold};fontColor={fc};fontFamily={FONT};'
        f'align=center;verticalAlign=middle;spacingLeft=3;spacingRight=3;{extra}', mk(ls))


def vbox(cid, x, y, w, h, text, fill, stroke, fs=FS_T, fc=INK, arc=12):
    chars = list(str(text))
    if len(chars) * (fs + 3) > h:
        problems.append(f'{cid}: 竖排 {len(chars)} 字需 {len(chars) * (fs + 3)}px > 槽高 {h:g}px')
    raw(cid, x, y, w, h,
        f'rounded=1;arcSize={arc};whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};'
        f'strokeWidth=2;fontSize={fs};fontStyle=1;fontColor={fc};fontFamily={FONT};'
        f'align=center;verticalAlign=middle;', '&lt;br&gt;'.join(esc(c) for c in chars))


def diamond(cid, x, y, w, h, text, fill, stroke, fs=FS):
    ls = lines_of(text)
    raw(cid, x, y, w, h,
        f'rhombus;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};strokeWidth=1.4;'
        f'fontSize={fs};fontStyle=1;fontColor={INK};fontFamily={FONT};align=center;'
        f'verticalAlign=middle;', mk(ls))


def edge(cid, pts, stroke=INK, width=1.6, end='block', start='none', extra=''):
    (sx, sy), (tx, ty) = pts[0], pts[-1]
    way = ''
    if len(pts) > 2:
        way = ('\n            <Array as="points">\n' + '\n'.join(
            f'              <mxPoint x="{px:g}" y="{py:g}" />' for px, py in pts[1:-1]) +
            '\n            </Array>')
    cells.append(
        f'        <mxCell id="{cid}" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;'
        f'html=1;endArrow={end};endFill=1;endSize=6;startArrow={start};startFill=1;startSize=6;'
        f'strokeColor={stroke};strokeWidth={width};{extra}" edge="1" parent="1">\n'
        f'          <mxGeometry relative="1" as="geometry">\n'
        f'            <mxPoint x="{sx:g}" y="{sy:g}" as="sourcePoint" />\n'
        f'            <mxPoint x="{tx:g}" y="{ty:g}" as="targetPoint" />{way}\n'
        f'          </mxGeometry>\n        </mxCell>')


def dashframe(cid, x, y, w, h, color='#5a5a5a', pattern='5 4'):
    # 一律画成无填充虚线 vertex（体检以 fillColor=none & dashed 判定为框架层而非实心盒），
    # 避免小尺寸时退化为 edge 画框导致框线穿过内部条目盒的误报
    raw(cid, x, y, w, h, f'rounded=0;html=1;fillColor=none;strokeColor={color};'
                         f'strokeWidth=1.2;dashed=1;dashPattern={pattern};')


def slots(a, b, n, gap):
    size = (b - a - (n - 1) * gap) / n
    return [(a + i * (size + gap), size) for i in range(n)]


# ---------------------------------------------------------------- 段
def sec_h(s):
    t = s['type']
    if t == 'cards':
        return 40 + max(len(lines_of(c['desc'])) for c in s['cards']) * 18 + 22
    if t == 'groups':
        return 34 + max(len(g['items']) for g in s['groups']) * 32
    if t == 'list_grid':
        return 34 + max(len(s['left']['items']), len(s['right']['rows'])) * 32
    if t == 'scenarios':
        return 40 + 120 + 44
    if t == 'fanout':
        return 40 + 12 + 46
    sys.exit(f'未知段型 {t}')


def draw_sec(k, s, x0, x1, y, tone):
    TB, TBS, DEEP, LIGHT, STK = TONES[tone]
    t, h = s['type'], sec_h(s)

    if t == 'cards':
        cs = s['cards']
        dh = max(len(lines_of(c['desc'])) for c in cs) * 18 + 12
        for i, (cx, cw) in enumerate(slots(x0 + 14, x1 - 14, len(cs), 10)):
            box(f'{k}_ch{i}', cx, y, cw, 30, cs[i]['header'], DEEP, STK)
            box(f'{k}_cd{i}', cx, y + 36, cw, dh, cs[i]['desc'], LIGHT, STK, fs=12, bold=0)
        return h

    if t == 'groups':
        gs = s['groups']
        for i, (gx, gw) in enumerate(slots(x0 + 14, x1 - 14, len(gs), 34)):
            dashframe(f'{k}_gf{i}', gx - 8, y - 6, gw + 16, h - 4, pattern='4 4')
            box(f'{k}_gh{i}', gx, y, gw, 28, gs[i]['header'], DEEP, STK)
            for j, it in enumerate(gs[i]['items']):
                box(f'{k}_gi{i}_{j}', gx, y + 34 + j * 32, gw, 27, it, LIGHT, STK)
            if i:
                edge(f'{k}_ga{i}', [(gx - 30, y + h / 2 - 10), (gx - 10, y + h / 2 - 10)],
                     TB, 2.4, 'block', 'block')
        return h

    if t == 'list_grid':
        L, R = s['left'], s['right']
        lw = (x1 - x0) * 0.22
        lx = x0 + 16
        rx = lx + lw + 46
        rw = x1 - 16 - rx
        box(f'{k}_lh', lx, y, lw, 28, L['header'], DEEP, STK)
        for j, it in enumerate(L['items']):
            box(f'{k}_li{j}', lx, y + 34 + j * 32, lw, 27, it, LIGHT, STK)
        dashframe(f'{k}_rf', rx - 10, y - 6, rw + 20, h - 4, pattern='4 4')
        box(f'{k}_rh', rx + rw * 0.16, y, rw * 0.68, 28, R['header'], DEEP, STK)
        for j, row in enumerate(R['rows']):
            for i, (cx, cw) in enumerate(slots(rx, rx + rw, len(row), 10)):
                box(f'{k}_ri{j}_{i}', cx, y + 34 + j * 32, cw, 27, row[i], LIGHT, STK)
        edge(f'{k}_e', [(lx + lw + 6, y + h / 2), (rx - 14, y + h / 2)], TB, 3)
        return h

    if t == 'scenarios':
        scs = s['scenarios']
        for i, (cx, cw) in enumerate(slots(x0 + 20, x1 - 20, len(scs), 22)):
            box(f'{k}_sh{i}', cx, y, cw, 30, scs[i]['name'], DEEP, STK)
            if i:
                edge(f'{k}_sa{i}', [(cx - 20, y + 15), (cx - 2, y + 15)], INK, 1.4,
                     'block', 'block')
            dw = cw * 0.42
            # 两侧标签在参考图里是竖排窄盒，不是横排
            vbox(f'{k}_sl{i}', cx, y + 44, cw * 0.26, 92, scs[i]['left'], LIGHT, STK, fs=14)
            diamond(f'{k}_sd{i}', cx + cw * 0.29, y + 44, dw, 92, scs[i]['decide'], LIGHT, STK)
            vbox(f'{k}_sr{i}', cx + cw * 0.74, y + 44, cw * 0.26, 92, scs[i]['right'],
                 LIGHT, STK, fs=14)
            box(f'{k}_so{i}', cx, y + 152, cw, 30, scs[i]['out'], LIGHT, STK)
            edge(f'{k}_se{i}', [(cx + cw / 2, y + 137), (cx + cw / 2, y + 151)], INK, 1.6)
        return h

    if t == 'fanout':
        outs = s['outs']
        cw = (x1 - x0) * 0.72
        cx = (x0 + x1) / 2 - cw / 2
        box(f'{k}_c', cx, y, cw, 30, s['center'], DEEP, STK)
        oy = y + 52
        pos = slots(x0 + 16, x1 - 16, len(outs), 12)
        bus = y + 42
        edge(f'{k}_stub', [((x0 + x1) / 2, y + 31), ((x0 + x1) / 2, bus)], INK, 1.4, 'none')
        edge(f'{k}_bus', [(pos[0][0] + pos[0][1] / 2, bus),
                          (pos[-1][0] + pos[-1][1] / 2, bus)], INK, 1.4, 'none')
        for i, (ox, ow) in enumerate(pos):
            box(f'{k}_o{i}', ox, oy, ow, 34, outs[i], LIGHT, STK)
            edge(f'{k}_oe{i}', [(ox + ow / 2, bus), (ox + ow / 2, oy - 1)], INK, 1.4)
        return h


# ---------------------------------------------------------------- 主体
def build(c):
    blocks, stages, rights = c['blocks'], c['stages'], c.get('rights', [])
    heads = c.get('headers', ['研究框架', '研究内容', '研究方法'])
    TOP, GAP = 96, 18
    hs = []
    for b in blocks:
        secs = [sec_h(s) for s in b['sections']]
        hs.append(14 + 34 + 14 + sum(secs) + (len(secs) - 1) * 14 + 14)
    H = TOP + sum(hs) + GAP * (len(blocks) - 1) + 20

    for i, (x, t) in enumerate(zip([58, 430, 820], heads)):
        box(f'hd{i}', x, 28, 120, 34, t, PINK, PINK_S, FS_T, arc=25)

    tops, y = [], TOP
    for bi, b in enumerate(blocks):
        tone = b.get('tone', 'blue')
        TB, TBS, DEEP, LIGHT, STK = TONES[tone]
        h = hs[bi]
        tops.append((y, h))
        dashframe(f'blk{bi}', MID[0], y, MID[1] - MID[0], h)
        tw_ = (MID[1] - MID[0]) * 0.62
        box(f'blk{bi}_t', MID[0] + (MID[1] - MID[0] - tw_) / 2, y + 14, tw_, 34,
            b['title'], TB, TBS, FS_T, fc='#ffffff', arc=8)
        yy = y + 14 + 34 + 14
        for si, s in enumerate(b['sections']):
            yy += draw_sec(f's{bi}{si}', s, MID[0], MID[1], yy, tone) + 14
        y += h + GAP

    # 左栏：竖排方法盒，块间粗箭头推进
    prev = (0, 0)
    for i, st in enumerate(stages):
        bt, bh = tops[min(st.get('block', i), len(tops) - 1)]
        txt = st['text'] if isinstance(st, dict) else st
        sh = max(len(str(txt)) * (FS_T + 3) + 16, 72)
        sy = bt + bh * st.get('at', 0.35) - sh / 2 if isinstance(st, dict) else bt + 20
        vbox(f'st{i}', RAIL_L[0], sy, RAIL_L[1] - RAIL_L[0], sh, txt, '#ffffff', RAIL_S)
        if i:
            py = prev[0] + prev[1]
            if sy - py > 26:
                raw(f'st_a{i}', (RAIL_L[0] + RAIL_L[1]) / 2 - 9, py + 8, 18, sy - py - 16,
                    f'shape=singleArrow;direction=south;arrowWidth=0.5;arrowSize=0.32;html=1;'
                    f'fillColor={RAIL_ARROW};strokeColor=none;')
        prev = (sy, sh)

    # 右栏：左向块箭头，箭头体内竖排文字，指入对应块
    for i, rt in enumerate(rights):
        bt, bh = tops[min(rt.get('block', i), len(tops) - 1)]
        txt = rt['text'] if isinstance(rt, dict) else rt
        rh = max(len(str(txt)) * (FS_T + 3) + 26, 80)
        ry = bt + bh * rt.get('at', 0.45) - rh / 2
        raw(f'rt{i}', RAIL_R[0], ry, RAIL_R[1] - RAIL_R[0], rh,
            f'shape=singleArrow;direction=west;arrowWidth=0.68;arrowSize=0.3;html=1;'
            f'fillColor={RRAIL};strokeColor={RRAIL_S};strokeWidth=1.4;fontSize={FS_T};'
            f'fontStyle=1;fontColor={INK};fontFamily={FONT};whiteSpace=wrap;align=center;'
            f'verticalAlign=middle;spacingLeft=16;',
            '&lt;br&gt;'.join(esc(ch) for ch in str(txt)))
    return int(H)


# ---------------------------------------------------------------- 聚合校验
REFDOC = 'diagram/references/stageflow-3col.md'
_TONE_OK = ('teal', 'green', 'olive', 'orange', 'blue')


def validate(c):
    """一次返回全部缺失字段 / 数量不符 / 格式不符（带字段规格与参考文档）。"""
    out = []

    def p(ctx, msg):
        out.append(f'{ctx}: {msg}；详见 {REFDOC}')

    if 'blocks' not in c or not isinstance(c['blocks'], list) or not c['blocks']:
        p('blocks', '缺失或为空（必填：内容块数组，1–8 个，每块 {title, tone?, sections}）')
        return out
    if not 1 <= len(c['blocks']) <= 8:
        p('blocks', f'需 1–8 个，实际 {len(c["blocks"])} 个')
    if 'stages' not in c or not isinstance(c['stages'], list) or not c['stages']:
        p('stages', '缺失或为空（必填：左栏方法链，2–8 个；每项 {text ≤6 字竖排, block?, at?} 或字符串）')
    elif not 2 <= len(c['stages']) <= 8:
        p('stages', f'需 2–8 个，实际 {len(c["stages"])} 个')
    if 'rights' in c and (not isinstance(c['rights'], list) or not c['rights']):
        p('rights', '可选；若提供须为 1 个以上 {text ≤6 字, block?, at?} 或字符串')
    if 'headers' in c and (not isinstance(c['headers'], list) or len(c['headers']) != 3):
        p('headers', '可选；若提供须正好 3 个（左/中/右栏头，各 ≤6 汉字）')

    _SEC = {
        'cards': ('卡片数组 3–6 个；每项 {header ≤7 汉字, desc ≤9 汉字/行}', 3, 6,
                  ('header', 'desc'), 'cards'),
        'groups': ('组数组 2–4 个；每项 {header ≤12 汉字, items} 各条 ≤12 汉字', 2, 4,
                   ('items',), 'groups'),
        'list_grid': ('left {header, items} → 粗箭头 → right {header, rows}；网格每行 2–4 列', 1, None,
                      (), None),
        'scenarios': ('场景数组 2–4 个；每项 {name ≤12 汉字, left ≤5 字竖排, decide ≤4 汉字, '
                      'right ≤5 字竖排, out}', 2, 4, ('name', 'left', 'decide', 'right', 'out'),
                      'scenarios'),
        'fanout': ('center ≤28 汉字（必填）+ outs 数组 3–6 个（各 ≤7 汉字）', 3, 6,
                   ('outs',), 'fanout'),
    }
    for bi, b in enumerate(c['blocks']):
        if not isinstance(b, dict):
            p(f'blocks[{bi}]', '必须为对象 {title, tone?, sections}')
            continue
        if not isinstance(b.get('title'), str):
            p(f'blocks[{bi}].title', '缺失或非字符串（必填；≤24 汉字）')
        if 'tone' in b and b['tone'] not in _TONE_OK:
            p(f'blocks[{bi}].tone', f"未知 '{b['tone']}'；可用: {'/'.join(_TONE_OK)}")
        secs = b.get('sections')
        if not isinstance(secs, list) or not secs:
            p(f'blocks[{bi}].sections', '缺失或为空（必填：版式段数组）')
            continue
        for si, s in enumerate(secs):
            path = f'blocks[{bi}].sections[{si}]'
            if not isinstance(s, dict) or 'type' not in s:
                p(path, '必须是含 type 的版式段对象')
                continue
            t = s['type']
            if t not in _SEC:
                p(f'{path}.type', f"未知段型 '{t}'；可用: cards|groups|list_grid|scenarios|fanout")
                continue
            spec, lo, hi, keyreq, chk = _SEC[t]
            if t == 'list_grid':
                L, R = s.get('left'), s.get('right')
                if not (isinstance(L, dict) and isinstance(L.get('header'), str)
                        and isinstance(L.get('items'), list) and L['items']):
                    p(f'{path}.left', '必须为 {header, items}（items 非空；左列 ≤9 汉字/条）')
                if not (isinstance(R, dict) and isinstance(R.get('header'), str)
                        and isinstance(R.get('rows'), list) and R['rows']):
                    p(f'{path}.right', '必须为 {header, rows}（rows 非空；网格单元 ≤9 汉字）')
                elif any(not isinstance(r, list) or not 2 <= len(r) <= 4 for r in R['rows']):
                    p(f'{path}.right.rows', '每行需 2–4 列')
                continue
            _KEY_OF = {'cards': 'cards', 'groups': 'groups', 'scenarios': 'scenarios',
                      'fanout': 'outs', 'list_grid': 'left'}
            val = s.get(_KEY_OF.get(t, keyreq[0]))
            if not isinstance(val, list) or not val:
                p(f'{path}.{keyreq[0]}', f'缺失或为空（必填；{spec}）')
            elif lo and not lo <= len(val) <= hi:
                p(f'{path}.{keyreq[0]}', f'需 {lo}–{hi} 项，实际 {len(val)} 项；{spec}')
            items = val if isinstance(val, list) else []
            if chk == 'cards':
                for i, cd in enumerate(items):
                    for k in ('header', 'desc'):
                        if not isinstance(cd.get(k), str):
                            p(f'{path}.cards[{i}].{k}', f'缺失或非字符串（{spec}）')
            elif chk == 'groups':
                for i, g in enumerate(items):
                    if not isinstance(g.get('header'), str):
                        p(f'{path}.groups[{i}].header', f'缺失或非字符串（{spec}）')
                    if not (isinstance(g.get('items'), list) and g['items']):
                        p(f'{path}.groups[{i}].items', f'缺失或为空（每个条目 ≤12 汉字）')
            elif chk == 'scenarios':
                for i, sc in enumerate(items):
                    for k in ('name', 'left', 'decide', 'right', 'out'):
                        if not isinstance(sc.get(k), str):
                            p(f'{path}.scenarios[{i}].{k}', f'缺失或非字符串（{spec}）')
            elif chk == 'fanout':
                if not isinstance(s.get('center'), str):
                    p(f'{path}.center', '缺失或非字符串（必填；≤28 汉字）')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('content')
    ap.add_argument('-o', '--out')
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    c = json.loads(pathlib.Path(a.content).read_text(encoding='utf-8'))
    schema = validate(c)
    if schema:
        print(f'✗ 字段校验未通过（{len(schema)} 处）：', file=sys.stderr)
        for p in schema:
            print('  - ' + p, file=sys.stderr)
        print('\n调试建议：按 references/stageflow-3col.md 补齐/修正字段后重试。', file=sys.stderr)
        sys.exit(1)
    H = build(c)
    if problems:
        print(f'✗ 容量检查未通过（{len(problems)} 处）：', file=sys.stderr)
        for p in problems:
            print('  - ' + p, file=sys.stderr)
        sys.exit(2)
    print(f'✓ 容量检查通过（画布 {W}×{H}）')
    if a.check:
        return
    out = pathlib.Path(a.out or pathlib.Path(a.content).with_suffix('.drawio'))
    out.write_text(
        '<mxfile host="app.diagrams.net" agent="claude-code" version="24.7.17" pages="1">\n'
        '  <diagram id="stageflow" name="阶段流程框架">\n'
        f'    <mxGraphModel dx="{W}" dy="{H}" grid="0" gridSize="10" guides="1" tooltips="1" '
        f'connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{W}" pageHeight="{H}" '
        'math="0" shadow="0">\n      <root>\n        <mxCell id="0" />\n'
        '        <mxCell id="1" parent="0" />\n' + '\n'.join(cells) +
        '\n      </root>\n    </mxGraphModel>\n  </diagram>\n</mxfile>\n', encoding='utf-8')
    print(f'✓ 已写出 {out}（{len(cells)} 个图元）')


if __name__ == '__main__':
    main()

import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import * as d3 from 'd3';
import { Search, Crosshair } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { FEATURED_STAGES, getRecommend, getStageSubgraph, loadCatalog } from '@/api/client';
import type {
  EvidenceLevel, NodeKind, RecommendResponse, Relation,
  SubgraphEdge, SubgraphResponse,
} from '@/types/kb';

const NODE_COLORS: Record<NodeKind, string> = {
  operator: '#38bdf8', // 干员 蓝
  enemy: '#f87171',    // 敌人 红
  stage: '#fb923c',    // 关卡 橙
  skill: '#2dd4bf',    // 技能 青
};

const TYPE_LABEL: Record<NodeKind, string> = {
  operator: '干员', enemy: '敌人', stage: '关卡', skill: '技能',
};

const REL_LABEL: Record<Relation, string> = {
  HAS_SKILL: '拥有技能',
  CONTAINS_ENEMY: '出场敌人',
  COUNTERS: '克制',
  RECOMMENDS: '推荐干员',
};

interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  type: NodeKind;
  label: string;
  sub?: string;
}
interface SimLink {
  source: string | SimNode;
  target: string | SimNode;
  relation: Relation;
  evidence: EvidenceLevel;
  score?: number;
  support?: number;
  count?: string;
}

function asId(v: string | SimNode): string {
  return typeof v === 'string' ? v : v.id;
}

export default function GraphPage() {
  const [stages, setStages] = useState(FEATURED_STAGES);
  const [stageId, setStageId] = useState(FEATURED_STAGES[0].stage_id);
  const [subgraph, setSubgraph] = useState<SubgraphResponse | null>(null);
  const [recommend, setRecommend] = useState<RecommendResponse | null>(null);
  const [nodes, setNodes] = useState<SimNode[]>([]);
  const [links, setLinks] = useState<SimLink[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [highlight, setHighlight] = useState<Set<string> | null>(null);
  const [notFound, setNotFound] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const simRef = useRef<d3.Simulation<SimNode, SimLink> | null>(null);
  const [searchParams] = useSearchParams();

  useEffect(() => {
    loadCatalog().then((cat) => {
      const mapped = cat.stages
        .map((s) => ({ stage_id: s.stage_id || '', title: s.title || s.stage_id || '' }))
        .filter((s) => s.stage_id);
      if (mapped.length) setStages(mapped);
    });
    const focus = searchParams.get('stage') || searchParams.get('focus');
    if (focus) setStageId(focus);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let cancelled = false;
    setNotFound(false);
    setSelected(null);
    setHighlight(null);
    (async () => {
      const [sub, rec] = await Promise.all([
        getStageSubgraph(stageId),
        getRecommend(stageId),
      ]);
      if (cancelled) return;
      setSubgraph(sub);
      setRecommend(rec);
      if (!sub) {
        setNodes([]);
        setLinks([]);
        setNotFound(true);
        return;
      }
      setNodes(sub.nodes.map((n) => ({
        id: n.node_id,
        type: n.kind,
        label: n.name || n.node_id.split(':')[1],
        sub: n.class ? `${TYPE_LABEL[n.kind]} · ${n.class}` : TYPE_LABEL[n.kind],
      })));
      setLinks(sub.edges.map((e: SubgraphEdge) => ({
        source: e.source, target: e.target, relation: e.relation,
        evidence: e.evidence, score: e.score, support: e.support, count: e.count,
      })));
    })();
    return () => { cancelled = true; };
  }, [stageId]);

  useEffect(() => {
    if (!nodes.length || !svgRef.current) return;
    const sim = d3
      .forceSimulation<SimNode>(nodes)
      .force('charge', d3.forceManyBody().strength(-360))
      .force('link', d3.forceLink<SimNode, SimLink>(links).id((d) => d.id).distance(110))
      .force('center', d3.forceCenter(430, 270))
      .force('collide', d3.forceCollide<SimNode>().radius(22))
      .force('x', d3.forceX(430).strength(0.05))
      .force('y', d3.forceY(270).strength(0.08));
    simRef.current = sim;
    sim.on('tick', () => {
      setNodes([...nodes]);
      setLinks([...links]);
    });
    const drag = d3
      .drag<SVGCircleElement, SimNode>()
      .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; });
    d3.select(svgRef.current).selectAll<SVGCircleElement, SimNode>('circle.node').call(drag);
    return () => { sim.stop(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subgraph]);

  const nodeById = useMemo(() => {
    const m = new Map<string, SimNode>();
    nodes.forEach((n) => m.set(n.id, n));
    return m;
  }, [nodes]);

  const selNode = selected ? nodeById.get(selected) ?? null : null;
  const neighbors = useMemo(() => {
    if (!selNode || !subgraph) return [] as { edge: SimLink; other: SimNode | undefined }[];
    return subgraph.edges
      .filter((e) => e.source === selNode.id || e.target === selNode.id)
      .map((e) => {
        const otherId = e.source === selNode.id ? e.target : e.source;
        return {
          edge: links.find((l) => asId(l.source) === e.source && asId(l.target) === e.target) ?? {
            source: e.source, target: e.target, relation: e.relation, evidence: e.evidence,
            score: e.score, support: e.support, count: e.count,
          },
          other: nodeById.get(otherId),
        };
      });
  }, [selNode, subgraph, links, nodeById]);

  const stats = useMemo(() => {
    const c: Record<NodeKind, number> = { operator: 0, enemy: 0, stage: 0, skill: 0 };
    nodes.forEach((n) => { c[n.type]++; });
    return c;
  }, [nodes]);

  const locate = () => {
    if (!query.trim() || !simRef.current) return;
    const q = query.trim().toLowerCase();
    const target = nodes.find((n) => n.label.toLowerCase().includes(q) && n.type !== 'skill');
    if (!target) return;
    setSelected(target.id);
    const ids = new Set<string>([target.id]);
    links.forEach((l) => {
      const s = asId(l.source);
      const t = asId(l.target);
      if (s === target.id || t === target.id) { ids.add(s); ids.add(t); }
    });
    setHighlight(ids);
    simRef.current.alpha(0.4).restart();
  };

  const dim = (id: string) => highlight !== null && !highlight.has(id);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">关卡知识子图</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            数据来自 <code className="rounded bg-secondary px-1 font-mono-num text-xs">/api/graph/subgraph</code> 与{' '}
            <code className="rounded bg-secondary px-1 font-mono-num text-xs">/api/recommend</code>；前端不再本地建图。
            实线 fact，虚线 inferred。
          </p>
        </div>
        {stats && (
          <div className="flex gap-3 text-xs">
            {(Object.keys(stats) as NodeKind[]).filter((t) => stats[t] > 0).map((t) => (
              <span key={t} className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: NODE_COLORS[t] }} />
                {TYPE_LABEL[t]} <span className="font-mono-num">{stats[t]}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {stages.map((s) => (
          <button
            key={s.stage_id}
            onClick={() => setStageId(s.stage_id)}
            className={`rounded-full border px-3 py-1 text-sm transition-colors ${
              stageId === s.stage_id
                ? 'border-primary/60 bg-primary/15 text-primary'
                : 'border-border text-muted-foreground hover:text-foreground'
            }`}
          >
            {s.title}
          </button>
        ))}
      </div>

      <div className="flex gap-2">
        <div className="relative w-72">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && locate()}
            placeholder="在本关节点中定位，如：碎骨 / 阿米娅"
            className="pl-9"
          />
        </div>
        <button onClick={locate} className="rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:opacity-90">
          定位
        </button>
        {highlight && (
          <button onClick={() => { setHighlight(null); setSelected(null); }} className="rounded-md border border-border px-3 text-sm text-muted-foreground hover:text-foreground">
            清除高亮
          </button>
        )}
      </div>

      {notFound && (
        <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
          关卡「{stageId}」无子图数据（mock 仅含 {stages.map((s) => s.stage_id).join(' / ')}；真实模式请先 build_graph）。
        </CardContent></Card>
      )}

      {subgraph && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardContent className="p-0">
              <svg ref={svgRef} viewBox="0 0 860 540" className="h-[540px] w-full rounded-md">
                <defs>
                  <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto">
                    <path d="M0,0 L8,4 L0,8 z" fill="hsl(224 10% 40%)" />
                  </marker>
                </defs>
                {links.map((l, i) => {
                  const s = asId(l.source);
                  const t = asId(l.target);
                  const faded = dim(s) || dim(t);
                  const isSel = selected && (s === selected || t === selected);
                  return (
                    <path
                      key={i}
                      d={`M${(l.source as SimNode).x ?? 0},${(l.source as SimNode).y ?? 0} L${(l.target as SimNode).x ?? 0},${(l.target as SimNode).y ?? 0}`}
                      fill="none"
                      stroke={isSel ? 'hsl(18 100% 58% / 0.7)' : 'hsl(224 10% 32%)'}
                      strokeWidth={isSel ? 1.6 : l.relation === 'RECOMMENDS' ? 1 : 0.7}
                      strokeDasharray={l.evidence === 'inferred' ? '4 3' : undefined}
                      opacity={faded ? 0.08 : isSel ? 1 : highlight ? 0.15 : 0.55}
                      markerEnd="url(#arrow)"
                    />
                  );
                })}
                {nodes.map((n) => (
                  <g key={n.id} opacity={dim(n.id) ? 0.15 : 1} className="cursor-pointer"
                     onClick={() => setSelected(n.id === selected ? null : n.id)}>
                    <circle
                      className="node"
                      cx={n.x} cy={n.y}
                      r={selected === n.id ? 12 : n.type === 'stage' ? 11 : 9}
                      fill={NODE_COLORS[n.type]}
                      stroke={selected === n.id ? '#fff' : 'hsl(224 32% 6%)'}
                      strokeWidth={selected === n.id ? 2 : 1.2}
                    />
                    <text x={n.x} y={(n.y ?? 0) - 13} textAnchor="middle" fontSize={10}
                          fill={selected === n.id ? 'hsl(18 100% 65%)' : 'hsl(40 20% 80%)'}>
                      {n.label.length > 8 ? n.label.slice(0, 8) + '…' : n.label}
                    </text>
                  </g>
                ))}
              </svg>
            </CardContent>
          </Card>

          <div className="space-y-4">
            {/* 推荐干员（inferred） */}
            <Card>
              <CardContent className="pt-4">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-bold">{subgraph.stage_title} 推荐干员</span>
                  <Badge variant="outline" className="border-amber-500/30 text-amber-400">inferred</Badge>
                </div>
                <div className="max-h-52 space-y-1.5 overflow-y-auto pr-1">
                  {(recommend?.operators ?? []).map((o) => (
                    <div key={o.operator} className="rounded border border-border px-2.5 py-1.5 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full" style={{ background: NODE_COLORS.operator }} />
                        <span className="font-medium">{o.operator}</span>
                        <span className="text-muted-foreground">{o.class}</span>
                        <span className="ml-auto font-mono-num text-primary">score {o.score.toFixed(1)}</span>
                      </div>
                      <div className="mt-1 text-muted-foreground">
                        克制 {o.matched_enemies.join('、')}（{o.matched_rules.join('、')}，support {o.support}）
                      </div>
                    </div>
                  ))}
                  {(!recommend || recommend.operators.length === 0) && (
                    <p className="text-xs text-muted-foreground">无推荐干员（规则不无中生有）</p>
                  )}
                </div>
                {recommend?.note && (
                  <p className="mt-2 rounded border border-amber-500/20 bg-amber-500/5 px-2 py-1.5 text-[11px] leading-relaxed text-muted-foreground">
                    {recommend.note}
                  </p>
                )}
              </CardContent>
            </Card>

            {/* 选中节点详情与邻居 */}
            <Card>
              <CardContent className="pt-4">
                {!selNode ? (
                  <div className="flex h-40 flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
                    <Crosshair className="h-6 w-6 opacity-50" />
                    点击图中节点查看详情与邻居
                    <span className="text-xs">拖拽节点可调整布局</span>
                  </div>
                ) : (
                  <div className="space-y-3 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="h-3 w-3 rounded-full" style={{ background: NODE_COLORS[selNode.type] }} />
                      <span className="text-base font-bold">{selNode.label}</span>
                      <Badge variant="outline" className="border-border text-muted-foreground">{TYPE_LABEL[selNode.type]}</Badge>
                    </div>
                    {selNode.sub && <p className="text-xs text-muted-foreground">{selNode.sub}</p>}
                    <Separator />
                    <div>
                      <div className="mb-1.5 text-xs font-medium text-muted-foreground">关联（{neighbors.length} 条边）</div>
                      <div className="max-h-64 space-y-1.5 overflow-y-auto pr-1">
                        {neighbors.map(({ edge, other }, i) => {
                          const otherId = edge.source === selNode.id ? asId(edge.target) : asId(edge.source);
                          const label = other?.label ?? otherId.split(':')[1];
                          const meta = edge.relation === 'RECOMMENDS'
                            ? `score ${edge.score?.toFixed?.(1) ?? edge.score} · support ${edge.support ?? 0}`
                            : edge.relation === 'CONTAINS_ENEMY'
                              ? `×${edge.count ?? ''}`
                              : '';
                          return (
                            <button key={i} onClick={() => other && setSelected(other.id)}
                                    className="block w-full rounded border border-border px-2.5 py-1.5 text-left hover:border-primary/50">
                              <div className="flex items-center gap-1.5 text-xs">
                                <span className="h-2 w-2 rounded-full" style={{ background: other ? NODE_COLORS[other.type] : '#888' }} />
                                <span className="font-medium">{label}</span>
                                <span className="text-muted-foreground">
                                  {edge.source === selNode.id ? '' : '← '}{REL_LABEL[edge.relation]}{edge.source === selNode.id ? ' →' : ''}
                                </span>
                                <Badge variant="outline" className={`ml-auto ${edge.evidence === 'fact' ? 'text-emerald-400 border-emerald-500/30' : 'text-amber-400 border-amber-500/30'}`}>
                                  {edge.evidence}
                                </Badge>
                              </div>
                              {meta && <div className="mt-1 font-mono-num text-[11px] text-muted-foreground">{meta}</div>}
                            </button>
                          );
                        })}
                        {!neighbors.length && <p className="text-xs text-muted-foreground">无关联边</p>}
                      </div>
                    </div>
                    {subgraph.note && (
                      <p className="text-[11px] leading-relaxed text-muted-foreground/80">{subgraph.note}</p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

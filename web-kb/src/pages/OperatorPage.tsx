import { useEffect, useMemo, useState } from 'react';
import { Search, Star } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { getNodeDetail, getOperatorDetail, loadCatalog } from '@/api/client';
import type { NodeDetailResponse, NodeNeighbor, OperatorDetail } from '@/types/kb';

export default function OperatorPage() {
  const [name, setName] = useState('');
  const [op, setOp] = useState<OperatorDetail | null>(null);
  const [node, setNode] = useState<NodeDetailResponse | null>(null);
  const [allNames, setAllNames] = useState<string[]>([]);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadCatalog().then((cat) => {
      const names = cat.operators.map((o) => o.name).filter((n): n is string => !!n);
      setAllNames(names);
    });
    load('阿米娅');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = async (n: string) => {
    if (!n.trim()) return;
    setLoading(true);
    setNotFound(false);
    const detail = await getOperatorDetail(n.trim());
    setOp(detail);
    setNode(detail ? await getNodeDetail(`operator:${detail.name}`) : null);
    setName(n.trim());
    setNotFound(!detail);
    setLoading(false);
  };

  const related = useMemo(() => {
    const counters: NodeNeighbor[] = [];
    const stages: NodeNeighbor[] = [];
    for (const nb of node?.neighbors ?? []) {
      if (nb.direction === 'out' && nb.relation === 'COUNTERS') counters.push(nb);
      if (nb.direction === 'in' && nb.relation === 'RECOMMENDS') stages.push(nb);
    }
    return { counters, stages };
  }, [node]);

  const stars = op?.star_rating ?? 0;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold">干员详情</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          输入干员名查看完整档案（<code className="rounded bg-secondary px-1 font-mono-num text-xs">GET /api/operator/&#123;name&#125;</code>），
          右侧克制敌人 / 推荐关卡来自 <code className="rounded bg-secondary px-1 font-mono-num text-xs">/api/graph/node</code>（inferred）。
        </p>
      </div>

      <form
        className="flex gap-2"
        onSubmit={(e) => { e.preventDefault(); load(name); }}
      >
        <div className="relative w-80">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="干员名，如：阿米娅 / 能天使" className="pl-9" list="op-names" />
          <datalist id="op-names">
            {allNames.map((n) => <option key={n} value={n} />)}
          </datalist>
        </div>
        <Button type="submit" disabled={loading}>{loading ? '加载中…' : '查询'}</Button>
        <div className="flex flex-wrap items-center gap-1">
          {allNames.slice(0, 8).map((n) => (
            <button key={n} type="button" onClick={() => load(n)}
                    className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground hover:border-primary/50 hover:text-primary">
              {n}
            </button>
          ))}
          {allNames.length > 8 && <span className="text-xs text-muted-foreground">等 {allNames.length} 名</span>}
        </div>
      </form>

      {notFound && <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">未找到干员「{name}」</CardContent></Card>}

      {op && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            {/* Meta */}
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center gap-3">
                  <CardTitle className="text-lg">{op.display_name || op.name}</CardTitle>
                  <span className="text-sm text-muted-foreground">{op.name}</span>
                  <span className="ml-auto flex items-center gap-0.5">
                    {Array.from({ length: Math.min(stars, 6) }).map((_, i) => (
                      <Star key={i} className="h-4 w-4 fill-primary text-primary" />
                    ))}
                  </span>
                </div>
              </CardHeader>
              <CardContent className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
                {[
                  ['职业', op.class], ['分支', op.branch], ['势力', op.faction],
                  ['位置', op.position], ['标签', op.tags.join(' / ')],
                  ['部署费用', op.deploy_cost],
                ].map(([k, v]) => (
                  <div key={k as string}>
                    <div className="text-xs text-muted-foreground">{k}</div>
                    <div className="mt-0.5">{v || '-'}</div>
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* 特性 */}
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">特性</CardTitle></CardHeader>
              <CardContent className="text-sm">
                {op.trait ? (
                  <>
                    <div className="mb-2 flex flex-wrap gap-1.5">
                      {op.trait.branch && <Badge variant="outline" className="border-primary/40 text-primary">{op.trait.branch}</Badge>}
                    </div>
                    <p className="text-muted-foreground">{op.trait.desc || '-'}</p>
                    {op.trait.branch_info && (
                      <p className="mt-1 text-xs text-muted-foreground/80">{op.trait.branch_info}</p>
                    )}
                  </>
                ) : <p className="text-muted-foreground">-</p>}
              </CardContent>
            </Card>

            {/* 基础属性 */}
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">基础属性</CardTitle></CardHeader>
              <CardContent className="grid grid-cols-2 gap-2 text-sm">
                {Object.entries(op.extra_attrs ?? {}).map(([k, v]) => (
                  <div key={k} className="flex justify-between border-b border-border/60 pb-1">
                    <span className="text-muted-foreground">{k}</span>
                    <span className="font-mono-num">{v}</span>
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* 技能 */}
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">技能</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {op.skills.map((s) => {
                  const lv7 = s.levels.find((l) => l.level === '7') ?? s.levels[0];
                  return (
                    <div key={s.name} className="rounded-md border border-border p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{s.name}</span>
                        {s.type && <Badge variant="outline" className="border-teal-500/30 text-teal-400">{s.type}</Badge>}
                        {lv7 && (
                          <span className="ml-auto font-mono-num text-xs text-muted-foreground">
                            初动 {lv7.initial || '-'} · 消耗 {lv7.cost || '-'} · 持续 {lv7.duration || '-'}
                          </span>
                        )}
                      </div>
                      <p className="mt-1.5 text-sm text-muted-foreground">{lv7?.desc || '-'}</p>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          </div>

          {/* 关联：来自 /api/graph/node（克制关系恒为 inferred） */}
          <div className="space-y-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">克制敌人 <span className="font-mono-num text-muted-foreground">({related.counters.length})</span></CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {related.counters.map((c) => (
                  <div key={c.node_id} className="rounded-md border border-red-500/20 bg-red-500/5 px-2.5 py-2 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-red-400">{c.name}</span>
                      <Badge variant="outline" className="ml-auto border-amber-500/30 text-amber-400">inferred</Badge>
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{c.relation} · 规则推断，非 PRTS 官方结论</div>
                  </div>
                ))}
                {!related.counters.length && <p className="text-xs text-muted-foreground">无克制关系（规则不无中生有）</p>}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">推荐关卡 <span className="font-mono-num text-muted-foreground">({related.stages.length})</span></CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {related.stages.map((s) => (
                  <div key={s.node_id} className="flex items-center justify-between rounded-md border border-orange-500/20 bg-orange-500/5 px-2.5 py-2 text-sm">
                    <span className="text-orange-300">{s.name}</span>
                    <Badge variant="outline" className="border-amber-500/30 text-amber-400">inferred</Badge>
                  </div>
                ))}
                {!related.stages.length && <p className="text-xs text-muted-foreground">暂无推荐关卡</p>}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
      <Separator className="opacity-0" />
    </div>
  );
}

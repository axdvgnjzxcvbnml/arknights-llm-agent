import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';
import { Search, FileJson } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { searchRag, TYPE_LABEL } from '@/api/client';
import type { DocType, EvidenceLevel, RagHit } from '@/types/kb';

const TYPE_STYLES: Record<DocType, string> = {
  operator: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
  enemy: 'bg-red-500/15 text-red-400 border-red-500/30',
  stage: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  guide: 'bg-teal-500/15 text-teal-400 border-teal-500/30',
};

const EVIDENCE_STYLE: Record<EvidenceLevel, { cls: string; label: string }> = {
  fact: { cls: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400', label: 'fact 事实' },
  retrieved: { cls: 'border-sky-500/30 bg-sky-500/10 text-sky-400', label: 'retrieved 参考' },
  inferred: { cls: 'border-amber-500/30 bg-amber-500/10 text-amber-400', label: 'inferred 推断' },
};

const FILTERS: { value: DocType | 'all'; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'operator', label: '干员' },
  { value: 'enemy', label: '敌人' },
  { value: 'stage', label: '关卡' },
  { value: 'guide', label: '攻略' },
];

const SUGGESTIONS = ['高防御敌人怎么打', '碎骨', '回费先锋', '4-7 攻略', '减速控制'];

export default function RagPage() {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<DocType | 'all'>('all');
  const [k, setK] = useState(8);
  const [result, setResult] = useState<{ hits: RagHit[]; note: string } | null>(null);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState('');
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const q = searchParams.get('q');
    if (q) { setQuery(q); run(q, 'all', 8); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = async (q: string, f: DocType | 'all', topK: number) => {
    if (!q.trim()) return;
    setSearching(true);
    setSearched(q);
    try {
      const resp = await searchRag(q, topK, f === 'all' ? null : f);
      setResult({ hits: resp.hits, note: resp.note });
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold">RAG 检索</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          对知识库分片做 Top-K 相似度检索（<code className="rounded bg-secondary px-1 font-mono-num text-xs">GET /api/search</code>）。
          score 为 1 - cosine 距离（0~1）；命中一律 <code className="font-mono-num text-xs">retrieved</code>，是参考资料而非事实判断。
        </p>
      </div>

      <Card>
        <CardContent className="pt-5">
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              run(query, filter, k);
            }}
          >
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="输入检索词，如：高防御敌人怎么打 / 碎骨 / 回费先锋…"
                className="pl-9"
              />
            </div>
            <select
              value={k}
              onChange={(e) => setK(Number(e.target.value))}
              className="rounded-md border border-input bg-secondary px-2 text-sm"
              title="Top-K"
            >
              {[5, 8, 10, 15].map((v) => (
                <option key={v} value={v}>Top {v}</option>
              ))}
            </select>
            <Button type="submit" disabled={searching || !query.trim()}>
              {searching ? '检索中…' : '检索'}
            </Button>
          </form>

          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">类型过滤：</span>
            {FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => { setFilter(f.value); if (searched) run(searched, f.value, k); }}
                className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
                  filter === f.value
                    ? 'border-primary/60 bg-primary/15 text-primary'
                    : 'border-border text-muted-foreground hover:text-foreground'
                }`}
              >
                {f.label}
              </button>
            ))}
            <span className="mx-2 text-xs text-muted-foreground">试试：</span>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => { setQuery(s); run(s, filter, k); }}
                className="text-xs text-muted-foreground underline decoration-dotted underline-offset-4 hover:text-primary"
              >
                {s}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {result && (
        <div className="space-y-3">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              “{searched}” 命中 <span className="font-mono-num text-primary">{result.hits.length}</span> 条
            </span>
            <span className="font-mono-num text-xs">score = 1 - cosine_distance</span>
          </div>
          {result.hits.length === 0 ? (
            <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">无匹配结果，换个检索词试试</CardContent></Card>
          ) : (
            result.hits.map((r, i) => {
              const ev = EVIDENCE_STYLE[r.evidence ?? 'retrieved'];
              return (
                <Card key={i} className="overflow-hidden">
                  <CardContent className="pt-4">
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="font-mono-num text-muted-foreground">#{i + 1}</span>
                      <Badge variant="outline" className={TYPE_STYLES[r.type]}>
                        {TYPE_LABEL[r.type]}
                      </Badge>
                      <Badge variant="outline" className={ev.cls}>
                        evidence: {ev.label}
                      </Badge>
                      {r.section && (
                        <span className="rounded bg-secondary px-1.5 py-0.5 text-muted-foreground">{r.section}</span>
                      )}
                      <span className="ml-auto font-mono-num text-sm font-semibold text-primary">
                        {(r.score * 100).toFixed(1)}%
                      </span>
                    </div>
                    <p className="mt-2.5 text-sm leading-relaxed">{r.content}</p>
                    <Separator className="my-2.5" />
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <FileJson className="h-3.5 w-3.5" />
                      <span className="font-mono-num">{r.source}</span>
                      {r.url && (
                        <a href={r.url} target="_blank" rel="noreferrer" className="ml-auto hover:text-primary hover:underline">
                          PRTS 来源页面 ↗
                        </a>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })
          )}
          {result.hits.length > 0 && (
            <p className="rounded-md border border-sky-500/20 bg-sky-500/5 px-3 py-2 text-xs text-muted-foreground">
              {result.note}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

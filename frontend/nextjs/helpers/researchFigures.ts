/** Only resolve figures explicitly registered on the current research run. */
export function resolveResearchFigure(src: string, artifacts: Record<string, string>): string | null {
  const match = /^figures\/([a-z][a-z0-9-]{0,40})\.png$/.exec(src);
  if (!match) return null;
  const path = artifacts[`chart_${match[1]}`];
  return path && /^outputs\/review_[a-f0-9]{32}\/figures\/[a-z][a-z0-9-]{0,40}\.png$/.test(path)
    && path.endsWith(`/${match[1]}.png`) ? path : null;
}

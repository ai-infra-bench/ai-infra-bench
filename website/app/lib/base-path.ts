export const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? '';
const isStaticExport = process.env.NEXT_PUBLIC_STATIC_EXPORT === 'true';

export function withBasePath(value: string) {
  if (!basePath || !value.startsWith('/') || value === basePath || value.startsWith(`${basePath}/`)) {
    return value;
  }
  return `${basePath}${value}`;
}

export function withRouteBasePath(value: string) {
  const hashIndex = value.indexOf('#');
  const path = hashIndex === -1 ? value : value.slice(0, hashIndex);
  const hash = hashIndex === -1 ? '' : value.slice(hashIndex);
  const staticPath = isStaticExport && (/^\/tasks\/[^/]+$/.test(path) || path === '/tasks' || path === '/leaderboard') ? `${path}.html` : path;
  return withBasePath(`${staticPath}${hash}`);
}

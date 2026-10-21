// The local server uses live API routes. GitHub Pages reads the published,
// precomputed JSON snapshot; no CLIDATA credentials or raw cache reach visitors.
export function apiUrl(path) {
  if (!window.WEATHER_STATIC_SNAPSHOT) return path;
  const request = new URL(path, window.location.origin);
  const route = request.pathname;
  const params = request.searchParams;
  let file;
  if (route === '/api/status') file = 'status.json';
  else if (route === '/api/forecast') file = `forecast/${params.get('date')}.json`;
  else if (route === '/api/month') file = `month/${params.get('month')}.json`;
  else if (route === '/api/october-analogues')
    file = `october/${params.get('period')}/${params.get('method') || 'temperature'}.json`;
  else if (route === '/api/precipitation/forecast')
    file = `precipitation/forecast/${params.get('date')}.json`;
  else if (route === '/api/precipitation/october')
    file = `precipitation/october/${params.get('period')}/${params.get('method') || 'amount'}.json`;
  else throw new Error('Šis pieprasījums nav pieejams publicētajā izgriezumā.');
  return new URL(`./api/${file}`, document.baseURI).href;
}

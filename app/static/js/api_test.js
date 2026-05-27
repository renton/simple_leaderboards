(function () {
  const inputs = ['param-game','param-range','param-sort','param-seed','param-name','param-page-size','param-page'];

  function buildUrl() {
    const game     = document.getElementById('param-game').value;
    const range    = document.getElementById('param-range').value;
    const sort     = document.getElementById('param-sort').value;
    const seed     = document.getElementById('param-seed').value.trim();
    const name     = document.getElementById('param-name').value.trim();
    const pageSize = document.getElementById('param-page-size').value;
    const page     = document.getElementById('param-page').value;

    const params = new URLSearchParams({ game, range, sort, page_size: pageSize, page });
    if (seed) params.set('seed', seed);
    if (name) params.set('name', name);

    return '/api/v1/leaderboards?' + params.toString();
  }

  function updateUrl() {
    document.getElementById('request-url').textContent = buildUrl();
  }

  inputs.forEach(function (id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('input', updateUrl);
    el.addEventListener('change', updateUrl);
  });

  updateUrl();

  function syntaxHighlight(json) {
    json = json.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    return json.replace(
      /("(\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
      function (match) {
        if (/^"/.test(match)) {
          return /:$/.test(match)
            ? '<span class="json-key">' + match + '</span>'
            : '<span class="json-string">' + match + '</span>';
        }
        if (/true|false/.test(match)) return '<span class="json-bool">' + match + '</span>';
        if (/null/.test(match))       return '<span class="json-null">' + match + '</span>';
        return '<span class="json-number">' + match + '</span>';
      }
    );
  }

  document.getElementById('send-btn').addEventListener('click', async function () {
    const url = buildUrl();
    const btn = this;
    btn.disabled = true;
    btn.textContent = 'Sending…';

    const card  = document.getElementById('response-card');
    const body  = document.getElementById('response-body');
    const badge = document.getElementById('status-badge');

    card.style.display = 'block';
    body.innerHTML = '<span class="muted">Loading…</span>';
    badge.textContent = '';
    badge.className = 'status-badge';

    try {
      const resp = await fetch(url, { headers: { 'Accept': 'application/json' } });
      const text = await resp.text();

      try {
        const pretty = JSON.stringify(JSON.parse(text), null, 2);
        body.innerHTML = syntaxHighlight(pretty);
      } catch (_) {
        body.textContent = text;
      }

      if (resp.ok) {
        badge.textContent = resp.status + ' OK';
        badge.className = 'status-badge status-ok';
      } else {
        badge.textContent = resp.status + ' ' + resp.statusText;
        badge.className = 'status-badge status-err';
      }
    } catch (err) {
      body.textContent = 'Request failed: ' + err.message;
      badge.textContent = 'Error';
      badge.className = 'status-badge status-err';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Send Request';
    }
  });

  document.getElementById('clear-btn').addEventListener('click', function () {
    document.getElementById('response-card').style.display = 'none';
  });
})();

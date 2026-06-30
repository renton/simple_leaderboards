(function () {
  const inputs = [
    'param-endpoint','param-game','param-range','param-sort','param-seed',
    'param-name','param-since','param-until','param-page-size','param-page'
  ];

  function val(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  }

  function currentEndpoint() {
    return document.getElementById('param-endpoint').value;
  }

  function toggleEndpointFields() {
    const ep = currentEndpoint();
    document.querySelectorAll('.endpoint-leaderboards').forEach(function (el) {
      el.style.display = ep === 'leaderboards' ? '' : 'none';
    });
    document.querySelectorAll('.endpoint-champions').forEach(function (el) {
      el.style.display = ep === 'champions' ? '' : 'none';
    });
  }

  function buildUrl() {
    const ep       = currentEndpoint();
    const game     = val('param-game');
    const pageSize = val('param-page-size');
    const page     = val('param-page');

    if (ep === 'champions') {
      const since = val('param-since');
      const until = val('param-until');
      const params = new URLSearchParams({ game, page_size: pageSize, page });
      if (since) params.set('since', since);
      if (until) params.set('until', until);
      return '/api/v1/champions?' + params.toString();
    }

    const range = val('param-range');
    const sort  = val('param-sort');
    const seed  = val('param-seed');
    const name  = val('param-name');
    const params = new URLSearchParams({ game, range, sort, page_size: pageSize, page });
    if (seed) params.set('seed', seed);
    if (name) params.set('name', name);
    return '/api/v1/leaderboards?' + params.toString();
  }

  function updateUrl() {
    document.getElementById('request-url').textContent = buildUrl();
  }

  function loadSeeds(slug) {
    var select = document.getElementById('param-seed');
    select.innerHTML = '<option value="">— normal play —</option>';
    if (!slug) { updateUrl(); return; }
    fetch('/admin/api/seeds?game=' + encodeURIComponent(slug), {
      headers: { 'Accept': 'application/json' }
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        (data.seeds || []).forEach(function (s) {
          var opt = document.createElement('option');
          opt.value = s;
          opt.textContent = s;
          select.appendChild(opt);
        });
        updateUrl();
      });
  }

  inputs.forEach(function (id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('input', updateUrl);
    el.addEventListener('change', updateUrl);
  });

  document.getElementById('param-endpoint').addEventListener('change', toggleEndpointFields);

  document.getElementById('param-game').addEventListener('change', function () {
    loadSeeds(this.value);
  });

  toggleEndpointFields();
  loadSeeds(val('param-game'));

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

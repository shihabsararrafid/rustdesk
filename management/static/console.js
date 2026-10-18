'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const state = {token: '', me: null, view: 'Clients', offset: 0, limit: 25, generation: 0};
  const policyNames = {
    allow_remote_control: 'Remote control', allow_file_transfer: 'File transfer',
    allow_clipboard: 'Clipboard', allow_tcp_tunnel: 'TCP tunnel / RDP',
    allow_terminal: 'Terminal', allow_camera: 'Camera'
  };
  const node = (tag, text, cls) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = String(text ?? '');
    if (cls) element.className = cls;
    return element;
  };
  const icons = () => { if (window.lucide) window.lucide.createIcons(); };
  function button(text, action, icon, cls = '') {
    const element = node('button', icon ? undefined : text, icon ? `icon ${cls}` : cls);
    element.type = 'button';
    element.title = text;
    element.setAttribute('aria-label', text);
    if (icon) { const i = node('i'); i.setAttribute('data-lucide', icon); element.append(i); }
    element.addEventListener('click', () => Promise.resolve().then(action).catch(error));
    return element;
  }
  function error(err) { $('message').textContent = err.message || 'Request failed'; }
  function signout() {
    state.generation++;
    state.token = ''; state.me = null;
    $('login-panel').hidden = false; $('workspace').hidden = true;
    $('content').replaceChildren(); $('identity').replaceChildren();
    $('login-form').reset(); $('editor').close();
  }
  async function api(path, options = {}) {
    const headers = {Authorization: `Bearer ${state.token}`, ...options.headers};
    if (options.json !== undefined) {
      headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(options.json);
    }
    const response = await fetch(path, {...options, headers, signal: options.signal || AbortSignal.timeout(15000)});
    if (response.status === 401) { signout(); throw new Error('Your session expired. Sign in again.'); }
    if (!response.ok) {
      let message = `Request failed (${response.status})`;
      try { message = (await response.json()).error || message; } catch (_) { /* Non-JSON proxy error. */ }
      throw new Error(message);
    }
    return response;
  }
  const json = async (path, options) => (await api(path, options)).json();
  $('login-form').addEventListener('submit', async (event) => {
    event.preventDefault(); $('message').textContent = '';
    const submit = event.submitter; submit.disabled = true;
    const form = new FormData(event.target);
    try {
      const response = await fetch('/api/login', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: form.get('username'), password: form.get('password')}), signal: AbortSignal.timeout(15000)});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Sign in failed');
      state.token = result.access_token;
      state.me = await json('/api/management/me');
      $('login-form').reset(); $('login-panel').hidden = true; $('workspace').hidden = false;
      $('identity').textContent = `${state.me.user.name} · ${state.me.role}`;
      const views = state.me.role === 'admin' ? ['Clients', 'Sessions', 'Employees', 'Policies'] : ['Clients', 'Sessions'];
      $('navigation').replaceChildren(...views.map(view => button(view, () => select(view))));
      await select('Clients');
    } catch (err) { error(err); } finally { submit.disabled = false; }
  });
  $('logout').addEventListener('click', async () => {
    try { await api('/api/logout', {method: 'POST'}); } catch (err) { error(err); } finally { signout(); }
  });
  function field(name, title, value = '', type = 'text', required = true) {
    const label = node('label', title); const input = node(type === 'textarea' ? 'textarea' : 'input');
    input.name = name; if (type !== 'textarea') input.type = type;
    input.value = value; input.required = required; label.append(input); return label;
  }
  let saveEditor;
  function edit(title, fields, save) {
    $('editor-title').textContent = title; $('editor-error').textContent = '';
    $('editor-fields').replaceChildren(...fields); saveEditor = save; $('editor').showModal();
  }
  $('close-dialog').addEventListener('click', () => $('editor').close());
  $('editor').addEventListener('close', () => { $('editor-fields').replaceChildren(); saveEditor = null; });
  $('editor-form').addEventListener('submit', async event => {
    event.preventDefault(); event.submitter.disabled = true;
    try { await saveEditor(Object.fromEntries(new FormData(event.target))); $('editor').close(); await load(); }
    catch (err) { $('editor-error').textContent = err.message; }
    finally { event.submitter.disabled = false; }
  });
  async function select(view) {
    state.view = view; state.offset = 0; $('filters').replaceChildren(); $('heading').textContent = view;
    for (const b of $('navigation').children) b.setAttribute('aria-current', b.textContent === view ? 'page' : 'false');
    $('scope-note').textContent = view === 'Sessions' ? 'Employee-app-reported sessions. Connections through other applications are not included.'
      : view === 'Policies' ? 'Restrictions apply to managed employee builds, not unchanged customer clients.'
      : view === 'Clients' ? 'Shared company directory. Online presence is not verified.' : '';
    if (view === 'Sessions') {
      for (const [name, title, type] of [['employee_id', 'Employee UUID', 'text'], ['client_id', 'Client UUID', 'text'], ['since', 'From', 'datetime-local'], ['until', 'Until', 'datetime-local']]) {
        if (name === 'employee_id' && state.me.role !== 'admin') continue;
        $('filters').append(field(name, title, '', type, false));
      }
      $('filters').append(button('Apply filters', () => { state.offset = 0; return load(); }));
    }
    $('filters').onsubmit = event => { event.preventDefault(); state.offset = 0; load().catch(error); };
    await load();
  }
  const date = stamp => stamp == null ? 'Unknown' : new Date(stamp * 1000).toLocaleString();
  function badge(value) { return node('span', value, `badge ${['closed', 'authenticated'].includes(value) ? 'good' : ['failed', 'interrupted', 'disabled'].includes(value) ? 'bad' : ''}`); }
  function table(headers, rows) {
    const wrap = node('div', undefined, 'table-wrap'); const t = node('table'); const head = node('tr');
    headers.forEach(label => head.append(node('th', label))); const thead = node('thead'); thead.append(head); t.append(thead);
    const body = node('tbody');
    rows.forEach(values => { const row = node('tr'); values.forEach(value => {
      const cell = node('td'); if (value instanceof Node) cell.append(value); else cell.textContent = String(value ?? ''); row.append(cell);
    }); body.append(row); }); t.append(body); wrap.append(t); return wrap;
  }
  function clientEditor(client) {
    const fields = [['rustdesk_id', 'RustDesk ID'], ['customer_name', 'Customer'], ['device_label', 'Device'], ['notes', 'Notes']]
      .map(([key, label]) => field(key, label, client?.[key] || '', key === 'notes' ? 'textarea' : 'text', key !== 'notes'));
    edit(client ? 'Edit client' : 'Add client', fields, data => json('/api/management/clients' + (client ? '/' + client.id : ''),
      {method: client ? 'PUT' : 'POST', json: data}));
  }
  async function exportCSV() {
    const response = await api('/api/management/clients/export'); const blob = await response.blob();
    const url = URL.createObjectURL(blob), a = node('a'); a.href = url; a.download = 'clients.csv'; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function importCSV() {
    const file = node('input'); file.type = 'file'; file.accept = '.csv,text/csv';
    file.onchange = async () => {
      try {
        const data = file.files[0]; if (!data) return;
        if (data.size > 2097152) throw new Error('CSV must be 2 MiB or smaller');
        if (!confirm('Import this CSV into the shared client directory?')) return;
        const result = await json('/api/management/clients/import', {method: 'POST', body: data,
          headers: {'Content-Type': 'text/csv'}});
        await load(); $('message').textContent = `Imported ${result.imported} clients.`;
      } catch (err) { error(err); }
    }; file.click();
  }
  function employeeEditor() {
    const role = node('label', 'Role'), select = node('select'); select.name = 'role';
    for (const value of ['employee', 'admin']) { const opt = node('option', value); opt.value = value; select.append(opt); } role.append(select);
    const pw = field('password', 'Initial password', '', 'password'); pw.querySelector('input').minLength = 12;
    edit('Add employee', [field('username', 'Username'), pw, role], data => json('/api/management/employees', {method: 'POST', json: data}));
  }
  function actions(...items) { const group = node('div', undefined, 'row-actions'); group.append(...items); return group; }
  async function load() {
    const generation = ++state.generation, view = state.view; $('message').textContent = '';
    $('content').replaceChildren(node('p', 'Loading…', 'loading')); $('pagination').replaceChildren();
    $('commands').replaceChildren(button('Refresh', load, 'refresh-cw'));
    const admin = state.me.role === 'admin';
    try {
      if (view === 'Policies') { await policyView(generation); return; }
      const path = {Clients: 'clients', Employees: 'employees', Sessions: 'reports/sessions'}[view];
      const query = new URLSearchParams({limit: state.limit, offset: state.offset});
      if (view === 'Sessions') for (let [key, value] of new FormData($('filters'))) {
        if (value) query.set(key, ['since', 'until'].includes(key) ? new Date(value).toISOString() : value);
      }
      const data = await json(`/api/management/${path}?${query}`); if (generation !== state.generation) return;
      let headers, rows;
      if (view === 'Clients') {
        if (admin) $('commands').append(button('Export CSV', exportCSV, 'download'), button('Import CSV', importCSV, 'upload'), button('Add client', () => clientEditor(), null, 'primary'));
        headers = ['Customer', 'Device', 'RustDesk ID', 'Presence', 'Notes', 'Client UUID'];
        rows = data.items.map(c => [c.customer_name, c.device_label, c.rustdesk_id, badge(c.presence), c.notes, c.id]);
        if (admin) { headers.push('Actions'); rows.forEach((row, i) => {
          const c = data.items[i]; row.push(actions(button('Edit client', () => clientEditor(c), 'pencil'), button('Delete client', async () => {
            if (confirm(`Delete ${c.customer_name}? Clients with audit history cannot be deleted.`)) { await api(`/api/management/clients/${c.id}`, {method: 'DELETE'}); await load(); }
          }, 'trash-2', 'danger')));
        }); }
      } else if (view === 'Employees') {
        $('commands').append(button('Add employee', employeeEditor, null, 'primary'));
        headers = ['Username', 'Role', 'Status', 'Employee UUID', 'Actions'];
        rows = data.items.map(u => [u.username, u.role, badge(u.disabled ? 'disabled' : 'active'), u.id,
          actions(button(u.disabled ? 'Enable' : 'Disable', async () => {
            if (confirm(`${u.disabled ? 'Enable' : 'Disable'} ${u.username}? Disabling revokes their login sessions.`)) {
              await json(`/api/management/employees/${u.id}`, {method: 'PATCH', json: {disabled: !u.disabled}}); await load();
            }
          }), button('Reset password', () => {
            const input = field('password', 'New password', '', 'password'); input.querySelector('input').minLength = 12;
            edit(`Reset password: ${u.username}`, [input], data => json(`/api/management/employees/${u.id}/password`, {method: 'POST', json: data}));
          }))]);
      } else {
        headers = ['Employee', 'Target', 'Mode', 'Started', 'Ended', 'State', 'Outcome', 'Duration', 'Telemetry'];
        rows = data.items.map(s => [s.employee_name || s.employee_id, s.target_id, s.mode, date(s.started_at), date(s.ended_at), badge(s.state), s.outcome || '—',
          s.duration_seconds == null ? 'Unknown' : `${Math.round(s.duration_seconds)}s`, s.telemetry_gap ? 'Gap detected' : 'No gap reported']);
      }
      $('content').replaceChildren(data.items.length ? table(headers, rows) : node('p', 'No records found.', 'empty'));
      $('pagination').append(node('span', `${data.total} records`));
      const prev = button('Previous page', () => { state.offset = Math.max(0, state.offset - state.limit); return load(); }, 'chevron-left'); prev.disabled = state.offset === 0;
      const next = button('Next page', () => { state.offset += state.limit; return load(); }, 'chevron-right'); next.disabled = state.offset + state.limit >= data.total;
      $('pagination').append(prev, node('span', `Page ${Math.floor(state.offset / state.limit) + 1}`), next); icons();
    } catch (err) { if (generation === state.generation) { $('content').replaceChildren(node('p', 'Unable to load records. Refresh to retry.', 'empty')); error(err); } }
  }
  async function policyView(generation) {
    const policies = await json('/api/management/policies');
    const users = {items: []};
    for (let offset = 0; ; offset += 500) {
      const page = await json(`/api/management/employees?limit=500&offset=${offset}`);
      users.items.push(...page.items);
      if (offset + page.items.length >= page.total || !page.items.length) break;
    }
    if (generation !== state.generation) return;
    const layout = node('div', undefined, 'policy-grid');
    function policyForm(title, values, path, overrides) {
      const form = node('form', undefined, 'policy-block'); form.append(node('h2', title));
      for (const [key, label] of Object.entries(policyNames)) {
        if (overrides) {
          const wrap = node('label', label), select = node('select'); select.name = key; select.setAttribute('aria-label', label);
          for (const [value, name] of [['inherit', 'Company default'], ['true', 'Allow'], ['false', 'Block']]) {
            const opt = node('option', name); opt.value = value; select.append(opt);
          }
          select.value = key in values ? String(values[key]) : 'inherit'; wrap.append(select); form.append(wrap);
        } else {
          const wrap = node('label', label, 'check'), input = node('input'); input.type = 'checkbox'; input.name = key; input.checked = values[key] !== false;
          wrap.prepend(input); form.append(wrap);
        }
      }
      const save = node('button', 'Save policy', 'primary'); save.type = 'submit'; form.append(save);
      form.onsubmit = async event => {
        event.preventDefault(); save.disabled = true;
        try {
          const data = {};
          for (const key of Object.keys(policyNames)) {
            const input = form.elements.namedItem(key);
            if (overrides) { if (input.value !== 'inherit') data[key] = input.value === 'true'; }
            else data[key] = input.checked;
          }
          await json(path, {method: 'PUT', json: data});
          if (overrides) policies.employees[path.split('/').pop()] = data;
          else policies.company = data;
          $('message').textContent = 'Policy saved for new managed connections.';
        } catch (err) { error(err); } finally { save.disabled = false; }
      }; return form;
    }
    layout.append(policyForm('Company defaults', policies.company, '/api/management/policies/company', false));
    const block = node('section', undefined, 'policy-block'), label = node('label', 'Employee override'), select = node('select');
    select.setAttribute('aria-label', 'Employee override');
    for (const user of users.items) { const opt = node('option', user.username); opt.value = user.id; select.append(opt); }
    label.append(select); const holder = node('div');
    const display = () => { holder.replaceChildren(policyForm('Employee policy', policies.employees[select.value] || {}, `/api/management/policies/employees/${select.value}`, true)); };
    select.onchange = display; block.append(label, holder); if (users.items.length) display(); layout.append(block);
    $('content').replaceChildren(layout); icons();
  }
})();

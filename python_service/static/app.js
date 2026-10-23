'use strict';

// Solo presentación: recomendación, conversación y comparación se resuelven en Python.
const base = new URL('./', document.baseURI);
const $ = id => document.getElementById(id);
const money = value => new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP', maximumFractionDigits: 0 }).format(value) + ' CLP';
const history = [];

async function api(path, data) {
  const response = await fetch(new URL('api/' + path, base), data === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : 'Revisa los campos: usa montos positivos y las opciones disponibles.');
  }
  return response.json();
}

function rate(optional = false) {
  const input = $('rate');
  if (optional && !input.value) return null;
  if (!input.reportValidity()) throw new Error('Ingresa un tipo de cambio válido.');
  return input.value;
}

function feedback(id, text, error = false) {
  $(id).textContent = text;
  $(id).classList.toggle('error', error);
}

function element(tag, text, className) {
  const el = document.createElement(tag);
  el.textContent = text;
  if (className) el.className = className;
  return el;
}

document.querySelectorAll('[data-panel]').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('[data-panel]').forEach(tab => tab.setAttribute('aria-pressed', String(tab === button)));
    document.querySelectorAll('.panel').forEach(panel => { panel.hidden = panel.id !== button.dataset.panel; });
  });
});

$('recommend-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.target.querySelector('button[type=submit]');
  button.disabled = true;
  $('recommend-results').replaceChildren();
  try {
    const data = Object.fromEntries(new FormData(event.target));
    data.age = Number(data.age);
    data.budget_clp = Number(data.budget_clp);
    data.rate = rate();
    feedback('recommend-message', 'Buscando afinidades en el modelo…');
    const result = await api('recommendations', data);
    result.items.forEach((perfume, index) => {
      const card = element('article', '', 'perfume-card');
      card.append(element('span', '0' + (index + 1), 'rank'), element('h3', perfume.name),
        element('p', perfume.price_formatted, 'price'), element('small', 'Precio referencial · stock sin confirmar'),
        element('p', 'Puntaje del modelo: ' + perfume.score_percent + '%', 'score'),
        element('span', perfume.within_budget ? 'Dentro de tu presupuesto' : 'Supera tu presupuesto', 'badge' + (perfume.within_budget ? '' : ' over')));
      $('recommend-results').append(card);
    });
    feedback('recommend-message', `Tus sugerencias · Conversión utilizada: ${result.rate} CLP por USD.`);
  } catch (error) { feedback('recommend-message', error.message, true); }
  finally { button.disabled = false; }
});

$('compare-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.target.querySelector('button[type=submit]');
  button.disabled = true;
  $('compare-table').hidden = true;
  $('compare-results').replaceChildren();
  try {
    const data = Object.fromEntries(new FormData(event.target));
    data.budget_clp = Number(data.budget_clp);
    data.rate = rate();
    feedback('compare-message', 'Comparando precios…');
    const result = await api('compare', data);
    result.items.forEach(perfume => {
      const row = document.createElement('tr');
      row.append(element('td', perfume.name), element('td', perfume.price_formatted), element('td', money(perfume.remaining_clp)));
      $('compare-results').append(row);
    });
    $('compare-table').hidden = result.items.length === 0;
    feedback('compare-message', result.items.length ? `Mostrando ${result.items.length} de ${result.total_matches} opciones · ${result.rate} CLP por USD.` : 'No encontramos perfumes con ese nombre y presupuesto. Prueba otro filtro.');
  } catch (error) { feedback('compare-message', error.message, true); }
  finally { button.disabled = false; }
});

function bubble(role, text, sources = []) {
  const item = element('article', '', 'bubble ' + role);
  item.append(element('strong', role === 'user' ? 'Tú' : 'Asesor UPerfumes'), element('p', text));
  if (sources.length) item.append(element('small', 'Fuente: ' + sources.join(' · ')));
  $('chat-log').append(item);
  $('chat-log').scrollTop = $('chat-log').scrollHeight;
}

$('chat-form').addEventListener('submit', async event => {
  event.preventDefault();
  const message = $('chat-message').value.trim();
  if (!message) return;
  const button = event.target.querySelector('button');
  button.disabled = true;
  try {
    const exchange = rate(true);
    bubble('user', message);
    feedback('chat-feedback', 'Consultando la base de conocimiento local…');
    const result = await api('chat', { message, history: history.slice(-8), rate: exchange });
    bubble('assistant', result.answer, result.sources);
    history.push({ role: 'user', content: message }, { role: 'assistant', content: result.answer });
    history.splice(0, Math.max(0, history.length - 8));
    $('chat-message').value = '';
    feedback('chat-feedback', '');
  } catch (error) { feedback('chat-feedback', error.message, true); }
  finally { button.disabled = false; $('chat-message').focus(); }
});

document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => {
  $('chat-message').value = button.dataset.question;
  $('chat-message').focus();
}));

async function initialize() {
  try {
    const [options, health] = await Promise.all([api('options'), api('health')]);
    for (const [id, values] of [['climate', options.climates], ['occasion', options.occasions], ['gender', options.genders]]) {
      values.forEach(value => { const option = element('option', value); option.value = value; $(id).append(option); });
    }
    $('service-status').textContent = health.model_status === 'ready'
      ? `${health.perfume_count} perfumes para descubrir · Asistente local disponible`
      : 'El modelo aún no está disponible. Puedes usar el asistente para consultas generales.';
  } catch (error) { $('service-status').textContent = 'No pudimos conectar con el asesor. Revisa que el servicio esté iniciado.'; }
}
initialize();

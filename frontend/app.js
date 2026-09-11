let graph;
const chatHistory = [];

const graphStyle = [
  { selector: 'node', style: { 'background-color': '#58d3bd', 'label': 'data(label)', 'color': '#e8f0ef', 'font-size': 9, 'text-wrap': 'wrap', 'text-max-width': 86, 'text-valign': 'bottom', 'text-margin-y': 7, 'width': 34, 'height': 34 } },
  { selector: 'edge', style: { 'line-color': '#789695', 'target-arrow-color': '#789695', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'label': 'data(label)', 'font-size': 7, 'color': '#91a8a7', 'text-background-color': '#0b1b1b', 'text-background-opacity': 1, 'text-background-padding': 2 } }
];

function renderGraph(data, fullNetwork = false) {
  const displayLabel = (node) => {
    const properties = node.properties || {};
    if (properties.port_name && properties.country_code) {
      return `${properties.port_name} · ${properties.country_code}`;
    }
    const primary = properties.company_name
      || properties.facility_name
      || properties.product_name
      || properties.shipment_id
      || properties.port_name
      || properties.country_name
      || properties.company_id
      || properties.facility_id
      || properties.product_id
      || properties.port_code
      || properties.country_code
      || node.labels?.[0]
      || 'Entity';
    const secondary = properties.status
      || properties.facility_type
      || properties.product_type
      || properties.company_type
      || properties.region;
    return secondary && !primary.includes(secondary)
      ? `${primary} · ${secondary}`
      : primary;
  };
  const elements = [
    ...(data.nodes || []).map((node) => ({ data: { id: node.id, label: displayLabel(node) } })),
    ...(data.relationships || []).map((relationship) => ({ data: { id: relationship.id, source: relationship.source, target: relationship.target, label: relationship.type } }))
  ];
  document.querySelector('#empty-graph').style.display = elements.length ? 'none' : 'block';
  if (graph) graph.destroy();
  graph = cytoscape({
    container: document.querySelector('#graph'),
    elements,
    style: graphStyle,
    layout: fullNetwork
      ? { name: 'breadthfirst', directed: true, circle: false, spacingFactor: 1.55, avoidOverlap: true, padding: 80 }
      : { name: 'cose', animate: false, padding: 35, idealEdgeLength: 90, nodeRepulsion: 4500, componentSpacing: 40, numIter: 500 },
    minZoom: .2,
    maxZoom: 2.5,
  });
}

function renderRows(rows) {
  const head = document.querySelector('#table-head');
  const body = document.querySelector('#table-body');
  head.innerHTML = '';
  body.innerHTML = '';
  document.querySelector('#row-count').textContent = `${rows.length} row${rows.length === 1 ? '' : 's'}`;
  if (!rows.length) return;
  const columns = Object.keys(rows[0]);
  head.innerHTML = `<tr>${columns.map((column) => `<th>${column}</th>`).join('')}</tr>`;
  body.innerHTML = rows.map((row) => `<tr>${columns.map((column) => `<td>${String(row[column] ?? '')}</td>`).join('')}</tr>`).join('');
}

async function loadFullGraph() {
  const status = document.querySelector('#result-status');
  status.textContent = 'Loading full network';
  try {
    const response = await fetch('/graph/full');
    const payload = await readResponse(response);
    if (!response.ok) throw new Error(payload.detail || 'The full graph could not be loaded.');
    renderGraph(payload, true);
    status.textContent = `${payload.nodes.length} nodes · ${payload.relationships.length} edges`;
  } catch (error) {
    status.textContent = 'Full network unavailable';
    document.querySelector('#empty-graph').textContent = error.message;
  }
}

async function readResponse(response) {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(response.ok ? 'The server returned an invalid response.' : text || 'The request failed.');
  }
}

document.querySelector('#full-graph').addEventListener('click', loadFullGraph);

document.querySelector('#chat-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const input = document.querySelector('#question');
  const question = input.value.trim();
  if (!question) return;
  const conversation = document.querySelector('#conversation');
  conversation.insertAdjacentHTML('beforeend', `<div class="message user">${question}</div><div class="message assistant">Tracing the graph...</div>`);
  input.value = '';
  const pending = conversation.lastElementChild;
  document.querySelector('#result-status').textContent = 'Querying Aura';
  try {
    const response = await fetch('/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, history: chatHistory.slice(-10) }) });
    const payload = await readResponse(response);
    if (!response.ok) throw new Error(payload.detail || 'The query could not be completed.');
    pending.textContent = payload.answer || payload.reason || 'No explanation returned.';
    chatHistory.push({ role: 'user', content: question });
    chatHistory.push({ role: 'assistant', content: payload.answer || payload.reason || '' });
    document.querySelector('#answer').textContent = payload.answer || payload.reason || 'No explanation returned.';
    document.querySelector('#cypher').textContent = payload.cypher || '-- no query generated';
    document.querySelector('#result-status').textContent = payload.status;
    renderRows(payload.rows || []);
    renderGraph(payload.graph || { nodes: [], relationships: [] });
    document.querySelector('#graph').scrollIntoView({ behavior: 'smooth', block: 'center' });
  } catch (error) {
    pending.textContent = error.message;
    document.querySelector('#result-status').textContent = 'Request failed';
  }
});

loadFullGraph();
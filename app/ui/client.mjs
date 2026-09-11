import { streamTurn, cancelTurn } from '/test-client/stream-client.mjs';
import { presets, examples, applyTheme, curatedThemes } from './personalization.mjs';
const $ = id => document.getElementById(id);
let activeTheme = { ...curatedThemes.clean }, draftTheme = { ...activeTheme };
let notes = [], editingNoteId = null, sourceMessageId = null, omittedNotes = new Set();
let token = '', conversationId = null, conversations = [], messages = [];
let busy = false, streaming = false, assistantId = null, controller = null, uncertain = false;
const fields = {
  name: 'Assistant name', preferred_user_name: 'Your preferred name',
  warmth: 'Warmth', verbosity: 'Verbosity', humor: 'Humor', formality: 'Formality',
  primary_language: 'Primary language', language_switching_mode: 'Language mode',
  custom_instructions: 'Custom instructions', preferred_model: 'Model (blank uses server default)',
  morning_greeting_enabled: 'Morning greeting', evening_greeting_enabled: 'Evening greeting',
  good_night_greeting_enabled: 'Good night greeting', holiday_preferences: 'Holiday preferences (JSON)',
};
const sliders = ['warmth', 'verbosity', 'humor', 'formality'];
function notice(text, error = false) { $('settings-notice').textContent = $('settings-dialog').open ? text : ''; $('notice').textContent = text; $('notice').className = error ? 'error' : ''; }
function controls() {
  const locked = busy || streaming;
  for (const id of ['new', 'more', 'save', 'profile-fields', 'disconnect', 'preset', 'shorter', 'detail', 'theme-apply', 'theme-reset', 'theme-generate', 'tone-live', 'memory-save', 'memory-content', 'memory-cancel']) $(id).disabled = !token || locked;
  $('more').disabled ||= conversations.length % 50 !== 0;
  $('refresh').disabled = !conversationId || locked;
  $('send').disabled = $('content').disabled = !conversationId || locked || uncertain;
  $('shorter').disabled = $('detail').disabled = !conversationId || locked || uncertain || !messages.some(m => m.role === 'assistant' && m.status === 'completed');
  $('stop').disabled = !streaming;
  $('token').disabled = locked || !!token;
  $('connection').querySelector('button').disabled = locked || !!token;
  for (const button of $('conversations').children) button.disabled = locked;
  for (const button of document.querySelectorAll('[data-memory-action]')) button.disabled = !token || locked;
}
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } });
  if (!response.ok) {
    let detail; try { detail = (await response.json()).detail; } catch { /* non-JSON server error */ }
    throw new Error(`HTTP ${response.status}: ${typeof detail === 'string' ? detail : JSON.stringify(detail) || response.statusText}`);
  }
  return response.json();
}
async function action(fn) {
  if (busy || streaming) return;
  busy = true; controls();
  try { await fn(); } catch (error) { notice(error.message, true); }
  finally { busy = false; controls(); }
}
function renderMessages() {
  $('messages').replaceChildren();
  if (!messages.length) { const p = document.createElement('p'); p.className = 'empty'; p.textContent = 'No messages yet. Say hello.'; $('messages').append(p); }
  for (const message of messages) {
    const article = document.createElement('article'); article.className = `message ${message.role}`;
    const heading = document.createElement('strong'); heading.textContent = message.role === 'user' ? 'You' : ($('assistant-label').textContent || 'Assistant');
    const content = document.createElement('p'); content.textContent = message.content;
    const status = document.createElement('small'); status.textContent = message.status;
    article.append(heading, content, status);
    if (message.role === 'user') {
      const remember = document.createElement('button'); remember.textContent = 'Remember this'; remember.className = 'remember quiet'; remember.dataset.memoryAction = 'remember'; remember.disabled = busy || streaming;
      remember.onclick = () => { editingNoteId = null; sourceMessageId = message.id; $('memory-content').value = message.content.slice(0, 300); $('memory-save').textContent = 'Save note'; $('memory-status').textContent = message.content.length > 300 ? 'Shorten or edit this excerpt to the exact note you want to save (300 characters max).' : 'Review this note, then save it to use across conversations.'; $('settings-dialog').showModal(); $('memory-section').scrollIntoView(); $('memory-content').focus(); };
      article.append(remember);
    }
    $('messages').append(article);
  }
  $('messages').scrollTop = $('messages').scrollHeight;
}
function upsert(message) {
  const index = messages.findIndex(m => m.id === message.id);
  if (index < 0) messages.push(message); else messages[index] = message;
  renderMessages();
}
function renderConversations() {
  $('conversations').replaceChildren();
  for (const item of conversations) {
    const button = document.createElement('button');
    button.textContent = `${new Date(item.created_at).toLocaleString()} · ${item.id.slice(0, 8)}`;
    button.setAttribute('aria-current', String(item.id === conversationId));
    button.onclick = () => action(async () => {
      conversationId = item.id; omittedNotes.clear(); $('memory-context-status').textContent = ''; messages = []; uncertain = true; renderMessages(); renderConversations();
      $('chat-title').textContent = `Conversation · ${item.id.slice(0, 8)}`; await history();
    });
    $('conversations').append(button);
  }
}
async function list(reset = false) {
  const page = await api(`/conversations?limit=50&offset=${reset ? 0 : conversations.length}`);
  conversations = reset ? page : [...conversations, ...page]; renderConversations();
}
async function history() {
  const saved = []; let position = 0;
  while (true) {
    const page = await api(`/conversations/${conversationId}/messages?limit=100&after_position=${position}`);
    saved.push(...page); if (page.length < 100) break; position = page.at(-1).position;
  }
  messages = saved; uncertain = false; renderMessages();
  notice(messages.some(m => m.status === 'in_progress') ? 'A turn is still in progress. Refresh history to check its saved outcome.' : 'Saved history is up to date.');
}
function renderProfile(profile) {
  $('assistant-label').textContent = profile.name;
  $('profile-fields').replaceChildren();
  for (const [key, title] of Object.entries(fields)) {
    const label = document.createElement('label'); label.textContent = title;
    let input;
    if (key === 'language_switching_mode') {
      input = document.createElement('select');
      for (const value of ['follow_user', 'fixed']) { const option = document.createElement('option'); option.value = value; option.textContent = value; input.append(option); }
    } else if (['custom_instructions', 'holiday_preferences'].includes(key)) {
      input = document.createElement('textarea'); input.rows = 3;
      if (key === 'custom_instructions') input.maxLength = 10000;
    } else {
      input = document.createElement('input'); input.type = key.endsWith('_enabled') ? 'checkbox' : sliders.includes(key) ? 'range' : 'text';
      if (sliders.includes(key)) { input.min = 0; input.max = 1; input.step = .05; }
    }
    input.name = key;
    if (input.type === 'checkbox') input.checked = profile[key];
    else input.value = key === 'holiday_preferences' ? JSON.stringify(profile[key], null, 2) : profile[key] ?? '';
    label.append(input); $('profile-fields').append(label);
  }
}
$('connection').onsubmit = event => { event.preventDefault(); action(async () => {
  token = $('token').value.trim();
  try { renderProfile(await api('/assistant')); activeTheme = await api('/assistant/theme'); draftTheme = { ...activeTheme }; applyTheme(document.documentElement, activeTheme); renderTheme(); await loadNotes(); await list(true); $('token').value = ''; document.querySelector('.connection-panel').open = false; notice('Connected. Select a conversation or create one.'); }
  catch (error) { token = ''; throw error; }
}); };
$('disconnect').onclick = () => {
  token = ''; activeTheme = { ...curatedThemes.clean }; draftTheme = { ...activeTheme }; applyTheme(document.documentElement, activeTheme); renderTheme(); $('assistant-label').textContent = 'Your assistant'; conversationId = null; conversations = []; messages = []; uncertain = false;
  notes = []; omittedNotes.clear(); clearNoteEditor(); renderNotes(); $('memory-context-status').textContent = ''; $('theme-prompt').value = ''; $('tone-example').textContent = 'Choose a style to see a sample response.'; $('tone-status').textContent = ''; $('preset').value = '';
  $('token').value = ''; $('content').value = ''; $('profile-fields').replaceChildren();
  $('chat-title').textContent = 'Start a conversation'; renderConversations(); renderMessages(); controls(); notice('Disconnected. Token cleared.');
};
$('new').onclick = () => action(async () => {
  const item = await api('/conversations', { method: 'POST' });
  conversationId = item.id; omittedNotes.clear(); $('memory-context-status').textContent = ''; messages = []; uncertain = false;
  $('chat-title').textContent = `Conversation · ${item.id.slice(0, 8)}`; renderMessages();
  await list(true); notice('New conversation ready.');
});
$('more').onclick = () => action(() => list());
$('refresh').onclick = () => action(() => history());
$('profile').onsubmit = event => { event.preventDefault(); action(async () => {
  const patch = profilePatch();
  renderProfile(await api('/assistant', { method: 'PATCH', body: JSON.stringify(patch) })); notice('Settings saved. They apply to the next turn.'); $('tone-status').textContent = 'Communication settings saved.';
}); };
$('composer').onsubmit = async event => {
  event.preventDefault(); if ($('send').disabled || !$('content').value.trim()) return;
  const content = $('content').value; streaming = true; assistantId = null; controller = new AbortController(); controls();
  $('turn-status').textContent = 'Generating…'; notice('Streaming response…');
  let failure;
  try {
    const saved = await streamTurn({ conversationId, token, content, signal: controller.signal, onEvent(event) {
      if (event.event === 'turn.started') { omittedNotes = new Set(event.payload.omitted_memory_ids || []); $('memory-context-status').textContent = omittedNotes.size ? `${omittedNotes.size} saved note(s) did not fit this request. See Memory for details.` : ''; renderNotes(); assistantId = event.message_id; $('content').value = ''; upsert(event.payload.user_message); upsert(event.payload.assistant_message); }
      if (event.event === 'message.delta') { const message = messages.find(m => m.id === event.message_id); if (message) { message.content += event.payload.text; renderMessages(); } }
    } });
    upsert(saved);
    if (saved.status === 'failed') failure = 'Generation failed. The saved partial response is shown.';
  } catch (error) { failure = `${error.name === 'AbortError' ? 'Stream stopped.' : error.message} No message was automatically resent.`; }
  finally {
    uncertain = true;
    try { await history(); } catch (error) { failure = `${failure || ''} Could not reconcile saved history: ${error.message}. Refresh history before sending again.`; }
    streaming = false; assistantId = null; controller = null; $('turn-status').textContent = 'Ready'; controls();
    if (failure) notice(failure, true);
  }
};
$('stop').onclick = async () => {
  if (!streaming) return;
  if (!assistantId) { controller?.abort(); return; }
  const activeController = controller;
  const activeConversation = conversationId;
  $('stop').disabled = true;
  try {
    const saved = await cancelTurn({ conversationId: activeConversation, messageId: assistantId, token });
    if (controller === activeController) { upsert(saved); activeController?.abort(); }
  }
  catch (error) { notice(`Cancellation could not be confirmed: ${error.message}. Refresh history after the stream ends.`, true); }
  finally { controls(); }
};
controls();

function renderTheme() {
  $('theme').value = Object.entries(curatedThemes).find(([, theme]) => Object.entries(theme).every(([key, value]) => key === 'spacing' || draftTheme[key] === value))?.[0] || 'custom';
  $('density').value = draftTheme.spacing;
  applyTheme($('theme-preview'), draftTheme);
}
$('theme').onchange = () => { if (curatedThemes[$('theme').value]) draftTheme = { ...curatedThemes[$('theme').value], spacing: $('density').value }; renderTheme(); };
$('density').onchange = () => { draftTheme = { ...draftTheme, spacing: $('density').value }; renderTheme(); };
$('theme-form').onsubmit = event => { event.preventDefault(); action(async () => {
  $('theme-status').textContent = 'Creating your preview…';
  try {
    draftTheme = await api('/assistant/theme/generate', { method: 'POST', body: JSON.stringify({ prompt: $('theme-prompt').value, current: draftTheme }) });
    renderTheme(); $('theme-status').textContent = 'Preview ready. Refine it or apply when it feels right.';
  } catch (error) { $('theme-status').textContent = error.message; }
}); };
$('theme-apply').onclick = () => action(async () => {
  activeTheme = await api('/assistant/theme', { method: 'PUT', body: JSON.stringify(draftTheme) });
  applyTheme(document.documentElement, activeTheme); $('theme-status').textContent = 'Appearance saved.';
});
$('theme-reset').onclick = () => action(async () => {
  activeTheme = await api('/assistant/theme', { method: 'PUT', body: JSON.stringify(curatedThemes.clean) });
  draftTheme = { ...activeTheme }; applyTheme(document.documentElement, activeTheme); renderTheme(); $('theme-status').textContent = 'Default appearance restored.';
});
$('tone-live').onclick = () => action(async () => {
  $('tone-status').textContent = 'Generating a sample with your current preferences…';
  try {
    const result = await api('/assistant/preview', { method: 'POST', body: JSON.stringify({ changes: profilePatch() }) });
    $('tone-example').textContent = result.text; $('tone-status').textContent = 'Live model sample. Your preferences have not been saved.';
  } catch (error) { $('tone-status').textContent = error.message; }
});
$('preset').onchange = () => {
  const value = $('preset').value;
  if (!presets[value]) return;
  for (const [key, number] of Object.entries(presets[value])) $('profile-fields').querySelector(`[name="${key}"]`).value = number;
  $('tone-example').textContent = examples[value];
  $('tone-status').textContent = 'Illustrative example. Save communication settings to use this style.';
};
for (const [id, prompt] of [['shorter', 'Please make your last answer shorter.'], ['detail', 'Please explain your last answer in more detail.']]) {
  $(id).onclick = () => { $('content').value = prompt; $('content').focus(); };
}
$('settings-open').onclick = () => { $('settings-dialog').showModal(); $('settings-dialog').scrollTop = 0; };
$('settings-close').onclick = () => $('settings-dialog').close();
renderTheme();

function profilePatch() {
  const patch = {};
  for (const input of $('profile-fields').querySelectorAll('input,textarea,select')) {
    patch[input.name] = input.type === 'checkbox' ? input.checked : sliders.includes(input.name) ? Number(input.value) : input.name === 'holiday_preferences' ? JSON.parse(input.value) : ['preferred_model', 'preferred_user_name'].includes(input.name) ? input.value.trim() || null : input.value;
  }
  return patch;
}

async function loadNotes() { notes = await api('/memories'); renderNotes(); }
function renderNotes() {
  $('memory-list').replaceChildren();
  $('memory-count').textContent = `${notes.length} of 20 notes`;
  for (const note of notes) {
    const item = document.createElement('article'); item.className = 'note';
    const content = document.createElement('p'); content.textContent = note.content;
    const metadata = document.createElement('small'); metadata.textContent = `Updated ${new Date(note.updated_at).toLocaleDateString()}${note.source_message_id ? ' · From your message' : ' · Added by you'}${omittedNotes.has(note.id) ? ' · Not included in the last request (context limit)' : ''}`;
    const actions = document.createElement('div'); actions.className = 'actions';
    const edit = document.createElement('button'); edit.textContent = 'Edit'; edit.dataset.memoryAction = 'edit';
    edit.onclick = () => { editingNoteId = note.id; sourceMessageId = note.source_message_id; $('memory-content').value = note.content; $('memory-save').textContent = 'Update note'; $('memory-status').textContent = 'Changes apply to the next request.'; $('memory-content').focus(); };
    const remove = document.createElement('button'); remove.textContent = 'Delete'; remove.dataset.memoryAction = 'delete';
    remove.onclick = () => action(async () => { await api(`/memories/${note.id}`, { method: 'DELETE' }); if (editingNoteId === note.id) clearNoteEditor(); await loadNotes(); $('memory-status').textContent = 'Note deleted. Its original chat message, if any, remains in history.'; });
    actions.append(edit, remove); item.append(content, metadata, actions); $('memory-list').append(item);
  }
  for (const button of $('memory-list').querySelectorAll('button')) button.disabled = !token || busy || streaming;
}
function clearNoteEditor() { editingNoteId = null; sourceMessageId = null; $('memory-content').value = ''; $('memory-save').textContent = 'Save note'; $('memory-status').textContent = ''; }
$('memory-cancel').onclick = clearNoteEditor;
$('memory-form').onsubmit = event => { event.preventDefault(); action(async () => {
  const payload = { content: $('memory-content').value };
  if (!editingNoteId) payload.source_message_id = sourceMessageId;
  await api(editingNoteId ? `/memories/${editingNoteId}` : '/memories', { method: editingNoteId ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
  clearNoteEditor(); await loadNotes(); $('memory-status').textContent = 'Note saved. It is available in new conversations and your next request.';
}); };
renderNotes();

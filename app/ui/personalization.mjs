export const presets = {
  concise: { warmth: .4, verbosity: .2, humor: .1, formality: .6 },
  warm: { warmth: .85, verbosity: .4, humor: .25, formality: .2 },
  detailed: { warmth: .5, verbosity: .85, humor: .1, formality: .6 },
};
export const examples = {
  concise: 'Pick one task. Work on it for 25 minutes, then take a short break.',
  warm: 'Let’s make a little space to focus. Choose one manageable task, and give yourself 25 minutes to get started.',
  detailed: 'Start by choosing one concrete outcome. Set aside 25 minutes, silence distractions, and work only on that task. Afterwards, review what moved forward and decide on your next step.',
};
export const curatedThemes = {
  clean: { background: '#f4f6fa', surface: '#ffffff', text: '#202b40', accent: '#294fc4', font: 'system', font_size: 16, spacing: 'comfortable', radius: 16, version: 1 },
  warm: { background: '#f4efe5', surface: '#fffdf7', text: '#302e24', accent: '#35533c', font: 'serif', font_size: 16, spacing: 'comfortable', radius: 16, version: 1 },
  dark: { background: '#141925', surface: '#202838', text: '#f2f5fc', accent: '#a9c2ff', font: 'system', font_size: 16, spacing: 'comfortable', radius: 16, version: 1 },
};
export function applyTheme(element, theme) {
  for (const key of ['background', 'surface', 'text', 'accent']) element.style.setProperty(`--${key}`, theme[key]);
  element.style.setProperty('--font', theme.font === 'serif' ? 'Georgia, serif' : 'system-ui, sans-serif');
  element.style.setProperty('--size', `${theme.font_size}px`);
  element.style.setProperty('--radius', `${theme.radius}px`);
  element.dataset.density = theme.spacing;
}

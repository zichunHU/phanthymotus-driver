/** Battery readout for the PrimeBot Q1 status topic. */
export const q1BatteryTopic = '/primebot_q1/status';

const metrics = [
  ['voltage_v', '电压', 'V', 2],
  ['current_a', '电流', 'A', 2],
  ['power_w', '输出功率', 'W', 2],
  ['cycle_count', '完整循环', '次', 0],
  ['temperature_c', '电池温度', '°C', 1],
  ['remaining_capacity_mah', '剩余容量', 'mAh', 0],
];
const extra = [
  ['cycle_total_capacity_mah', '累计充放电容量', 'mAh', 0],
  ['status_bits', 'BMS 状态位', '', 0],
];

export const Q1BatteryRenderer = {
  mount(container) {
    const panel = document.createElement('section');
    panel.className = 'q1-battery';
    panel.setAttribute('aria-label', 'Q1 电池状态');
    const rows = fields => fields.map(([key, label, unit]) =>
      `<div><dt>${label}</dt><dd><b data-key="${key}">—</b> <small>${unit}</small></dd></div>`
    ).join('');
    panel.innerHTML = `<header><span>荷电状态 · SOC</span><span class="q1-signal">等待数据</span></header>
      <div class="q1-charge"><strong>—</strong><span>%</span></div>
      <progress aria-label="电池电量" max="100" value="0"></progress>
      <dl class="q1-metrics">${rows(metrics)}</dl>
      <details><summary>更多电池数据</summary><dl class="q1-metrics">${rows(extra)}</dl></details>`;
    this.panel = panel;
    this.signal = panel.querySelector('.q1-signal');
    this.charge = panel.querySelector('strong');
    this.bar = panel.querySelector('progress');
    this.values = new Map([...panel.querySelectorAll('[data-key]')].map(el => [el.dataset.key, el]));
    container.appendChild(panel);
  },

  onData(buffer) {
    let sample;
    try { sample = JSON.parse(new TextDecoder().decode(buffer)).battery; }
    catch { return; }
    if (sample) this.renderSample(sample, true);
  },

  renderSample(sample, streaming) {
    clearTimeout(this.expiry);
    const live = sample.state === 'live';
    const stale = () => { this.signal.textContent = '上次读数'; this.panel.dataset.state = 'stale'; };
    this.panel.dataset.state = sample.state;
    this.signal.textContent = live ? (streaming ? '实时' : '本次读数') : sample.state === 'stale' ? '上次读数' : '等待数据';
    if (live && streaming) this.expiry = setTimeout(stale, Math.max(0, 5 - (sample.age_s || 0)) * 1000);
    this.charge.textContent = Number.isFinite(sample.percentage) ? sample.percentage : '—';
    this.bar.value = Number.isFinite(sample.percentage) ? sample.percentage : 0;
    for (const [key, , , digits] of [...metrics, ...extra]) {
      const value = sample[key];
      this.values.get(key).textContent = Number.isFinite(value) ? value.toFixed(digits) : '—';
    }
  },

  onDataSilent(buffer) { this.onData(buffer); },
  unmount() { clearTimeout(this.expiry); this.panel?.remove(); },
};

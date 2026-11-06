const MODES = {
  parado: "Desligado", degelo: "Degelo", aquecimento: "20 °C · Modo Eco",
  amaciar: "40 °C · Baixa Temp", secar: "50 °C · Alta Temp",
  esterilizar: "60 °C · Esterilizar", timer: "Timer",
};
const TEMPERATURES = Object.entries(MODES)
  .filter(([mode]) => !["parado", "degelo", "timer"].includes(mode))
  .map(([, label]) => label);


function isThermoluxMode(hass, entityId) {
  if (!entityId.startsWith("sensor.")) return false;
  const entity = hass.entities?.[entityId];
  if (entity?.platform) return entity.platform === "thermolux_local";
  return entityId.endsWith("_modo_atual") && entityId.includes("thermolux");
}

class ThermoluxSuiteCard extends HTMLElement {
  static getStubConfig(hass, entities = [], fallback = []) {
    const entity = [...entities, ...fallback, ...Object.keys(hass.states)].find(id => isThermoluxMode(hass, id));
    return entity ? {entity} : {};
  }
  static getConfigForm() {
    return {schema: [
      {name: "entity", required: true, selector: {entity: {filter: [{domain: "sensor", integration: "thermolux_local"}]}}},
      {name: "name", selector: {text: {}}},
    ]};
  }
  setConfig(config) {
    if (!config.entity) throw Error("Escolha a entidade Modo atual do Thermolux");
    const changedDevice = this.config?.entity !== config.entity || this.config?.device_identity !== config.device_identity;
    if (changedDevice) {
      this._entry = undefined;
      this._resolvedEntity = undefined;
      this._previewRequested = false;
      this._reportedMode = undefined;
      this.agendaEnabled = undefined;
      this._agendaRestored = false;
    }
    this.config = config;
    if (this.shadowRoot) {
      if (changedDevice) {
        this.$("photo").hidden = true;
        this.closeAgenda(false);
      }
      if (this._hass) this.hass = this._hass;
      return;
    }
    const root = this.attachShadow({mode: "open"});
    root.innerHTML = '<style>' +
      'ha-card{padding:16px;display:grid;gap:10px}.header{display:flex;gap:12px;align-items:center}' +
      '*{box-sizing:border-box}.header img{width:52px;height:52px;border-radius:50%;object-fit:cover}.header img[hidden],section[hidden]{display:none}' +
      'strong{font-size:1.05rem}.state,#status{color:var(--secondary-text-color);font-size:.9rem}' +
      '.controls{display:grid;grid-template-columns:1fr 1fr;gap:6px}.wide{grid-column:1/-1}' +
      'button,select{display:block;min-height:40px;width:100%;border:0;border-radius:12px;padding:0 10px;' +
      'color:var(--primary-text-color);background:var(--secondary-background-color);font:inherit;cursor:pointer}' +
      'button{display:flex;align-items:center;justify-content:center;gap:6px}button[disabled]{opacity:.5;cursor:wait}' +
      'select{min-width:0}.mode{position:relative}.mode select{padding-inline-start:36px}.mode ha-icon{position:absolute;inset-inline-start:10px;top:50%;transform:translateY(-50%);display:flex;align-items:center;justify-content:center;width:18px;height:18px;pointer-events:none;--mdc-icon-size:18px}' +
      '.agenda{border-top:1px solid var(--divider-color);padding-top:8px;min-width:0;container-type:inline-size}#status:empty{display:none}' +
      '.agenda-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.1fr);gap:8px;align-items:center;padding:4px 0;min-width:0}' +
      '.agenda-heading{display:flex;align-items:center;justify-content:space-between;margin:8px 0 3px;font-size:.9rem}.agenda-heading button{width:32px;min-height:32px;padding:0}.add-agenda{margin-top:8px}.agenda-heading:first-child{margin-top:2px}.mode-label{position:absolute;inset-inline-start:36px;top:50%;transform:translateY(-50%);pointer-events:none}.mode-label[hidden]{display:none}.agenda-row span{font-size:.9rem;overflow-wrap:anywhere}.agenda-row select,.agenda-row input{min-width:0;max-width:100%;width:100%;font:inherit;color:var(--primary-text-color);background:var(--secondary-background-color);border:0;border-radius:8px;padding:7px;min-height:36px}' +
      '.agenda-row input[type=time]{font-size:16px}.agenda-row input[type=checkbox]{width:22px;min-height:22px;justify-self:end;accent-color:var(--primary-color)}' +
      '@container (max-width: 270px){.agenda-row:not(.switch){grid-template-columns:minmax(0,1fr);gap:3px}}' +
      '.crop[hidden]{display:none}.crop{display:grid;gap:8px;min-width:0}.crop canvas{width:min(100%,240px);height:auto;aspect-ratio:1;justify-self:center;display:block;border-radius:12px;touch-action:none;cursor:grab;background:#000}.crop label{display:flex;align-items:center;gap:8px}.crop input{width:100%;min-width:0}.crop-actions{display:grid;grid-template-columns:1fr 1fr;gap:6px}' +
      '</style><ha-card><div class="header"><img id="photo" hidden alt="Foto da tela de descanso"><div>' +
      '<strong id="title">Toalheiro Thermolux</strong><div class="state" id="state"></div></div></div>' +
      '<div class="controls"><div class="mode wide"><ha-icon icon="mdi:radiator"></ha-icon><select id="mode" aria-label="Modos">' +
      '</select><span class="mode-label" id="modeLabel">Modos</span></div>' +
      '<button id="off"><ha-icon icon="mdi:power"></ha-icon>Desligar</button>' +
      '<button id="agenda" aria-expanded="false"><ha-icon icon="mdi:calendar-clock-outline"></ha-icon>Agenda</button>' +
      '<button id="screen" class="wide"><ha-icon icon="mdi:image-outline"></ha-icon>Tela de descanso</button></div>' +
      '<input id="file" type="file" accept="image/*" hidden><div id="status" role="status"></div>' +
      '<section class="crop" id="crop" hidden><strong>Enquadrar foto</strong><canvas id="cropPreview" width="240" height="240" aria-label="Prévia da tela de descanso"></canvas>' +
      '<label>Zoom<input id="cropZoom" type="range" min="0" max="100" value="0" aria-label="Zoom"></label>' +
      '<div class="crop-actions"><button id="cropCancel" type="button">Cancelar</button><button id="cropSend" type="button">Confirmar e enviar</button></div></section>' +
      '<section class="agenda" id="agendaPanel" hidden></section></ha-card>';
    for (const [key, label] of Object.entries(MODES)) {
      if (key !== "parado" && key !== "timer") this.$("mode").add(new Option(label, key));
    }
    this.$("mode").selectedIndex = -1;
    this.$("mode").addEventListener("change", () => {
      const mode = this.$("mode").value;
      this.$("modeLabel").hidden = Boolean(mode);
      if (mode) void this.run(mode);
    });
    this.$("off").addEventListener("click", () => void this.run("desligar"));
    this.$("agenda").addEventListener("click", () => void this.toggleAgenda());
    this.$("screen").addEventListener("click", () => this.$("file").click());
    this.$("file").addEventListener("change", (event) => {
      const file = event.target.files[0];
      event.target.value = "";
      if (file) void this.openCrop(file);
    });
    this.$("cropCancel").addEventListener("click", () => this.closeCrop());
    this.$("cropSend").addEventListener("click", () => {
      this.closeCrop();
      void this.upload(this.$("cropPreview"));
    });
    this.$("cropZoom").addEventListener("input", () => this.drawCrop());
    const preview = this.$("cropPreview");
    preview.addEventListener("pointerdown", event => {
      if (!this.cropImage || this.cropDrag) return;
      this.cropDrag = {id: event.pointerId, x: event.clientX, y: event.clientY};
      preview.setPointerCapture(event.pointerId);
    });
    preview.addEventListener("pointermove", event => {
      const drag = this.cropDrag;
      if (!drag || drag.id !== event.pointerId) return;
      const ratio = 240 / preview.getBoundingClientRect().width;
      this.cropX += (event.clientX - drag.x) * ratio;
      this.cropY += (event.clientY - drag.y) * ratio;
      drag.x = event.clientX;
      drag.y = event.clientY;
      this.drawCrop();
    });
    preview.addEventListener("lostpointercapture", () => { this.cropDrag = undefined; });
    if (this._hass) this.hass = this._hass;
  }
  $(id) { return this.shadowRoot.getElementById(id); }
  set hass(value) {
    this._hass = value;
    if (!this.shadowRoot) return;
    const entity = value.states[this._resolvedEntity || this.config.entity];
    this.$("title").textContent = this.config.name || entity?.attributes.friendly_name?.replace(/ Modo atual$/i, "") || "Toalheiro Thermolux";
    const reported = entity?.state;
    const mode = Object.hasOwn(MODES, reported) ? reported : "unknown";
    this.$("state").textContent = mode === "unknown" ? "Indisponível" : mode === "parado" ? "Desligado" : "Ligado";
    if (mode !== this._reportedMode) {
      this._reportedMode = mode;
      this.showMode(mode);
    }
    this.updateAgenda();
    if (!this._agendaRestored) {
      this._agendaRestored = true;
      if (this.$("agendaPanel").hidden && this.agendaOpenInSession()) void this.toggleAgenda();
    }
    if (!this._previewRequested) {
      this._previewRequested = true;
      this.request("device")
        .then(({preview}) => this.showPhoto(preview))
        .catch(() => {});
    }
  }
  showMode(mode) {
    const select = this.$("mode");
    select.value = mode;
    this.$("modeLabel").hidden = select.selectedIndex >= 0;
  }
  async request(command, data = {}) {
    if (!this._entry) {
      const lookup = {type: "thermolux_local/lookup", entity: this.config.entity};
      if (this.config.device_identity) lookup.identity = this.config.device_identity;
      this._entry = this._hass.callWS(lookup)
        .then(device => {
          this._resolvedEntity = device.entity;
          this.hass = this._hass;
          return device.entry_id;
        }).catch(error => { this._entry = undefined; throw error; });
    }
    const entry_id = await this._entry;
    return this._hass.callWS({type: "thermolux_local/" + command, entry_id, ...data});
  }
  async run(key) {
    try {
      await this.request("mode", {mode: key === "desligar" ? "parado" : key});
    } catch (error) {
      this.showMode(this._reportedMode);
      this.$("status").textContent = error.message || "Falha no comando";
    }
  }
  agendaSessionKey() {
    return "thermolux-agenda:" + location.pathname + ":" + this.config.entity;
  }
  agendaOpenInSession() {
    try { return sessionStorage.getItem(this.agendaSessionKey()) === "open"; }
    catch { return false; }
  }
  setAgendaSession(open) {
    try {
      if (open) sessionStorage.setItem(this.agendaSessionKey(), "open");
      else sessionStorage.removeItem(this.agendaSessionKey());
    } catch { /* Session storage can be unavailable in embedded browsers. */ }
  }
  async toggleAgenda() {
    const panel = this.$("agendaPanel");
    if (!panel.hidden) { this.closeAgenda(); return; }
    panel.hidden = false;
    this.setAgendaSession(true);
    this.$("agenda").setAttribute("aria-expanded", "true");
    panel.textContent = "Carregando agendas…";
    this.agendaSaveFailed = false;
    try {
      await this.agendaSaves;
      this.schedule = await this.request("device");
      if (!panel.hidden) this.buildAgenda();
    } catch (error) {
      panel.textContent = error.message || "Não foi possível abrir a agenda";
    }
  }
  agendaField(name, type, value, change) {
    const label = document.createElement("label");
    label.className = "agenda-row" + (type === "checkbox" ? " switch" : "");
    const caption = document.createElement("span");
    caption.textContent = name;
    const field = document.createElement(type === "select" ? "select" : "input");
    if (type === "select") field.replaceChildren(...TEMPERATURES.map(option => new Option(option)));
    else field.type = type;
    if (type === "checkbox") field.checked = value;
    else field.value = value;
    field.addEventListener("change", () => change(type === "checkbox" ? field.checked : field.value));
    label.append(caption, field);
    return label;
  }
  buildAgenda() {
    const panel = this.$("agendaPanel");
    panel.replaceChildren();
    const enabled = this.agendaField("Ativar agenda", "checkbox", false, async (on) => {
      const save = async () => {
        try {
          this.schedule = await this.request("agenda_enable", {enabled: on});
          this.agendaSaveFailed = false;
          this.updateAgenda();
        } catch (error) {
          this.agendaSaveFailed = true;
          this.updateAgenda();
          this.$("status").textContent = error.message || "Não foi possível alterar a agenda";
        }
      };
      this.agendaSaves = (this.agendaSaves || Promise.resolve()).then(save);
    });
    this.agendaEnabled = enabled.querySelector("input");
    panel.append(enabled);
    this.updateAgenda();
    const rows = this.schedule.rows;
    rows.forEach((row, index) => {
      const heading = document.createElement("div");
      heading.className = "agenda-heading";
      const title = document.createElement("strong");
      title.textContent = "Agenda " + (index + 1);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.setAttribute("aria-label", "Excluir agenda " + (index + 1));
      remove.title = "Excluir agenda";
      remove.innerHTML = '<ha-icon icon="mdi:trash-can-outline"></ha-icon>';
      remove.addEventListener("click", () => {
        if (window.confirm("Excluir Agenda " + (index + 1) + "?")) {
          void this.saveAgenda(current => current.filter((_, position) => position !== index));
        }
      });
      heading.append(title, remove);
      panel.append(heading);
      const edit = (key, value) => {
        if (!value) { this.buildAgenda(); return; }
        void this.saveAgenda(current => current.map((entry, position) =>
          position === index ? {...entry, [key]: value} : entry
        ), false);
      };
      panel.append(
        this.agendaField("Ligar", "time", row.start, value => edit("start", value)),
        this.agendaField("Desligar", "time", row.end, value => edit("end", value)),
        this.agendaField("Temperatura", "select", row.temperature, value => edit("temperature", value)),
      );
    });
    const add = document.createElement("button");
    add.type = "button";
    add.className = "add-agenda";
    add.innerHTML = '<ha-icon icon="mdi:plus"></ha-icon> Nova agenda';
    add.disabled = rows.length >= 30;
    add.addEventListener("click", () => {
      void this.saveAgenda(current => [...current, {start: "06:00", end: "07:00", temperature: TEMPERATURES[0]}]);
    });
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "add-agenda";
    confirm.innerHTML = '<ha-icon icon="mdi:check"></ha-icon> Confirmar agendamento';
    confirm.addEventListener("click", async () => {
      confirm.disabled = true;
      try {
        let pending;
        do {
          pending = this.agendaSaves;
          await pending;
        } while (pending !== this.agendaSaves);
        if (this.agendaSaveFailed) return;
        this.closeAgenda();
        this.$("status").textContent = this.schedule.enabled
          ? "Agendamentos confirmados"
          : "Agendamentos salvos · agenda desativada";
      } finally {
        confirm.disabled = false;
      }
    });
    panel.append(add, confirm);
  }
  saveAgenda(update, rebuild = true) {
    const panel = this.$("agendaPanel");
    if (rebuild) panel.querySelectorAll("button, input, select").forEach(field => { field.disabled = true; });
    const save = async () => {
      let refresh = rebuild;
      try {
        const rows = typeof update === "function" ? update(this.schedule.rows) : update;
        this.schedule = await this.request("agenda_save", {
          revision: this.schedule.revision, rows,
        });
        this.agendaSaveFailed = false;
      } catch (error) {
        this.agendaSaveFailed = true;
        refresh = true;
        this.$("status").textContent = error.message || "Não foi possível salvar a agenda";
      } finally {
        if (refresh && !panel.hidden) this.buildAgenda();
      }
    };
    this.agendaSaves = (this.agendaSaves || Promise.resolve()).then(save);
    return this.agendaSaves;
  }
  updateAgenda() {
    if (!this.agendaEnabled) return;
    this.agendaEnabled.checked = this.schedule.enabled;
  }
  closeAgenda(remember = true) {
    if (remember) this.setAgendaSession(false);
    this.$("agendaPanel").hidden = true;
    this.$("agenda").setAttribute("aria-expanded", "false");
  }
  showPhoto(preview) {
    if (!preview) return;
    this.$("photo").src = "data:image/jpeg;base64," + preview;
    this.$("photo").hidden = false;
  }
  async openCrop(file) {
    const screen = this.$("screen");
    const status = this.$("status");
    screen.disabled = true;
    status.textContent = "Preparando a foto…";
    let source;
    try {
      if (file.size > 30 * 1024 * 1024) throw Error("Escolha uma imagem de até 30 MB");
      source = URL.createObjectURL(file);
      const image = new Image();
      image.src = source;
      await image.decode();
      this.cropImage = image;
      this.cropX = this.cropY = 0;
      // Start with the canvas filled, while allowing zoom out to the full photo.
      const aspect = Math.max(image.naturalWidth, image.naturalHeight) /
        Math.min(image.naturalWidth, image.naturalHeight);
      this.$("cropZoom").value = Math.round(100 * (aspect - 1) / (aspect * 4 - 1));
      this.$("crop").hidden = false;
      this.drawCrop();
      status.textContent = "";
    } catch (error) {
      this.closeCrop();
      status.textContent = error.message || "Não foi possível abrir a foto";
    } finally {
      if (source) URL.revokeObjectURL(source);
      screen.disabled = false;
    }
  }
  closeCrop() {
    this.$("crop").hidden = true;
    this.cropImage = undefined;
    this.cropDrag = undefined;
  }
  drawCrop() {
    const image = this.cropImage;
    if (!image) return;
    const {naturalWidth, naturalHeight} = image;
    const fit = 240 / Math.max(naturalWidth, naturalHeight);
    const cover = 240 / Math.min(naturalWidth, naturalHeight);
    const scale = fit + (4 * cover - fit) * Number(this.$("cropZoom").value) / 100;
    const width = naturalWidth * scale;
    const height = naturalHeight * scale;
    const limit = (value, size) => Math.max(-Math.abs(size - 240) / 2, Math.min(Math.abs(size - 240) / 2, value));
    this.cropX = limit(this.cropX, width);
    this.cropY = limit(this.cropY, height);
    const context = this.$("cropPreview").getContext("2d");
    context.fillStyle = "black";
    context.fillRect(0, 0, 240, 240);
    context.drawImage(image, (240 - width) / 2 + this.cropX, (240 - height) / 2 + this.cropY, width, height);
  }
  async upload(canvas) {
    const screen = this.$("screen");
    const status = this.$("status");
    screen.disabled = true;
    try {
      const context = canvas.getContext("2d");
      const rgba = context.getImageData(0, 0, 240, 240).data;
      let raw = "";
      for (let i = 0; i < rgba.length; i += 4) {
        const pixel = (rgba[i] >> 3) << 11 | (rgba[i+1] >> 2) << 5 | rgba[i+2] >> 3;
        raw += String.fromCharCode(pixel >> 8, pixel & 255);
      }
      status.textContent = "Enviando a foto…";
      const response = await this.request("upload", {
        pixels: btoa(raw),
        preview: canvas.toDataURL("image/jpeg", .85).split(",")[1],
      });
      this.showPhoto(response.preview);
      status.textContent = "Foto enviada";
    } catch (error) {
      status.textContent = error.message || "Falha no envio da foto";
    } finally {
      screen.disabled = false;
    }
  }
  getCardSize() { return 3; }
}
customElements.define("thermolux-local-card", ThermoluxSuiteCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "thermolux-local-card",
  name: "Thermolux Local",
  description: "Modos, agenda e foto de descanso de um toalheiro",
  preview: true,
  getEntitySuggestion(hass, entityId) {
    if (!isThermoluxMode(hass, entityId)) return null;
    return {config: {type: "custom:thermolux-local-card", entity: entityId}};
  },
});

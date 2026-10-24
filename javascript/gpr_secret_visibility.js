(() => {
    const fields = [
        {id: "setting_gpr_api_key", ru: "API-ключ", en: "API key"},
        {id: "setting_gpr_proxy_url", ru: "URL прокси", en: "proxy URL"}
    ];

    function updateButton(button, input, field, wrapper) {
        const hasLanguage = typeof opts === "object" && opts && Object.prototype.hasOwnProperty.call(opts, "gpr_language");
        const russian = hasLanguage ? opts.gpr_language === "ru" : /[а-яё]/i.test(wrapper.querySelector("label")?.textContent || "");
        const visible = input.type === "text";
        const text = russian ? (visible ? "Скрыть" : "Показать") : (visible ? "Hide" : "Show");
        const label = `${text} ${russian ? field.ru : field.en}`;
        if (button.textContent !== text) button.textContent = text;
        for (const [name, value] of Object.entries({"aria-label": label, "aria-pressed": String(visible), "title": label})) {
            if (button.getAttribute(name) !== value) button.setAttribute(name, value);
        }
        if (input.id && button.getAttribute("aria-controls") !== input.id) button.setAttribute("aria-controls", input.id);
    }

    function enhanceFields() {
        const root = typeof gradioApp === "function" ? gradioApp() : document;
        for (const field of fields) {
            const wrapper = root.querySelector(`#${field.id}`);
            const input = wrapper?.querySelector('input[type="password"], input[type="text"]');
            if (!input) continue;
            let button = wrapper.querySelector("button.gpr-secret-toggle");
            if (!button) {
                button = document.createElement("button");
                button.type = "button";
                button.className = "gpr-secret-toggle";
                button.addEventListener("click", event => {
                    event.preventDefault();
                    event.stopPropagation();
                    const currentInput = wrapper.querySelector('input[type="password"], input[type="text"]');
                    if (!currentInput) return;
                    const start = currentInput.selectionStart;
                    const end = currentInput.selectionEnd;
                    const direction = currentInput.selectionDirection;
                    currentInput.type = currentInput.type === "password" ? "text" : "password";
                    if (start !== null && end !== null) currentInput.setSelectionRange(start, end, direction || "none");
                    updateButton(button, currentInput, field, wrapper);
                });
                wrapper.appendChild(button);
            }
            updateButton(button, input, field, wrapper);
        }
    }

    if (typeof onUiLoaded === "function") onUiLoaded(enhanceFields);
    if (typeof onAfterUiUpdate === "function") onAfterUiUpdate(enhanceFields);
    else if (typeof onUiUpdate === "function") onUiUpdate(enhanceFields);
    if (typeof onOptionsChanged === "function") onOptionsChanged(enhanceFields);
    enhanceFields();
})();

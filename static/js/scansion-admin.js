(() => {
    "use strict";

    const panel = document.querySelector("[data-scansion-assistant]");
    if (!panel || panel.dataset.initialized === "true") return;
    panel.dataset.initialized = "true";

    const body = document.getElementById("id_poem_body");
    const enabled = document.getElementById("id_scansion_enabled");
    const mode = document.getElementById("id_scansion_mode");
    const overridesField = document.getElementById("id_scansion_overrides");
    const results = panel.querySelector("[data-scansion-results]");
    const status = panel.querySelector("[data-scansion-status]");
    const symbolButtons = panel.querySelectorAll("[data-scansion-symbol-style]");
    const keySymbols = panel.querySelectorAll("[data-scansion-key]");
    if (!body || !enabled || !mode || !overridesField || !results || !status) return;

    let documentData = null;
    let requestSequence = 0;
    let debounceTimer = null;
    let overrides = readOverrides();
    let symbolStyle = readSymbolStyle();

    function readSymbolStyle() {
        try {
            return window.localStorage.getItem("poetry-scansion-symbols") === "traditional"
                ? "traditional"
                : "easy";
        } catch (_error) {
            return "easy";
        }
    }

    function symbolFor(stress) {
        if (symbolStyle === "traditional") return stress ? "\u00b4" : "\u02d8";
        return stress ? "+" : "\u2212";
    }

    function syncSymbolDisplay() {
        panel.dataset.symbolStyle = symbolStyle;
        symbolButtons.forEach((control) => {
            control.setAttribute(
                "aria-pressed",
                String(control.dataset.scansionSymbolStyle === symbolStyle),
            );
        });
        keySymbols.forEach((key) => {
            key.textContent = symbolFor(key.dataset.scansionKey === "stressed");
        });
    }

    function selectSymbolStyle(style) {
        symbolStyle = style === "traditional" ? "traditional" : "easy";
        try {
            window.localStorage.setItem("poetry-scansion-symbols", symbolStyle);
        } catch (_error) {
            // The preference is optional when browser storage is unavailable.
        }
        syncSymbolDisplay();
        render();
    }

    function readOverrides() {
        try {
            const parsed = JSON.parse(overridesField.value || "{}");
            return parsed && typeof parsed === "object" ? parsed : {};
        } catch (_error) {
            return {};
        }
    }

    function csrfToken() {
        const formToken = document.querySelector("input[name=csrfmiddlewaretoken]");
        return formToken ? formToken.value : "";
    }

    function occurrenceOverrides() {
        if (!overrides.occurrences || typeof overrides.occurrences !== "object") {
            overrides.occurrences = {};
        }
        return overrides.occurrences;
    }

    function saveOverrides() {
        overrides.version = 1;
        overrides.source_hash = documentData ? documentData.source_hash : null;
        overridesField.value = JSON.stringify(overrides);
        overridesField.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function selectedState(word) {
        const saved = occurrenceOverrides()[word.id];
        if (saved && saved.word === word.normalized && Array.isArray(saved.stresses)) {
            return {
                pronunciation: Number.isInteger(saved.pronunciation)
                    ? saved.pronunciation
                    : word.selected_pronunciation,
                stresses: saved.stresses.map(Boolean),
            };
        }
        return {
            pronunciation: word.selected_pronunciation,
            stresses: word.stresses.map(Boolean),
        };
    }

    function setState(word, state) {
        occurrenceOverrides()[word.id] = {
            word: word.normalized,
            pronunciation: state.pronunciation,
            stresses: state.stresses.map(Boolean),
        };
        saveOverrides();
    }

    function pruneOverrides() {
        const valid = new Map();
        let changed = false;
        documentData.lines.forEach((line) => {
            line.words.forEach((word) => valid.set(word.id, word.normalized));
        });
        Object.entries(occurrenceOverrides()).forEach(([id, saved]) => {
            if (!saved || valid.get(id) !== saved.word) {
                delete overrides.occurrences[id];
                changed = true;
            }
        });
        if (changed) saveOverrides();
    }

    function button(label, className, title) {
        const element = document.createElement("button");
        element.type = "button";
        element.className = className;
        element.textContent = label;
        element.title = title;
        return element;
    }

    function renderWord(word, lineSyllableIndex, rerender) {
        const state = selectedState(word);
        const card = document.createElement("div");
        card.className = `scansion-word${word.source === "unknown" ? " scansion-word--unknown" : ""}`;

        const wordText = document.createElement("span");
        wordText.className = "scansion-word__text";
        wordText.textContent = word.text;
        card.appendChild(wordText);

        if (word.pronunciations.length > 1) {
            const select = document.createElement("select");
            select.className = "scansion-word__pronunciation";
            select.setAttribute("aria-label", `Pronunciation for ${word.text}`);
            word.pronunciations.forEach((pronunciation, index) => {
                const option = document.createElement("option");
                option.value = String(index);
                option.textContent = `Option ${index + 1}: ${pronunciation.stresses
                    .map((stress) => (stress ? "stressed" : "unstressed"))
                    .join(" / ")}`;
                select.appendChild(option);
            });
            select.value = String(state.pronunciation ?? 0);
            select.addEventListener("change", () => {
                const pronunciation = Number(select.value);
                setState(word, {
                    pronunciation,
                    stresses: word.pronunciations[pronunciation].stresses.slice(),
                });
                rerender();
            });
            card.appendChild(select);
        }

        if (word.source === "unknown") {
            const unknown = document.createElement("span");
            unknown.className = "scansion-word__unknown";
            unknown.textContent = "!";
            unknown.setAttribute("role", "img");
            unknown.setAttribute("aria-label", `${word.text}: not in dictionary`);
            unknown.title = `${word.text} is not in the pronunciation dictionary`;
            card.appendChild(unknown);
        }

        const syllables = document.createElement("div");
        syllables.className = "scansion-word__syllables";
        state.stresses.forEach((stress, index) => {
            const control = button(symbolFor(stress), "scansion-syllable", "");
            const expectedStress = (lineSyllableIndex + index) % 2 === 1;
            const expectation = expectedStress ? "stressed" : "unstressed";
            control.setAttribute("aria-pressed", String(stress));
            control.setAttribute(
                "aria-label",
                `${word.text}, syllable ${index + 1}: ${stress ? "stressed" : "unstressed"}`,
            );
            control.title =
                mode.value === "iambic_pentameter" ? `Expected ${expectation}` : "Toggle stress";
            if (mode.value === "iambic_pentameter" && stress !== expectedStress) {
                control.classList.add("scansion-syllable--mismatch");
            }
            control.addEventListener("click", () => {
                state.stresses[index] = !state.stresses[index];
                setState(word, state);
                rerender();
            });
            syllables.appendChild(control);
        });
        card.appendChild(syllables);

        const controls = document.createElement("div");
        controls.className = "scansion-word__controls";
        const add = button("+ syll.", "scansion-word__adjust", `Add a syllable to ${word.text}`);
        add.setAttribute("aria-label", `Add a syllable to ${word.text}`);
        add.addEventListener("click", () => {
            state.stresses.push(false);
            setState(word, state);
            rerender();
        });
        controls.appendChild(add);
        const remove = button(
            "\u2212 syll.",
            "scansion-word__adjust",
            `Remove a syllable from ${word.text}`,
        );
        remove.setAttribute("aria-label", `Remove a syllable from ${word.text}`);
        remove.disabled = state.stresses.length === 0;
        remove.addEventListener("click", () => {
            state.stresses.pop();
            setState(word, state);
            rerender();
        });
        controls.appendChild(remove);
        card.appendChild(controls);
        return { card, syllableCount: state.stresses.length };
    }

    function render() {
        results.replaceChildren();
        if (!documentData) return;
        documentData.lines.forEach((line) => {
            const lineElement = document.createElement("section");
            lineElement.className = "scansion-assistant__line";
            lineElement.setAttribute("aria-label", `Line ${line.index + 1}`);

            if (mode.value === "iambic_pentameter" && line.words.length) {
                const meter = document.createElement("p");
                meter.className = "scansion-assistant__meter";
                meter.textContent = `Guide: ${Array.from({ length: 10 }, (_value, index) =>
                    symbolFor(index % 2 === 1),
                ).join(" ")}`;
                lineElement.appendChild(meter);
            }

            const words = document.createElement("div");
            words.className = "scansion-assistant__words";
            let syllableIndex = 0;
            line.words.forEach((word) => {
                const rendered = renderWord(word, syllableIndex, render);
                words.appendChild(rendered.card);
                syllableIndex += rendered.syllableCount;
            });
            lineElement.appendChild(words);
            results.appendChild(lineElement);
        });
        results.hidden = false;
        status.textContent = documentData.unknown_words
            ? `${documentData.unknown_words} word occurrence(s) need manual syllables.`
            : "Dictionary stress loaded. Select any syllable to change it.";
    }

    async function analyze() {
        if (!enabled.checked) {
            requestSequence += 1;
            results.hidden = true;
            status.textContent = "";
            return;
        }
        const sequence = ++requestSequence;
        status.textContent = "Analyzing stress\u2026";
        try {
            const response = await fetch(panel.dataset.analysisUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken(),
                },
                body: JSON.stringify({
                    text: body.value,
                    mode: mode.value,
                    page_id: panel.dataset.pageId || null,
                }),
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || "Stress analysis failed.");
            if (sequence !== requestSequence) return;
            documentData = payload;
            pruneOverrides();
            render();
        } catch (error) {
            if (sequence !== requestSequence) return;
            results.hidden = true;
            status.textContent = `${error.message} You can still save or publish the poem.`;
        }
    }

    function scheduleAnalysis() {
        window.clearTimeout(debounceTimer);
        debounceTimer = window.setTimeout(analyze, 300);
    }

    body.addEventListener("input", scheduleAnalysis);
    enabled.addEventListener("change", analyze);
    mode.addEventListener("change", analyze);
    symbolButtons.forEach((control) => {
        control.addEventListener("click", () =>
            selectSymbolStyle(control.dataset.scansionSymbolStyle),
        );
    });
    syncSymbolDisplay();
    analyze();
})();

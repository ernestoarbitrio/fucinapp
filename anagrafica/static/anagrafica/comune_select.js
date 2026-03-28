document.addEventListener("DOMContentLoaded", function () {
    let comuniData = [];

    fetch("/static/anagrafica/comuni.json")
        .then(r => r.json())
        .then(data => {
            comuniData = data;
            const prov = document.getElementById("id_provincia");
            if (prov && prov.value) popolaComuni(prov.value);
        });

    function popolaComuni(prov, selectedComune = "") {
        const comuneSelect = document.getElementById("id_comune");
        if (!comuneSelect) return;

        const current = selectedComune || comuneSelect.value;
        comuneSelect.innerHTML = '<option value="">— Seleziona comune —</option>';

        const filtered = comuniData
            .filter(c => c.provincia === prov)
            .sort((a, b) => a.comune.localeCompare(b.comune));

        filtered.forEach(c => {
            const opt = document.createElement("option");
            opt.value = c.comune;
            opt.textContent = c.comune;
            opt.dataset.cap = c.cap;
            if (c.comune === current) opt.selected = true;
            comuneSelect.appendChild(opt);
        });

        // Auto-fill CAP if comune already selected
        const capInput = document.getElementById("id_cap");
        if (capInput) {
            const selected = comuneSelect.options[comuneSelect.selectedIndex];
            if (selected && selected.dataset.cap) {
                capInput.value = selected.dataset.cap;
            }
        }
    }

    document.addEventListener("change", function (e) {
        if (e.target.id === "id_provincia") {
            const capInput = document.getElementById("id_cap");
            if (capInput) capInput.value = "";
            popolaComuni(e.target.value);
        }

        if (e.target.id === "id_comune") {
            const selected = e.target.options[e.target.selectedIndex];
            const capInput = document.getElementById("id_cap");
            if (capInput && selected) {
                capInput.value = selected.dataset.cap || "";
            }
        }
    });
});

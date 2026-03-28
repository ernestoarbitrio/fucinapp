from django import forms

from anagrafica.models import Socio, valida_codice_fiscale

PROVINCE_ITALIANE = [
    ("AG", "Agrigento"),
    ("AL", "Alessandria"),
    ("AN", "Ancona"),
    ("AO", "Aosta"),
    ("AQ", "L'Aquila"),
    ("AR", "Arezzo"),
    ("AP", "Ascoli Piceno"),
    ("AT", "Asti"),
    ("AV", "Avellino"),
    ("BA", "Bari"),
    ("BT", "Barletta-Andria-Trani"),
    ("BL", "Belluno"),
    ("BN", "Benevento"),
    ("BG", "Bergamo"),
    ("BI", "Biella"),
    ("BO", "Bologna"),
    ("BZ", "Bolzano"),
    ("BS", "Brescia"),
    ("BR", "Brindisi"),
    ("CA", "Cagliari"),
    ("CL", "Caltanissetta"),
    ("CB", "Campobasso"),
    ("CE", "Caserta"),
    ("CT", "Catania"),
    ("CZ", "Catanzaro"),
    ("CH", "Chieti"),
    ("CO", "Como"),
    ("CS", "Cosenza"),
    ("CR", "Cremona"),
    ("KR", "Crotone"),
    ("CN", "Cuneo"),
    ("EN", "Enna"),
    ("FM", "Fermo"),
    ("FE", "Ferrara"),
    ("FI", "Firenze"),
    ("FG", "Foggia"),
    ("FC", "Forlì-Cesena"),
    ("FR", "Frosinone"),
    ("GE", "Genova"),
    ("GO", "Gorizia"),
    ("GR", "Grosseto"),
    ("IM", "Imperia"),
    ("IS", "Isernia"),
    ("SP", "La Spezia"),
    ("LT", "Latina"),
    ("LE", "Lecce"),
    ("LC", "Lecco"),
    ("LI", "Livorno"),
    ("LO", "Lodi"),
    ("LU", "Lucca"),
    ("MC", "Macerata"),
    ("MN", "Mantova"),
    ("MS", "Massa-Carrara"),
    ("MT", "Matera"),
    ("ME", "Messina"),
    ("MI", "Milano"),
    ("MO", "Modena"),
    ("MB", "Monza e della Brianza"),
    ("NA", "Napoli"),
    ("NO", "Novara"),
    ("NU", "Nuoro"),
    ("OR", "Oristano"),
    ("PD", "Padova"),
    ("PA", "Palermo"),
    ("PR", "Parma"),
    ("PV", "Pavia"),
    ("PG", "Perugia"),
    ("PU", "Pesaro e Urbino"),
    ("PE", "Pescara"),
    ("PC", "Piacenza"),
    ("PI", "Pisa"),
    ("PT", "Pistoia"),
    ("PN", "Pordenone"),
    ("PZ", "Potenza"),
    ("PO", "Prato"),
    ("RG", "Ragusa"),
    ("RA", "Ravenna"),
    ("RC", "Reggio Calabria"),
    ("RE", "Reggio Emilia"),
    ("RI", "Rieti"),
    ("RN", "Rimini"),
    ("RM", "Roma"),
    ("RO", "Rovigo"),
    ("SA", "Salerno"),
    ("SS", "Sassari"),
    ("SV", "Savona"),
    ("SI", "Siena"),
    ("SR", "Siracusa"),
    ("SO", "Sondrio"),
    ("SU", "Sud Sardegna"),
    ("TA", "Taranto"),
    ("TE", "Teramo"),
    ("TR", "Terni"),
    ("TO", "Torino"),
    ("TP", "Trapani"),
    ("TN", "Trento"),
    ("TV", "Treviso"),
    ("TS", "Trieste"),
    ("UD", "Udine"),
    ("VA", "Varese"),
    ("VE", "Venezia"),
    ("VB", "Verbano-Cusio-Ossola"),
    ("VC", "Vercelli"),
    ("VR", "Verona"),
    ("VV", "Vibo Valentia"),
    ("VI", "Vicenza"),
    ("VT", "Viterbo"),
]


class IscrizioneForm(forms.ModelForm):
    provincia = forms.ChoiceField(
        choices=[("", "— Seleziona provincia —")] + PROVINCE_ITALIANE,
        widget=forms.Select(attrs={"id": "id_provincia"}),
        label="Provincia",
    )

    comune = forms.CharField(
        widget=forms.Select(attrs={"id": "id_comune"}),
        label="Comune",
    )

    class Meta:
        model = Socio
        fields = (
            "nome",
            "cognome",
            "data_nascita",
            "luogo_nascita",
            "codice_fiscale",
            "via",
            "comune",
            "provincia",
            "cap",
            "email",
            "tutore_nome",
            "tutore_cognome",
            "tutore_codice_fiscale",
            "tutore_residenza",
            "tutore_email",
            "tutore_telefono",
            "telefono",
            "consenso_marketing",
            "consenso_immagini",
        )
        widgets = {
            "data_nascita": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_codice_fiscale(self):
        cf = self.cleaned_data.get("codice_fiscale", "").upper().strip()
        valida_codice_fiscale(cf)
        odd = {
            "0": 1,
            "1": 0,
            "2": 5,
            "3": 7,
            "4": 9,
            "5": 13,
            "6": 15,
            "7": 17,
            "8": 19,
            "9": 21,
            "A": 1,
            "B": 0,
            "C": 5,
            "D": 7,
            "E": 9,
            "F": 13,
            "G": 15,
            "H": 17,
            "I": 19,
            "J": 21,
            "K": 2,
            "L": 4,
            "M": 18,
            "N": 20,
            "O": 11,
            "P": 3,
            "Q": 6,
            "R": 8,
            "S": 12,
            "T": 14,
            "U": 16,
            "V": 10,
            "W": 22,
            "X": 25,
            "Y": 24,
            "Z": 23,
        }
        even = {
            "0": 0,
            "1": 1,
            "2": 2,
            "3": 3,
            "4": 4,
            "5": 5,
            "6": 6,
            "7": 7,
            "8": 8,
            "9": 9,
            "A": 0,
            "B": 1,
            "C": 2,
            "D": 3,
            "E": 4,
            "F": 5,
            "G": 6,
            "H": 7,
            "I": 8,
            "J": 9,
            "K": 10,
            "L": 11,
            "M": 12,
            "N": 13,
            "O": 14,
            "P": 15,
            "Q": 16,
            "R": 17,
            "S": 18,
            "T": 19,
            "U": 20,
            "V": 21,
            "W": 22,
            "X": 23,
            "Y": 24,
            "Z": 25,
        }
        total = sum(
            (even[c] if (i + 1) % 2 == 0 else odd[c]) for i, c in enumerate(cf[:15])
        )
        expected = chr(total % 26 + ord("A"))
        if cf[15] != expected:
            raise forms.ValidationError(
                f"Carattere di controllo errato (atteso: {expected})."
            )
        return cf

    def clean(self):
        cleaned_data = super().clean()
        data_nascita = cleaned_data.get("data_nascita")
        if data_nascita:
            from datetime import date

            today = date.today()
            eta = (today - data_nascita).days // 365
            if eta < 18:
                for field in [
                    "tutore_nome",
                    "tutore_cognome",
                    "tutore_codice_fiscale",
                    "tutore_email",
                    "tutore_residenza",
                ]:
                    if not cleaned_data.get(field):
                        self.add_error(field, "Campo obbligatorio per i minorenni.")
        return cleaned_data

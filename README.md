# Weather Scanner — Rīgas LU temperatūras un nokrišņu analogi

Prototips ar pārslēdzamiem **Temperatūra / Nokrišņi** skatiem, lokālu Python serveri un [publisku GitHub Pages datu izgriezumu](https://dboka.github.io/Analog_Forecasting/). Temperatūras 24h → 24h algoritms izmanto `HTDRY` un ir saglabāts nemainīts. Eksperimentālais nokrišņu skats izmanto `HPRAB` stundas summas. **Gan mērķis, gan visi analogi abos skatos ir tikai no `RIGASLU`.**

## Palaišana

PowerShell, no projekta mapes:

    python sync_clidata.py --station RIGASLU
    python sync_precipitation.py
    python server.py

Atver [http://127.0.0.1:8777/](http://127.0.0.1:8777/). Pirmās divas komandas izveido atsevišķus `HTDRY` un `HPRAB` kešus; tām vajadzīga CLIDATA piekļuve. `CLIDATA_REFERENCE` var norādīt esošās Oracle pieslēguma palīdzfunkcijas failu. Serveris klausās tikai `127.0.0.1` un apmēram reizi 10 minūtēs mēģina atjaunot jaunākos mērījumus.

## GitHub Pages un privātie pieslēguma dati

GitHub Pages ir statiska vietne, tādēļ `site/` satur iepriekš aprēķinātas, katrai dienai un metodei atsevišķas JSON atbildes. Tā ir **publicēšanas brīža kopija**, ne tiešraides CLIDATA savienojums; lapas augšā redzams atjaunināšanas laiks. 24h temperatūras un nokrišņu prognozes, oktobra metodes un grafiki darbojas bez publiska Python servera. Vietnes failu kopējais apjoms ir neliels; pārlūks ielādē tikai izvēlētās dienas un metodes JSON. Google meklēšanai ir aprakstošs lapas nosaukums, `robots.txt` un `sitemap.xml`; indeksēšanas laiku nosaka meklētājs.

CLIDATA pieteikšanās informāciju glabā tikai ignorētā `.env` failā (`.env.example` ir tukšs paraugs) vai privātā palīdzfunkcijas failā **ārpus repozitorija**. `.env` atbalsta `CLIDATA_USER`, `CLIDATA_PASSWORD`, `CLIDATA_DSN` vai `CLIDATA_REFERENCE`. `data/`, `.runtime/`, žurnāli un neapstrādātie keši ir Git ignorēti. Publiskais `site/` satur tikai aprēķinātus Rīgas LU rezultātus un tajos attēlotos meteoroloģiskos novērojumus; **nekādas paroles, Oracle savienojuma virknes vai neapstrādātu kešu tur nav**.

Jauni mērījumi jāsinhronizē datorā, kam ir CLIDATA piekļuve. PowerShell komanda veic inkrementālu pašreizējā un iepriekšējā gada ielādi, QC, testus un statiskās kopijas pārbūvi; `-Push` papildus publicē jaunās kopijas commit, kas izraisa GitHub Pages darbplūsmu:

    .\publish_snapshot.ps1 -Push

Šo komandu var ieplānot Windows Task Scheduler, kamēr dators un CLIDATA ir pieejami. GitHub Actions darbplūsma **tikai izvieto** jau aprēķināto `site/` mapi; CLIDATA parole netiek nodota GitHub. Ja lokālā sinhronizācija vai testi neizdodas, jauna kopija netiek publicēta. Komanda bez `-Push` ļauj vispirms apskatīt izmaiņas lokāli.

## Lapa

- Viens **24h → 24h** grafiks: tirkīzzils ir vakardienas ievades profils, violets ir astoņu analogu svērtā prognoze, violetais laukums ir analogu 10.–90. procentiļu diapazons.
- Dzeltenā punktotā līkne ir izvēlētā vēsturiskā analoga **nākamās dienas turpinājums**, vertikāli pārbīdīts līdz vakardienas pēdējai temperatūrai. Citu analogu var izvēlēties labajā sarakstā; leģendā šo līkni var ieslēgt un izslēgt.
- Zaļā līkne ir jau saņemtie šodienas Rīgas LU mērījumi. Rozā punktotā līkne, ja ir vismaz sešas šodienas stundas, ir **pēc fakta** tuvākā pilnā vēsturiskā diena. To var ieslēgt vai izslēgt; tā nemaina prognozi.
- Zilā pārtrauktā līkne ir izvēlētās prognozes dienas **vēsturiskā stundas norma**: katras vietējās stundas aritmētiskais vidējais tā paša kalendāra datuma pilnajās Rīgas LU `HTDRY` dienās **iepriekšējos gados**. Leģenda rāda izmantoto gadu skaitu. Šī ir datu izlases vidējā vērtība, nevis oficiālā 30 gadu klimatiskā norma, un tā neietekmē analogu prognozi.
- Labais panelis rāda analoga datumu, staciju, ievades līknes RMSE, vertikālo nobīdi un kopējo atbilstības vērtējumu. Mazāks vērtējums ir labāks.
- Virs grafika ir dienu pārslēdzējs ar **ŠODIEN** pogu. Zem grafika ir oktobra mēneša pārskats: katra pieejamā diena atver savu 24h prognozi un faktisko rezultātu; dienas kartītē redzama vidējā absolūtā kļūda (MAE). 1. oktobra prognozes ievade ir **30. septembris**. Nepilni un nākotnes datumi ir atzīmēti atsevišķi.
- Atsevišķā **Oktobra analogi** sadaļa salīdzina 2026. gada pilnās oktobra dienas ar identiskām dienām un stundām iepriekšējos Rīgas LU gados. Var izvēlēties visu pieejamo oktobri, pēdējās 10 vai 7 dienas, kā arī pārslēgt TOP 5 rangu starp **temperatūras**, **diennakts profila** un **vairāku dienu režīma** līdzību. Temperatūras metode ir sākotnējā un noklusētā. Grafikā var ieslēgt jebkuru TOP 5 gadu. Vēsturiskās dienas pēc salīdzinājuma robežas līdz 31. oktobrim ir pārtrauktas līnijas; to vērtības nemaina rangu. Nepilnās dienas ir tukšumi.

Vēsturiskās prognozes tiek **rekonstruētas tagad** ar pašreizējo algoritmu un pašreiz saglabāto CLIDATA arhīvu. Katras dienas atlase izmanto tikai tai iepriekšējās dienas ievadi un senākus analogus. Tā nav agrāk saglabāta, toreiz publicēta prognoze. Izvēlētās dienas faktiskie mērījumi kalpo tikai rezultāta salīdzināšanai.

## Nokrišņu skats

- `HPRAB` CLIDATA metadatos ir “Precipitation amount, hourly sum”, mērvienība **mm**, stacijas intervāls **01:00**. Laika atzīmei piesaistām tās sākuma stundu UTC un attēlojam Rīgas vietējā laikā. LVĢMC skaidro, ka stundas summa raksturo katru stundu un tukšs lauks šim rādītājam nozīmē trūkstošu datu. Tukšs lauks **nav 0 mm**.
- Atsevišķais `data/stations/RIGASLU_HPRAB.json.gz` glabā tikai QC pieņemtās stundas. Noraidām neesošus, neskaitliskus, ārpus 0–250 mm esošus, ar `FI` atzīmētus un ar dokumentētajiem nederīgajiem `FII` kodiem atzīmētus mērījumus. Dienas un analogi pieejami tikai ar visām 24 derīgajām vietējām stundām; 23/25 stundu pārejas dienas izlaižam. Metadatu pārbaude aptur sinhronizāciju, ja mainās HPRAB nozīme, vienība vai intervāls.
- Nokrišņu **Oktobra analogi** ļauj pārslēgt daudzuma, slapjo stundu/epizožu vai vairāku dienu sausuma/lietus ritma rangu. Katram TOP 5 gadam rāda visu trīs metožu rezultātu. Dienu stabiņi, izvēlētās dienas stundas stabiņi un kumulatīvā līkne salīdzina 2026. gadu ar izvēlēto vēsturisko gadu. Pēc salīdzinājuma robežas esošais vēsturiskais turpinājums ir atsevišķi iekrāsots un **nekad** neietekmē rangu.
- Eksperimentālā 24h nokrišņu prognoze atlasa astoņus pilnus vēsturiskos 24h + 24h pārus pēc iepriekšējās dienas nokrišņiem. Grafikā ir analogu svērtais stundas daudzums, slapjas stundas svarotā daļa un faktiski saņemtie mērījumi. Rādām ≥1 mm dienas iespēju un 10./50./90. procentiles **analogu scenārijus**; tās nav kalibrētas varbūtības vai ticamības intervāls.
- Retrospektīvā pārbaude 2025. gada oktobra 23 pilnām dienām: dienas summas MAE **4,0 mm**, 0 mm bāzes prognozei **3,9 mm**; ≥1 mm dienas Brier kļūda **0,228**, sezonālās frekvences bāzei **0,244**. Rezultāts ir jaukts un nav pierādījums operatīvai prognozes kvalitātei. Vairāku gadu rezultāti ir `ARCHITECTURE.md`.

## API un testi

- `GET /api/status` — datu un pilno dienu/pāru skaitītāji.
- `GET /api/forecast` — šodienas 24h prognoze. `GET /api/forecast?date=2026-10-01` — 1. oktobra prognozes rekonstrukcija no 30. septembra ievades. Atbildē ir arī `normal` (24 stundas), `normalSampleDays` un `normalYears`.
- `GET /api/month?month=2026-10` — oktobra dienu pieejamība un dienu kļūdas pārskats.
- `GET /api/october-analogues?period=all|10|7&method=temperature|profile|regime` — 2026. gada oktobra salīdzinājums, TOP 5 gadi, atsevišķi salīdzinājuma un vēlākā turpinājuma dati. `method` nav obligāts; noklusējums ir `temperature`, kura rangs ir `0,30 × MAE + 0,40 × RMSE + 0,30 × formas RMSE`. Citu metožu formulas un robežas aprakstītas `ARCHITECTURE.md`.
- `GET /api/precipitation/forecast?date=YYYY-MM-DD` — izvēlētās dienas 24h HPRAB scenārijs; bez datuma šodiena.
- `GET /api/precipitation/october?period=all|10|7&method=amount|episodes|rhythm` — nokrišņu TOP 5, dienu/stundu dati un atsevišķi vēlākie turpinājumi.
- `GET /api/precipitation/backtest` — retrospektīvās kļūdas un vienkāršie bāzes salīdzinājumi.
- `python -m unittest -v` — kvalitātes kontroles, Rīgas LU atlases, pilno dienu un nākotnes datu robežas testi.

Datu plūsma un modelis ir [ARCHITECTURE.md](ARCHITECTURE.md); norādes nākamajam aģentam ir [AGENTS.md](AGENTS.md).

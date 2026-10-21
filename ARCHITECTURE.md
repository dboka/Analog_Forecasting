# Weather Scanner arhitektūra un pašreizējais stāvoklis

Atjaunots: 2026-10-21. Rīks ir lokāls **Rīgas LU 24h → 24h analogu pilots** ar atsevišķiem `HTDRY` temperatūras un `HPRAB` nokrišņu režīmiem. Temperatūras prognozes metode un tās grafiks ir saglabāti nemainīti. Abos režīmos ir atsevišķa “Oktobra analogi” sadaļa. Mērķa stacija, faktiskie mērījumi un visi vēsturiskie analogi vienmēr ir `RIGASLU`.

## Publiskā statiskā versija

`build_static_site.py` lokāli nolasa abus QC kešus un izveido `site/` ar frontend failiem un maziem JSON gabaliem katrai oktobra prognozes dienai, periodam un līdzības metodei. Tas salīdzina pieņemto novērojumu un avota failu SHA-256 nospiedumu ar iepriekšējo izgriezumu, lai neveidotu jaunu commit bez izmaiņām. `public/api-client.js` lokālajā režīmā izmanto Python `/api/...`; statiskajā režīmā tos pašus pieprasījumus piesaista `site/api/...json`. Tas **nemaina** `model.py` vai `precipitation.py` algoritmus. `site/` nesatur Oracle piekļuves datus vai neapstrādātus datubāzes kešus; tas satur publiski redzamos atvasinātos grafiku datus un vēsturiskos turpinājumus. Lapa skaidri parāda izgriezuma datumu. `.github/workflows/pages.yml` izvieto tikai `site/`; Python serveris GitHub Pages vidē nedarbojas. `publish_snapshot.ps1 -Push` sinhronizē jaunāko datu gadu un iepriekšējo gadu (vēlākām korekcijām), izpilda testus, pārbūvē izgriezumu un push tikai pēc veiksmīgas pārbaudes. Darbplūsma pati nevar iegūt svaigus CLIDATA datus; vajadzīgs lokālais atjaunināšanas solis ar piekļuvi datubāzei.

`register_update_task.ps1` veido lokālu Windows uzdevumu `AnalogForecastingSnapshot` ik pēc trim stundām (sākuma laiks 06:00); uzdevums izsauc tikai `publish_snapshot.ps1 -Push` šajā datorā. Ja dators ir izslēgts, nav pieejams CLIDATA vai Git Credential Manager nevar autentificēt push, publiskais izgriezums paliek ar pēdējo veiksmīgo datumu.

## Dati un kvalitātes kontrole

1. `sync_clidata.py` atver esošo CLIDATA Oracle pieslēguma palīdzfunkciju (`CLIDATA_REFERENCE`) un lasa `CLIDATA.RDATA` rindas ar `EG_GH_ID='RIGASLU'`, `EG_EL_ABBREVIATION='HTDRY'`, `REGULAR='Y'`. Kešs: `data/stations/RIGASLU.json.gz`; tajā nav paroļu.
2. Pieņem tikai derīgu UTC stundas atzīmi, skaitlisku galīgu temperatūru −55…+55 °C un šūnas bez netukša `FIxx` karodziņa. Identiskus dublikātus apvieno, pretrunīgas viena laika vērtības izslēdz. `FIIxx` un `VALIDATION` semantika nav zināma; šis ir **lietotnes QC**, ne CLIDATA oficiāla validācija vai homogenizācija.
3. `model.py` veido tikai pilnas Rīgas vietējās kalendāra dienas ar **visām 24 pieņemtajām stundām**. Secīgs pilnas ievades un pilna turpinājuma dienas pāris ir kandidāts. Trūkstošas stundas netiek aizpildītas. Vasaras laika maiņas 23/25 stundu dienas tiek izslēgtas.
4. `server.py` ielādē **tikai** Rīgas LU kešu un pārbūvē pilno dienu indeksu. Citu staciju keši, ja tie palikuši diskā, nav kandidātu avots. `model.py` atlasē vēlreiz filtrē `pair.station == 'RIGASLU'`.

## Analogu izvēle

Mērķis ir iepriekšējā pilnā Rīgas LU diena. Kandidāts ir tās pašas stacijas pilns `24h ievade + 24h turpinājums`, kura ievades datums ir vismaz astoņas dienas senāks un sezonā atrodas ±60 kalendāra dienu robežās. Vērtē tikai vēsturiskā pāra **pirmo** 24h līkni:

    score = 0,48 × absolūtais RMSE
          + 0,37 × pēc dienas vidējās atņemšanas aprēķināts formas RMSE
          + 0,15 × 23 secīgo stundu izmaiņu RMSE
          + 0,35 × sezonas attālums / 60

Izvēlas astoņus zemākos vērtējumus, starp to datumiem ievērojot vismaz piecu dienu atstarpi. Vēsturiskais nākamās dienas turpinājums tiek vertikāli pārbīdīts par `Rīgas LU vakardienas pēdējā vērtība − analoga ievades pēdējā vērtība`. Prognoze ir astoņu nobīdīto turpinājumu svērtais vidējais ar svaru `1 / (score + 0,35)^2`. Iekrāsotais laukums ir turpinājumu 10. un 90. procentile katrā stundā. Tā ir analogu izkliede, **ne kalibrēts ticamības intervāls**.

Izvēlētās prognozes dienas faktiskie mērījumi **nekad** nepiedalās kandidātu atlasē, vērtējumā vai svaros. Rozā “dienas sakritība” pēc vismaz sešām saņemtām stundām meklē tām tuvāko pilno, vismaz astoņas dienas seno Rīgas LU vēsturisko dienu. Tā ir retrospektīva ilustrācija.

## Lietotne un API

`public/index.html`, `style.css` un `app.js` veido 24h prognozes grafiku, analogu paneli, oktobra dienu pārskatu un atsevišķu oktobra analogu salīdzinājuma grafiku. Prognozes grafikā 00:00 robeža atdala izvēlētajai dienai iepriekšējo 24h ievadi no tās prognozes. Dienu var izvēlēties ar kalendāra kartītēm vai ←/→ pogām; **ŠODIEN** atgriež pie jaunākās prognozes. Nākotnes dienas un dienas bez pilnas ievades nevar atvērt. Analogu saraksta pogas maina dzelteno turpinājuma līkni; leģendā gan dzeltenajai, gan rozā līknei ir atsevišķa ieslēgšanas poga. Dzeltenās līknes paslēpšana saglabā izvēlēto analogu un nemaina prognozi. Agrākais visus gadus aptverošais vēstures grafiks, 7 dienu prognozes ievades režīms un diagnostikas panelis nav atjaunoti.

`GET /api/forecast` atdod šodienas rezultātu; `GET /api/forecast?date=YYYY-MM-DD` rekonstruē izvēlēto pagājušo dienu, izmantojot **iepriekšējo** pilno dienu kā ievadi. 1. oktobra ievade ir 30. septembris. Atbilde satur `input` un `forecast` kā 24 [UTC milisekundes, °C] punktus, `lower`/`upper` diapazonu, `matches` ar datumu, staciju, vērtējumu, ievades RMSE, nobīdi un 24h turpinājumu, kā arī `actual` un, ja iespējams, `observedDayMatch`. Nākotnes datumi un neatbalstīti parametri dod HTTP 400. `GET /api/status` atdod vietējo šodienas datumu un aktuālo oktobra `reviewMonth`.

`GET /api/month?month=YYYY-MM` atdod visas mēneša kalendāra dienas ar iepriekšējās ievades datumu, statusu (`complete`, `partial`, `unobserved`, `unavailable`, `future`), pieejamo faktisko stundu skaitu un dienas MAE/RMSE, ja ir faktiski mērījumi. Mēneša kopējais MAE/RMSE ir aprēķināts tikai no **pilnām 24h novērotām dienām**, sverot katru stundu vienādi. Serveris šos aprēķinus kešo līdz nākamajai veiksmīgajai CLIDATA atjaunināšanai vai vietējās dienas maiņai. Tas nelasa citu staciju kešus. Serveris klausās tikai `127.0.0.1:8777`.

Šī ir **retrospektīva rekonstrukcija**, ne saglabātas vēsturiskas prognozes nolasīšana. Kandidāta ievades datums vienmēr ir vismaz astoņas dienas pirms izvēlētās ievades dienas; vēlāko novērojumu klātbūtne pašreizējā kešā atlasi nemaina. Taču arhīva vēlākas labošanas nevar atgriezt tādā stāvoklī, kāds tas bija konkrētajā vēsturiskajā dienā.

## Vēsturiskā stundas norma

`model.py:hourly_day_normal` atlasa tikai pilnas 24 stundu `RIGASLU` dienas ar **to pašu mēneša datumu** kā izvēlētajai prognozes dienai, tikai no **iepriekšējiem gadiem**. Katrai vietējai stundai 00–23 tā aprēķina šo dienu temperatūru aritmētisko vidējo. Iztrūkstošas vai vasaras laika pārejas 23/25 stundu dienas netiek izmantotas. Izlases apjoms var atšķirties starp datumiem, tāpēc API atdod `normalSampleDays` un `normalYears`; ja nav nevienas derīgas agrākas dienas, `normal` ir tukšs un līkne netiek zīmēta.

`/api/forecast` laukā `normal` ir 24 `[UTC milisekundes, °C]` punkti, kas laika ziņā sakrīt ar `forecast`. Zilā pārtrauktā līkne atrodas tikai prognozes 24h pusē un tiek parādīta arī kursora informācijā. Tā ir **aprakstoša vēsturiskā vidējā vērtība**, ne oficiāla 1991–2020 klimatiskā norma un ne prognozes modeļa ievade. Izvēlētās dienas faktiskie mērījumi, šī paša gada diena un jebkādi vēlākie gadi normā nepiedalās; atlases rangs, astoņu analogu svari un violetā prognoze no tās nemainās.

## Oktobra analogi

`GET /api/october-analogues?period=all|10|7` vienmēr izmanto **2026. gada oktobri** un vienīgi `server.py` ielādēto `RIGASLU` kešu. `model.py:make_october_analogues` izmanto jau QC izturējušo `DayRecord` indeksu. Pēdējā salīdzināmā diena ir jaunākā **pilnā 24h diena** oktobrī, kas ir agrāk par šodienu Rīgas laikā. `all` nozīmē 1. oktobri līdz šai dienai; `10` un `7` nozīmē attiecīgās pēdējās kalendāra dienas līdz tai. Nepilnās mērķa dienas izvēlētajā kalendāra posmā ir tukšumi: tās **visiem gadiem vienādi** izslēdz no vērtējuma, bet parāda grafika pārtraukumu. Agrāks gads ir kandidāts tikai tad, ja **visas mērķa derīgās kalendāra dienas un stundas** arī tajā gadā ir pilnas. Trūkumus neinterpolē, citus datumus nepārbīda un citas stacijas neizmanto.

Katram kandidātam aprēķina stundu temperatūras MAE, absolūto RMSE un **formas RMSE**, ko iegūst pēc katras salīdzināmās stundu līknes perioda vidējās temperatūras atņemšanas. Rangs ir `0,30 × MAE + 0,40 × RMSE + 0,30 × formas RMSE` (visi lielumi °C); sakritības gadījumā vispirms iet agrākais gads. API atdod piecus zemākos rangus, kandidātu skaitu, `comparisonDays` kopīgo dienu sarakstu, mērķa pilnās dienas un katra analoga salīdzinājuma vērtības. Katra analoga **turpmākās** oktobra dienas no robežas līdz 31. datumam atdod atsevišķā `continuationDays` masīvā ar `null` nepilnām dienām. Šīs vērtības **nekad** netiek nodotas kļūdu vai ranga aprēķinam. Vasaras laika maiņas 25h diena paliek tukšums. Grafiks attēlo 2026. gada pilnās dienas, ieslēgto TOP 5 gadu salīdzinājuma līknes ar nepārtrauktu līniju un to vēlākos novērojumus ar pārtrauktu līniju. Tas ir vēsturiska scenārija salīdzinājums, ne 24h modeļa prognoze.

Serveris kešo katru perioda un metodes pāri līdz veiksmīgai CLIDATA atjaunināšanai vai vietējās dienas maiņai. Esošais `make_forecast` un 24h analogu atlases svari nav mainīti. `test_model.py` pārbauda identisku kalendāra stundu atlasi, tikai Rīgas LU filtru, metožu vērtējumus, trūkstošo dienu noraidīšanu, perioda robežas, API datu formu un to, ka turpinājuma maiņa neietekmē rangu.

## Papildu oktobra atlases metodes (2026-10-21)

Oktobra API pieņem arī izvēles parametru `method=temperature|profile|regime`; bez tā paliek agrākā `temperature` metode ar nemainītu 30% MAE, 40% RMSE, 30% formas RMSE formulu. TOP 5 pārslēdzējs maina tikai šīs oktobra sadaļas rangu. Tas nemaina astoņu analogu 24h prognozi. Servera keša atslēgā ir gan periods, gan metode, gan Rīgas vietējais datums. Visām trim metodēm ir viena un tā pati tikai RIGASLU HTDRY pilno dienu kandidātu kopa. API `score` atbilst izvēlētajai metodei; katram atlasītajam gadam pievienoti `methodScores`, `profile` un `regime` komponenti. Mazāks rezultāts ir labāks, vienādu rezultātu gadījumā uzvar agrākais gads.

`profile` katrai salīdzināmajai dienai atsevišķi aprēķina 24h līknes formas RMSE pēc attiecīgās dienas vidējās temperatūras atņemšanas, 00–06 un 06–12 parakstīto temperatūras izmaiņu absolūto kļūdu, diennakts amplitūdas kļūdu, lielākā stundas kāpuma un krituma kļūdu vidējo, kā arī pirmā dienas maksimuma laika kļūdu stundās. Dienu komponentes aritmētiski vidējo. Vērtējums ir `0,40 × shapeRmse + 0,12 × nightChangeMae + 0,12 × morningChangeMae + 0,14 × amplitudeMae + 0,14 × jumpMae + 0,08 × 0,25 × peakHourMae`; pēdējā koeficientā 1 stunda atbilst 0,25 °C. Metode ir nejutīga pret katras dienas konstantu temperatūras nobīdi.

`regime` salīdzina dienu vidējo temperatūru secību pēc visa izvēlētā perioda vidējā atņemšanas, temperatūras izmaiņas starp secīgām dienām, pirmās–trešās dienas izmaiņas katrā trīs secīgu dienu logā un diennakts amplitūdu secību. Vērtējums ir `0,20 × dailyMeanShapeRmse + 0,40 × dailyChangeRmse + 0,25 × threeDayChangeRmse + 0,15 × amplitudeMae`. Pāri trūkstošām kalendāra dienām pārejas neveido. Ja nav neviena derīga pāra vai trīs dienu loga, attiecīgo locekli izlaiž un atlikušos svarus normalizē. Metode ir nejutīga pret visa perioda konstantu temperatūras nobīdi.

Visu metožu grafikā paliek **oriģinālās absolūtās °C vērtības**, tāpēc pēc formas ļoti līdzīga līkne var grafikā atrasties vertikāli tālu. Vēsturiskais turpinājums līdz 31. oktobrim netiek izmantots nevienā vērtējumā; arī šodienas novērojumi nepiedalās atlasē. Tās ir temperatūras rakstu heuristikas, ne atmosfēras procesu noteikšana. Spiediens, vējš, nokrišņi, NAO un ENSO pašlaik netiek izmantoti.

## Nokrišņu režīms (2026-10-21)

Augšējais pārslēdzējs paslēpj vienu no diviem atsevišķiem skatiem. Temperatūras `model.py:make_forecast`, HTDRY kešs, API un oktobra vērtējumi netika mainīti. Nokrišņu kods ir `sync_precipitation.py`, `precipitation.py`, `public/precip.js` un `public/precip.css`. Abos režīmos izmanto tikai `RIGASLU`; citu staciju keši netiek lasīti. Temperatūras un nokrišņu atlasēm nav kopīgu svērumu vai kopīgas prognozes.

### HPRAB semantika un QC

CLIDATA `ELEMENTS` ieraksts `HPRAB` saka **“Precipitation amount, hourly sum”**, mērvienība `mm`, robežas 0–250; `ST_ELEMENTS` Rīgas LU intervāls ir `01:00`. LVĢMC [meteoroloģijas datu skaidrojums](https://videscentrs.lvgmc.lv/media/247029298/3713de8537a0005203ac4b538d4368221a006643a260e1c7ec7d59f01b6b5f15/meteorologijas%20datu%20meklesanas%20rezultatu%20skaidrojumi.pdf) apstiprina, ka stundas summa ir automātisks katras stundas nokrišņu daudzums; šim parametram **tukšs lauks nozīmē datu trūkumu**, bet 0 var nozīmēt gan nokrišņu pēdu, gan to neesamību. CLIDATA `ELEMENTS_FLAGS` definē `T` kā nokrišņu pēdu. Nokrišņu pēdu ar `FI` karodziņu neuzdodam par precīzu 0 mm — šūnu izslēdzam.

CLIDATA `RDATA` `YEAR/MONTH/day/TIME` apstrādājam kā UTC atzīmi un pārvēršam `Europe/Riga` dienā. LVĢMC novērojumu laika atzīmes sākuma stundas konvenciju (piemēram, 14:00 apzīmē 14:00–15:00 nokrišņus) apraksta [LU meteoroloģiskās verifikācijas pārskats](https://www.promesys.lu.lv/fileadmin/_migrated/content_uploads/verification_atskaite.pdf). Šo konvenciju izmantojam HPRAB stundas intervālam, nevis nobīdām summu uz nākamās stundas beigām. CLIDATA `RDATA` UTC interpretāciju apstiprina lietotāja esošais nokrišņu apstrādes kods `interpolacija_Qgis/Kodi/izveidot_2026_09_2_dekade_ndev.R`; publiskais LVĢMC skaidrojums pats apraksta vietējā laika datu meklētāju, ne tieši Oracle `RDATA` lauku.

`sync_precipitation.py` **katrā sinhronizācijā** atkārtoti pārbauda CLIDATA elementa nosaukumu, mērvienību, intervālu un robežas; neatbilstības gadījumā kešu nepārraksta. Lasa tikai `RDATA` `EG_GH_ID='RIGASLU'`, `EG_EL_ABBREVIATION='HPRAB'`, `REGULAR='Y'`. Glabā tikai galīgas 0–250 mm stundas ar derīgu UTC atzīmi. `NULL` paliek trūkums, tikai avotā skaidri ierakstīts 0 paliek nulle. Netukšu `FIxx` noraida. `FIIxx` noraida, ja tajā ir CLIDATA `QC_FLAGS` dokumentēts `E` (interpolēts), `R` (kļūdains), `N` (izlaists), `?` (apšaubāms), `I` (labots) vai `A` (aprēķināts ar formulu). Biežie `P`/`C`/`W`/`L` kodi nav dokumentēti kā automātiska kļūda un pašlaik paliek; `VALIDATION` `N`/`P` semantika nav droši noskaidrota, tāpēc to neuzskatām par QC apstiprinājumu. Identiski dublikāti saplūst, pretrunīgi tiek izslēgti. Kešs ir **atsevišķs** `data/stations/RIGASLU_HPRAB.json.gz` ar `metadata`, `qc` un stundu rindām. Pirmajā pilnajā ielādē 2005–2026 bija 179 607 pieņemtas stundas, 4976 tukšas un 2161 ar noraidītu `FII` kodu. Šī ir konservatīva lietotnes QC, ne oficiāla LVĢMC validācija. `model.build_day_index` pieņem tikai 24 pilnas vietējās stundas, nepiepilda tukšumus un izslēdz 23/25 stundu pārejas dienas.

### Nokrišņu oktobra analogi

`GET /api/precipitation/october?period=all|10|7&method=amount|episodes|rhythm` izmanto 2026. gada 1. oktobri līdz pēdējai pilnajai **vakardienai** vai izvēlētās pēdējās 10/7 kalendāra dienas. Ja mērķa diena ir nepilna, to visiem gadiem vienādi izslēdz; kandidātam nepieciešamas visas pārējās salīdzināmās pilnās dienas. TOP 5 var mainīties atkarībā no metodes. Kļūdas vērtējums ir mazāks labākai sakritībai, vienādas vērtības kārto pēc gada. API katram TOP 5 gadam atdod `methodScores` un komponentes.

- `amount`: `0,4 × dienu summu MAE + 0,4 × dienu summu RMSE + 0,2 × |periodu kopējo summu starpība|/dienu skaits`, vienība aptuveni mm/dienā.
- `episodes`: slapja stunda ir vismaz 0,1 mm. Vērtējums `0,7 × slapjo stundu nesakritības daļa + 0,2 × epizožu skaita starpība/dienu skaits + 0,1 × vidējā epizodes ilguma starpība/24`. Epizode drīkst pāriet pāri pusnaktij tikai secīgās pilnās dienās; pāri datu iztrūkumam to nepagarina. Rezultāts ir bezdimensiju heuristika.
- `rhythm`: slapja diena ir vismaz 1 mm. Vērtējums `0,55 × dienu slapjš/sauss nesakritība + 0,25 × secīgu dienu stāvokļa maiņas nesakritība + 0,20 × garākā sausuma posma starpība/dienu skaits`. Trūkstošas dienas pārtrauc pārejas un sausuma posmus. Ja nav derīgas pārejas, atlikušos svarus normalizē. Rezultāts ir bezdimensiju heuristika.

Visas trīs metodes lasa tikai `comparisonDays`. `continuationDays` ir atsevišķas vēsturiskās pilnās dienas no robežas līdz 31. oktobrim ar `null` iztrūkumiem. Diennakts stabiņos un mēneša kumulatīvajā līknē turpinājums ir atsevišķi iekrāsots; izvēlētās dienas stundas skatā tas arī ir marķēts. Kumulatīvā līkne pēc iztrūkuma **apstājas**, jo nezināmo dienu nevar pielīdzināt nullei. Grafiki rāda sākotnējos mm bez laika pārbīdīšanas vai interpolācijas.

### Eksperimentālā 24h nokrišņu prognoze

`GET /api/precipitation/forecast?date=YYYY-MM-DD` no izvēlētajai dienai iepriekšējās pilnās 24h HPRAB dienas meklē Rīgas LU pilnus `24h ievade + 24h turpinājums` pārus ar ievades datumu vismaz 8 dienas agrāk un ±60 sezonas dienu intervālā. Salīdzina tikai pāra **ievadi**: `0,5 × log1p(stundas summu) RMSE + 0,3 × slapjo stundu nesakritības daļa + 0,2 × dienu summu starpība/24 + 0,08 × sezonas attālums/60`. Izvēlas ne vairāk par 8 ar vismaz 5 dienu savstarpēju atstarpi. Svars ir `1/(score+0,3)^2`. Stundas sagaidāmā summa ir vēsturisko turpinājumu svērtais vidējais; stundas slapjuma un ≥1 mm dienas iespēja ir analogu svaru daļa. Dienas summu 10./50./90. procentiles ir **astoņu analogu scenāriji**, ne kalibrēts ticamības intervāls. Šodienas faktiskais HPRAB drīkst parādīties tikai `actual` un statusā; tas nemaina analogu atlasi, svarus vai scenārijus. Temperatūras prognoze nav saistīta ar šo modeli.

Retrospektīvā pārbaude (`GET /api/precipitation/backtest`) katru 2020–2025 oktobra pilno dienu rekonstruē ar tikai tai laikā jau pagājušiem vēsturiskajiem pāriem. Dienas summas MAE salīdzina ar 0 mm bāzi, dienas slapjuma Brier kļūdu ar tā paša vēsturiskā sezonas kandidātu kopuma slapjo dienu frekvenci. Diena ar nepilniem HPRAB mērījumiem nav vērtēta. Rezultāti (dienas; analogu MAE / 0 mm MAE; analogu Brier / sezonālā frekvence): 2020: 27; 2,38 / 2,40 mm; 0,302 / 0,280. 2021: 28; 2,03 / 1,24; 0,206 / 0,193. 2022: 25; 2,07 / 1,31; 0,232 / 0,220. 2023: 21; 3,27 / 3,00; 0,288 / 0,222. 2024: 21; 2,10 / 0,70; 0,216 / 0,170. 2025: 23; 4,00 / 3,90; 0,228 / 0,244. Šī metode lielākoties **nepārspēj** vienkāršās bāzes; produkta marķējums “eksperimentāla” ir būtisks. Periodam un sezonai jāveic turpmāka kalibrēšana, pirms šos skaitļus interpretē kā operatīvu varbūtību.

## Faili un robežas

| Fails | Loma |
| --- | --- |
| `sync_clidata.py` | Tikai Rīgas LU `HTDRY` ielāde un stundu QC |
| `model.py` | Pilno dienu indekss, analogu atlase, prognoze un pēc fakta sakritība |
| `server.py` | Lokālais HTTP, kešs un jaunāko stundu atjaunināšana |
| `public/` | 24h prognozes skats un atsevišķā oktobra analogu sadaļa |
| `test_model.py` | QC, pilno pāru, tikai Rīgas LU un laika robežas testi |
| `data/stations/RIGASLU.json.gz` | QC izturējušo novērojumu lokālais kešs |

Agrāko citu staciju kešus neizdzēšam, taču aktīvais serveris tos nelasa. Nav `TDRY` aizvietojuma vai trūkstošo stundu interpolācijas. Servera koda izmaiņām jāpārstartē process; pārlūka izmaiņām jāpārlādē lapa. Visas pašreizējās metodes balstās tikai temperatūras datos. Pirms operatīvas izmantošanas jāveic retrospektīva validācija pa sezonām un jāizvērtē procentiļu joslas pārklājums.

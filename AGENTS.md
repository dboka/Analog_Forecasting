# Norādes nākamajam aģentam

Sāc ar `README.md` un `ARCHITECTURE.md`. Ir divi pārslēdzami lokāli Rīgas LU skati: sākotnējā nemainītā `HTDRY` temperatūras 24h → 24h prognoze ar oktobra analogiem un atsevišķais eksperimentālais `HPRAB` nokrišņu režīms. Abos izmanto tikai `RIGASLU` un tikai pilnas QC izturējušas 24h dienas; `HPRAB` trūkums nekad nav 0 mm. Neatjauno agrāko atsevišķo vēstures temperatūras grafiku, `TDRY`, citu staciju analogus vai 7 dienu ievades režīmu bez jauna lietotāja pieprasījuma.

`server.py` lasa `data/stations/RIGASLU.json.gz` temperatūrai un `data/stations/RIGASLU_HPRAB.json.gz` nokrišņiem; citu staciju kešus nelasa. `model.py` un `precipitation.py` atlasē vēlreiz filtrē pēc `RIGASLU`. Vēsturiskās dienas prognoze ir rekonstrukcija no iepriekšējās dienas ievades; izvēlētās dienas faktiskais rezultāts drīkst tikt izmantots tikai rezultāta validācijā, nekad analogu atlasē. Datu kvalitātes noteikumi un formulas ir `ARCHITECTURE.md`.

`server.py` lokāli apkalpo `public/` un `/api/...`; `build_static_site.py` veido publisku `site/` kopiju GitHub Pages videi. `public/api-client.js` pārslēdz lokālos API pieprasījumus uz statiskajiem JSON. Ja maini frontend vai API, pārbaudi lokālo serveri un pārbūvē `site/`. Nekad neiekļauj `.env`, `data/`, CLIDATA pieslēguma palīdzfunkcijas vai paroles projekta avota failos vai commitā; `.env.example` ir tukšs paraugs.

Zilā pārtrauktā `normal` līkne ir tā paša mēneša datuma katras stundas vidējais no **agrāku gadu pilnajām Rīgas LU dienām**. Tā ir aprakstoša atsauce, ne oficiāla klimatiskā norma, un nekad nemaina prognozi. Saglabā `normalSampleDays`/`normalYears` caurskatāmībai.

“Oktobra analogi” sadaļā `method=temperature|profile|regime` pārslēdz tikai mēneša TOP 5 rangu. `temperature` ir sākotnējais noklusējums; abu papildu metožu formulas un iztrūkumu apstrāde ir `ARCHITECTURE.md`. 24h prognozes algoritms no šī pārslēdzēja nav atkarīgs.

Pārbaude: `python -m unittest -v`, `node --check public/app.js`, `node --check public/precip.js`, tad lokāli `python server.py` un pārbaudi `/api/status`, `/api/forecast?date=2026-10-01`, `/api/month?month=2026-10`, `/api/precipitation/forecast`, `/api/precipitation/october?period=all&method=amount` un lapu `http://127.0.0.1:8777/`. Ja maini algoritmu vai API, aktualizē `ARCHITECTURE.md`. Datubāzes piekļuves dati nav repozitorijā.
